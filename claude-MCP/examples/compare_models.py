#!/usr/bin/env python3
"""
Model Comparison Benchmark

Compare multiple models across various metrics to help choose the best option
for your specific use case and hardware constraints.

Usage:
    python compare_models.py model1 model2 model3 --output comparison_results.json
    python compare_models.py ./models/* --test-prompts custom_prompts.txt
"""

import argparse
from pathlib import Path
import json
import time
from typing import List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from mlx_pipeline import BenchmarkRunner, BenchmarkConfig, InferenceEngine

console = Console()

def load_test_prompts(prompts_file: Path) -> List[str]:
    """Load custom test prompts from file."""
    try:
        with open(prompts_file, 'r') as f:
            prompts = [line.strip() for line in f if line.strip()]
        return prompts
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load prompts file: {e}[/yellow]")
        return [
            "Explain the concept of artificial intelligence.",
            "What are the benefits of renewable energy?", 
            "Describe how neural networks learn.",
            "Write a short explanation of quantum computing.",
            "How does photosynthesis work in plants?"
        ]

def quick_response_test(model_path: Path, test_prompts: List[str]) -> Dict[str, Any]:
    """Perform a quick response quality test on a model."""
    engine = InferenceEngine()
    
    try:
        load_result = engine.load_model(model_path)
        if not load_result["success"]:
            return {"error": f"Failed to load model: {load_result['error']}"}
        
        responses = []
        total_time = 0
        total_tokens = 0
        
        for prompt in test_prompts[:3]:  # Test with first 3 prompts
            result = engine.generate_response(
                prompt, 
                {"max_tokens": 100, "temperature": 0.7}
            )
            
            if result["success"]:
                responses.append({
                    "prompt": prompt,
                    "response": result["response"],
                    "tokens": result["metadata"]["tokens_generated"],
                    "time": result["metadata"]["inference_time"],
                    "speed": result["metadata"]["tokens_per_second"]
                })
                total_time += result["metadata"]["inference_time"]
                total_tokens += result["metadata"]["tokens_generated"]
        
        avg_speed = total_tokens / total_time if total_time > 0 else 0
        avg_response_length = sum(len(r["response"]) for r in responses) / len(responses) if responses else 0
        
        return {
            "responses": responses,
            "avg_speed": avg_speed,
            "avg_response_length": avg_response_length,
            "total_time": total_time,
            "model_info": load_result.get("model_info", {}),
            "memory_usage": load_result.get("memory_usage_gb", 0)
        }
        
    except Exception as e:
        return {"error": str(e)}

def compare_models(model_paths: List[Path], test_prompts: List[str], full_benchmark: bool = False) -> Dict[str, Any]:
    """Compare multiple models across various metrics."""
    
    results = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        
        main_task = progress.add_task("Comparing models...", total=len(model_paths))
        
        for model_path in model_paths:
            model_name = model_path.name
            progress.update(main_task, description=f"Testing {model_name}...")
            
            if full_benchmark:
                # Run comprehensive benchmark
                try:
                    runner = BenchmarkRunner()
                    config = BenchmarkConfig(
                        speed_test=True,
                        memory_test=True,
                        quality_test=True,
                        stress_test=False,  # Skip stress test for comparison
                        context_test=False  # Skip context test for speed
                    )
                    
                    benchmark_results = runner.run_benchmark(
                        model_path=model_path,
                        config=config
                    )
                    
                    results[model_name] = {
                        "type": "full_benchmark",
                        "results": benchmark_results,
                        "model_path": str(model_path)
                    }
                    
                except Exception as e:
                    results[model_name] = {
                        "type": "error",
                        "error": str(e),
                        "model_path": str(model_path)
                    }
            else:
                # Run quick response test
                quick_results = quick_response_test(model_path, test_prompts)
                results[model_name] = {
                    "type": "quick_test",
                    "results": quick_results,
                    "model_path": str(model_path)
                }
            
            progress.advance(main_task)
    
    return results

