"""
Benchmarking and Performance Validation Module

Benchmarking is essential for understanding how your fine-tuned models perform
in real-world scenarios. This module provides comprehensive performance testing
across multiple dimensions: speed, quality, memory efficiency, and reliability.

The benchmark suite helps answer critical questions:
- How fast does my model generate responses?
- How much memory does it actually use under load?
- Is the quality consistent across different prompt types?
- How does performance degrade with longer contexts?
- What's the optimal configuration for my hardware?

The philosophy here is "measure everything that matters" - providing detailed
insights that help optimize both model configuration and deployment strategies.
"""

import time
import json
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import threading
import queue
import gc

try:
    import mlx.core as mx
    from mlx_lm import load, generate
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

import psutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live


@dataclass
class BenchmarkConfig:
    """
    Configuration for benchmark tests.
    
    This defines the scope and parameters of benchmark testing,
    allowing comprehensive evaluation whilst keeping test times reasonable.
    """
    # Test categories to run
    speed_test: bool = True
    memory_test: bool = True
    quality_test: bool = True
    stress_test: bool = True
    context_test: bool = True
    
    # Speed test parameters
    speed_test_prompts: int = 10
    speed_test_max_tokens: int = 100
    speed_test_temperatures: List[float] = None
    
    # Memory test parameters
    memory_test_batch_sizes: List[int] = None
    memory_test_sequence_lengths: List[int] = None
    
    # Quality test parameters
    quality_test_domains: List[str] = None
    quality_comparison_model: Optional[str] = None
    
    # Stress test parameters
    stress_test_duration: int = 300  # seconds
    stress_test_concurrent_requests: int = 4
    
    # Context test parameters
    context_test_lengths: List[int] = None
    
    def __post_init__(self):
        # Set defaults for list parameters
        if self.speed_test_temperatures is None:
            self.speed_test_temperatures = [0.1, 0.7, 1.0]
        
        if self.memory_test_batch_sizes is None:
            self.memory_test_batch_sizes = [1, 2, 4, 8]
        
        if self.memory_test_sequence_lengths is None:
            self.memory_test_sequence_lengths = [256, 512, 1024, 2048]
        
        if self.quality_test_domains is None:
            self.quality_test_domains = ["general", "reasoning", "creative"]
        
        if self.context_test_lengths is None:
            self.context_test_lengths = [100, 500, 1000, 2000, 4000]


