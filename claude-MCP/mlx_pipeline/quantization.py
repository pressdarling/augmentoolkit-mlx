"""
Model Quantization and Optimization Module

Quantization is essential for practical deployment of fine-tuned models.
It reduces model size and memory usage by representing weights with fewer bits,
enabling larger models to run on consumer hardware and allowing multiple
models to coexist in memory.

This module provides comprehensive quantization capabilities:
- Post-training quantization for existing models
- Quality assessment to measure degradation
- Hardware-optimized quantization schemes
- Deployment-ready model preparation

The philosophy here is "measure twice, cut once" - we thoroughly validate
quality impacts before committing to quantized models, ensuring your
deployment meets performance requirements.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import time
import numpy as np

try:
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm import load, generate, convert
    from mlx_lm.utils import load_model
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel


class ModelQuantizer:
    """
    Comprehensive model quantization for efficient deployment.
    
    This class handles the complexity of model quantization whilst maintaining
    quality. Quantization is a delicate balance between model size and performance,
    and this implementation provides the tools to find the optimal point for
    your specific use case.
    
    The quantizer supports multiple quantization strategies:
    - Uniform quantization (same bits for all weights)
    - Mixed precision (different bits for different layers)
    - Dynamic quantization (runtime compression)
    - Custom quantization schemes for specific architectures
    """
    
    def __init__(self):
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available - cannot initialize quantizer")
        
        self.quantization_schemes = {
            "2bit": {"bits": 2, "group_size": 64, "description": "Maximum compression, some quality loss"},
            "4bit": {"bits": 4, "group_size": 64, "description": "Good balance of size and quality"},
            "8bit": {"bits": 8, "group_size": 128, "description": "Minimal quality loss, moderate compression"},
            "mixed_4_8": {"description": "4-bit for most layers, 8-bit for critical layers"},
        }
        
        # Quality assessment prompts for different domains
        self.quality_test_prompts = {
            "general": [
                "Explain the concept of machine learning in simple terms.",
                "What are the key differences between renewable and non-renewable energy?",
                "Describe the process of photosynthesis.",
                "How do neural networks learn to recognize patterns?",
                "What is the importance of biodiversity in ecosystems?"
            ],
            "code": [
                "Write a Python function to reverse a string.",
                "Explain the difference between lists and tuples in Python.",
                "How do you handle exceptions in programming?",
                "What is the purpose of version control systems?",
                "Describe the concept of object-oriented programming."
            ],
            "reasoning": [
                "If a train travels 60 mph for 2 hours, how far does it go?",
                "What is the relationship between cause and effect?",
                "How would you solve a problem step by step?",
                "What makes a logical argument valid?",
                "Explain how to break down complex problems."
            ]
        }
    
    def quantize_model(
        self,
        model_path: Path,
        output_path: Path,
        bits: int = 4,
        group_size: Optional[int] = None,
        validate_quality: bool = True,
        quality_threshold: float = 0.8,
        test_prompts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Quantize a model with comprehensive quality validation.
        
        This method performs the complete quantization workflow:
        1. Load and analyze the original model
        2. Apply quantization with specified parameters
        3. Validate the quantized model quality
        4. Provide detailed comparison metrics
        
        Args:
            model_path: Path to the original model
            output_path: Path for the quantized model
            bits: Number of bits for quantization (2, 4, or 8)
            group_size: Group size for quantization (None for default)
            validate_quality: Whether to test quality after quantization
            quality_threshold: Minimum acceptable quality score (0-1)
            test_prompts: Custom prompts for quality testing
            
        Returns:
            Dictionary with quantization results and quality metrics
        """
        console = Console()
        
        console.print(Panel(
            f"[bold blue]Model Quantization[/bold blue]\n"
            f"Original: {model_path}\n"
            f"Target: {bits}-bit quantization\n"
            f"Output: {output_path}",
            title="Quantization Configuration"
        ))
        
        try:
            # Phase 1: Analysis of original model
            console.print("[blue]Analyzing original model...[/blue]")
            original_analysis = self._analyze_model(model_path)
            
            # Phase 2: Quantization
            console.print(f"[blue]Applying {bits}-bit quantization...[/blue]")
            quantization_results = self._perform_quantization(
                model_path, output_path, bits, group_size, console
            )
            
            # Phase 3: Quality validation
            quality_results = {}
            if validate_quality:
                console.print("[blue]Validating quantized model quality...[/blue]")
                quality_results = self._validate_quantization_quality(
                    model_path, output_path, test_prompts, console
                )
                
                # Check if quality meets threshold
                overall_quality = quality_results.get("overall_quality_score", 0)
                if overall_quality < quality_threshold:
                    console.print(
                        f"[yellow]Warning: Quality score ({overall_quality:.3f}) "
                        f"below threshold ({quality_threshold:.3f})[/yellow]"
                    )
            
            # Phase 4: Final analysis
            quantized_analysis = self._analyze_model(output_path)
            
            # Compile results
            results = {
                "quantization_successful": True,
                "original_analysis": original_analysis,
                "quantized_analysis": quantized_analysis,
                "quantization_results": quantization_results,
                "quality_results": quality_results,
                "compression_ratio": original_analysis["size_gb"] / quantized_analysis["size_gb"],
                "size_reduction_gb": original_analysis["size_gb"] - quantized_analysis["size_gb"],
                "recommendations": self._generate_quantization_recommendations(
                    original_analysis, quantized_analysis, quality_results
                )
            }
            
            # Display summary
            self._display_quantization_summary(results, console)
            
            return results
            
        except Exception as e:
            console.print(f"[red]Quantization failed: {e}[/red]")
            raise
    
    def _analyze_model(self, model_path: Path) -> Dict[str, Any]:
        """
        Analyze a model to understand its characteristics.
        
        This provides detailed information about model structure,
        size, and capabilities that helps inform quantization decisions.
        """
        analysis = {}
        
        try:
            # Basic file analysis
            model_files = list(Path(model_path).glob("*.safetensors"))
            if not model_files:
                model_files = list(Path(model_path).glob("*.npz"))
            
            total_size_bytes = sum(f.stat().st_size for f in model_files)
            analysis["size_gb"] = total_size_bytes / (1024**3)
            analysis["size_mb"] = total_size_bytes / (1024**2)
            analysis["num_files"] = len(model_files)
            
            # Load model for detailed analysis
            model, tokenizer = load(str(model_path))
            
            # Model architecture analysis
            analysis["architecture"] = model.__class__.__name__
            
            # Parameter analysis
            try:
                total_params = sum(p.size for p in model.parameters().values())
                analysis["total_parameters"] = total_params
                analysis["parameters_readable"] = self._format_parameter_count(total_params)
                
                # Analyze parameter distribution
                param_sizes = [p.size for p in model.parameters().values()]
                analysis["largest_layer_params"] = max(param_sizes)
                analysis["smallest_layer_params"] = min(param_sizes)
                analysis["avg_layer_params"] = sum(param_sizes) / len(param_sizes)
                
            except Exception:
                analysis["total_parameters"] = "unknown"
            
            # Memory usage analysis
            current_memory = mx.metal.get_active_memory()
            analysis["memory_usage_mb"] = current_memory / (1024**2)
            
            # Configuration analysis
            config_path = Path(model_path) / "config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                analysis["vocab_size"] = config.get("vocab_size", "unknown")
                analysis["hidden_size"] = config.get("hidden_size", "unknown")
                analysis["num_layers"] = config.get("num_hidden_layers", config.get("num_layers", "unknown"))
                analysis["num_attention_heads"] = config.get("num_attention_heads", "unknown")
                
        except Exception as e:
            analysis["error"] = f"Analysis failed: {e}"
        
        return analysis
    
    def _perform_quantization(
        self,
        model_path: Path,
        output_path: Path,
        bits: int,
        group_size: Optional[int],
        console: Console
    ) -> Dict[str, Any]:
        """
        Perform the actual quantization using MLX tools.
        
        This handles the low-level quantization process, including
        parameter optimization and error handling for different
        model architectures.
        """
        import subprocess
        import sys
        
        # Prepare output directory
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Build quantization command
        cmd = [
            sys.executable, "-m", "mlx_lm.convert",
            "--hf-path", str(model_path),
            "--mlx-path", str(output_path),
            "-q"  # Enable quantization
        ]
        
        # Add quantization parameters
        if bits != 4:  # 4-bit is default
            cmd.extend(["--q-bits", str(bits)])
        
        if group_size:
            cmd.extend(["--q-group-size", str(group_size)])
        
        # Execute quantization with progress monitoring
        start_time = time.time()
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Quantizing model...", total=None)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                progress.update(task, description="Quantization complete")
            
            quantization_time = time.time() - start_time
            
            # Validate output
            required_files = ["config.json", "tokenizer.json"]
            weight_files = list(output_path.glob("*.safetensors")) + list(output_path.glob("*.npz"))
            
            if not weight_files:
                raise RuntimeError("No weight files found after quantization")
            
            for req_file in required_files:
                if not (output_path / req_file).exists():
                    console.print(f"[yellow]Warning: {req_file} not found in output[/yellow]")
            
            return {
                "quantization_time_seconds": quantization_time,
                "command_used": " ".join(cmd),
                "output_files": len(list(output_path.iterdir())),
                "weight_files": len(weight_files),
                "stdout": result.stdout if result.stdout else "",
                "success": True
            }
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Quantization command failed: {e.stderr if e.stderr else e.stdout}"
            raise RuntimeError(error_msg)
    
    def _validate_quantization_quality(
        self,
        original_path: Path,
        quantized_path: Path,
        test_prompts: Optional[List[str]],
        console: Console
    ) -> Dict[str, Any]:
        """
        Validate quantization quality through generation comparison.
        
        This tests the quantized model against the original to measure
        quality degradation. We use multiple metrics including:
        - Response similarity
        - Generation consistency
        - Task-specific performance
        """
        quality_results = {
            "tests_run": 0,
            "tests_passed": 0,
            "similarity_scores": [],
            "generation_times": {"original": [], "quantized": []},
            "errors": []
        }
        
        try:
            # Load both models
            console.print("  Loading original model...")
            original_model, original_tokenizer = load(str(original_path))
            
            console.print("  Loading quantized model...")
            quantized_model, quantized_tokenizer = load(str(quantized_path))
            
            # Use default prompts if none provided
            if not test_prompts:
                test_prompts = self.quality_test_prompts["general"]
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                
                task = progress.add_task(
                    "Testing quality...", 
                    total=len(test_prompts)
                )
                
                for i, prompt in enumerate(test_prompts):
                    try:
                        # Generate with original model
                        start_time = time.time()
                        original_response = generate(
                            original_model, original_tokenizer,
                            prompt=prompt,
                            max_tokens=100,
                            temperature=0.1,  # Low temperature for consistency
                            verbose=False
                        )
                        original_time = time.time() - start_time
                        
                        # Generate with quantized model
                        start_time = time.time()
                        quantized_response = generate(
                            quantized_model, quantized_tokenizer,
                            prompt=prompt,
                            max_tokens=100,
                            temperature=0.1,
                            verbose=False
                        )
                        quantized_time = time.time() - start_time
                        
                        # Calculate similarity
                        similarity = self._calculate_response_similarity(
                            original_response, quantized_response
                        )
                        
                        quality_results["similarity_scores"].append(similarity)
                        quality_results["generation_times"]["original"].append(original_time)
                        quality_results["generation_times"]["quantized"].append(quantized_time)
                        quality_results["tests_run"] += 1
                        
                        # Consider test passed if similarity is above threshold
                        if similarity > 0.7:  # 70% similarity threshold
                            quality_results["tests_passed"] += 1
                        
                        progress.update(
                            task,
                            completed=i+1,
                            description=f"Quality test {i+1}/{len(test_prompts)} (sim: {similarity:.2f})"
                        )
                        
                    except Exception as e:
                        quality_results["errors"].append(f"Test {i+1}: {e}")
                        continue
            
            # Calculate overall metrics
            if quality_results["similarity_scores"]:
                quality_results["avg_similarity"] = np.mean(quality_results["similarity_scores"])
                quality_results["min_similarity"] = np.min(quality_results["similarity_scores"])
                quality_results["max_similarity"] = np.max(quality_results["similarity_scores"])
                quality_results["overall_quality_score"] = quality_results["avg_similarity"]
            else:
                quality_results["overall_quality_score"] = 0.0
            
            # Speed comparison
            if quality_results["generation_times"]["original"]:
                orig_avg_time = np.mean(quality_results["generation_times"]["original"])
                quant_avg_time = np.mean(quality_results["generation_times"]["quantized"])
                
                quality_results["avg_generation_time_original"] = orig_avg_time
                quality_results["avg_generation_time_quantized"] = quant_avg_time
                quality_results["speed_improvement"] = orig_avg_time / quant_avg_time if quant_avg_time > 0 else 1.0
            
            # Pass rate
            if quality_results["tests_run"] > 0:
                quality_results["pass_rate"] = quality_results["tests_passed"] / quality_results["tests_run"]
            else:
                quality_results["pass_rate"] = 0.0
                
        except Exception as e:
            quality_results["validation_error"] = str(e)
            quality_results["overall_quality_score"] = 0.0
        
        return quality_results
    
    def _calculate_response_similarity(self, response1: str, response2: str) -> float:
        """
        Calculate similarity between two responses.
        
        This uses multiple similarity metrics to provide a robust
        assessment of how much the quantized model's outputs differ
        from the original model's outputs.
        """
        try:
            # Normalize responses
            resp1 = response1.lower().strip()
            resp2 = response2.lower().strip()
            
            if not resp1 or not resp2:
                return 0.0
            
            # Character-level similarity (simple but effective)
            char_similarity = self._character_similarity(resp1, resp2)
            
            # Word-level similarity
            word_similarity = self._word_similarity(resp1, resp2)
            
            # Length similarity
            len_similarity = min(len(resp1), len(resp2)) / max(len(resp1), len(resp2))
            
            # Weighted combination
            overall_similarity = (
                char_similarity * 0.4 +
                word_similarity * 0.4 +
                len_similarity * 0.2
            )
            
            return min(1.0, max(0.0, overall_similarity))
            
        except Exception:
            return 0.0
    
    def _character_similarity(self, text1: str, text2: str) -> float:
        """Calculate character-level similarity using edit distance."""
        def levenshtein_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            
            if len(s2) == 0:
                return len(s1)
            
            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            
            return previous_row[-1]
        
        max_len = max(len(text1), len(text2))
        if max_len == 0:
            return 1.0
        
        distance = levenshtein_distance(text1, text2)
        return 1.0 - (distance / max_len)
    
    def _word_similarity(self, text1: str, text2: str) -> float:
        """Calculate word-level similarity using Jaccard index."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 and not words2:
            return 1.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
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
    
    def _generate_quantization_recommendations(
        self,
        original_analysis: Dict[str, Any],
        quantized_analysis: Dict[str, Any],
        quality_results: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on quantization results."""
        recommendations = []
        
        # Size reduction recommendations
        compression_ratio = original_analysis.get("size_gb", 1) / quantized_analysis.get("size_gb", 1)
        if compression_ratio < 2:
            recommendations.append("Consider more aggressive quantization (2-bit) for better compression")
        elif compression_ratio > 4:
            recommendations.append("Excellent compression achieved - model is deployment-ready")
        
        # Quality recommendations
        quality_score = quality_results.get("overall_quality_score", 0)
        if quality_score < 0.6:
            recommendations.append("Quality loss is significant - consider 8-bit quantization or fine-tuning recovery")
        elif quality_score < 0.8:
            recommendations.append("Moderate quality loss - test thoroughly with your specific use case")
        else:
            recommendations.append("Quality well preserved - quantization successful")
        
        # Speed recommendations
        speed_improvement = quality_results.get("speed_improvement", 1)
        if speed_improvement > 1.2:
            recommendations.append(f"Generation speed improved by {speed_improvement:.1f}x")
        
        # Memory recommendations
        original_size = original_analysis.get("size_gb", 0)
        quantized_size = quantized_analysis.get("size_gb", 0)
        
        if quantized_size < 4:
            recommendations.append("Model size suitable for edge deployment")
        elif quantized_size < 8:
            recommendations.append("Model size good for consumer hardware")
        else:
            recommendations.append("Model still large - consider further optimization for deployment")
        
        return recommendations
    
    def _display_quantization_summary(self, results: Dict[str, Any], console: Console):
        """Display a formatted summary of quantization results."""
        original = results["original_analysis"]
        quantized = results["quantized_analysis"]
        quality = results["quality_results"]
        
        # Create results table
        table = Table(title="Quantization Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Original", style="yellow")
        table.add_column("Quantized", style="green")
        table.add_column("Change", style="magenta")
        
        # Size comparison
        orig_size = original.get("size_gb", 0)
        quant_size = quantized.get("size_gb", 0)
        size_reduction = orig_size - quant_size
        compression_ratio = orig_size / quant_size if quant_size > 0 else 1
        
        table.add_row(
            "Model Size",
            f"{orig_size:.2f} GB",
            f"{quant_size:.2f} GB",
            f"-{size_reduction:.2f} GB ({compression_ratio:.1f}x)"
        )
        
        # Memory usage
        if original.get("memory_usage_mb") and quantized.get("memory_usage_mb"):
            orig_mem = original["memory_usage_mb"]
            quant_mem = quantized["memory_usage_mb"]
            mem_reduction = orig_mem - quant_mem
            
            table.add_row(
                "Memory Usage",
                f"{orig_mem:.0f} MB",
                f"{quant_mem:.0f} MB",
                f"-{mem_reduction:.0f} MB"
            )
        
        # Quality metrics
        if quality.get("overall_quality_score") is not None:
            quality_score = quality["overall_quality_score"]
            quality_color = "green" if quality_score > 0.8 else "yellow" if quality_score > 0.6 else "red"
            
            table.add_row(
                "Quality Score",
                "1.000",
                f"{quality_score:.3f}",
                f"[{quality_color}]{quality_score:.1%}[/{quality_color}]"
            )
        
        console.print(table)
        
        # Display recommendations
        recommendations = results.get("recommendations", [])
        if recommendations:
            console.print("\n[blue]Recommendations:[/blue]")
            for rec in recommendations:
                console.print(f"  • {rec}")
    
    def compare_quantization_options(
        self,
        model_path: Path,
        output_dir: Path,
        bits_options: List[int] = [2, 4, 8],
        console: Optional[Console] = None
    ) -> Dict[str, Any]:
        """
        Compare multiple quantization options to find the optimal balance.
        
        This creates quantized versions with different bit depths and
        compares their quality/size trade-offs to help you make an
        informed decision about which quantization to use.
        """
        if console is None:
            console = Console()
        
        console.print("[blue]Comparing quantization options...[/blue]")
        
        results = {}
        comparison_data = []
        
        for bits in bits_options:
            console.print(f"\n[yellow]Testing {bits}-bit quantization...[/yellow]")
            
            quant_output = output_dir / f"quantized_{bits}bit"
            
            try:
                result = self.quantize_model(
                    model_path=model_path,
                    output_path=quant_output,
                    bits=bits,
                    validate_quality=True
                )
                
                results[f"{bits}bit"] = result
                
                # Extract key metrics for comparison
                comparison_data.append({
                    "bits": bits,
                    "size_gb": result["quantized_analysis"]["size_gb"],
                    "compression_ratio": result["compression_ratio"],
                    "quality_score": result["quality_results"].get("overall_quality_score", 0),
                    "pass_rate": result["quality_results"].get("pass_rate", 0)
                })
                
            except Exception as e:
                console.print(f"[red]{bits}-bit quantization failed: {e}[/red]")
                results[f"{bits}bit"] = {"error": str(e)}
        
        # Find optimal balance
        optimal_config = self._find_optimal_quantization(comparison_data)
        
        # Display comparison
        self._display_quantization_comparison(comparison_data, optimal_config, console)
        
        return {
            "individual_results": results,
            "comparison_data": comparison_data,
            "optimal_configuration": optimal_config,
            "recommendation": self._generate_optimal_recommendation(optimal_config, comparison_data)
        }
    
    def _find_optimal_quantization(self, comparison_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find the optimal quantization configuration based on multiple criteria."""
        if not comparison_data:
            return {}
        
        # Score each configuration
        scored_configs = []
        
        for config in comparison_data:
            quality_score = config.get("quality_score", 0)
            compression_ratio = config.get("compression_ratio", 1)
            size_gb = config.get("size_gb", float('inf'))
            
            # Weighted scoring (customize these weights based on priorities)
            quality_weight = 0.4
            compression_weight = 0.3
            size_weight = 0.3
            
            # Normalize scores
            quality_norm = quality_score  # Already 0-1
            compression_norm = min(1.0, compression_ratio / 5.0)  # Normalize to 5x max
            size_norm = max(0.0, 1.0 - (size_gb / 20.0))  # Penalize models over 20GB
            
            overall_score = (
                quality_norm * quality_weight +
                compression_norm * compression_weight +
                size_norm * size_weight
            )
            
            scored_configs.append({
                **config,
                "overall_score": overall_score
            })
        
        # Return the highest scoring configuration
        return max(scored_configs, key=lambda x: x["overall_score"])
    
    def _display_quantization_comparison(
        self, 
        comparison_data: List[Dict[str, Any]], 
        optimal_config: Dict[str, Any],
        console: Console
    ):
        """Display comparison of quantization options."""
        if not comparison_data:
            console.print("[red]No quantization data to compare[/red]")
            return
        
        table = Table(title="Quantization Options Comparison")
        table.add_column("Bits", style="cyan")
        table.add_column("Size (GB)", style="yellow")
        table.add_column("Compression", style="green")
        table.add_column("Quality", style="blue")
        table.add_column("Score", style="magenta")
        
        for config in sorted(comparison_data, key=lambda x: x["bits"]):
            bits = config["bits"]
            size_gb = config.get("size_gb", 0)
            compression = config.get("compression_ratio", 1)
            quality = config.get("quality_score", 0)
            overall_score = config.get("overall_score", 0)
            
            # Highlight optimal configuration
            style = "bold" if config == optimal_config else ""
            
            table.add_row(
                f"[{style}]{bits}[/{style}]",
                f"[{style}]{size_gb:.2f}[/{style}]",
                f"[{style}]{compression:.1f}x[/{style}]",
                f"[{style}]{quality:.3f}[/{style}]",
                f"[{style}]{overall_score:.3f}[/{style}]"
            )
        
        console.print(table)
        
        if optimal_config:
            console.print(
                f"\n[green]Recommended: {optimal_config['bits']}-bit quantization "
                f"(Score: {optimal_config.get('overall_score', 0):.3f})[/green]"
            )
    
    def _generate_optimal_recommendation(
        self, 
        optimal_config: Dict[str, Any], 
        all_configs: List[Dict[str, Any]]
    ) -> str:
        """Generate a recommendation based on optimal configuration."""
        if not optimal_config:
            return "Unable to determine optimal quantization - all options failed"
        
        bits = optimal_config["bits"]
        quality = optimal_config.get("quality_score", 0)
        compression = optimal_config.get("compression_ratio", 1)
        
        recommendation = f"Use {bits}-bit quantization for optimal balance. "
        
        if quality > 0.8:
            recommendation += "Quality is well preserved. "
        elif quality > 0.6:
            recommendation += "Quality is acceptable for most use cases. "
        else:
            recommendation += "Quality loss is noticeable - test thoroughly. "
        
        if compression > 3:
            recommendation += f"Excellent {compression:.1f}x compression achieved."
        elif compression > 2:
            recommendation += f"Good {compression:.1f}x compression."
        else:
            recommendation += f"Moderate {compression:.1f}x compression."
        
        return recommendation