def display_comparison_table(results: Dict[str, Any]):
    """Display comparison results in a formatted table."""
    
    table = Table(title="Model Comparison Results")
    table.add_column("Model", style="cyan")
    table.add_column("Speed (tok/s)", style="green")
    table.add_column("Memory (GB)", style="yellow")
    table.add_column("Response Quality", style="blue")
    table.add_column("Status", style="magenta")
    
    for model_name, model_data in results.items():
        if model_data["type"] == "error":
            table.add_row(
                model_name,
                "Error",
                "Error", 
                "Error",
                f"❌ {model_data['error'][:50]}..."
            )
            continue
        
        model_results = model_data["results"]
        
        if model_data["type"] == "full_benchmark":
            # Extract metrics from full benchmark
            summary = model_results.get("summary", {})
            key_metrics = summary.get("key_metrics", {})
            
            speed = key_metrics.get("tokens_per_second", 0)
            memory = key_metrics.get("peak_memory_gb", 0)
            quality = key_metrics.get("quality_score", 0)
            overall_score = summary.get("overall_score", 0)
            
            table.add_row(
                model_name,
                f"{speed:.1f}",
                f"{memory:.1f}",
                f"{quality:.2f}",
                f"✅ Score: {overall_score:.1f}/100"
            )
            
        elif model_data["type"] == "quick_test":
            # Extract metrics from quick test
            if "error" in model_results:
                table.add_row(
                    model_name,
                    "Error",
                    "Error",
                    "Error", 
                    f"❌ {model_results['error'][:50]}..."
                )
            else:
                speed = model_results.get("avg_speed", 0)
                memory = model_results.get("memory_usage", 0)
                avg_length = model_results.get("avg_response_length", 0)
                
                # Simple quality heuristic based on response length and speed
                quality_score = min(1.0, avg_length / 200) * 0.7 + min(1.0, speed / 50) * 0.3
                
                table.add_row(
                    model_name,
                    f"{speed:.1f}",
                    f"{memory:.1f}",
                    f"{quality_score:.2f}",
                    "✅ Quick test"
                )
    
    console.print(table)

def display_detailed_comparison(results: Dict[str, Any]):
    """Display detailed comparison with recommendations."""
    
    # Find best models by different criteria
    best_speed = None
    best_memory = None
    best_quality = None
    best_overall = None
    
    best_speed_val = 0
    best_memory_val = float('inf')
    best_quality_val = 0
    best_overall_val = 0
    
    for model_name, model_data in results.items():
        if model_data["type"] == "error":
            continue
        
        model_results = model_data["results"]
        
        if model_data["type"] == "full_benchmark":
            summary = model_results.get("summary", {})
            key_metrics = summary.get("key_metrics", {})
            
            speed = key_metrics.get("tokens_per_second", 0)
            memory = key_metrics.get("peak_memory_gb", float('inf'))
            quality = key_metrics.get("quality_score", 0)
            overall = summary.get("overall_score", 0)
            
        elif model_data["type"] == "quick_test" and "error" not in model_results:
            speed = model_results.get("avg_speed", 0)
            memory = model_results.get("memory_usage", float('inf'))
            avg_length = model_results.get("avg_response_length", 0)
            quality = min(1.0, avg_length / 200) * 0.7 + min(1.0, speed / 50) * 0.3
            overall = speed * 0.4 + (100 - memory) * 0.3 + quality * 100 * 0.3
        else:
            continue
        
        # Update bests
        if speed > best_speed_val:
            best_speed = model_name
            best_speed_val = speed
        
        if memory < best_memory_val:
            best_memory = model_name
            best_memory_val = memory
        
        if quality > best_quality_val:
            best_quality = model_name
            best_quality_val = quality
        
        if overall > best_overall_val:
            best_overall = model_name
            best_overall_val = overall
    
    # Display recommendations
    recommendations = []
    
    if best_speed:
        recommendations.append(f"🚀 **Fastest**: {best_speed} ({best_speed_val:.1f} tokens/sec)")
    
    if best_memory:
        recommendations.append(f"💾 **Most Memory Efficient**: {best_memory} ({best_memory_val:.1f} GB)")
    
    if best_quality:
        recommendations.append(f"⭐ **Best Quality**: {best_quality} (score: {best_quality_val:.2f})")
    
    if best_overall:
        recommendations.append(f"🏆 **Best Overall**: {best_overall} (score: {best_overall_val:.1f})")
    
    if recommendations:
        console.print(Panel(
            "\n".join(recommendations),
            title="🎯 Recommendations",
            border_style="green"
        ))

