"""
MLX Training Module

This module handles the complex process of fine-tuning language models using MLX.
Fine-tuning is where theory meets reality - all the preparation work culminates
in the actual training process that adapts a general model to your specific needs.

The training process involves several critical considerations:
- Memory management on Apple Silicon's unified memory architecture
- Learning rate scheduling and optimization
- Progress monitoring and checkpoint management
- Validation and overfitting detection
- Hardware-specific optimizations for M1/M2/M3 chips

The philosophy here is to provide maximum control whilst maintaining sensible
defaults. Advanced users can fine-tune every parameter, whilst beginners can
get good results with minimal configuration.
"""

import os
import time
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, asdict
import math

try:
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx_lm import load, lora
    from mlx_lm.utils import generate
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

import psutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live
from rich.table import Table
from rich.panel import Panel


@dataclass
class TrainingConfig:
    """
    Comprehensive configuration for MLX fine-tuning.
    
    This dataclass captures all the parameters that affect training,
    from basic settings like learning rate through advanced options
    like gradient accumulation and memory management.
    """
    # Model and data paths
    model_path: str
    data_path: str
    output_path: str
    adapter_path: Optional[str] = None
    
    # Training hyperparameters
    learning_rate: float = 1e-4
    batch_size: int = 4
    max_iters: int = 1000
    warmup_steps: int = 100
    weight_decay: float = 0.01
    grad_clip_norm: Optional[float] = 1.0
    
    # LoRA specific parameters
    lora_layers: int = 16
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    
    # Training strategy
    training_type: str = "lora"  # "lora" or "full"
    gradient_accumulation_steps: int = 1
    mixed_precision: bool = True
    
    # Evaluation and checkpointing
    eval_every: int = 100
    save_every: int = 200
    eval_steps: int = 50
    
    # Memory management
    max_sequence_length: Optional[int] = None
    gradient_checkpointing: bool = False
    
    # Learning rate scheduling
    lr_schedule: str = "cosine"  # "constant", "linear", "cosine"
    lr_warmup_fraction: float = 0.1
    
    # Validation
    validation_split: float = 0.1
    early_stopping_patience: Optional[int] = None
    
    # Logging and monitoring
    log_every: int = 10
    verbose: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.training_type not in ["lora", "full"]:
            raise ValueError("training_type must be 'lora' or 'full'")
        
        if self.lr_schedule not in ["constant", "linear", "cosine"]:
            raise ValueError("lr_schedule must be 'constant', 'linear', or 'cosine'")
        
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")


