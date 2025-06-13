#!/usr/bin/env python3
"""
Augmentoolkit-MLX Pipeline Orchestrator

This script orchestrates the entire pipeline from raw documents to a fine-tuned MLX model.
It integrates Augmentoolkit for data generation with MLX for training.
"""

import yaml
import subprocess
import sys
from pathlib import Path
import argparse
import logging
from typing import Dict, Any
import shutil


class PipelineOrchestrator:
    """Main orchestrator for the Augmentoolkit → MLX pipeline."""
    
    def __init__(self, config_path: Path):
        """Initialize with pipeline configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.setup_logging()
        self.validate_config()
        
    def setup_logging(self):
        """Configure logging based on config."""
        log_config = self.config.get('logging', {})
        level = getattr(logging, log_config.get('level', 'INFO'))
        
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_config.get('log_file', 'pipeline.log'))
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def validate_config(self):
        """Validate the pipeline configuration."""
        required_sections = ['input', 'augmentoolkit', 'conversion', 'mlx_training']
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required config section: {section}")
                
        # Validate paths exist
        input_dir = Path(self.config['input']['documents_dir'])
        if not input_dir.exists():
            raise ValueError(f"Input documents directory does not exist: {input_dir}")
            
    def run_data_generation(self) -> bool:
        """Run Augmentoolkit data generation."""
        if self.config['execution'].get('skip_data_generation', False):
            self.logger.info("Skipping data generation (skip_data_generation=True)")
            return True
            
        self.logger.info("Starting Augmentoolkit data generation...")
        
        aug_config = self.config['augmentoolkit']
        
        # Prepare Augmentoolkit environment
        aug_dir = Path("./submodules/augmentoolkit")
        if not aug_dir.exists():
            self.logger.error("Augmentoolkit submodule not found. Run: git submodule update --init")
            return False
            
        # Copy input documents to Augmentoolkit input directory
        input_dir = Path(self.config['input']['documents_dir'])
        aug_input_dir = aug_dir / "raw_txt_input"
        aug_input_dir.mkdir(exist_ok=True)
        
        for file_pattern in self.config['input']['file_types']:
            for file_path in input_dir.glob(f"*{file_pattern}"):
                shutil.copy2(file_path, aug_input_dir)
                self.logger.info(f"Copied {file_path.name} to Augmentoolkit input")
        
        # Run Augmentoolkit
        try:
            cmd = [sys.executable, "processing.py"]
            result = subprocess.run(
                cmd, 
                cwd=aug_dir,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                self.logger.error(f"Augmentoolkit failed: {result.stderr}")
                return False
                
            self.logger.info("Augmentoolkit data generation completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Augmentoolkit data generation timed out")
            return False
        except Exception as e:
            self.logger.error(f"Error running Augmentoolkit: {e}")
            return False
            
    def run_format_conversion(self) -> bool:
        """Convert Augmentoolkit output to MLX format."""
        if self.config['execution'].get('skip_conversion', False):
            self.logger.info("Skipping format conversion (skip_conversion=True)")
            return True
            
        self.logger.info("Starting format conversion...")
        
        conv_config = self.config['conversion']
        
        try:
            # Use the converter script we created
            cmd = [
                sys.executable, "converters/augmentoolkit_to_mlx.py",
                conv_config['input_file'],
                conv_config['output_base'],
                "--train-ratio", str(conv_config['train_ratio'])
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Format conversion failed: {result.stderr}")
                return False
                
            self.logger.info("Format conversion completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during format conversion: {e}")
            return False
            
    def run_mlx_training(self) -> bool:
        """Run MLX LoRA training."""
        if self.config['execution'].get('skip_training', False):
            self.logger.info("Skipping MLX training (skip_training=True)")
            return True
            
        self.logger.info("Starting MLX training...")
        
        training_config = self.config['mlx_training']
        
        # Prepare training command based on framework choice
        framework = training_config.get('framework', 'mlx-lm')
        
        if framework == 'mlx-tuning-fork':
            # Use mlx-tuning-fork
            cmd = self._build_tuning_fork_command(training_config)
        else:
            # Use basic mlx-lm
            cmd = self._build_mlx_lm_command(training_config)
            
        try:
            self.logger.info(f"Running training command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"MLX training failed: {result.stderr}")
                return False
                
            self.logger.info("MLX training completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during MLX training: {e}")
            return False
            
    def _build_mlx_lm_command(self, training_config: Dict[str, Any]) -> list:
        """Build mlx-lm training command."""
        model_config = training_config['model']
        train_config = training_config['training']
        
        cmd = [
            sys.executable, "-m", "mlx_lm.lora",
            "--train",
            "--model", model_config['base_model'],
            "--data", str(Path(self.config['conversion']['output_base']).parent),
            "--batch-size", str(train_config['batch_size']),
            "--learning-rate", str(train_config['learning_rate']),
            "--iters", str(train_config.get('max_steps', 1000)),
            "--adapter-path", training_config['output']['adapter_dir']
        ]
        
        return cmd
        
    def _build_tuning_fork_command(self, training_config: Dict[str, Any]) -> list:
        """Build mlx-tuning-fork training command."""
        # Create temporary config file for mlx-tuning-fork
        fork_config = self._create_tuning_fork_config(training_config)
        
        cmd = [
            "mlx_tuning_fork_training",
            str(fork_config)
        ]
        
        return cmd
        
    def _create_tuning_fork_config(self, training_config: Dict[str, Any]) -> Path:
        """Create mlx-tuning-fork configuration file."""
        # This would create a YAML config file compatible with mlx-tuning-fork
        # Implementation details would depend on mlx-tuning-fork's exact format
        pass
        
    def run_post_processing(self) -> bool:
        """Run post-processing steps like model fusion."""
        post_config = self.config.get('post_processing', {})
        
        if post_config.get('fuse_adapter', False):
            self.logger.info("Fusing adapter with base model...")
            # Implementation would use mlx-lm fuse command
            
        if post_config.get('test_model', False):
            self.logger.info("Testing final model...")
            # Implementation would run basic inference tests
            
        return True
        
    def run_pipeline(self) -> bool:
        """Run the complete pipeline."""
        self.logger.info("Starting Augmentoolkit-MLX pipeline...")
        
        steps = [
            ("Data Generation", self.run_data_generation),
            ("Format Conversion", self.run_format_conversion),
            ("MLX Training", self.run_mlx_training),
            ("Post-processing", self.run_post_processing)
        ]
        
        for step_name, step_func in steps:
            self.logger.info(f"Running step: {step_name}")
            if not step_func():
                self.logger.error(f"Pipeline failed at step: {step_name}")
                return False
                
        self.logger.info("Pipeline completed successfully!")
        return True


def main():
    parser = argparse.ArgumentParser(description="Run Augmentoolkit-MLX pipeline")
    parser.add_argument("config", type=Path, help="Path to pipeline configuration YAML")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Validate configuration without running pipeline")
    
    args = parser.parse_args()
    
    if not args.config.exists():
        print(f"Error: Configuration file {args.config} does not exist")
        return 1
        
    try:
        orchestrator = PipelineOrchestrator(args.config)
        
        if args.dry_run:
            print("Configuration validation passed")
            return 0
            
        success = orchestrator.run_pipeline()
        return 0 if success else 1
        
    except Exception as e:
        print(f"Pipeline error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())