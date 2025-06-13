"""
Model Management and Selection Module

Model selection and acquisition is a critical step that often trips up newcomers
to MLX. The ecosystem has specific requirements for model formats, and the
landscape of available models changes rapidly.

This module handles the complexity of:
- Finding MLX-compatible models
- Converting models when necessary  
- Managing model storage and caching
- Validating model compatibility before fine-tuning
- Providing recommendations based on hardware capabilities

The philosophy here is to make model acquisition as automatic as possible
whilst being transparent about what's happening under the hood. We want
users to understand their options without getting lost in technical details.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
import json
import requests
from huggingface_hub import snapshot_download, list_repo_files, hf_hub_download
import psutil

try:
    import mlx.core as mx
    from mlx_lm import load, convert
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False


class ModelManager:
    """
    Comprehensive model management for MLX fine-tuning.
    
    This class handles the entire lifecycle of model acquisition and preparation:
    - Discovery of MLX-compatible models
    - Automatic downloading and caching
    - Format conversion when necessary
    - Validation and compatibility checking
    - Storage organisation and cleanup
    
    The manager maintains a local database of model metadata to avoid
    repeated network calls and provide quick compatibility checks.
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".mlx_models"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Model database for tracking downloads and metadata
        self.model_db_path = self.cache_dir / "model_database.json"
        self.model_db = self._load_model_database()
        
        # MLX Community models are pre-converted and ready to use
        self.mlx_community_prefix = "mlx-community/"
        
        # Supported model architectures for MLX
        self.supported_architectures = {
            "llama", "mistral", "phi", "qwen", "deepseek", "gemma", 
            "codellama", "mixtral", "starcoder", "falcon"
        }
        
        # Quantisation options
        self.quantization_options = {
            "none": {"bits": None, "suffix": ""},
            "2bit": {"bits": 2, "suffix": "-2bit"},
            "4bit": {"bits": 4, "suffix": "-4bit"},
            "8bit": {"bits": 8, "suffix": "-8bit"},
        }
    
    def download_model(
        self,
        model_id: str,
        quantization: str = "4bit",
        force_redownload: bool = False,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Download and prepare a model for MLX fine-tuning.
        
        This method handles the complexity of model acquisition, including:
        - Checking for existing cached versions
        - Determining if conversion is needed
        - Managing quantisation options
        - Validating the final result
        
        Args:
            model_id: HuggingFace model identifier
            quantization: Quantisation level (2bit, 4bit, 8bit, or none)
            force_redownload: Skip cache and download fresh
            progress_callback: Function to call with progress updates
        
        Returns:
            Path to the prepared model directory
        """
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available - cannot download models")
        
        if progress_callback:
            progress_callback(5)
        
        # Determine target path and check cache
        model_name = self._sanitize_model_name(model_id)
        quant_suffix = self.quantization_options[quantization]["suffix"]
        target_path = self.cache_dir / f"{model_name}{quant_suffix}"
        
        # Check if model already exists and is valid
        if target_path.exists() and not force_redownload:
            if self._validate_cached_model(target_path):
                if progress_callback:
                    progress_callback(100)
                return target_path
            else:
                # Remove invalid cached model
                shutil.rmtree(target_path, ignore_errors=True)
        
        if progress_callback:
            progress_callback(10)
        
        # Check if this is already an MLX community model
        if model_id.startswith(self.mlx_community_prefix):
            return self._download_mlx_community_model(
                model_id, target_path, progress_callback
            )
        
        # Check if MLX community version exists
        mlx_community_id = self._find_mlx_community_version(model_id)
        if mlx_community_id:
            return self._download_mlx_community_model(
                mlx_community_id, target_path, progress_callback
            )
        
        # Download and convert standard HuggingFace model
        return self._download_and_convert_model(
            model_id, target_path, quantization, progress_callback
        )
    
    def _download_mlx_community_model(
        self,
        model_id: str,
        target_path: Path,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Download a pre-converted MLX community model.
        
        These models are already in the correct format and don't need
        conversion, which makes them much faster to acquire and use.
        """
        try:
            if progress_callback:
                progress_callback(20)
            
            # Download the model files
            snapshot_download(
                repo_id=model_id,
                local_dir=target_path,
                local_dir_use_symlinks=False,
                ignore_patterns=["*.bin", "*.pth", "*.pt"]  # Skip non-MLX weights
            )
            
            if progress_callback:
                progress_callback(80)
            
            # Update model database
            self._update_model_database(model_id, target_path, "mlx_community")
            
            if progress_callback:
                progress_callback(100)
            
            return target_path
            
        except Exception as e:
            # Clean up partial download
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)
            raise RuntimeError(f"Failed to download MLX community model {model_id}: {e}")
    
    def _download_and_convert_model(
        self,
        model_id: str,
        target_path: Path,
        quantization: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Download a standard HuggingFace model and convert it to MLX format.
        
        This process is more involved than downloading pre-converted models:
        1. Download the original model
        2. Convert to MLX format
        3. Apply quantisation if requested
        4. Validate the result
        """
        temp_download_path = self.cache_dir / f"temp_{self._sanitize_model_name(model_id)}"
        
        try:
            if progress_callback:
                progress_callback(20)
            
            # Download original model
            snapshot_download(
                repo_id=model_id,
                local_dir=temp_download_path,
                local_dir_use_symlinks=False
            )
            
            if progress_callback:
                progress_callback(50)
            
            # Convert to MLX format
            self._convert_to_mlx(
                temp_download_path, 
                target_path, 
                quantization
            )
            
            if progress_callback:
                progress_callback(90)
            
            # Clean up temporary download
            if temp_download_path.exists():
                shutil.rmtree(temp_download_path, ignore_errors=True)
            
            # Update model database
            self._update_model_database(model_id, target_path, "converted")
            
            if progress_callback:
                progress_callback(100)
            
            return target_path
            
        except Exception as e:
            # Clean up on failure
            for path in [temp_download_path, target_path]:
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
            raise RuntimeError(f"Failed to download and convert model {model_id}: {e}")
    
    def _convert_to_mlx(
        self, 
        source_path: Path, 
        target_path: Path, 
        quantization: str
    ) -> None:
        """
        Convert a HuggingFace model to MLX format with optional quantisation.
        
        This uses MLX's built-in conversion tools, but adds error handling
        and validation to ensure the conversion succeeds completely.
        """
        try:
            # Prepare conversion command
            cmd = [
                sys.executable, "-m", "mlx_lm.convert",
                "--hf-path", str(source_path),
                "--mlx-path", str(target_path),
            ]
            
            # Add quantisation if requested
            if quantization != "none":
                cmd.append("-q")
                bits = self.quantization_options[quantization]["bits"]
                if bits in [2, 8]:  # 4-bit is default, others need specification
                    cmd.extend(["--q-bits", str(bits)])
            
            # Run conversion
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Validate conversion succeeded
            if not (target_path / "config.json").exists():
                raise RuntimeError("Conversion failed - no config.json found")
            
            if not any(target_path.glob("*.safetensors")):
                raise RuntimeError("Conversion failed - no weight files found")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"MLX conversion failed: {e.stderr if e.stderr else e.stdout}"
            raise RuntimeError(error_msg)
    
    def _find_mlx_community_version(self, model_id: str) -> Optional[str]:
        """
        Check if an MLX community version of this model exists.
        
        The MLX community often converts popular models, which saves time
        and ensures compatibility. We check for common naming patterns.
        """
        # Extract model name from full ID
        if "/" in model_id:
            org, model_name = model_id.split("/", 1)
        else:
            model_name = model_id
        
        # Common patterns for MLX community models
        potential_names = [
            f"mlx-community/{model_name}",
            f"mlx-community/{model_name}-4bit",
            f"mlx-community/{model_name.lower()}",
            f"mlx-community/{model_name.lower()}-4bit",
        ]
        
        for mlx_name in potential_names:
            if self._check_model_exists(mlx_name):
                return mlx_name
        
        return None
    
    def _check_model_exists(self, model_id: str) -> bool:
        """
        Check if a model exists on HuggingFace Hub.
        
        This makes a lightweight API call to avoid downloading models
        that don't exist. We cache results to avoid repeated checks.
        """
        try:
            # Check our local cache first
            if model_id in self.model_db.get("existence_cache", {}):
                return self.model_db["existence_cache"][model_id]
            
            # Make API call to check existence
            files = list_repo_files(repo_id=model_id, repo_type="model")
            exists = len(files) > 0
            
            # Cache the result
            if "existence_cache" not in self.model_db:
                self.model_db["existence_cache"] = {}
            self.model_db["existence_cache"][model_id] = exists
            self._save_model_database()
            
            return exists
            
        except Exception:
            return False
    
    def list_available_models(self, architecture_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List available models suitable for fine-tuning.
        
        This provides a curated list of models that work well with MLX,
        filtered by architecture if specified. The list includes both
        MLX community models and popular HuggingFace models.
        """
        models = []
        
        # MLX Community models (these are guaranteed to work)
        mlx_community_models = self._get_mlx_community_models()
        models.extend(mlx_community_models)
        
        # Popular HuggingFace models (these will need conversion)
        popular_models = self._get_popular_hf_models()
        models.extend(popular_models)
        
        # Filter by architecture if requested
        if architecture_filter:
            models = [m for m in models if architecture_filter.lower() in m.get("architecture", "").lower()]
        
        return models
    
    def _get_mlx_community_models(self) -> List[Dict[str, Any]]:
        """
        Get a curated list of MLX community models.
        
        These models are pre-converted and ready to use, making them
        the best choice for most users. We maintain a curated list
        of the most useful models.
        """
        # This would ideally query the MLX community organization,
        # but for now we'll use a curated list of known good models
        curated_models = [
            {
                "id": "mlx-community/Mistral-7B-Instruct-v0.3-4bit",
                "name": "Mistral 7B Instruct v0.3 (4-bit)",
                "architecture": "mistral",
                "parameters": "7B",
                "quantization": "4bit",
                "size_gb": 4.1,
                "source": "mlx_community",
                "description": "Excellent general-purpose instruction model",
                "recommended_for": ["general", "instruction_following", "chat"]
            },
            {
                "id": "mlx-community/Llama-3.2-8B-Instruct-4bit",
                "name": "Llama 3.2 8B Instruct (4-bit)",
                "architecture": "llama",
                "parameters": "8B", 
                "quantization": "4bit",
                "size_gb": 4.5,
                "source": "mlx_community",
                "description": "Meta's latest instruction-tuned model",
                "recommended_for": ["general", "reasoning", "code"]
            },
            {
                "id": "mlx-community/Qwen2.5-7B-Instruct-4bit",
                "name": "Qwen 2.5 7B Instruct (4-bit)",
                "architecture": "qwen",
                "parameters": "7B",
                "quantization": "4bit", 
                "size_gb": 4.2,
                "source": "mlx_community",
                "description": "Strong multilingual capabilities",
                "recommended_for": ["multilingual", "reasoning", "math"]
            },
            {
                "id": "mlx-community/SmolLM-135M-Instruct-4bit",
                "name": "SmolLM 135M Instruct (4-bit)",
                "architecture": "llama",
                "parameters": "135M",
                "quantization": "4bit",
                "size_gb": 0.075,
                "source": "mlx_community", 
                "description": "Tiny model for testing and experimentation",
                "recommended_for": ["testing", "prototyping", "edge_deployment"]
            }
        ]
        
        return curated_models
    
    def _get_popular_hf_models(self) -> List[Dict[str, Any]]:
        """
        Get popular HuggingFace models that work well with MLX.
        
        These models will need conversion but represent the latest
        and most capable options available.
        """
        popular_models = [
            {
                "id": "mistralai/Mistral-7B-v0.1",
                "name": "Mistral 7B v0.1 (Base)",
                "architecture": "mistral", 
                "parameters": "7B",
                "quantization": "none",
                "size_gb": 14.2,
                "source": "huggingface",
                "description": "Base Mistral model for fine-tuning",
                "recommended_for": ["fine_tuning", "domain_adaptation"]
            },
            {
                "id": "meta-llama/Llama-3.3-70B-Instruct",
                "name": "Llama 3.3 70B Instruct",
                "architecture": "llama",
                "parameters": "70B",
                "quantization": "none", 
                "size_gb": 140,
                "source": "huggingface",
                "description": "Very large, high-quality instruction model",
                "recommended_for": ["high_quality", "complex_reasoning"],
                "hardware_requirements": "64GB+ RAM, quantization recommended"
            }
        ]
        
        return popular_models
    
    def get_model_recommendations(
        self, 
        task_type: str = "general",
        memory_limit_gb: Optional[float] = None,
        hardware_info: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get model recommendations based on task and hardware constraints.
        
        This helps users choose appropriate models without getting lost
        in the overwhelming number of options available.
        """
        if hardware_info is None:
            hardware_info = self._get_hardware_info()
        
        if memory_limit_gb is None:
            memory_limit_gb = hardware_info.get("available_memory_gb", 8)
        
        # Get all available models
        all_models = self.list_available_models()
        
        # Filter by memory constraints (leaving headroom for training)
        suitable_models = []
        for model in all_models:
            # Estimate memory usage including training overhead
            model_memory = model.get("size_gb", 0)
            training_memory = model_memory * 2.5  # Rule of thumb for LoRA training
            
            if training_memory <= memory_limit_gb * 0.8:  # Leave 20% headroom
                model["estimated_training_memory_gb"] = training_memory
                suitable_models.append(model)
        
        # Rank by suitability for task
        ranked_models = self._rank_models_for_task(suitable_models, task_type)
        
        return ranked_models[:10]  # Return top 10 recommendations
    
    def _rank_models_for_task(self, models: List[Dict[str, Any]], task_type: str) -> List[Dict[str, Any]]:
        """
        Rank models by suitability for a specific task type.
        
        This implements heuristics for choosing models based on the
        intended use case, balancing capability with practical constraints.
        """
        task_preferences = {
            "general": {
                "preferred_architectures": ["mistral", "llama", "qwen"],
                "min_parameters": "1B",
                "max_parameters": "13B",
                "prefer_instruct": True
            },
            "code": {
                "preferred_architectures": ["codellama", "deepseek", "qwen"],
                "min_parameters": "7B", 
                "max_parameters": "34B",
                "prefer_instruct": True
            },
            "reasoning": {
                "preferred_architectures": ["llama", "qwen"],
                "min_parameters": "7B",
                "max_parameters": "70B", 
                "prefer_instruct": True
            },
            "experimentation": {
                "preferred_architectures": ["llama", "mistral"],
                "min_parameters": "135M",
                "max_parameters": "7B",
                "prefer_instruct": False
            }
        }
        
        preferences = task_preferences.get(task_type, task_preferences["general"])
        
        def score_model(model: Dict[str, Any]) -> float:
            score = 0.0
            
            # Architecture preference
            arch = model.get("architecture", "").lower()
            if arch in preferences["preferred_architectures"]:
                score += 10.0
            
            # Parameter count preference
            params = model.get("parameters", "0B")
            param_score = self._score_parameter_count(params, preferences)
            score += param_score
            
            # Instruction tuning preference
            name = model.get("name", "").lower()
            is_instruct = "instruct" in name or "chat" in name
            if preferences["prefer_instruct"] and is_instruct:
                score += 5.0
            elif not preferences["prefer_instruct"] and not is_instruct:
                score += 5.0
            
            # Source preference (MLX community models are easier)
            if model.get("source") == "mlx_community":
                score += 3.0
            
            # Quantization penalty for larger models
            if model.get("quantization") == "none" and "B" in params:
                param_num = float(params.replace("B", ""))
                if param_num > 7:
                    score -= 2.0
            
            return score
        
        # Sort by score (highest first)
        return sorted(models, key=score_model, reverse=True)
    
    def _score_parameter_count(self, params: str, preferences: Dict[str, Any]) -> float:
        """Score a model's parameter count against task preferences."""
        if not params or params == "unknown":
            return 0.0
        
        try:
            # Convert parameter string to number
            if "B" in params:
                param_num = float(params.replace("B", ""))
            elif "M" in params:
                param_num = float(params.replace("M", "")) / 1000
            else:
                return 0.0
            
            # Get preference bounds
            min_params = preferences.get("min_parameters", "1B")
            max_params = preferences.get("max_parameters", "13B")
            
            min_num = float(min_params.replace("B", "")) if "B" in min_params else float(min_params.replace("M", "")) / 1000
            max_num = float(max_params.replace("B", "")) if "B" in max_params else float(max_params.replace("M", "")) / 1000
            
            # Score based on how well it fits the range
            if min_num <= param_num <= max_num:
                # Within range - higher score for models closer to sweet spot
                sweet_spot = (min_num + max_num) / 2
                distance_from_sweet_spot = abs(param_num - sweet_spot) / (max_num - min_num)
                return 10.0 * (1 - distance_from_sweet_spot)
            elif param_num < min_num:
                # Too small
                return max(0, 5.0 - (min_num - param_num))
            else:
                # Too large
                return max(0, 5.0 - (param_num - max_num) / 10)
                
        except Exception:
            return 0.0
    
    def validate_model(self, model_path: Path) -> Dict[str, Any]:
        """
        Comprehensive validation of a model for MLX fine-tuning.
        
        This checks everything needed for successful fine-tuning:
        - File structure and format
        - MLX compatibility
        - Memory requirements
        - Architecture support
        """
        model_path = Path(model_path)
        result = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "info": {}
        }
        
        try:
            # Check basic file structure
            structure_issues = self._validate_model_structure(model_path)
            if structure_issues:
                result["issues"].extend(structure_issues)
                result["valid"] = False
            
            # Try to load with MLX
            if result["valid"]:
                load_result = self._validate_mlx_loading(model_path)
                if not load_result["success"]:
                    result["issues"].append(f"MLX loading failed: {load_result['error']}")
                    result["valid"] = False
                else:
                    result["info"].update(load_result["info"])
            
            # Check memory requirements
            memory_info = self._estimate_memory_requirements(model_path)
            result["info"].update(memory_info)
            
            # Validate against current hardware
            hardware_warnings = self._check_hardware_compatibility(memory_info)
            result["warnings"].extend(hardware_warnings)
            
        except Exception as e:
            result["valid"] = False
            result["issues"].append(f"Validation error: {e}")
        
        return result
    
    def _validate_model_structure(self, model_path: Path) -> List[str]:
        """Validate basic model file structure."""
        issues = []
        
        if not model_path.exists():
            issues.append("Model path does not exist")
            return issues
        
        if not model_path.is_dir():
            issues.append("Model path is not a directory")
            return issues
        
        # Check for required files
        required_files = ["config.json"]
        for req_file in required_files:
            if not (model_path / req_file).exists():
                issues.append(f"Missing required file: {req_file}")
        
        # Check for weight files
        weight_files = list(model_path.glob("*.safetensors")) + list(model_path.glob("*.npz"))
        if not weight_files:
            issues.append("No weight files found (.safetensors or .npz)")
        
        # Check config.json is valid
        try:
            with open(model_path / "config.json", 'r') as f:
                config = json.load(f)
                
            # Check for required config fields
            if "model_type" not in config:
                issues.append("config.json missing model_type field")
                
        except json.JSONDecodeError:
            issues.append("config.json is not valid JSON")
        except FileNotFoundError:
            pass  # Already caught above
        
        return issues
    
    def _validate_mlx_loading(self, model_path: Path) -> Dict[str, Any]:
        """Attempt to load the model with MLX to validate compatibility."""
        try:
            from mlx_lm import load
            
            # Attempt to load the model
            model, tokenizer = load(str(model_path))
            
            # Extract model information
            info = {
                "architecture": model.__class__.__name__,
                "loading_successful": True
            }
            
            # Try to get parameter count
            try:
                total_params = sum(p.size for p in model.parameters().values())
                info["parameters"] = total_params
                info["parameters_readable"] = self._format_parameter_count(total_params)
            except Exception:
                info["parameters"] = "unknown"
            
            return {"success": True, "info": info}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _estimate_memory_requirements(self, model_path: Path) -> Dict[str, Any]:
        """Estimate memory requirements for the model."""
        memory_info = {}
        
        try:
            # Calculate model size from files
            total_size = sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file())
            model_size_gb = total_size / (1024**3)
            
            memory_info["model_size_gb"] = round(model_size_gb, 2)
            
            # Estimate inference memory (model + activations + overhead)
            inference_memory = model_size_gb * 1.3
            memory_info["inference_memory_gb"] = round(inference_memory, 2)
            
            # Estimate training memory (model + gradients + optimizer states + activations)
            training_memory = model_size_gb * 2.5  # Conservative estimate for LoRA
            memory_info["training_memory_gb"] = round(training_memory, 2)
            
            # Full fine-tuning estimate
            full_training_memory = model_size_gb * 4.0
            memory_info["full_training_memory_gb"] = round(full_training_memory, 2)
            
        except Exception as e:
            memory_info["error"] = f"Could not estimate memory: {e}"
        
        return memory_info
    
    def _check_hardware_compatibility(self, memory_info: Dict[str, Any]) -> List[str]:
        """Check compatibility with current hardware."""
        warnings = []
        
        try:
            # Get current memory info
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            total_gb = memory.total / (1024**3)
            
            # Check training memory requirements
            training_memory = memory_info.get("training_memory_gb", 0)
            if training_memory > available_gb:
                warnings.append(
                    f"Insufficient memory for training: need {training_memory:.1f}GB, "
                    f"have {available_gb:.1f}GB available"
                )
            elif training_memory > total_gb * 0.8:
                warnings.append(
                    f"Training will use {training_memory:.1f}GB of {total_gb:.1f}GB total memory - "
                    "consider smaller batch sizes"
                )
            
            # Check if quantization would help
            model_size = memory_info.get("model_size_gb", 0)
            if model_size > 8 and training_memory > available_gb:
                warnings.append(
                    "Consider using a quantized version of this model to reduce memory usage"
                )
                
        except Exception:
            warnings.append("Could not check hardware compatibility")
        
        return warnings
    
    def _format_parameter_count(self, param_count: int) -> str:
        """Format parameter count in human-readable form."""
        if param_count >= 1e9:
            return f"{param_count / 1e9:.1f}B"
        elif param_count >= 1e6:
            return f"{param_count / 1e6:.1f}M"
        elif param_count >= 1e3:
            return f"{param_count / 1e3:.1f}K"
        else:
            return str(param_count)
    
    def _get_hardware_info(self) -> Dict[str, Any]:
        """Get current hardware information."""
        memory = psutil.virtual_memory()
        
        return {
            "total_memory_gb": memory.total / (1024**3),
            "available_memory_gb": memory.available / (1024**3),
            "memory_percent_used": memory.percent,
            "platform": os.uname().machine if hasattr(os, 'uname') else "unknown"
        }
    
    def _sanitize_model_name(self, model_id: str) -> str:
        """Convert model ID to safe directory name."""
        # Replace problematic characters
        safe_name = model_id.replace("/", "_").replace(":", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-.")
        return safe_name
    
    def _load_model_database(self) -> Dict[str, Any]:
        """Load the model database from disk."""
        if self.model_db_path.exists():
            try:
                with open(self.model_db_path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_model_database(self) -> None:
        """Save the model database to disk."""
        try:
            with open(self.model_db_path, 'w') as f:
                json.dump(self.model_db, f, indent=2)
        except Exception:
            pass  # Fail silently for database saves
    
    def _update_model_database(self, model_id: str, model_path: Path, source: str) -> None:
        """Update the model database with new model information."""
        if "models" not in self.model_db:
            self.model_db["models"] = {}
        
        self.model_db["models"][model_id] = {
            "path": str(model_path),
            "source": source,
            "downloaded_at": str(pd.Timestamp.now()),
            "size_gb": sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file()) / (1024**3)
        }
        
        self._save_model_database()
    
    def _validate_cached_model(self, model_path: Path) -> bool:
        """Validate that a cached model is complete and functional."""
        try:
            # Check basic structure
            if not (model_path / "config.json").exists():
                return False
            
            # Check for weight files
            weight_files = list(model_path.glob("*.safetensors")) + list(model_path.glob("*.npz"))
            if not weight_files:
                return False
            
            # Try a quick load test
            from mlx_lm import load
            model, tokenizer = load(str(model_path))
            
            return True
            
        except Exception:
            return False
    
    def cleanup_cache(self, keep_recent: int = 5) -> Dict[str, Any]:
        """
        Clean up old cached models to free disk space.
        
        This removes older models whilst keeping the most recently
        used ones. It's helpful for managing disk space when you've
        downloaded many models for experimentation.
        """
        if "models" not in self.model_db:
            return {"cleaned": 0, "freed_gb": 0}
        
        models = self.model_db["models"]
        
        # Sort models by download date
        sorted_models = sorted(
            models.items(),
            key=lambda x: x[1].get("downloaded_at", ""),
            reverse=True
        )
        
        # Keep the most recent ones
        to_keep = sorted_models[:keep_recent]
        to_remove = sorted_models[keep_recent:]
        
        freed_gb = 0
        cleaned = 0
        
        for model_id, info in to_remove:
            model_path = Path(info["path"])
            if model_path.exists():
                try:
                    size_gb = info.get("size_gb", 0)
                    shutil.rmtree(model_path)
                    freed_gb += size_gb
                    cleaned += 1
                    
                    # Remove from database
                    del models[model_id]
                    
                except Exception:
                    continue
        
        # Update database
        self._save_model_database()
        
        return {
            "cleaned": cleaned,
            "freed_gb": round(freed_gb, 2),
            "remaining": len(to_keep)
        }