class BenchmarkResults:
    """
    Comprehensive benchmark results with analysis capabilities.
    
    This class stores and analyzes benchmark data, providing insights
    into performance characteristics and optimization opportunities.
    """
    
    def __init__(self):
        self.results = {
            "metadata": {
                "timestamp": time.time(),
                "hardware_info": self._get_hardware_info(),
                "mlx_info": self._get_mlx_info()
            },
            "speed_test": {},
            "memory_test": {},
            "quality_test": {},
            "stress_test": {},
            "context_test": {}
        }
    
    def _get_hardware_info(self) -> Dict[str, Any]:
        """Collect hardware information for benchmark context."""
        memory = psutil.virtual_memory()
        cpu_info = {}
        
        try:
            import platform
            cpu_info = {
                "processor": platform.processor(),
                "machine": platform.machine(),
                "system": platform.system(),
                "cpu_count": psutil.cpu_count(),
            }
        except Exception:
            pass
        
        return {
            "total_memory_gb": memory.total / (1024**3),
            "available_memory_gb": memory.available / (1024**3),
            "cpu_info": cpu_info
        }
    
    def _get_mlx_info(self) -> Dict[str, Any]:
        """Collect MLX-specific information."""
        mlx_info = {}
        
        if MLX_AVAILABLE:
            try:
                mlx_info["metal_memory_gb"] = mx.metal.get_active_memory() / (1024**3)
                mlx_info["metal_available"] = True
            except Exception:
                mlx_info["metal_available"] = False
        else:
            mlx_info["mlx_available"] = False
        
        return mlx_info
    
    def add_speed_results(self, results: Dict[str, Any]):
        """Add speed test results."""
        self.results["speed_test"] = results
    
    def add_memory_results(self, results: Dict[str, Any]):
        """Add memory test results."""
        self.results["memory_test"] = results
    
    def add_quality_results(self, results: Dict[str, Any]):
        """Add quality test results."""
        self.results["quality_test"] = results
    
    def add_stress_results(self, results: Dict[str, Any]):
        """Add stress test results."""
        self.results["stress_test"] = results
    
    def add_context_results(self, results: Dict[str, Any]):
        """Add context length test results."""
        self.results["context_test"] = results
    
    def get_summary(self) -> Dict[str, Any]:
        """Generate a comprehensive summary of all benchmark results."""
        summary = {
            "overall_score": self._calculate_overall_score(),
            "key_metrics": self._extract_key_metrics(),
            "performance_class": self._classify_performance(),
            "recommendations": self._generate_recommendations(),
            "bottlenecks": self._identify_bottlenecks()
        }
        
        return summary
    
    def _calculate_overall_score(self) -> float:
        """Calculate an overall performance score (0-100)."""
        scores = []
        
        # Speed score (tokens per second)
        speed_data = self.results.get("speed_test", {})
        if "avg_tokens_per_second" in speed_data:
            # Normalize based on expected performance ranges
            tps = speed_data["avg_tokens_per_second"]
            speed_score = min(100, (tps / 50) * 100)  # 50 TPS = 100 score
            scores.append(speed_score)
        
        # Memory efficiency score
        memory_data = self.results.get("memory_test", {})
        if "memory_efficiency_score" in memory_data:
            scores.append(memory_data["memory_efficiency_score"])
        
        # Quality score
        quality_data = self.results.get("quality_test", {})
        if "overall_quality_score" in quality_data:
            scores.append(quality_data["overall_quality_score"] * 100)
        
        # Stress test score
        stress_data = self.results.get("stress_test", {})
        if "reliability_score" in stress_data:
            scores.append(stress_data["reliability_score"])
        
        return statistics.mean(scores) if scores else 0.0
    
    def _extract_key_metrics(self) -> Dict[str, Any]:
        """Extract the most important metrics for quick reference."""
        metrics = {}
        
        # Speed metrics
        speed_data = self.results.get("speed_test", {})
        if speed_data:
            metrics["tokens_per_second"] = speed_data.get("avg_tokens_per_second", 0)
            metrics["avg_latency_ms"] = speed_data.get("avg_latency_ms", 0)
        
        # Memory metrics
        memory_data = self.results.get("memory_test", {})
        if memory_data:
            metrics["peak_memory_gb"] = memory_data.get("peak_memory_gb", 0)
            metrics["memory_per_token_mb"] = memory_data.get("memory_per_token_mb", 0)
        
        # Quality metrics
        quality_data = self.results.get("quality_test", {})
        if quality_data:
            metrics["quality_score"] = quality_data.get("overall_quality_score", 0)
        
        # Stress metrics
        stress_data = self.results.get("stress_test", {})
        if stress_data:
            metrics["max_concurrent"] = stress_data.get("max_concurrent_handled", 0)
            metrics["error_rate"] = stress_data.get("error_rate", 0)
        
        return metrics
    
    def _classify_performance(self) -> str:
        """Classify overall performance into categories."""
        score = self._calculate_overall_score()
        
        if score >= 80:
            return "Excellent"
        elif score >= 60:
            return "Good"
        elif score >= 40:
            return "Fair"
        else:
            return "Poor"
    
    def _generate_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on results."""
        recommendations = []
        
        # Speed recommendations
        speed_data = self.results.get("speed_test", {})
        if speed_data.get("avg_tokens_per_second", 0) < 20:
            recommendations.append("Consider model quantization to improve speed")
        
        # Memory recommendations
        memory_data = self.results.get("memory_test", {})
        if memory_data.get("peak_memory_gb", 0) > 50:
            recommendations.append("High memory usage detected - consider smaller batch sizes")
        
        # Quality recommendations
        quality_data = self.results.get("quality_test", {})
        if quality_data.get("overall_quality_score", 1) < 0.7:
            recommendations.append("Quality scores below optimal - review fine-tuning data")
        
        # Context recommendations
        context_data = self.results.get("context_test", {})
        if context_data and context_data.get("performance_degradation", 0) > 0.5:
            recommendations.append("Significant performance degradation with long contexts")
        
        return recommendations
    
    def _identify_bottlenecks(self) -> List[str]:
        """Identify performance bottlenecks from test results."""
        bottlenecks = []
        
        # Check for memory bottlenecks
        memory_data = self.results.get("memory_test", {})
        if memory_data.get("memory_growth_rate", 0) > 0.1:
            bottlenecks.append("Memory usage grows significantly with batch size")
        
        # Check for context length bottlenecks
        context_data = self.results.get("context_test", {})
        if context_data and context_data.get("context_scaling_factor", 1) > 2:
            bottlenecks.append("Context length severely impacts performance")
        
        # Check for temperature sensitivity
        speed_data = self.results.get("speed_test", {})
        temp_variance = speed_data.get("temperature_variance", 0)
        if temp_variance > 0.3:
            bottlenecks.append("Performance varies significantly with temperature")
        
        return bottlenecks
    
    def save_to_file(self, filepath: Path):
        """Save complete benchmark results to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)