class TrainingMetrics:
    """
    Tracks training metrics and provides analysis capabilities.
    
    This class maintains a comprehensive record of training progress,
    including loss curves, learning rates, memory usage, and timing
    information. It's designed to help identify training issues early
    and optimize performance.
    """
    
    def __init__(self):
        self.iteration = []
        self.train_loss = []
        self.val_loss = []
        self.learning_rate = []
        self.tokens_per_second = []
        self.memory_usage = []
        self.wall_time = []
        self.start_time = time.time()
    
    def log_step(self, iteration: int, metrics: Dict[str, float]):
        """Log metrics for a training step."""
        self.iteration.append(iteration)
        self.train_loss.append(metrics.get("train_loss", 0.0))
        self.val_loss.append(metrics.get("val_loss", 0.0))
        self.learning_rate.append(metrics.get("learning_rate", 0.0))
        self.tokens_per_second.append(metrics.get("tokens_per_second", 0.0))
        self.memory_usage.append(metrics.get("memory_usage_gb", 0.0))
        self.wall_time.append(time.time() - self.start_time)
    
    def get_latest_metrics(self) -> Dict[str, float]:
        """Get the most recent metrics."""
        if not self.iteration:
            return {}
        
        return {
            "iteration": self.iteration[-1],
            "train_loss": self.train_loss[-1],
            "val_loss": self.val_loss[-1] if self.val_loss[-1] > 0 else None,
            "learning_rate": self.learning_rate[-1],
            "tokens_per_second": self.tokens_per_second[-1],
            "memory_usage_gb": self.memory_usage[-1],
            "elapsed_time": self.wall_time[-1]
        }
    
    def detect_overfitting(self, patience: int = 5) -> bool:
        """
        Detect if the model is overfitting based on validation loss.
        
        This uses a simple heuristic: if validation loss increases
        for several consecutive evaluations while training loss
        continues to decrease, we're likely overfitting.
        """
        if len(self.val_loss) < patience + 1:
            return False
        
        # Check last 'patience' validation losses
        recent_val_losses = [loss for loss in self.val_loss[-patience-1:] if loss > 0]
        
        if len(recent_val_losses) < patience + 1:
            return False
        
        # Check if validation loss is consistently increasing
        increasing_count = 0
        for i in range(1, len(recent_val_losses)):
            if recent_val_losses[i] > recent_val_losses[i-1]:
                increasing_count += 1
        
        return increasing_count >= patience * 0.7  # 70% of recent steps show increase
    
    def get_convergence_metrics(self) -> Dict[str, Any]:
        """
        Analyze convergence characteristics of the training run.
        
        This provides insights into training stability and progress
        that can help optimize hyperparameters for future runs.
        """
        if len(self.train_loss) < 10:
            return {"error": "Insufficient data for analysis"}
        
        # Calculate loss trend over recent steps
        recent_steps = min(50, len(self.train_loss))
        recent_losses = self.train_loss[-recent_steps:]
        
        # Simple linear trend
        x = list(range(len(recent_losses)))
        y = recent_losses
        
        # Calculate slope using least squares
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x_sq = sum(x[i] ** 2 for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x_sq - sum_x ** 2)
        
        # Convergence analysis
        is_converging = slope < -1e-6  # Loss is decreasing
        is_stable = abs(slope) < 1e-6  # Loss is stable
        
        # Calculate loss volatility
        loss_diffs = [abs(recent_losses[i] - recent_losses[i-1]) 
                     for i in range(1, len(recent_losses))]
        volatility = sum(loss_diffs) / len(loss_diffs) if loss_diffs else 0
        
        return {
            "convergence_slope": slope,
            "is_converging": is_converging,
            "is_stable": is_stable,
            "loss_volatility": volatility,
            "recent_avg_loss": sum(recent_losses) / len(recent_losses),
            "best_loss": min(self.train_loss),
            "steps_since_best": len(self.train_loss) - self.train_loss.index(min(self.train_loss)) - 1
        }
    
    def save_to_file(self, filepath: Path):
        """Save metrics to JSON file for later analysis."""
        metrics_data = {
            "iteration": self.iteration,
            "train_loss": self.train_loss,
            "val_loss": self.val_loss,
            "learning_rate": self.learning_rate,
            "tokens_per_second": self.tokens_per_second,
            "memory_usage": self.memory_usage,
            "wall_time": self.wall_time,
            "convergence_analysis": self.get_convergence_metrics()
        }
        
        with open(filepath, 'w') as f:
            json.dump(metrics_data, f, indent=2)


