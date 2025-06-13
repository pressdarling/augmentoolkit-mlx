"""
MLX Complete Pipeline - A comprehensive toolkit for LLM development on Apple Silicon

This package provides end-to-end functionality for working with large language models
using MLX on Apple Silicon. It covers the entire pipeline from environment setup
through data preparation, model selection, fine-tuning, quantization, and deployment.

The architecture follows a modular design where each step can be used independently
or as part of a complete workflow. This approach allows for flexibility while
maintaining consistency across the entire pipeline.

Key modules:
- setup: Environment configuration and validation
- data: Data preparation and format conversion
- models: Model downloading and management  
- training: Fine-tuning with MLX
- quantization: Model optimization and compression
- inference: Deployment and serving
- integration: Foundation Models and Augmentoolkit integration
"""

__version__ = "0.1.0"
__author__ = "Brady Clarke"

# Make key classes available at package level for convenience
from .models import ModelManager
from .data import DataProcessor
from .training import MLXTrainer
from .inference import InferenceEngine

__all__ = [
    "ModelManager",
    "DataProcessor", 
    "MLXTrainer",
    "InferenceEngine",
]
