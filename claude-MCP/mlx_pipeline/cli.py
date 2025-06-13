"""
Command Line Interface for MLX Complete Pipeline

This module provides the main entry points for all pipeline operations.
The CLI is built using Typer, which creates a user-friendly command-line interface
with automatic help generation and type validation.

Each command corresponds to a major step in the MLX pipeline:
1. setup - Environment validation and configuration
2. prepare-data - Data format conversion and validation  
3. download-model - Model acquisition and caching
4. finetune - Model training with MLX
5. quantize - Model optimization for deployment
6. serve - Inference server deployment
7. benchmark - Performance testing and validation

The design philosophy here is to make each step explicit and verifiable,
so you can debug issues at any stage of the pipeline.
"""

import typer
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .setup import EnvironmentSetup
from .data import DataProcessor
from .models import ModelManager
from .training import MLXTrainer
from .quantization import ModelQuantizer
from .inference import InferenceEngine
from .benchmark import BenchmarkRunner

app = typer.Typer(help="MLX Complete Pipeline - End-to-end LLM development on Apple Silicon")
console = Console()

@app.command()
def setup_environment(
    validate_metal: bool = typer.Option(True, help="Validate Metal GPU support"),
    check_memory: bool = typer.Option(True, help="Check available memory"),
    install_deps: bool = typer.Option(False, help="Install missing dependencies"),
) -> None:
    """
    Validate and configure the MLX environment.
    
    This command performs comprehensive environment validation to ensure
    your Mac is properly configured for MLX development. It checks:
    - Python version and architecture (ARM vs x86)
    - MLX installation and compatibility
    - Metal GPU support and memory
    - Required dependencies
    
    Think of this as your pre-flight checklist before starting any serious work.
    """
    console.print("[bold blue]Setting up MLX environment...[/bold blue]")
    
    setup = EnvironmentSetup()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Validating environment...", total=None)
        
        results = setup.validate_environment(
            validate_metal=validate_metal,
            check_memory=check_memory,
            install_deps=install_deps
        )
        
        progress.update(task, completed=True)
    
    # Display results in a nice table
    table = Table(title="Environment Validation Results")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="yellow")
    
    for component, status in results.items():
        table.add_row(
            component,
            "✓ Pass" if status["passed"] else "✗ Fail",
            status.get("details", "")
        )
    
    console.print(table)