class BenchmarkRunner:
    """
    Comprehensive benchmark runner for MLX models.
    
    This class orchestrates all benchmark tests, providing detailed
    performance analysis across multiple dimensions. The runner is
    designed to be thorough yet efficient, completing comprehensive
    benchmarks in reasonable time.
    """
    
    def __init__(self):
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available - cannot run benchmarks")
        
        self.model = None
        self.tokenizer = None
        self.results = BenchmarkResults()
        
        # Test prompts for different scenarios
        self.test_prompts = {
            "short": [
                "Hello, how are you?",
                "What is the capital of France?",
                "Explain gravity briefly.",
                "Name three colors.",
                "What is 2 + 2?"
            ],
            "medium": [
                "Explain the concept of machine learning in simple terms.",
                "Describe the process of photosynthesis step by step.",
                "What are the main causes of climate change?",
                "How does the internet work?",
                "Explain the theory of relativity."
            ],
            "long": [
                "Write a detailed explanation of how neural networks learn, including the concepts of forward propagation, backpropagation, and gradient descent. Discuss the importance of activation functions and how different architectures like CNNs and RNNs are suited for different tasks.",
                "Provide a comprehensive analysis of renewable energy sources, comparing solar, wind, hydroelectric, and geothermal power in terms of efficiency, environmental impact, cost, and scalability. Discuss the challenges and opportunities for widespread adoption.",
                "Explain the history and development of programming languages, starting from assembly language through high-level languages like FORTRAN and COBOL, to modern languages like Python and JavaScript. Discuss how language design reflects the computing needs of different eras."
            ]
        }
    
    def run_benchmark(
        self,
        model_path: Path,
        config: Optional[BenchmarkConfig] = None,
        test_prompts: Optional[Path] = None,
        console: Optional[Console] = None
    ) -> Dict[str, Any]:
        """
        Run comprehensive benchmark suite.
        
        This executes all enabled benchmark tests and provides detailed
        analysis of model performance characteristics.
        
        Args:
            model_path: Path to the model to benchmark
            config: Benchmark configuration (uses defaults if None)
            test_prompts: Optional file with custom test prompts
            console: Rich console for progress display
            
        Returns:
            Comprehensive benchmark results dictionary
        """
        if config is None:
            config = BenchmarkConfig()
        
        if console is None:
            console = Console()
        
        console.print(Panel(
            f"[bold blue]MLX Model Benchmark Suite[/bold blue]\n"
            f"Model: {model_path}\n"
            f"Tests: {self._format_enabled_tests(config)}",
            title="Benchmark Configuration"
        ))
        
        try:
            # Load model
            console.print("[blue]Loading model...[/blue]")
            self._load_model(model_path)
            
            # Load custom prompts if provided
            if test_prompts:
                self._load_custom_prompts(test_prompts)
            
            # Run benchmark tests
            total_tests = sum([
                config.speed_test,
                config.memory_test,
                config.quality_test,
                config.stress_test,
                config.context_test
            ])
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                
                main_task = progress.add_task("Running benchmarks...", total=total_tests)
                completed = 0
                
                if config.speed_test:
                    progress.update(main_task, description="Speed test...")
                    self._run_speed_test(config, progress)
                    completed += 1
                    progress.update(main_task, completed=completed)
                
                if config.memory_test:
                    progress.update(main_task, description="Memory test...")
                    self._run_memory_test(config, progress)
                    completed += 1
                    progress.update(main_task, completed=completed)
                
                if config.quality_test:
                    progress.update(main_task, description="Quality test...")
                    self._run_quality_test(config, progress)
                    completed += 1
                    progress.update(main_task, completed=completed)
                
                if config.stress_test:
                    progress.update(main_task, description="Stress test...")
                    self._run_stress_test(config, progress)
                    completed += 1
                    progress.update(main_task, completed=completed)
                
                if config.context_test:
                    progress.update(main_task, description="Context test...")
                    self._run_context_test(config, progress)
                    completed += 1
                    progress.update(main_task, completed=completed)
            
            # Generate summary and display results
            summary = self.results.get_summary()
            self._display_benchmark_summary(summary, console)
            
            return {
                "summary": summary,
                "detailed_results": self.results.results,
                "model_path": str(model_path),
                "config": asdict(config)
            }
            
        except Exception as e:
            console.print(f"[red]Benchmark failed: {e}[/red]")
            raise
    
    def _format_enabled_tests(self, config: BenchmarkConfig) -> str:
        """Format list of enabled tests for display."""
        enabled = []
        if config.speed_test:
            enabled.append("Speed")
        if config.memory_test:
            enabled.append("Memory")
        if config.quality_test:
            enabled.append("Quality")
        if config.stress_test:
            enabled.append("Stress")
        if config.context_test:
            enabled.append("Context")
        
        return ", ".join(enabled)
    
    def _load_model(self, model_path: Path):
        """Load model for benchmarking."""
        self.model, self.tokenizer = load(str(model_path))
        
        # Warmup generation
        generate(
            self.model,
            self.tokenizer,
            prompt="Warmup",
            max_tokens=5,
            verbose=False
        )
    
    def _load_custom_prompts(self, prompts_file: Path):
        """Load custom test prompts from file."""
        try:
            with open(prompts_file, 'r') as f:
                custom_prompts = [line.strip() for line in f if line.strip()]
            
            # Replace default prompts with custom ones
            self.test_prompts["custom"] = custom_prompts
            
        except Exception as e:
            print(f"Warning: Could not load custom prompts: {e}")
    
    def _run_speed_test(self, config: BenchmarkConfig, progress: Progress):
        """
        Test generation speed across different parameters.
        
        This measures tokens per second, latency, and consistency
        across different temperature settings and prompt lengths.
        """
        speed_task = progress.add_task("Speed test", total=len(config.speed_test_temperatures))
        
        results = {
            "temperature_results": {},
            "prompt_length_results": {},
            "overall_stats": {}
        }
        
        all_speeds = []
        all_latencies = []
        
        # Test different temperatures
        for temp in config.speed_test_temperatures:
            temp_speeds = []
            temp_latencies = []
            
            for prompt in self.test_prompts["medium"][:config.speed_test_prompts]:
                start_time = time.time()
                
                response = generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=config.speed_test_max_tokens,
                    temperature=temp,
                    verbose=False
                )
                
                end_time = time.time()
                generation_time = end_time - start_time
                
                # Calculate tokens generated
                tokens_generated = len(self.tokenizer.encode(response)) - len(self.tokenizer.encode(prompt))
                tokens_per_second = tokens_generated / generation_time if generation_time > 0 else 0
                
                temp_speeds.append(tokens_per_second)
                temp_latencies.append(generation_time * 1000)  # ms
                all_speeds.append(tokens_per_second)
                all_latencies.append(generation_time * 1000)
            
            results["temperature_results"][temp] = {
                "avg_tokens_per_second": statistics.mean(temp_speeds),
                "avg_latency_ms": statistics.mean(temp_latencies),
                "speed_variance": statistics.variance(temp_speeds) if len(temp_speeds) > 1 else 0
            }
            
            progress.advance(speed_task)
        
        # Calculate overall statistics
        results["overall_stats"] = {
            "avg_tokens_per_second": statistics.mean(all_speeds),
            "avg_latency_ms": statistics.mean(all_latencies),
            "min_tokens_per_second": min(all_speeds),
            "max_tokens_per_second": max(all_speeds),
            "speed_consistency": 1.0 - (statistics.stdev(all_speeds) / statistics.mean(all_speeds)) if len(all_speeds) > 1 else 1.0,
            "temperature_variance": self._calculate_temperature_variance(results["temperature_results"])
        }
        
        self.results.add_speed_results(results)
    
    def _calculate_temperature_variance(self, temp_results: Dict[str, Dict[str, float]]) -> float:
        """Calculate how much performance varies with temperature."""
        speeds = [result["avg_tokens_per_second"] for result in temp_results.values()]
        if len(speeds) <= 1:
            return 0.0
        
        mean_speed = statistics.mean(speeds)
        variance = statistics.variance(speeds)
        return variance / (mean_speed ** 2) if mean_speed > 0 else 0.0
    
    def _run_memory_test(self, config: BenchmarkConfig, progress: Progress):
        """
        Test memory usage patterns under different loads.
        
        This measures peak memory usage, memory growth with batch size,
        and memory efficiency per token generated.
        """
        memory_task = progress.add_task("Memory test", total=len(config.memory_test_batch_sizes) + len(config.memory_test_sequence_lengths))
        
        results = {
            "batch_size_results": {},
            "sequence_length_results": {},
            "memory_efficiency": {}
        }
        
        # Test different batch sizes (simulated through rapid requests)
        for batch_size in config.memory_test_batch_sizes:
            gc.collect()  # Clean up before test
            start_memory = mx.metal.get_active_memory()
            
            # Simulate batch processing
            prompts = self.test_prompts["short"][:batch_size]
            batch_start_time = time.time()
            total_tokens = 0
            
            for prompt in prompts:
                response = generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=50,
                    temperature=0.7,
                    verbose=False
                )
                total_tokens += len(self.tokenizer.encode(response))
            
            batch_time = time.time() - batch_start_time
            end_memory = mx.metal.get_active_memory()
            memory_increase = end_memory - start_memory
            
            results["batch_size_results"][batch_size] = {
                "memory_increase_mb": memory_increase / (1024**2),
                "memory_per_token_kb": (memory_increase / total_tokens) / 1024 if total_tokens > 0 else 0,
                "processing_time": batch_time,
                "peak_memory_gb": end_memory / (1024**3)
            }
            
            progress.advance(memory_task)
        
        # Test different sequence lengths
        long_prompts = self._generate_prompts_by_length(config.memory_test_sequence_lengths)
        
        for seq_len, prompt in long_prompts.items():
            gc.collect()
            start_memory = mx.metal.get_active_memory()
            
            start_time = time.time()
            response = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=100,
                temperature=0.7,
                verbose=False
            )
            generation_time = time.time() - start_time
            
            end_memory = mx.metal.get_active_memory()
            memory_increase = end_memory - start_memory
            
            results["sequence_length_results"][seq_len] = {
                "memory_increase_mb": memory_increase / (1024**2),
                "generation_time": generation_time,
                "peak_memory_gb": end_memory / (1024**3)
            }
            
            progress.advance(memory_task)
        
        # Calculate efficiency metrics
        batch_results = results["batch_size_results"]
        if batch_results:
            memory_increases = [r["memory_increase_mb"] for r in batch_results.values()]
            batch_sizes = list(batch_results.keys())
            
            # Calculate memory growth rate
            if len(memory_increases) > 1:
                # Simple linear regression slope
                n = len(batch_sizes)
                sum_x = sum(batch_sizes)
                sum_y = sum(memory_increases)
                sum_xy = sum(x * y for x, y in zip(batch_sizes, memory_increases))
                sum_x2 = sum(x * x for x in batch_sizes)
                
                memory_growth_rate = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            else:
                memory_growth_rate = 0
            
            results["memory_efficiency"] = {
                "memory_growth_rate": memory_growth_rate,
                "peak_memory_gb": max(r["peak_memory_gb"] for r in batch_results.values()),
                "memory_per_token_mb": statistics.mean([r["memory_per_token_kb"] / 1024 for r in batch_results.values()]),
                "memory_efficiency_score": min(100, 1000 / memory_growth_rate) if memory_growth_rate > 0 else 100
            }
        
        self.results.add_memory_results(results)
    
    def _generate_prompts_by_length(self, target_lengths: List[int]) -> Dict[int, str]:
        """Generate prompts of specific token lengths for testing."""
        base_text = "This is a test prompt that will be repeated to create longer sequences. " * 100
        prompts = {}
        
        for target_length in target_lengths:
            # Tokenize and truncate to exact length
            tokens = self.tokenizer.encode(base_text)
            if len(tokens) > target_length:
                tokens = tokens[:target_length]
            
            prompt = self.tokenizer.decode(tokens)
            prompts[target_length] = prompt
        
        return prompts
    
    def _run_quality_test(self, config: BenchmarkConfig, progress: Progress):
        """
        Test response quality across different domains and scenarios.
        
        This evaluates consistency, coherence, and appropriateness
        of generated responses across various prompt types.
        """
        quality_task = progress.add_task("Quality test", total=len(config.quality_test_domains))
        
        results = {
            "domain_results": {},
            "consistency_test": {},
            "overall_quality": {}
        }
        
        quality_scores = []
        
        # Test different domains
        for domain in config.quality_test_domains:
            domain_prompts = self._get_domain_prompts(domain)
            domain_scores = []
            
            for prompt in domain_prompts:
                # Generate multiple responses for consistency testing
                responses = []
                for _ in range(3):
                    response = generate(
                        self.model,
                        self.tokenizer,
                        prompt=prompt,
                        max_tokens=150,
                        temperature=0.7,
                        verbose=False
                    )
                    responses.append(response)
                
                # Evaluate response quality
                quality_score = self._evaluate_response_quality(prompt, responses)
                domain_scores.append(quality_score)
                quality_scores.append(quality_score)
            
            results["domain_results"][domain] = {
                "avg_quality_score": statistics.mean(domain_scores),
                "quality_variance": statistics.variance(domain_scores) if len(domain_scores) > 1 else 0,
                "consistency_score": self._calculate_consistency_score(domain_scores)
            }
            
            progress.advance(quality_task)
        
        # Overall quality metrics
        results["overall_quality"] = {
            "overall_quality_score": statistics.mean(quality_scores) if quality_scores else 0,
            "quality_consistency": 1.0 - (statistics.stdev(quality_scores) / statistics.mean(quality_scores)) if len(quality_scores) > 1 else 1.0,
            "domain_variance": statistics.variance([r["avg_quality_score"] for r in results["domain_results"].values()]) if len(results["domain_results"]) > 1 else 0
        }
        
        self.results.add_quality_results(results)
    
    def _get_domain_prompts(self, domain: str) -> List[str]:
        """Get test prompts for a specific domain."""
        domain_prompts = {
            "general": [
                "Explain how photosynthesis works.",
                "What are the benefits of exercise?",
                "Describe the water cycle.",
                "How do computers process information?",
                "What causes seasons to change?"
            ],
            "reasoning": [
                "If all roses are flowers and some flowers are red, are some roses red?",
                "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?",
                "If it takes 5 machines 5 minutes to make 5 widgets, how long would it take 100 machines to make 100 widgets?",
                "Mary's father has five daughters: Nana, Nene, Nini, Nono. What is the fifth daughter's name?",
                "You have two coins that add up to 30 cents. One is not a nickel. What are the two coins?"
            ],
            "creative": [
                "Write a short story about a robot learning to paint.",
                "Describe a world where gravity works backwards.",
                "Create a recipe for happiness.",
                "Write a dialogue between the sun and the moon.",
                "Invent a new holiday and explain how it's celebrated."
            ]
        }
        
        return domain_prompts.get(domain, self.test_prompts["medium"])
    
    def _evaluate_response_quality(self, prompt: str, responses: List[str]) -> float:
        """
        Evaluate the quality of generated responses.
        
        This uses heuristics to assess response quality including
        length appropriateness, coherence, and relevance.
        """
        if not responses:
            return 0.0
        
        scores = []
        
        for response in responses:
            score = 0.0
            
            # Length appropriateness (responses should be substantial but not excessive)
            response_length = len(response.strip())
            if 50 <= response_length <= 500:
                score += 0.3
            elif response_length > 20:
                score += 0.1
            
            # Basic coherence (no excessive repetition)
            words = response.lower().split()
            if len(set(words)) / len(words) > 0.5:  # At least 50% unique words
                score += 0.2
            
            # Relevance to prompt (basic keyword matching)
            prompt_words = set(prompt.lower().split())
            response_words = set(response.lower().split())
            overlap = len(prompt_words.intersection(response_words))
            if overlap > 0:
                score += min(0.3, overlap * 0.1)
            
            # Structure (has sentences, proper capitalization)
            if response[0].isupper() and '.' in response:
                score += 0.2
            
            scores.append(score)
        
        return statistics.mean(scores)
    
    def _calculate_consistency_score(self, scores: List[float]) -> float:
        """Calculate consistency score based on variance in quality scores."""
        if len(scores) <= 1:
            return 1.0
        
        variance = statistics.variance(scores)
        mean_score = statistics.mean(scores)
        
        # Normalize by mean to get coefficient of variation
        cv = variance / (mean_score ** 2) if mean_score > 0 else 1.0
        
        # Convert to consistency score (lower variance = higher consistency)
        return max(0.0, 1.0 - cv)
    
    def _run_stress_test(self, config: BenchmarkConfig, progress: Progress):
        """
        Test model performance under sustained load.
        
        This simulates concurrent requests and measures stability,
        error rates, and performance degradation over time.
        """
        stress_task = progress.add_task("Stress test", total=config.stress_test_duration)
        
        results = {
            "concurrent_performance": {},
            "sustained_performance": {},
            "reliability_metrics": {}
        }
        
        # Concurrent requests test
        request_queue = queue.Queue()
        results_queue = queue.Queue()
        error_count = 0
        successful_requests = 0
        
        def worker():
            while True:
                try:
                    prompt = request_queue.get_nowait()
                    start_time = time.time()
                    
                    response = generate(
                        self.model,
                        self.tokenizer,
                        prompt=prompt,
                        max_tokens=100,
                        temperature=0.7,
                        verbose=False
                    )
                    
                    end_time = time.time()
                    results_queue.put({
                        "success": True,
                        "response_time": end_time - start_time,
                        "tokens": len(self.tokenizer.encode(response))
                    })
                    
                except queue.Empty:
                    break
                except Exception as e:
                    results_queue.put({
                        "success": False,
                        "error": str(e)
                    })
                finally:
                    request_queue.task_done()
        
        # Stress test execution
        start_time = time.time()
        test_prompts = self.test_prompts["medium"] * 100  # Repeat prompts
        
        while time.time() - start_time < config.stress_test_duration:
            # Add requests to queue
            batch_prompts = test_prompts[:config.stress_test_concurrent_requests]
            for prompt in batch_prompts:
                request_queue.put(prompt)
            
            # Start worker threads
            threads = []
            for _ in range(config.stress_test_concurrent_requests):
                t = threading.Thread(target=worker)
                t.start()
                threads.append(t)
            
            # Wait for completion
            request_queue.join()
            for t in threads:
                t.join()
            
            # Collect results
            batch_results = []
            while not results_queue.empty():
                result = results_queue.get()
                batch_results.append(result)
                
                if result["success"]:
                    successful_requests += 1
                else:
                    error_count += 1
            
            progress.advance(stress_task, advance=5)  # Update progress periodically
        
        total_requests = successful_requests + error_count
        
        results["reliability_metrics"] = {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "error_count": error_count,
            "error_rate": error_count / total_requests if total_requests > 0 else 0,
            "reliability_score": (successful_requests / total_requests * 100) if total_requests > 0 else 0,
            "max_concurrent_handled": config.stress_test_concurrent_requests,
            "test_duration": config.stress_test_duration
        }
        
        self.results.add_stress_results(results)
    
    def _run_context_test(self, config: BenchmarkConfig, progress: Progress):
        """
        Test performance with varying context lengths.
        
        This measures how model performance degrades as context
        length increases, helping optimize context usage.
        """
        context_task = progress.add_task("Context test", total=len(config.context_test_lengths))
        
        results = {
            "context_length_results": {},
            "performance_scaling": {}
        }
        
        baseline_speed = None
        
        for context_length in config.context_test_lengths:
            # Generate context of specified length
            context_prompt = self._generate_prompts_by_length([context_length])[context_length]
            test_prompt = context_prompt + "\n\nQuestion: Summarize the main points from the above text."
            
            # Measure performance
            start_time = time.time()
            response = generate(
                self.model,
                self.tokenizer,
                prompt=test_prompt,
                max_tokens=100,
                temperature=0.7,
                verbose=False
            )
            end_time = time.time()
            
            generation_time = end_time - start_time
            tokens_generated = len(self.tokenizer.encode(response)) - len(self.tokenizer.encode(test_prompt))
            tokens_per_second = tokens_generated / generation_time if generation_time > 0 else 0
            
            # Memory usage
            memory_used = mx.metal.get_active_memory() / (1024**3)
            
            if baseline_speed is None:
                baseline_speed = tokens_per_second
            
            results["context_length_results"][context_length] = {
                "generation_time": generation_time,
                "tokens_per_second": tokens_per_second,
                "memory_usage_gb": memory_used,
                "performance_ratio": tokens_per_second / baseline_speed if baseline_speed > 0 else 1.0
            }
            
            progress.advance(context_task)
        
        # Calculate scaling characteristics
        context_results = results["context_length_results"]
        if len(context_results) > 1:
            lengths = list(context_results.keys())
            speeds = [r["tokens_per_second"] for r in context_results.values()]
            
            # Calculate performance degradation
            max_speed = max(speeds)
            min_speed = min(speeds)
            performance_degradation = (max_speed - min_speed) / max_speed if max_speed > 0 else 0
            
            # Calculate scaling factor (how much slower with longest context)
            longest_speed = context_results[max(lengths)]["tokens_per_second"]
            shortest_speed = context_results[min(lengths)]["tokens_per_second"]
            context_scaling_factor = shortest_speed / longest_speed if longest_speed > 0 else 1.0
            
            results["performance_scaling"] = {
                "performance_degradation": performance_degradation,
                "context_scaling_factor": context_scaling_factor,
                "max_context_tested": max(lengths),
                "recommended_max_context": self._recommend_max_context(context_results)
            }
        
        self.results.add_context_results(results)
    
    def _recommend_max_context(self, context_results: Dict[int, Dict[str, float]]) -> int:
        """Recommend maximum context length based on performance degradation."""
        # Find context length where performance drops below 50% of baseline
        baseline_speed = min(r["tokens_per_second"] for r in context_results.values())
        threshold_speed = baseline_speed * 0.5
        
        for context_length, result in sorted(context_results.items()):
            if result["tokens_per_second"] < threshold_speed:
                return context_length
        
        # If no degradation found, return maximum tested
        return max(context_results.keys())
    
    def _display_benchmark_summary(self, summary: Dict[str, Any], console: Console):
        """Display formatted benchmark summary."""
        # Overall score panel
        score = summary["overall_score"]
        performance_class = summary["performance_class"]
        
        score_color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
        
        console.print(Panel(
            f"[bold {score_color}]Overall Score: {score:.1f}/100[/bold {score_color}]\n"
            f"Performance Class: {performance_class}",
            title="Benchmark Summary"
        ))
        
        # Key metrics table
        table = Table(title="Key Performance Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_column("Assessment", style="yellow")
        
        metrics = summary["key_metrics"]
        
        # Speed metrics
        if "tokens_per_second" in metrics:
            tps = metrics["tokens_per_second"]
            tps_assessment = "Excellent" if tps > 50 else "Good" if tps > 20 else "Fair" if tps > 10 else "Poor"
            table.add_row("Speed", f"{tps:.1f} tokens/sec", tps_assessment)
        
        if "avg_latency_ms" in metrics:
            latency = metrics["avg_latency_ms"]
            latency_assessment = "Excellent" if latency < 100 else "Good" if latency < 500 else "Fair" if latency < 1000 else "Poor"
            table.add_row("Latency", f"{latency:.0f} ms", latency_assessment)
        
        # Memory metrics
        if "peak_memory_gb" in metrics:
            memory = metrics["peak_memory_gb"]
            memory_assessment = "Excellent" if memory < 8 else "Good" if memory < 16 else "Fair" if memory < 32 else "High"
            table.add_row("Peak Memory", f"{memory:.1f} GB", memory_assessment)
        
        # Quality metrics
        if "quality_score" in metrics:
            quality = metrics["quality_score"]
            quality_assessment = "Excellent" if quality > 0.8 else "Good" if quality > 0.6 else "Fair" if quality > 0.4 else "Poor"
            table.add_row("Quality Score", f"{quality:.3f}", quality_assessment)
        
        console.print(table)
        
        # Recommendations
        recommendations = summary.get("recommendations", [])
        if recommendations:
            console.print("\n[blue]Recommendations:[/blue]")
            for rec in recommendations:
                console.print(f"  • {rec}")
        
        # Bottlenecks
        bottlenecks = summary.get("bottlenecks", [])
        if bottlenecks:
            console.print("\n[red]Identified Bottlenecks:[/red]")
            for bottleneck in bottlenecks:
                console.print(f"  • {bottleneck}")
    
    def save_results(self, results: Dict[str, Any], output_file: Path):
        """Save benchmark results to file."""
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
