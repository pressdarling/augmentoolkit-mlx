"""
Environment Setup and Validation Module

This module handles the critical task of ensuring your Mac is properly configured
for MLX development. Environment issues are often the source of mysterious failures
later in the pipeline, so we validate everything upfront.

The philosophy here is "fail fast with clear error messages" rather than
discovering problems hours into a training run. We check everything from
Python architecture to Metal GPU support to memory availability.

Think of this as your pre-flight checklist before taking off on a long journey.
Better to discover issues on the ground than at 30,000 feet.
"""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import psutil

try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

try:
    import mlx_lm
    MLX_LM_AVAILABLE = True
except ImportError:
    MLX_LM_AVAILABLE = False


class EnvironmentSetup:
    """
    Comprehensive environment validation for MLX development.
    
    This class performs systematic checks of your development environment,
    from low-level hardware support through high-level framework availability.
    Each check is designed to catch common issues and provide actionable
    error messages when problems are found.
    """
    
    def __init__(self):
        self.checks = {
            "python_architecture": self._check_python_architecture,
            "python_version": self._check_python_version,
            "mlx_installation": self._check_mlx_installation,
            "mlx_lm_installation": self._check_mlx_lm_installation,
            "metal_support": self._check_metal_support,
            "memory_availability": self._check_memory_availability,
            "xcode_tools": self._check_xcode_tools,
            "disk_space": self._check_disk_space,
        }
    
    def validate_environment(
        self, 
        validate_metal: bool = True,
        check_memory: bool = True,
        install_deps: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run comprehensive environment validation.
        
        This method orchestrates all the individual checks and provides
        a comprehensive report. The design allows you to skip certain
        checks if you're working in a constrained environment.
        
        Args:
            validate_metal: Check Metal GPU support (disable for debugging)
            check_memory: Validate available memory (disable for containers)
            install_deps: Attempt to install missing dependencies
            
        Returns:
            Dictionary with validation results for each component
        """
        results = {}
        
        # Core Python environment checks (always required)
        for check_name in ["python_architecture", "python_version"]:
            try:
                results[check_name] = self.checks[check_name]()
            except Exception as e:
                results[check_name] = {
                    "passed": False,
                    "details": f"Check failed: {e}",
                    "actionable_fix": "Check Python installation"
                }
        
        # MLX framework checks
        for check_name in ["mlx_installation", "mlx_lm_installation"]:
            try:
                result = self.checks[check_name]()
                if not result["passed"] and install_deps:
                    # Attempt automatic installation
                    self._attempt_install_mlx()
                    result = self.checks[check_name]()  # Re-check after install
                results[check_name] = result
            except Exception as e:
                results[check_name] = {
                    "passed": False,
                    "details": f"Check failed: {e}",
                    "actionable_fix": "Run: pip install mlx mlx-lm"
                }
        
        # Hardware and system checks
        if validate_metal:
            results["metal_support"] = self._check_metal_support()
        
        if check_memory:
            results["memory_availability"] = self._check_memory_availability()
        
        # Development tools
        results["xcode_tools"] = self._check_xcode_tools()
        results["disk_space"] = self._check_disk_space()
        
        return results
    
    def _check_python_architecture(self) -> Dict[str, Any]:
        """
        Verify we're running native ARM Python, not x86 emulation.
        
        This is crucial because x86 Python under Rosetta will be significantly
        slower and may cause compatibility issues with MLX. Many developers
        accidentally install x86 Python and wonder why performance is poor.
        """
        arch = platform.processor()
        machine = platform.machine()
        
        # We want ARM64 native execution
        is_native_arm = arch == "arm" and machine == "arm64"
        
        if is_native_arm:
            return {
                "passed": True,
                "details": f"Native ARM64 Python (arch: {arch}, machine: {machine})",
                "performance_impact": "Optimal"
            }
        else:
            return {
                "passed": False,
                "details": f"Non-native Python (arch: {arch}, machine: {machine})",
                "actionable_fix": "Install native ARM64 Python via Miniforge or python.org",
                "performance_impact": "Severely degraded under Rosetta"
            }
    
    def _check_python_version(self) -> Dict[str, Any]:
        """
        Verify Python version compatibility with MLX.
        
        MLX requires Python 3.8+ but works best with 3.9+. We also check
        for versions that are too new and might have compatibility issues.
        """
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        
        if version >= (3, 9) and version < (3, 13):
            return {
                "passed": True,
                "details": f"Python {version_str} (recommended range)",
                "compatibility": "Full"
            }
        elif version >= (3, 8) and version < (3, 9):
            return {
                "passed": True,
                "details": f"Python {version_str} (minimum supported)",
                "compatibility": "Good",
                "recommendation": "Consider upgrading to Python 3.9+ for best performance"
            }
        else:
            return {
                "passed": False,
                "details": f"Python {version_str} (unsupported)",
                "actionable_fix": "Install Python 3.9-3.12",
                "compatibility": "None"
            }
    
    def _check_mlx_installation(self) -> Dict[str, Any]:
        """
        Verify MLX is properly installed and functional.
        
        We don't just check if the module imports - we test basic functionality
        to ensure the installation is complete and working. A broken MLX install
        can pass import tests but fail during actual use.
        """
        if not MLX_AVAILABLE:
            return {
                "passed": False,
                "details": "MLX not installed",
                "actionable_fix": "pip install mlx",
                "required_for": "All MLX operations"
            }
        
        try:
            # Test basic MLX functionality
            import mlx.core as mx
            
            # Simple computation test
            a = mx.array([1, 2, 3])
            b = mx.array([4, 5, 6])
            c = a + b  # This should work if MLX is properly installed
            
            # Check version
            version = getattr(mx, '__version__', 'unknown')
            
            return {
                "passed": True,
                "details": f"MLX {version} installed and functional",
                "basic_operations": "Working",
                "test_result": f"Array computation successful: {c.tolist()}"
            }
            
        except Exception as e:
            return {
                "passed": False,
                "details": f"MLX installed but not functional: {e}",
                "actionable_fix": "Reinstall MLX: pip uninstall mlx && pip install mlx",
                "error_type": type(e).__name__
            }
    
    def _check_mlx_lm_installation(self) -> Dict[str, Any]:
        """
        Verify MLX-LM is installed for language model operations.
        
        MLX-LM is the high-level package that makes working with language models
        practical. It handles model loading, tokenization, and generation.
        """
        if not MLX_LM_AVAILABLE:
            return {
                "passed": False,
                "details": "MLX-LM not installed",
                "actionable_fix": "pip install mlx-lm",
                "required_for": "Language model operations"
            }
        
        try:
            # Test that we can import key components
            from mlx_lm import load, generate
            from mlx_lm.utils import load_model
            
            # Check version if available
            version = getattr(mlx_lm, '__version__', 'unknown')
            
            return {
                "passed": True,
                "details": f"MLX-LM {version} installed",
                "components": "load, generate, utils available",
                "language_model_support": "Ready"
            }
            
        except ImportError as e:
            return {
                "passed": False,
                "details": f"MLX-LM import failed: {e}",
                "actionable_fix": "Reinstall MLX-LM: pip install --upgrade mlx-lm",
                "missing_component": str(e)
            }
    
    def _check_metal_support(self) -> Dict[str, Any]:
        """
        Verify Metal GPU support is available and functional.
        
        Metal is Apple's GPU API that MLX uses for acceleration. Without
        proper Metal support, MLX will fall back to CPU-only operation,
        which is dramatically slower for large models.
        """
        if not MLX_AVAILABLE:
            return {
                "passed": False,
                "details": "Cannot check Metal support - MLX not available",
                "impact": "GPU acceleration unavailable"
            }
        
        try:
            import mlx.core as mx
            
            # Test Metal memory access
            metal_memory = mx.metal.get_active_memory()
            peak_memory = mx.metal.get_peak_memory()
            
            # Simple GPU computation test
            a = mx.array([1.0, 2.0, 3.0])
            b = mx.array([4.0, 5.0, 6.0])
            c = a @ b  # Matrix multiply should use GPU
            
            return {
                "passed": True,
                "details": "Metal GPU support active",
                "active_memory_gb": f"{metal_memory / 1e9:.2f}",
                "peak_memory_gb": f"{peak_memory / 1e9:.2f}",
                "gpu_computation": "Working",
                "acceleration": "Available"
            }
            
        except Exception as e:
            return {
                "passed": False,
                "details": f"Metal support check failed: {e}",
                "actionable_fix": "Update macOS and restart Terminal",
                "impact": "GPU acceleration unavailable",
                "fallback": "CPU-only operation (very slow)"
            }
    
    def _check_memory_availability(self) -> Dict[str, Any]:
        """
        Check available system memory for model operations.
        
        Memory is often the limiting factor in LLM work. We check both
        total memory and currently available memory to help you plan
        model sizes and batch sizes appropriately.
        """
        memory = psutil.virtual_memory()
        total_gb = memory.total / 1e9
        available_gb = memory.available / 1e9
        used_percent = memory.percent
        
        # Recommendations based on available memory
        if total_gb >= 32:
            model_rec = "Can run 7B-13B models comfortably, 32B models possible"
            memory_class = "High"
        elif total_gb >= 16:
            model_rec = "Can run 7B models, larger models with quantization"
            memory_class = "Medium"
        else:
            model_rec = "Limited to small models (1B-3B parameters)"
            memory_class = "Low"
        
        return {
            "passed": True,
            "total_memory_gb": f"{total_gb:.1f}",
            "available_memory_gb": f"{available_gb:.1f}",
            "used_percent": f"{used_percent:.1f}%",
            "memory_class": memory_class,
            "model_recommendations": model_rec,
            "warning": "High memory usage" if used_percent > 80 else None
        }
    
    def _check_xcode_tools(self) -> Dict[str, Any]:
        """
        Verify Xcode Command Line Tools are installed.
        
        These tools provide essential compilers and build tools that MLX
        dependencies require. Without them, pip installations often fail
        with cryptic error messages.
        """
        try:
            # Check if xcode-select can find the tools
            result = subprocess.run(
                ["xcode-select", "-p"],
                capture_output=True,
                text=True,
                check=True
            )
            
            tools_path = result.stdout.strip()
            
            return {
                "passed": True,
                "details": f"Xcode Command Line Tools installed at {tools_path}",
                "build_support": "Available"
            }
            
        except subprocess.CalledProcessError:
            return {
                "passed": False,
                "details": "Xcode Command Line Tools not found",
                "actionable_fix": "Run: xcode-select --install",
                "impact": "Cannot compile native dependencies"
            }
        except FileNotFoundError:
            return {
                "passed": False,
                "details": "xcode-select command not found",
                "actionable_fix": "Install Xcode Command Line Tools from Developer Tools",
                "impact": "Build tools unavailable"
            }
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """
        Check available disk space for models and datasets.
        
        LLMs and their associated datasets can be quite large. A 7B model
        might be 15GB, and training datasets can be similar sizes. We check
        available space to help you plan storage needs.
        """
        try:
            # Check space in current directory (likely where models will be stored)
            statvfs = Path.cwd().stat()
            
            # Alternative method using shutil for broader compatibility
            import shutil
            total, used, free = shutil.disk_usage(Path.cwd())
            
            total_gb = total / 1e9
            free_gb = free / 1e9
            used_gb = used / 1e9
            used_percent = (used / total) * 100
            
            # Recommendations based on free space
            if free_gb >= 100:
                storage_rec = "Ample space for multiple large models and datasets"
                storage_class = "Excellent"
            elif free_gb >= 50:
                storage_rec = "Good space for several 7B models and training data"
                storage_class = "Good"
            elif free_gb >= 20:
                storage_rec = "Limited space - can store 1-2 models"
                storage_class = "Limited"
            else:
                storage_rec = "Very limited space - may need external storage"
                storage_class = "Critical"
            
            return {
                "passed": free_gb >= 10,  # Minimum 10GB required
                "total_storage_gb": f"{total_gb:.1f}",
                "free_storage_gb": f"{free_gb:.1f}",
                "used_percent": f"{used_percent:.1f}%",
                "storage_class": storage_class,
                "recommendations": storage_rec,
                "warning": "Low disk space" if free_gb < 20 else None
            }
            
        except Exception as e:
            return {
                "passed": False,
                "details": f"Could not check disk space: {e}",
                "actionable_fix": "Ensure current directory is accessible"
            }
    
    def _attempt_install_mlx(self) -> None:
        """
        Attempt automatic installation of MLX packages.
        
        This is a convenience method for automated setups. In interactive
        environments, it's usually better to let users handle installations
        manually so they understand what's being installed.
        """
        packages = ["mlx", "mlx-lm"]
        
        for package in packages:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", package],
                    check=True,
                    capture_output=True
                )
            except subprocess.CalledProcessError as e:
                # Installation failed, but we'll let the validation catch this
                pass
    
    def generate_setup_script(self, output_path: Optional[Path] = None) -> str:
        """
        Generate a setup script based on current environment state.
        
        This creates a shell script that addresses any issues found during
        validation. It's particularly useful for setting up new environments
        or debugging installation problems.
        """
        script_lines = [
            "#!/bin/bash",
            "# MLX Environment Setup Script",
            "# Generated by MLX Complete Pipeline",
            "",
            "set -e  # Exit on any error",
            "",
            "echo 'Setting up MLX development environment...'",
            "",
        ]
        
        # Run validation to see what needs fixing
        results = self.validate_environment()
        
        # Add fixes for any failed checks
        for check_name, result in results.items():
            if not result.get("passed", False):
                fix = result.get("actionable_fix", "")
                if fix:
                    script_lines.extend([
                        f"echo 'Fixing {check_name}...'",
                        fix,
                        ""
                    ])
        
        script_lines.extend([
            "echo 'Environment setup complete!'",
            "echo 'Run: mlx-setup to validate the installation'",
            ""
        ])
        
        script_content = "\n".join(script_lines)
        
        if output_path:
            output_path.write_text(script_content)
            output_path.chmod(0o755)  # Make executable
        
        return script_content