@app.command()
def prepare_data(
    input_path: Path = typer.Argument(..., help="Input data file or directory"),
    output_path: Path = typer.Argument(..., help="Output directory for processed data"),
    format_type: str = typer.Option("chat", help="Data format: chat, completions, or text"),
    split_ratio: float = typer.Option(0.8, help="Train/validation split ratio"),
    validate_output: bool = typer.Option(True, help="Validate processed data"),
) -> None:
    """
    Prepare and validate training data for MLX fine-tuning.
    
    This command handles the often-tricky process of converting various data formats
    into the specific JSONL format that MLX expects. Data preparation is crucial
    because small formatting errors can cause silent failures during training.
    
    The processor can handle multiple input formats and automatically converts them
    to MLX-compatible JSONL with proper validation and error reporting.
    """
    console.print(f"[bold blue]Preparing data from {input_path}...[/bold blue]")
    
    processor = DataProcessor()
    
    try:
        # Process the data with progress tracking
        with Progress() as progress:
            task = progress.add_task("Processing data...", total=100)
            
            results = processor.process_data(
                input_path=input_path,
                output_path=output_path,
                format_type=format_type,
                split_ratio=split_ratio,
                progress_callback=lambda p: progress.update(task, completed=p)
            )
        
        console.print(f"[green]✓ Successfully processed {results['total_examples']} examples[/green]")
        console.print(f"  - Training: {results['train_examples']} examples")
        console.print(f"  - Validation: {results['valid_examples']} examples")
        
        if validate_output:
            console.print("[blue]Validating processed data...[/blue]")
            validation_results = processor.validate_data(output_path)
            
            if validation_results["valid"]:
                console.print("[green]✓ Data validation passed[/green]")
            else:
                console.print("[red]✗ Data validation failed[/red]")
                for issue in validation_results["issues"]:
                    console.print(f"  - {issue}")
                
    except Exception as e:
        console.print(f"[red]Error processing data: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def download_model(
    model_id: str = typer.Argument(..., help="Model identifier (e.g., 'mlx-community/Mistral-7B-Instruct-v0.3-4bit')"),
    output_dir: Optional[Path] = typer.Option(None, help="Download directory (default: ./models)"),
    quantization: str = typer.Option("4bit", help="Quantization level: 2bit, 4bit, 8bit, or none"),
    validate_model: bool = typer.Option(True, help="Validate model after download"),
) -> None:
    """
    Download and prepare models for MLX fine-tuning.
    
    This command handles the complexity of model acquisition, including:
    - Finding the right model format for MLX
    - Managing quantization options
    - Validating model compatibility
    - Organizing model storage
    
    The model manager handles the differences between HuggingFace models that need
    conversion and pre-converted MLX models from the community.
    """
    console.print(f"[bold blue]Downloading model: {model_id}[/bold blue]")
    
    manager = ModelManager(cache_dir=output_dir or Path("./models"))
    
    try:
        with Progress() as progress:
            task = progress.add_task("Downloading...", total=100)
            
            model_path = manager.download_model(
                model_id=model_id,
                quantization=quantization,
                progress_callback=lambda p: progress.update(task, completed=p)
            )
        
        console.print(f"[green]✓ Model downloaded to: {model_path}[/green]")
        
        if validate_model:
            console.print("[blue]Validating model...[/blue]")
            validation = manager.validate_model(model_path)
            
            if validation["valid"]:
                console.print("[green]✓ Model validation passed[/green]")
                console.print(f"  - Architecture: {validation['architecture']}")
                console.print(f"  - Parameters: {validation['parameters']}")
                console.print(f"  - Memory estimate: {validation['memory_gb']:.1f} GB")
            else:
                console.print("[red]✗ Model validation failed[/red]")
                for issue in validation["issues"]:
                    console.print(f"  - {issue}")
                    
    except Exception as e:
        console.print(f"[red]Error downloading model: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def finetune(
    model_path: Path = typer.Argument(..., help="Path to base model"),
    data_path: Path = typer.Argument(..., help="Path to training data directory"),
    output_path: Path = typer.Argument(..., help="Output path for fine-tuned model"),
    lora_rank: int = typer.Option(8, help="LoRA rank (higher = more capacity)"),
    learning_rate: float = typer.Option(1e-4, help="Learning rate for training"),
    batch_size: int = typer.Option(4, help="Training batch size"),
    max_iters: int = typer.Option(1000, help="Maximum training iterations"),
    save_every: int = typer.Option(100, help="Save checkpoint every N iterations"),
    eval_every: int = typer.Option(50, help="Evaluate every N iterations"),
) -> None:
    """
    Fine-tune models using MLX with LoRA or full fine-tuning.
    
    This is where the magic happens - taking a general model and teaching it
    your specific domain knowledge. The trainer handles the complexity of:
    - Memory management for your Mac's capabilities  
    - Learning rate scheduling and optimization
    - Progress monitoring and checkpointing
    - Validation and overfitting detection
    
    LoRA (Low-Rank Adaptation) is the default approach because it's efficient
    and works well on consumer hardware like your Mac Studio.
    """
    console.print("[bold blue]Starting fine-tuning...[/bold blue]")
    
    trainer = MLXTrainer()
    
    try:
        # Configure training parameters
        config = {
            "model_path": model_path,
            "data_path": data_path,
            "output_path": output_path,
            "lora_rank": lora_rank,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "max_iters": max_iters,
            "save_every": save_every,
            "eval_every": eval_every,
        }
        
        # Start training with progress monitoring
        trainer.train(config, console=console)
        
        console.print(f"[green]✓ Fine-tuning completed! Model saved to: {output_path}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error during fine-tuning: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def quantize(
    model_path: Path = typer.Argument(..., help="Path to model to quantize"),
    output_path: Path = typer.Argument(..., help="Output path for quantized model"),
    bits: int = typer.Option(4, help="Quantization bits: 2, 4, or 8"),
    validate_quality: bool = typer.Option(True, help="Test quality after quantization"),
) -> None:
    """
    Quantize models for efficient deployment.
    
    Quantization reduces model size and memory usage by representing weights
    with fewer bits. This is essential for deployment, especially when you
    want to run multiple models or have larger context windows.
    
    The quantizer tests quality loss to ensure the compressed model still
    performs well for your use case.
    """
    console.print(f"[bold blue]Quantizing model to {bits}-bit...[/bold blue]")
    
    quantizer = ModelQuantizer()
    
    try:
        results = quantizer.quantize_model(
            model_path=model_path,
            output_path=output_path,
            bits=bits,
            validate_quality=validate_quality
        )
        
        console.print(f"[green]✓ Model quantized successfully![/green]")
        console.print(f"  - Original size: {results['original_size_gb']:.1f} GB")
        console.print(f"  - Quantized size: {results['quantized_size_gb']:.1f} GB")
        console.print(f"  - Compression ratio: {results['compression_ratio']:.1f}x")
        
        if validate_quality:
            console.print(f"  - Quality score: {results['quality_score']:.3f}")
            
    except Exception as e:
        console.print(f"[red]Error during quantization: {e}[/red]")
        raise typer.Exit(1)

