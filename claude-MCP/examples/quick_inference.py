#!/usr/bin/env python3
"""
Quick Inference Script

Test a fine-tuned model with interactive prompts or batch processing.
Perfect for validating model quality and experimenting with different parameters.

Usage:
    python quick_inference.py ./fine-tuned-model
    python quick_inference.py ./fine-tuned-model --batch-file prompts.txt
    python quick_inference.py ./fine-tuned-model --interactive
"""

import argparse
from pathlib import Path
import json
import time
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table

from mlx_pipeline import InferenceEngine, InferenceConfig

console = Console()

def interactive_mode(engine: InferenceEngine):
    """Interactive chat mode with the model."""
    console.print(Panel(
        "[bold blue]Interactive Mode[/bold blue]\n"
        "Type your prompts and press Enter. Type 'quit' to exit.\n"
        "Commands: /temp <value>, /tokens <value>, /help",
        title="MLX Interactive Inference"
    ))
    
    # Default settings
    settings = {
        "temperature": 0.7,
        "max_tokens": 200,
        "top_p": 0.9
    }
    
    while True:
        try:
            user_input = Prompt.ask("\n[cyan]You[/cyan]")
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            # Handle commands
            if user_input.startswith('/'):
                if user_input.startswith('/temp '):
                    try:
                        settings['temperature'] = float(user_input.split(' ', 1)[1])
                        console.print(f"[green]Temperature set to {settings['temperature']}[/green]")
                    except ValueError:
                        console.print("[red]Invalid temperature value[/red]")
                    continue
                
                elif user_input.startswith('/tokens '):
                    try:
                        settings['max_tokens'] = int(user_input.split(' ', 1)[1])
                        console.print(f"[green]Max tokens set to {settings['max_tokens']}[/green]")
                    except ValueError:
                        console.print("[red]Invalid token count[/red]")
                    continue
                
                elif user_input == '/help':
                    console.print(Panel(
                        "Available commands:\n"
                        "• /temp <value> - Set temperature (0.0-2.0)\n"
                        "• /tokens <value> - Set max tokens\n"
                        "• /help - Show this help\n"
                        "• quit - Exit interactive mode"
                    ))
                    continue
                
                else:
                    console.print("[red]Unknown command. Type /help for available commands.[/red]")
                    continue
            
            # Generate response
            with console.status("[blue]Generating response..."):
                result = engine.generate_response(user_input, settings)
            
            if result["success"]:
                console.print(f"\n[green]Assistant:[/green] {result['response']}")
                
                # Show metadata
                metadata = result['metadata']
                console.print(
                    f"[dim]({metadata['tokens_generated']} tokens, "
                    f"{metadata['tokens_per_second']:.1f} tok/s, "
                    f"{metadata['inference_time']:.2f}s)[/dim]"
                )
            else:
                console.print(f"[red]Error: {result['error']}[/red]")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")
    
    console.print("[yellow]Goodbye![/yellow]")

def batch_mode(engine: InferenceEngine, batch_file: Path, output_file: Path = None):
    """Process a batch of prompts from a file."""
    try:
        with open(batch_file, 'r') as f:
            prompts = [line.strip() for line in f if line.strip()]
    except Exception as e:
        console.print(f"[red]Error reading batch file: {e}[/red]")
        return
    
    console.print(f"[blue]Processing {len(prompts)} prompts...[/blue]")
    
    results = []
    total_time = 0
    total_tokens = 0
    
    # Create results table
    table = Table(title="Batch Processing Results")
    table.add_column("Prompt", style="cyan", max_width=50)
    table.add_column("Response", style="green", max_width=60)
    table.add_column("Speed (tok/s)", style="yellow")
    table.add_column("Time (s)", style="magenta")
    
    for i, prompt in enumerate(prompts, 1):
        console.print(f"\n[blue]Processing {i}/{len(prompts)}:[/blue] {prompt[:100]}...")
        
        result = engine.generate_response(
            prompt,
            {"temperature": 0.7, "max_tokens": 150}
        )
        
        if result["success"]:
            response = result["response"]
            metadata = result["metadata"]
            
            total_time += metadata["inference_time"]
            total_tokens += metadata["tokens_generated"]
            
            # Add to table
            table.add_row(
                prompt[:50] + "..." if len(prompt) > 50 else prompt,
                response[:60] + "..." if len(response) > 60 else response,
                f"{metadata['tokens_per_second']:.1f}",
                f"{metadata['inference_time']:.2f}"
            )
            
            results.append({
                "prompt": prompt,
                "response": response,
                "metadata": metadata
            })
        else:
            console.print(f"[red]Error: {result['error']}[/red]")
            results.append({
                "prompt": prompt,
                "error": result["error"]
            })
    
    # Display results table
    console.print(table)
    
    # Summary statistics
    if total_tokens > 0:
        avg_speed = total_tokens / total_time
        console.print(f"\n[green]Batch Summary:[/green]")
        console.print(f"  Total prompts: {len(prompts)}")
        console.print(f"  Total time: {total_time:.2f}s")
        console.print(f"  Total tokens: {total_tokens}")
        console.print(f"  Average speed: {avg_speed:.1f} tokens/sec")
    
    # Save results if requested
    if output_file:
        batch_results = {
            "timestamp": time.time(),
            "total_prompts": len(prompts),
            "total_time": total_time,
            "total_tokens": total_tokens,
            "average_speed": avg_speed if total_tokens > 0 else 0,
            "results": results
        }
        
        with open(output_file, 'w') as f:
            json.dump(batch_results, f, indent=2)
        
        console.print(f"[green]Results saved to: {output_file}[/green]")

