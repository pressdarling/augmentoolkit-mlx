#!/usr/bin/env python3
"""
Complete MLX Pipeline Example

This script demonstrates the complete workflow from raw data to deployed model.
It serves as both a practical example and a template for your own projects.

Usage:
    python complete_workflow.py --input-data data.csv --domain-name "customer-support"
"""

import argparse
from pathlib import Path
import json
import time
from rich.console import Console
from rich.panel import Panel

from mlx_pipeline import (
    EnvironmentSetup, DataProcessor, ModelManager, 
    MLXTrainer, TrainingConfig, ModelQuantizer, 
    InferenceEngine, BenchmarkRunner
)

console = Console()

def main():
    parser = argparse.ArgumentParser(description="Complete MLX fine-tuning workflow")
    parser.add_argument("--input-data", type=Path, required=True, help="Input data file")
    parser.add_argument("--domain-name", type=str, required=True, help="Name for your domain/use case")
    parser.add_argument("--base-model", type=str, default="mlx-community/Mistral-7B-Instruct-v0.3-4bit", help="Base model to fine-tune")
    parser.add_argument("--output-dir", type=Path, default="./workflow_output", help="Output directory")
    parser.add_argument("--max-iters", type=int, default=500, help="Training iterations")
    parser.add_argument("--skip-benchmark", action="store_true", help="Skip benchmarking step")
    parser.add_argument("--serve-model", action="store_true", help="Start inference server after completion")
    
    args = parser.parse_args()
    
    # Setup output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(Panel(
        f"[bold blue]MLX Complete Workflow[/bold blue]\n"
        f"Domain: {args.domain_name}\n"
        f"Input: {args.input_data}\n"
        f"Base Model: {args.base_model}\n"
        f"Output: {args.output_dir}",
        title="Workflow Configuration"
    ))
    
    workflow_log = []
    
    try:
        # Step 1: Environment Validation
        console.print("\n[bold cyan]Step 1: Environment Validation[/bold cyan]")
        setup = EnvironmentSetup()
        env_results = setup.validate_environment(validate_metal=True, check_memory=True)
        
        # Check for critical issues
        critical_issues = [
            name for name, result in env_results.items() 
            if not result.get("passed", False)
        ]
        
        if critical_issues:
            console.print(f"[red]Critical environment issues found: {critical_issues}[/red]")
            console.print("[yellow]Run 'mlx-setup' to diagnose and fix issues[/yellow]")
            return 1
        
        console.print("[green]✓ Environment validation passed[/green]")
        workflow_log.append({"step": "environment", "status": "success", "issues": len(critical_issues)})
        
        # Step 2: Data Preparation
        console.print("\n[bold cyan]Step 2: Data Preparation[/bold cyan]")
        processor = DataProcessor()
        
        data_output = args.output_dir / "processed_data"
        data_results = processor.process_data(
            input_path=args.input_data,
            output_path=data_output,
            format_type="auto",  # Auto-detect format
            split_ratio=0.8,
            validate_output=True
        )
        
        if not data_results["validation_passed"]:
            console.print("[red]Data validation failed - check your input format[/red]")
            return 1
        
        console.print(f"[green]✓ Processed {data_results['total_examples']} examples[/green]")
        console.print(f"  Training: {data_results['train_examples']}, Validation: {data_results['valid_examples']}")
        workflow_log.append({"step": "data_prep", "status": "success", "examples": data_results['total_examples']})
        
        # Step 3: Model Download
        console.print("\n[bold cyan]Step 3: Model Acquisition[/bold cyan]")
        manager = ModelManager(cache_dir=args.output_dir / "models")
        
        model_path = manager.download_model(
            model_id=args.base_model,
            quantization="4bit"
        )
        
        # Validate model
        validation = manager.validate_model(model_path)
        if not validation["valid"]:
            console.print(f"[red]Model validation failed: {validation['issues']}[/red]")
            return 1
        
        console.print(f"[green]✓ Model ready: {validation['info']['architecture']}[/green]")
        console.print(f"  Memory estimate: {validation['info']['memory_gb']:.1f}GB")
        workflow_log.append({"step": "model_download", "status": "success", "model_path": str(model_path)})
        
        # Step 4: Fine-tuning
        console.print("\n[bold cyan]Step 4: Fine-tuning[/bold cyan]")
        
        # Configure training
        training_config = TrainingConfig(
            model_path=str(model_path),
            data_path=str(data_output),
            output_path=str(args.output_dir / f"fine_tuned_{args.domain_name}"),
            learning_rate=1e-4,
            lora_rank=8,
            max_iters=args.max_iters,
            batch_size=4,
            eval_every=50,
            save_every=100
        )
        
        trainer = MLXTrainer()
        training_results = trainer.train(training_config, console=console)
        
        if training_results["status"] != "completed":
            console.print(f"[red]Training failed or was interrupted[/red]")
            return 1
        
        console.print(f"[green]✓ Fine-tuning completed in {training_results['final_iteration']} iterations[/green]")
        workflow_log.append({"step": "training", "status": "success", "iterations": training_results['final_iteration']})
        
        # Step 5: Quantization (Optional but Recommended)
        console.print("\n[bold cyan]Step 5: Model Quantization[/bold cyan]")
        
        quantizer = ModelQuantizer()
        quantized_path = args.output_dir / f"quantized_{args.domain_name}"
        
        quant_results = quantizer.quantize_model(
            model_path=Path(training_config.output_path),
            output_path=quantized_path,
            bits=4,
            validate_quality=True
        )
        
        if not quant_results["quantization_successful"]:
            console.print("[yellow]Quantization failed - using original fine-tuned model[/yellow]")
            final_model_path = Path(training_config.output_path)
        else:
            console.print(f"[green]✓ Model quantized: {quant_results['compression_ratio']:.1f}x compression[/green]")
            final_model_path = quantized_path
        
        workflow_log.append({
            "step": "quantization", 
            "status": "success" if quant_results["quantization_successful"] else "skipped",
            "compression_ratio": quant_results.get("compression_ratio", 1.0)
        })
        
        # Step 6: Benchmarking (Optional)
        if not args.skip_benchmark:
            console.print("\n[bold cyan]Step 6: Performance Benchmarking[/bold cyan]")
            
            runner = BenchmarkRunner()
            benchmark_results = runner.run_benchmark(
                model_path=final_model_path,
                console=console
            )
            
            # Save benchmark results
            benchmark_file = args.output_dir / f"benchmark_{args.domain_name}.json"
            runner.save_results(benchmark_results, benchmark_file)
            
            console.print(f"[green]✓ Benchmark completed - results saved to {benchmark_file}[/green]")
            workflow_log.append({"step": "benchmark", "status": "success", "overall_score": benchmark_results["summary"]["overall_score"]})
        
        # Step 7: Quick Inference Test
        console.print("\n[bold cyan]Step 7: Inference Testing[/bold cyan]")
        
        engine = InferenceEngine()
        load_result = engine.load_model(final_model_path)
        
        if not load_result["success"]:
            console.print(f"[red]Failed to load model for inference: {load_result['error']}[/red]")
            return 1
        
        # Test generation
        test_prompts = [
            f"You are an expert in {args.domain_name}. How can you help users?",
            f"What are the key principles of {args.domain_name}?",
            "Explain your expertise and capabilities."
        ]
        
        for i, prompt in enumerate(test_prompts, 1):
            console.print(f"\n[blue]Test {i}:[/blue] {prompt}")
            result = engine.generate_response(prompt, {"max_tokens": 150, "temperature": 0.7})
            
            if result["success"]:
                console.print(f"[green]Response:[/green] {result['response']}")
                console.print(f"[dim]Speed: {result['metadata']['tokens_per_second']:.1f} tokens/sec[/dim]")
            else:
                console.print(f"[red]Error: {result['error']}[/red]")
        
        workflow_log.append({"step": "inference_test", "status": "success"})
        
        # Save workflow summary
        summary = {
            "domain_name": args.domain_name,
            "timestamp": time.time(),
            "final_model_path": str(final_model_path),
            "workflow_log": workflow_log,
            "model_info": {
                "base_model": args.base_model,
                "training_examples": data_results['total_examples'],
                "training_iterations": training_results['final_iteration'],
                "quantized": quant_results["quantization_successful"]
            }
        }
        
        summary_file = args.output_dir / f"workflow_summary_{args.domain_name}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Final success message
        console.print(Panel(
            f"[bold green]Workflow Completed Successfully![/bold green]\n\n"
            f"Your fine-tuned {args.domain_name} model is ready:\n"
            f"📍 Location: {final_model_path}\n"
            f"📊 Summary: {summary_file}\n"
            f"🔍 Examples processed: {data_results['total_examples']}\n"
            f"🎯 Training iterations: {training_results['final_iteration']}\n\n"
            f"[blue]Next steps:[/blue]\n"
            f"• Test more prompts: python examples/quick_inference.py {final_model_path}\n"
            f"• Start server: mlx-serve {final_model_path} --port 8080\n"
            f"• View benchmark: cat {args.output_dir}/benchmark_{args.domain_name}.json",
            title="🎉 Success!"
        ))
        
        # Optional: Start inference server
        if args.serve_model:
            console.print("\n[blue]Starting inference server...[/blue]")
            engine.start_server(
                model_path=final_model_path,
                host="localhost",
                port=8080,
                console=console
            )
        
        return 0
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Workflow interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"\n[red]Workflow failed: {e}[/red]")
        # Save partial results for debugging
        error_log = args.output_dir / "error_log.json"
        with open(error_log, 'w') as f:
            json.dump({
                "error": str(e),
                "completed_steps": workflow_log,
                "timestamp": time.time()
            }, f, indent=2)
        console.print(f"[dim]Error details saved to: {error_log}[/dim]")
        raise


if __name__ == "__main__":
    exit(main())