@app.command()  
def serve(
    model_path: Path = typer.Argument(..., help="Path to model to serve"),
    host: str = typer.Option("localhost", help="Server host"),
    port: int = typer.Option(8080, help="Server port"),
    max_concurrent: int = typer.Option(4, help="Maximum concurrent requests"),
    enable_metrics: bool = typer.Option(True, help="Enable Prometheus metrics"),
) -> None:
    """
    Start an inference server for your fine-tuned model.
    
    This creates a production-ready FastAPI server with OpenAI-compatible endpoints.
    The server handles request queuing, memory management, and monitoring to ensure
    reliable performance even under load.
    """
    console.print(f"[bold blue]Starting inference server on {host}:{port}...[/bold blue]")
    
    engine = InferenceEngine()
    
    try:
        engine.start_server(
            model_path=model_path,
            host=host,
            port=port,
            max_concurrent=max_concurrent,
            enable_metrics=enable_metrics,
            console=console
        )
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def benchmark(
    model_path: Path = typer.Argument(..., help="Path to model to benchmark"),
    test_prompts: Optional[Path] = typer.Option(None, help="File with test prompts"),
    output_file: Optional[Path] = typer.Option(None, help="Save results to file"),
) -> None:
    """
    Benchmark model performance and quality.
    
    This comprehensive benchmarking suite tests:
    - Inference speed and throughput
    - Memory usage patterns  
    - Response quality metrics
    - Hardware utilization efficiency
    
    Understanding these metrics helps you optimize deployment configurations
    and validate that your fine-tuned model meets performance requirements.
    """
    console.print("[bold blue]Running benchmark suite...[/bold blue]")
    
    runner = BenchmarkRunner()
    
    try:
        results = runner.run_benchmark(
            model_path=model_path,
            test_prompts=test_prompts,
            console=console
        )
        
        # Display results
        table = Table(title="Benchmark Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        for metric, value in results.items():
            table.add_row(metric, str(value))
        
        console.print(table)
        
        if output_file:
            runner.save_results(results, output_file)
            console.print(f"[green]Results saved to: {output_file}[/green]")
            
    except Exception as e:
        console.print(f"[red]Benchmark error: {e}[/red]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