def single_prompt_mode(engine: InferenceEngine, prompt: str, config_overrides: dict = None):
    """Process a single prompt with detailed output."""
    console.print(Panel(f"[cyan]Prompt:[/cyan] {prompt}", title="Input"))
    
    with console.status("[blue]Generating response..."):
        result = engine.generate_response(prompt, config_overrides or {})
    
    if result["success"]:
        # Display response
        console.print(Panel(f"[green]{result['response']}[/green]", title="Response"))
        
        # Display detailed metadata
        metadata = result["metadata"]
        
        metadata_table = Table(title="Generation Metadata")
        metadata_table.add_column("Metric", style="cyan")
        metadata_table.add_column("Value", style="green")
        
        metadata_table.add_row("Tokens Generated", str(metadata["tokens_generated"]))
        metadata_table.add_row("Generation Time", f"{metadata['inference_time']:.3f}s")
        metadata_table.add_row("Speed", f"{metadata['tokens_per_second']:.1f} tokens/sec")
        metadata_table.add_row("Memory Used", f"{metadata['memory_used_gb']:.2f} GB")
        
        console.print(metadata_table)
        
        # Show configuration used
        config_used = metadata.get("config_used", {})
        if config_used:
            console.print(f"\n[dim]Configuration: temperature={config_used.get('temperature', 'N/A')}, "
                         f"max_tokens={config_used.get('max_tokens', 'N/A')}, "
                         f"top_p={config_used.get('top_p', 'N/A')}[/dim]")
    else:
        console.print(Panel(f"[red]Error: {result['error']}[/red]", title="Error"))

def main():
    parser = argparse.ArgumentParser(description="Quick inference testing for MLX models")
    parser.add_argument("model_path", type=Path, help="Path to the model")
    parser.add_argument("--adapter-path", type=Path, help="Path to adapter (for LoRA models)")
    parser.add_argument("--prompt", type=str, help="Single prompt to test")
    parser.add_argument("--batch-file", type=Path, help="File with prompts (one per line)")
    parser.add_argument("--output-file", type=Path, help="Save batch results to file")
    parser.add_argument("--interactive", action="store_true", help="Start interactive mode")
    parser.add_argument("--temperature", type=float, default=0.7, help="Generation temperature")
    parser.add_argument("--max-tokens", type=int, default=200, help="Maximum tokens to generate")
    parser.add_argument("--top-p", type=float, default=0.9, help="Top-p sampling parameter")
    
    args = parser.parse_args()
    
    # Validate model path
    if not args.model_path.exists():
        console.print(f"[red]Model path does not exist: {args.model_path}[/red]")
        return 1
    
    # Configuration
    config = InferenceConfig(
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p
    )
    
    # Initialize inference engine
    console.print("[blue]Loading model...[/blue]")
    engine = InferenceEngine(config)
    
    load_result = engine.load_model(args.model_path, args.adapter_path)
    
    if not load_result["success"]:
        console.print(f"[red]Failed to load model: {load_result['error']}[/red]")
        return 1
    
    console.print(f"[green]✓ Model loaded successfully[/green]")
    console.print(f"  Architecture: {load_result['model_info']['architecture']}")
    console.print(f"  Loading time: {load_result['loading_time']:.2f}s")
    console.print(f"  Memory usage: {load_result['memory_usage_gb']:.2f}GB")
    
    # Determine mode and execute
    config_overrides = {
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "top_p": args.top_p
    }
    
    try:
        if args.interactive:
            interactive_mode(engine)
        elif args.batch_file:
            batch_mode(engine, args.batch_file, args.output_file)
        elif args.prompt:
            single_prompt_mode(engine, args.prompt, config_overrides)
        else:
            # Default: show some example prompts
            console.print("[yellow]No specific mode selected. Running example prompts...[/yellow]")
            
            example_prompts = [
                "Hello! How are you doing today?",
                "Explain quantum computing in simple terms.",
                "Write a short story about a robot learning to paint.",
                "What are the main benefits of renewable energy?",
                "How does machine learning work?"
            ]
            
            for i, prompt in enumerate(example_prompts, 1):
                console.print(f"\n[bold blue]Example {i}/{len(example_prompts)}[/bold blue]")
                single_prompt_mode(engine, prompt, config_overrides)
                
                if i < len(example_prompts):
                    input("\nPress Enter to continue to next example...")
        
        return 0
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[red]Error during inference: {e}[/red]")
        return 1

if __name__ == "__main__":
    exit(main())