class MLXTrainer:
    """
    Comprehensive MLX fine-tuning trainer.
    
    This class orchestrates the entire fine-tuning process, from data loading
    through final model saving. It's designed to handle the complexity of
    modern fine-tuning whilst providing clear feedback about what's happening.
    
    The trainer supports both LoRA (Low-Rank Adaptation) and full fine-tuning,
    with automatic memory management and optimization for Apple Silicon hardware.
    """
    
    def __init__(self):
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available - cannot initialize trainer")
        
        self.metrics = TrainingMetrics()
        self.model = None
        self.tokenizer = None
        self.optimizer = None
        self.lr_scheduler = None
        
        # Training state
        self.current_iteration = 0
        self.best_val_loss = float('inf')
        self.patience_counter = 0
        
        # Memory monitoring
        self.peak_memory_gb = 0.0
        self.memory_warnings_shown = set()
    
    def train(
        self, 
        config: Union[TrainingConfig, Dict[str, Any]], 
        console: Optional[Console] = None
    ) -> Dict[str, Any]:
        """
        Main training loop with comprehensive monitoring and error handling.
        
        This orchestrates the entire training process:
        1. Setup and validation
        2. Model and data loading  
        3. Training loop with monitoring
        4. Checkpointing and evaluation
        5. Final model saving and validation
        
        Args:
            config: Training configuration
            console: Rich console for output (optional)
            
        Returns:
            Dictionary with training results and metrics
        """
        if isinstance(config, dict):
            config = TrainingConfig(**config)
        
        if console is None:
            console = Console()
        
        console.print(Panel(
            f"[bold blue]Starting MLX Fine-tuning[/bold blue]\n"
            f"Model: {config.model_path}\n"
            f"Training Type: {config.training_type.upper()}\n"
            f"Target Iterations: {config.max_iters}",
            title="Training Configuration"
        ))
        
        try:
            # Phase 1: Setup and Validation
            self._setup_training(config, console)
            
            # Phase 2: Training Loop
            training_results = self._run_training_loop(config, console)
            
            # Phase 3: Final Processing
            final_results = self._finalize_training(config, console, training_results)
            
            return final_results
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Training interrupted by user[/yellow]")
            return self._handle_early_termination(config)
        except Exception as e:
            console.print(f"\n[red]Training failed: {e}[/red]")
            raise
    
    def _setup_training(self, config: TrainingConfig, console: Console):
        """Setup phase: validate configuration and load components."""
        with console.status("[blue]Setting up training environment..."):
            # Validate configuration
            self._validate_config(config)
            
            # Check memory availability
            self._check_memory_requirements(config, console)
            
            # Load model and tokenizer
            console.print("[green]Loading model and tokenizer...[/green]")
            self.model, self.tokenizer = load(config.model_path)
            
            # Setup training components
            self._setup_optimizer(config)
            self._setup_lr_scheduler(config)
            
            # Validate data
            self._validate_training_data(config)
            
            console.print("[green]✓ Training setup complete[/green]")
    
    def _validate_config(self, config: TrainingConfig):
        """Validate training configuration for common issues."""
        # Check paths exist
        if not Path(config.model_path).exists():
            raise FileNotFoundError(f"Model path not found: {config.model_path}")
        
        if not Path(config.data_path).exists():
            raise FileNotFoundError(f"Data path not found: {config.data_path}")
        
        # Create output directory
        output_path = Path(config.output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Validate hyperparameters
        if config.lora_rank <= 0:
            raise ValueError("LoRA rank must be positive")
        
        if config.lora_alpha <= 0:
            raise ValueError("LoRA alpha must be positive")
        
        if not 0 <= config.lora_dropout <= 1:
            raise ValueError("LoRA dropout must be between 0 and 1")
    
    def _check_memory_requirements(self, config: TrainingConfig, console: Console):
        """
        Estimate and validate memory requirements for training.
        
        This prevents out-of-memory errors by checking requirements upfront
        and providing recommendations for parameter adjustments.
        """
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        total_gb = memory.total / (1024**3)
        
        # Estimate model memory usage
        model_files = list(Path(config.model_path).glob("*.safetensors"))
        model_size_gb = sum(f.stat().st_size for f in model_files) / (1024**3)
        
        # Estimate training memory requirements
        if config.training_type == "lora":
            # LoRA training: model + adapters + gradients + activations
            estimated_memory = model_size_gb * 2.0 + (config.batch_size * 0.5)
        else:
            # Full fine-tuning: model + full gradients + optimizer states
            estimated_memory = model_size_gb * 3.5 + (config.batch_size * 1.0)
        
        console.print(f"[blue]Memory Analysis:[/blue]")
        console.print(f"  Available: {available_gb:.1f}GB / {total_gb:.1f}GB")
        console.print(f"  Estimated need: {estimated_memory:.1f}GB")
        
        if estimated_memory > available_gb * 0.9:
            suggestions = []
            
            if config.batch_size > 1:
                suggestions.append(f"Reduce batch_size from {config.batch_size} to 1")
            
            if config.training_type == "full":
                suggestions.append("Switch to LoRA training for lower memory usage")
            
            if config.lora_rank > 8:
                suggestions.append(f"Reduce lora_rank from {config.lora_rank} to 8")
            
            warning_msg = f"[yellow]Warning: Estimated memory usage ({estimated_memory:.1f}GB) " \
                         f"exceeds available memory ({available_gb:.1f}GB)[/yellow]"
            
            if suggestions:
                warning_msg += f"\nSuggestions: {'; '.join(suggestions)}"
            
            console.print(warning_msg)
            
            if estimated_memory > total_gb:
                raise RuntimeError("Insufficient memory for training even with optimizations")
    
    def _setup_optimizer(self, config: TrainingConfig):
        """Setup optimizer with appropriate settings for the training type."""
        if config.training_type == "lora":
            # For LoRA, we only optimize the adapter parameters
            # This will be handled by the MLX LoRA training function
            pass
        else:
            # For full fine-tuning, setup AdamW optimizer
            self.optimizer = optim.AdamW(
                learning_rate=config.learning_rate,
                weight_decay=config.weight_decay,
                eps=1e-8,
                betas=(0.9, 0.95)  # Standard values for LLM training
            )
    
    def _setup_lr_scheduler(self, config: TrainingConfig):
        """Setup learning rate scheduler."""
        if config.lr_schedule == "constant":
            self.lr_scheduler = None
        elif config.lr_schedule == "linear":
            self.lr_scheduler = self._create_linear_schedule(config)
        elif config.lr_schedule == "cosine":
            self.lr_scheduler = self._create_cosine_schedule(config)
    
    def _create_linear_schedule(self, config: TrainingConfig):
        """Create linear learning rate schedule with warmup."""
        def linear_schedule(step: int) -> float:
            if step < config.warmup_steps:
                # Linear warmup
                return config.learning_rate * (step / config.warmup_steps)
            else:
                # Linear decay
                progress = (step - config.warmup_steps) / (config.max_iters - config.warmup_steps)
                return config.learning_rate * (1.0 - progress)
        
        return linear_schedule
    
    def _create_cosine_schedule(self, config: TrainingConfig):
        """Create cosine learning rate schedule with warmup."""
        def cosine_schedule(step: int) -> float:
            if step < config.warmup_steps:
                # Linear warmup
                return config.learning_rate * (step / config.warmup_steps)
            else:
                # Cosine decay
                progress = (step - config.warmup_steps) / (config.max_iters - config.warmup_steps)
                return config.learning_rate * 0.5 * (1 + math.cos(math.pi * progress))
        
        return cosine_schedule
    
    def _validate_training_data(self, config: TrainingConfig):
        """Validate training data format and content."""
        data_path = Path(config.data_path)
        
        # Check for required files
        train_file = data_path / "train.jsonl"
        valid_file = data_path / "valid.jsonl"
        
        if not train_file.exists():
            raise FileNotFoundError(f"Training data not found: {train_file}")
        
        if not valid_file.exists():
            raise FileNotFoundError(f"Validation data not found: {valid_file}")
        
        # Quick validation of data format
        try:
            with open(train_file, 'r') as f:
                first_line = f.readline().strip()
                if first_line:
                    sample_data = json.loads(first_line)
                    if "messages" not in sample_data and "text" not in sample_data:
                        raise ValueError("Invalid data format - missing 'messages' or 'text' field")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in training data: {e}")
    
    def _run_training_loop(self, config: TrainingConfig, console: Console) -> Dict[str, Any]:
        """
        Execute the main training loop with monitoring.
        
        This is where the actual fine-tuning happens. The loop handles:
        - Progress tracking and display
        - Memory monitoring
        - Periodic evaluation
        - Checkpoint saving
        - Early stopping detection
        """
        if config.training_type == "lora":
            return self._run_lora_training(config, console)
        else:
            return self._run_full_training(config, console)
    
    def _run_lora_training(self, config: TrainingConfig, console: Console) -> Dict[str, Any]:
        """
        Run LoRA fine-tuning using MLX's built-in LoRA implementation.
        
        LoRA is the recommended approach for most fine-tuning tasks because
        it's memory efficient and often achieves comparable results to
        full fine-tuning whilst being much faster.
        """
        console.print("[blue]Starting LoRA training...[/blue]")
        
        # Prepare LoRA arguments
        lora_args = {
            "model": config.model_path,
            "data": config.data_path,
            "train": True,
            "iters": config.max_iters,
            "val_batches": config.eval_steps,
            "learning_rate": config.learning_rate,
            "steps_per_report": config.log_every,
            "steps_per_eval": config.eval_every,
            "adapter_path": config.output_path,
            "save_every": config.save_every,
            "batch_size": config.batch_size,
            "lora_layers": config.lora_layers,
            "lora_rank": config.lora_rank,
            "lora_alpha": config.lora_alpha,
            "lora_dropout": config.lora_dropout,
        }
        
        # Add optional parameters
        if config.max_sequence_length:
            lora_args["max_seq_length"] = config.max_sequence_length
        
        if config.grad_clip_norm:
            lora_args["grad_checkpoint"] = True
        
        # Custom training loop with monitoring
        return self._monitor_lora_training(lora_args, config, console)
    
    def _monitor_lora_training(
        self, 
        lora_args: Dict[str, Any], 
        config: TrainingConfig, 
        console: Console
    ) -> Dict[str, Any]:
        """
        Monitor LoRA training with custom progress tracking.
        
        Since MLX's LoRA function doesn't provide granular callbacks,
        we monitor it by parsing its output and tracking metrics.
        """
        import subprocess
        import threading
        from queue import Queue
        
        # Create command
        cmd = ["python", "-m", "mlx_lm.lora"] 
        for key, value in lora_args.items():
            if isinstance(value, bool) and value:
                cmd.append(f"--{key.replace('_', '-')}")
            elif not isinstance(value, bool):
                cmd.extend([f"--{key.replace('_', '-')}", str(value)])
        
        # Setup progress tracking
        progress_queue = Queue()
        
        def monitor_output(process, queue):
            """Monitor training output and extract metrics."""
            iteration_pattern = r"Iter (\d+): Train loss ([\d.]+).*?It/sec ([\d.]+)"
            val_pattern = r"Iter (\d+): Val loss ([\d.]+)"
            
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                
                line = line.strip()
                
                # Parse training metrics
                import re
                train_match = re.search(iteration_pattern, line)
                if train_match:
                    iteration = int(train_match.group(1))
                    train_loss = float(train_match.group(2))
                    it_per_sec = float(train_match.group(3))
                    
                    memory_gb = mx.metal.get_active_memory() / (1024**3)
                    
                    metrics = {
                        "iteration": iteration,
                        "train_loss": train_loss,
                        "tokens_per_second": it_per_sec * config.batch_size,
                        "memory_usage_gb": memory_gb,
                        "learning_rate": self._get_current_lr(iteration, config)
                    }
                    
                    queue.put(("train_step", metrics))
                
                # Parse validation metrics
                val_match = re.search(val_pattern, line)
                if val_match:
                    iteration = int(val_match.group(1))
                    val_loss = float(val_match.group(2))
                    
                    queue.put(("val_step", {"iteration": iteration, "val_loss": val_loss}))
                
                # Forward output to console
                queue.put(("output", line))
        
        # Start training process
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=monitor_output, 
                args=(process, progress_queue)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Progress display
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                
                task = progress.add_task(
                    "Training...", 
                    total=config.max_iters
                )
                
                # Process monitoring queue
                while process.poll() is None or not progress_queue.empty():
                    try:
                        msg_type, data = progress_queue.get(timeout=1.0)
                        
                        if msg_type == "train_step":
                            iteration = data["iteration"]
                            self.metrics.log_step(iteration, data)
                            
                            progress.update(
                                task,
                                completed=iteration,
                                description=f"Iter {iteration}: Loss {data['train_loss']:.4f}, "
                                          f"{data['tokens_per_second']:.1f} tok/s, "
                                          f"{data['memory_usage_gb']:.1f}GB"
                            )
                            
                            # Update peak memory
                            self.peak_memory_gb = max(
                                self.peak_memory_gb, 
                                data['memory_usage_gb']
                            )
                            
                        elif msg_type == "val_step":
                            # Update validation loss in metrics
                            current_metrics = self.metrics.get_latest_metrics()
                            current_metrics.update(data)
                            
                            # Check for early stopping
                            if (config.early_stopping_patience and 
                                self._should_stop_early(data["val_loss"], config)):
                                console.print("[yellow]Early stopping triggered[/yellow]")
                                process.terminate()
                                break
                        
                        elif msg_type == "output" and config.verbose:
                            # Optionally display raw output
                            pass
                            
                    except:
                        continue
            
            # Wait for process completion
            process.wait()
            
            if process.returncode != 0:
                raise RuntimeError("Training process failed")
            
            return {
                "status": "completed",
                "final_iteration": self.metrics.iteration[-1] if self.metrics.iteration else 0,
                "best_val_loss": self.best_val_loss,
                "peak_memory_gb": self.peak_memory_gb
            }
            
        except Exception as e:
            if 'process' in locals():
                process.terminate()
            raise e
    
    def _get_current_lr(self, iteration: int, config: TrainingConfig) -> float:
        """Get current learning rate based on schedule."""
        if self.lr_scheduler:
            return self.lr_scheduler(iteration)
        else:
            return config.learning_rate
    
    def _should_stop_early(self, val_loss: float, config: TrainingConfig) -> bool:
        """Check if training should stop early due to lack of improvement."""
        if not config.early_stopping_patience:
            return False
        
        if val_loss < self.best_val_loss:
            self.best_val_loss = val_loss
            self.patience_counter = 0
            return False
        else:
            self.patience_counter += 1
            return self.patience_counter >= config.early_stopping_patience
    
    def _run_full_training(self, config: TrainingConfig, console: Console) -> Dict[str, Any]:
        """
        Run full fine-tuning (all parameters).
        
        This is more memory intensive than LoRA but can achieve better
        results for domain adaptation where the base model knowledge
        is significantly different from the target domain.
        """
        console.print("[red]Full fine-tuning not yet implemented[/red]")
        console.print("Use LoRA training for now - it achieves comparable results with much lower memory usage")
        raise NotImplementedError("Full fine-tuning implementation coming soon")
    
    def _finalize_training(
        self, 
        config: TrainingConfig, 
        console: Console, 
        training_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Finalize training: save metrics, validate output, create summary.
        
        This phase ensures we have a complete record of what happened
        during training and validates that the output model works correctly.
        """
        console.print("[blue]Finalizing training...[/blue]")
        
        output_path = Path(config.output_path)
        
        # Save training metrics
        metrics_file = output_path / "training_metrics.json"
        self.metrics.save_to_file(metrics_file)
        console.print(f"[green]✓ Metrics saved to {metrics_file}[/green]")
        
        # Save training configuration
        config_file = output_path / "training_config.json"
        with open(config_file, 'w') as f:
            json.dump(asdict(config), f, indent=2)
        
        # Validate output model
        if self._validate_output_model(output_path):
            console.print("[green]✓ Output model validation passed[/green]")
        else:
            console.print("[yellow]⚠ Output model validation failed[/yellow]")
        
        # Generate training summary
        summary = self._generate_training_summary(config, training_results)
        
        summary_file = output_path / "training_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Display summary to user
        self._display_training_summary(summary, console)
        
        return summary
    
    def _validate_output_model(self, output_path: Path) -> bool:
        """Validate that the output model can be loaded and used."""
        try:
            # Check for required files
            if not (output_path / "adapters.safetensors").exists():
                return False
            
            if not (output_path / "adapter_config.json").exists():
                return False
            
            # Try loading the adapter (basic test)
            from mlx_lm import load
            model, tokenizer = load(str(output_path.parent), adapter_path=str(output_path))
            
            # Quick generation test
            response = generate(
                model, tokenizer,
                prompt="Test prompt",
                max_tokens=5,
                verbose=False
            )
            
            return len(response) > 0
            
        except Exception:
            return False
    
    def _generate_training_summary(
        self, 
        config: TrainingConfig, 
        training_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive training summary."""
        convergence_metrics = self.metrics.get_convergence_metrics()
        latest_metrics = self.metrics.get_latest_metrics()
        
        summary = {
            "training_config": asdict(config),
            "training_results": training_results,
            "final_metrics": latest_metrics,
            "convergence_analysis": convergence_metrics,
            "resource_usage": {
                "peak_memory_gb": self.peak_memory_gb,
                "total_training_time": latest_metrics.get("elapsed_time", 0),
                "avg_tokens_per_second": sum(self.metrics.tokens_per_second) / len(self.metrics.tokens_per_second) if self.metrics.tokens_per_second else 0
            },
            "recommendations": self._generate_recommendations(convergence_metrics, config)
        }
        
        return summary
    
    def _generate_recommendations(
        self, 
        convergence_metrics: Dict[str, Any], 
        config: TrainingConfig
    ) -> List[str]:
        """Generate recommendations for future training runs."""
        recommendations = []
        
        # Learning rate recommendations
        if convergence_metrics.get("loss_volatility", 0) > 0.1:
            recommendations.append("Consider reducing learning rate for more stable training")
        
        if not convergence_metrics.get("is_converging", True):
            recommendations.append("Loss is not decreasing - try higher learning rate or more training steps")
        
        # Memory optimization recommendations  
        if self.peak_memory_gb > 50:  # Assuming 64GB system
            recommendations.append("Consider reducing batch size or using gradient accumulation to lower memory usage")
        
        # Training length recommendations
        if convergence_metrics.get("is_stable", False):
            recommendations.append("Training appears to have converged - could stop earlier in future runs")
        
        return recommendations
    
    def _display_training_summary(self, summary: Dict[str, Any], console: Console):
        """Display a formatted training summary."""
        final_metrics = summary.get("final_metrics", {})
        resource_usage = summary.get("resource_usage", {})
        
        # Create summary table
        table = Table(title="Training Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Final Iteration", str(final_metrics.get("iteration", "Unknown")))
        table.add_row("Final Loss", f"{final_metrics.get('train_loss', 0):.4f}")
        
        if final_metrics.get("val_loss"):
            table.add_row("Final Val Loss", f"{final_metrics.get('val_loss', 0):.4f}")
        
        table.add_row("Peak Memory", f"{resource_usage.get('peak_memory_gb', 0):.1f} GB")
        table.add_row("Training Time", f"{resource_usage.get('total_training_time', 0):.1f} seconds")
        table.add_row("Avg Speed", f"{resource_usage.get('avg_tokens_per_second', 0):.1f} tokens/sec")
        
        console.print(table)
        
        # Display recommendations
        recommendations = summary.get("recommendations", [])
        if recommendations:
            console.print("\n[blue]Recommendations for future training:[/blue]")
            for rec in recommendations:
                console.print(f"  • {rec}")
    
    def _handle_early_termination(self, config: TrainingConfig) -> Dict[str, Any]:
        """Handle early termination and save whatever progress was made."""
        return {
            "status": "interrupted",
            "iterations_completed": self.current_iteration,
            "metrics": self.metrics.get_latest_metrics(),
            "note": "Training was interrupted but partial progress may be saved"
        }