def generate_comparison_report(results: Dict[str, Any], output_file: Path):
    """Generate a detailed comparison report."""
    
    report = {
        "timestamp": time.time(),
        "comparison_results": results,
        "summary": {
            "total_models": len(results),
            "successful_tests": len([r for r in results.values() if r["type"] != "error"]),
            "failed_tests": len([r for r in results.values() if r["type"] == "error"])
        }
    }
    
    # Add recommendations to report
    recommendations = []
    best_metrics = {}
    
    for model_name, model_data in results.items():
        if model_data["type"] == "error":
            continue
        
        model_results = model_data["results"]
        
        if model_data["type"] == "full_benchmark":
            summary = model_results.get("summary", {})
            key_metrics = summary.get("key_metrics", {})
            best_metrics[model_name] = key_metrics
        
        elif model_data["type"] == "quick_test" and "error" not in model_results:
            best_metrics[model_name] = {
                "tokens_per_second": model_results.get("avg_speed", 0),
                "peak_memory_gb": model_results.get("memory_usage", 0),
                "avg_response_length": model_results.get("avg_response_length", 0)
            }
    
    report["best_metrics_by_model"] = best_metrics
    
    # Save report
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    return report

def main():
    parser = argparse.ArgumentParser(description="Compare multiple MLX models")
    parser.add_argument("models", nargs="+", type=Path, help="Paths to models to compare")
    parser.add_argument("--output", type=Path, help="Save detailed results to JSON file")
    parser.add_argument("--test-prompts", type=Path, help="File with custom test prompts")
    parser.add_argument("--full-benchmark", action="store_true", help="Run full benchmark (slower but more detailed)")
    parser.add_argument("--quick-only", action="store_true", help="Only run quick response tests")
    
    args = parser.parse_args()
    
    # Validate model paths
    valid_models = []
    for model_path in args.models:
        if model_path.exists():
            valid_models.append(model_path)
        else:
            console.print(f"[yellow]Warning: Model path does not exist: {model_path}[/yellow]")
    
    if not valid_models:
        console.print("[red]No valid model paths provided[/red]")
        return 1
    
    # Load test prompts
    test_prompts = []
    if args.test_prompts:
        test_prompts = load_test_prompts(args.test_prompts)
    else:
        test_prompts = load_test_prompts(Path("default"))  # Will use defaults
    
    console.print(Panel(
        f"[bold blue]Model Comparison[/bold blue]\n"
        f"Models: {len(valid_models)}\n"
        f"Test prompts: {len(test_prompts)}\n"
        f"Mode: {'Full benchmark' if args.full_benchmark else 'Quick test'}",
        title="Comparison Configuration"
    ))
    
    # Run comparison
    try:
        results = compare_models(
            valid_models, 
            test_prompts, 
            full_benchmark=args.full_benchmark and not args.quick_only
        )
        
        # Display results
        console.print("\n")
        display_comparison_table(results)
        console.print("\n")
        display_detailed_comparison(results)
        
        # Save detailed results if requested
        if args.output:
            report = generate_comparison_report(results, args.output)
            console.print(f"\n[green]Detailed results saved to: {args.output}[/green]")
        
        return 0
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Comparison interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"\n[red]Comparison failed: {e}[/red]")
        return 1

if __name__ == "__main__":
    exit(main())
