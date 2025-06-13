"""
Inference and Deployment Module

This module transforms fine-tuned models from experimental artifacts into
production-ready systems that can serve real users. Deployment is where
all the preparation work pays off - creating reliable, efficient services
that deliver the capabilities you've built.

The inference engine supports multiple deployment patterns:
- Local Python API for development and testing
- FastAPI server with OpenAI-compatible endpoints
- Streaming responses for real-time applications
- Batch processing for high-throughput scenarios
- Memory-efficient serving for resource-constrained environments

The philosophy here is "production-ready by default" - every component
is designed with reliability, monitoring, and scalability in mind, even
for single-user deployments.
"""

import asyncio
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Callable
from dataclasses import dataclass, asdict
from queue import Queue, Empty
import signal
import sys

try:
    import mlx.core as mx
    from mlx_lm import load, generate, stream_generate
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

import psutil
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel

# FastAPI and related imports (optional for server functionality)
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@dataclass
class InferenceConfig:
    """
    Configuration for inference operations.
    
    This captures all the parameters that affect inference quality,
    performance, and behaviour. The configuration is designed to be
    both comprehensive and easy to use, with sensible defaults for
    most common scenarios.
    """
    # Generation parameters
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: Optional[int] = None
    repetition_penalty: float = 1.0
    
    # Performance parameters
    batch_size: int = 1
    use_cache: bool = True
    
    # Memory management
    max_memory_gb: Optional[float] = None
    unload_after_idle: int = 300  # seconds
    
    # Quality controls
    min_response_length: int = 1
    max_response_length: Optional[int] = None
    stop_sequences: List[str] = None
    
    # Safety parameters
    content_filter: bool = False
    rate_limit_requests: Optional[int] = None
    rate_limit_window: int = 60  # seconds
    
    def __post_init__(self):
        if self.stop_sequences is None:
            self.stop_sequences = []
        
        if self.temperature < 0:
            raise ValueError("Temperature must be non-negative")
        
        if not 0 <= self.top_p <= 1:
            raise ValueError("top_p must be between 0 and 1")


class RequestMetrics:
    """
    Tracks request-level metrics for monitoring and optimization.
    
    This provides detailed insights into inference performance,
    helping identify bottlenecks and optimize configurations.
    """
    
    def __init__(self):
        self.request_count = 0
        self.total_tokens_generated = 0
        self.total_inference_time = 0.0
        self.error_count = 0
        self.memory_peaks = []
        self.response_times = []
        
        # Prometheus metrics (if available)
        if PROMETHEUS_AVAILABLE:
            self.request_counter = Counter('mlx_requests_total', 'Total inference requests')
            self.request_duration = Histogram('mlx_request_duration_seconds', 'Request duration')
            self.tokens_generated = Counter('mlx_tokens_generated_total', 'Total tokens generated')
            self.memory_usage = Gauge('mlx_memory_usage_bytes', 'Current memory usage')
            self.error_counter = Counter('mlx_errors_total', 'Total inference errors')
    
    def record_request(
        self, 
        tokens_generated: int, 
        inference_time: float, 
        memory_used: float,
        error: bool = False
    ):
        """Record metrics for a completed request."""
        self.request_count += 1
        
        if not error:
            self.total_tokens_generated += tokens_generated
            self.total_inference_time += inference_time
            self.response_times.append(inference_time)
            self.memory_peaks.append(memory_used)
        else:
            self.error_count += 1
        
        # Update Prometheus metrics
        if PROMETHEUS_AVAILABLE:
            self.request_counter.inc()
            if not error:
                self.request_duration.observe(inference_time)
                self.tokens_generated.inc(tokens_generated)
            else:
                self.error_counter.inc()
            self.memory_usage.set(memory_used)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        if self.request_count == 0:
            return {"no_requests": True}
        
        valid_requests = self.request_count - self.error_count
        
        stats = {
            "total_requests": self.request_count,
            "successful_requests": valid_requests,
            "error_rate": self.error_count / self.request_count,
            "total_tokens": self.total_tokens_generated,
        }
        
        if valid_requests > 0:
            stats.update({
                "avg_tokens_per_request": self.total_tokens_generated / valid_requests,
                "avg_response_time": sum(self.response_times) / len(self.response_times),
                "tokens_per_second": self.total_tokens_generated / self.total_inference_time if self.total_inference_time > 0 else 0,
            })
        
        if self.memory_peaks:
            stats.update({
                "peak_memory_gb": max(self.memory_peaks),
                "avg_memory_gb": sum(self.memory_peaks) / len(self.memory_peaks),
            })
        
        return stats


class InferenceEngine:
    """
    High-performance inference engine for MLX models.
    
    This class provides the core inference capabilities with advanced
    features like request queuing, memory management, and performance
    monitoring. It's designed to handle everything from single requests
    to high-throughput serving scenarios.
    """
    
    def __init__(self, config: Optional[InferenceConfig] = None):
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available - cannot initialize inference engine")
        
        self.config = config or InferenceConfig()
        self.model = None
        self.tokenizer = None
        self.model_path = None
        self.adapter_path = None
        
        # Performance monitoring
        self.metrics = RequestMetrics()
        self.last_request_time = time.time()
        
        # Request management
        self.request_queue = Queue()
        self.processing_requests = False
        self.shutdown_requested = False
        
        # Rate limiting
        self.request_times = []
    
    def load_model(
        self, 
        model_path: Union[str, Path], 
        adapter_path: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Load a model for inference with comprehensive validation.
        
        This method handles both base models and fine-tuned adapters,
        with automatic optimization for the target hardware.
        
        Args:
            model_path: Path to the base model
            adapter_path: Optional path to fine-tuned adapter
            
        Returns:
            Dictionary with loading results and model information
        """
        try:
            start_time = time.time()
            
            # Store paths for potential reloading
            self.model_path = str(model_path)
            self.adapter_path = str(adapter_path) if adapter_path else None
            
            # Load model with optional adapter
            if adapter_path:
                self.model, self.tokenizer = load(
                    self.model_path, 
                    adapter_path=self.adapter_path
                )
            else:
                self.model, self.tokenizer = load(self.model_path)
            
            loading_time = time.time() - start_time
            
            # Get model information
            model_info = self._analyze_loaded_model()
            
            # Perform warmup generation
            warmup_time = self._warmup_model()
            
            return {
                "success": True,
                "model_path": self.model_path,
                "adapter_path": self.adapter_path,
                "loading_time": loading_time,
                "warmup_time": warmup_time,
                "model_info": model_info,
                "memory_usage_gb": mx.metal.get_active_memory() / (1024**3)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model_path": model_path,
                "adapter_path": adapter_path
            }
    
    def _analyze_loaded_model(self) -> Dict[str, Any]:
        """Analyze the loaded model to understand its characteristics."""
        info = {
            "architecture": self.model.__class__.__name__,
            "tokenizer_type": self.tokenizer.__class__.__name__,
        }
        
        try:
            # Test tokenization
            test_text = "Hello, this is a test."
            tokens = self.tokenizer.encode(test_text)
            decoded = self.tokenizer.decode(tokens)
            
            info.update({
                "vocab_size": len(self.tokenizer.get_vocab()) if hasattr(self.tokenizer, 'get_vocab') else "unknown",
                "tokenization_test": "passed",
                "test_tokens": len(tokens),
            })
            
        except Exception as e:
            info["tokenization_test"] = f"failed: {e}"
        
        return info
    
    def _warmup_model(self) -> float:
        """
        Warm up the model to avoid cold start latency on first request.
        
        This performs a small generation to ensure all model components
        are loaded and optimized before serving real requests.
        """
        try:
            start_time = time.time()
            
            # Simple warmup generation
            warmup_response = generate(
                self.model,
                self.tokenizer,
                prompt="Hello",
                max_tokens=5,
                temperature=0.1,
                verbose=False
            )
            
            return time.time() - start_time
            
        except Exception:
            return 0.0
    
    def generate_response(
        self,
        prompt: str,
        config_override: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a single prompt.
        
        This is the main inference method that handles individual requests
        with comprehensive error handling and performance monitoring.
        
        Args:
            prompt: Input text to generate from
            config_override: Temporary config overrides for this request
            request_id: Optional identifier for request tracking
            
        Returns:
            Dictionary with generated response and metadata
        """
        if not self.model or not self.tokenizer:
            raise RuntimeError("No model loaded - call load_model() first")
        
        # Apply rate limiting
        if not self._check_rate_limit():
            raise RuntimeError("Rate limit exceeded")
        
        # Merge configuration
        effective_config = self._merge_config(config_override)
        
        # Record request start
        request_start = time.time()
        start_memory = mx.metal.get_active_memory()
        
        try:
            # Input validation and preprocessing
            processed_prompt = self._preprocess_prompt(prompt)
            
            # Generate response
            response = generate(
                self.model,
                self.tokenizer,
                prompt=processed_prompt,
                max_tokens=effective_config["max_tokens"],
                temperature=effective_config["temperature"],
                top_p=effective_config["top_p"],
                repetition_penalty=effective_config["repetition_penalty"],
                verbose=False
            )
            
            # Post-process response
            processed_response = self._postprocess_response(response, processed_prompt)
            
            # Calculate metrics
            inference_time = time.time() - request_start
            tokens_generated = len(self.tokenizer.encode(processed_response)) - len(self.tokenizer.encode(processed_prompt))
            peak_memory = mx.metal.get_active_memory()
            
            # Record metrics
            self.metrics.record_request(
                tokens_generated=tokens_generated,
                inference_time=inference_time,
                memory_used=peak_memory / (1024**3)
            )
            
            # Update last request time
            self.last_request_time = time.time()
            
            return {
                "success": True,
                "response": processed_response,
                "prompt": processed_prompt,
                "request_id": request_id,
                "metadata": {
                    "tokens_generated": tokens_generated,
                    "inference_time": inference_time,
                    "tokens_per_second": tokens_generated / inference_time if inference_time > 0 else 0,
                    "memory_used_gb": peak_memory / (1024**3),
                    "config_used": effective_config
                }
            }
            
        except Exception as e:
            # Record error
            error_time = time.time() - request_start
            error_memory = mx.metal.get_active_memory()
            
            self.metrics.record_request(
                tokens_generated=0,
                inference_time=error_time,
                memory_used=error_memory / (1024**3),
                error=True
            )
            
            return {
                "success": False,
                "error": str(e),
                "prompt": prompt,
                "request_id": request_id,
                "metadata": {
                    "error_time": error_time,
                    "memory_used_gb": error_memory / (1024**3)
                }
            }
    
    async def generate_response_stream(
        self,
        prompt: str,
        config_override: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate a streaming response for real-time applications.
        
        This method yields tokens as they're generated, enabling
        responsive user interfaces and real-time interaction patterns.
        """
        if not self.model or not self.tokenizer:
            raise RuntimeError("No model loaded - call load_model() first")
        
        # Apply rate limiting
        if not self._check_rate_limit():
            raise RuntimeError("Rate limit exceeded")
        
        # Merge configuration
        effective_config = self._merge_config(config_override)
        
        # Record request start
        request_start = time.time()
        start_memory = mx.metal.get_active_memory()
        tokens_generated = 0
        
        try:
            # Input preprocessing
            processed_prompt = self._preprocess_prompt(prompt)
            
            # Yield initial metadata
            yield {
                "type": "start",
                "request_id": request_id,
                "prompt": processed_prompt
            }
            
            # Stream generation
            full_response = ""
            
            for token_str in stream_generate(
                self.model,
                self.tokenizer,
                prompt=processed_prompt,
                max_tokens=effective_config["max_tokens"],
                temperature=effective_config["temperature"],
                top_p=effective_config["top_p"],
                repetition_penalty=effective_config["repetition_penalty"]
            ):
                full_response += token_str
                tokens_generated += 1
                
                yield {
                    "type": "token",
                    "token": token_str,
                    "partial_response": full_response,
                    "tokens_generated": tokens_generated
                }
            
            # Final processing
            processed_response = self._postprocess_response(full_response, processed_prompt)
            inference_time = time.time() - request_start
            peak_memory = mx.metal.get_active_memory()
            
            # Record metrics
            self.metrics.record_request(
                tokens_generated=tokens_generated,
                inference_time=inference_time,
                memory_used=peak_memory / (1024**3)
            )
            
            # Update last request time
            self.last_request_time = time.time()
            
            # Yield completion
            yield {
                "type": "complete",
                "response": processed_response,
                "metadata": {
                    "tokens_generated": tokens_generated,
                    "inference_time": inference_time,
                    "tokens_per_second": tokens_generated / inference_time if inference_time > 0 else 0,
                    "memory_used_gb": peak_memory / (1024**3)
                }
            }
            
        except Exception as e:
            # Record error and yield error message
            error_time = time.time() - request_start
            error_memory = mx.metal.get_active_memory()
            
            self.metrics.record_request(
                tokens_generated=tokens_generated,
                inference_time=error_time,
                memory_used=error_memory / (1024**3),
                error=True
            )
            
            yield {
                "type": "error",
                "error": str(e),
                "metadata": {
                    "tokens_generated": tokens_generated,
                    "error_time": error_time
                }
            }
    
    def _merge_config(self, override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge base config with request-specific overrides."""
        effective_config = asdict(self.config)
        
        if override:
            # Validate and apply overrides
            for key, value in override.items():
                if key in effective_config:
                    effective_config[key] = value
        
        return effective_config
    
    def _preprocess_prompt(self, prompt: str) -> str:
        """Preprocess input prompt for better generation quality."""
        # Basic preprocessing
        processed = prompt.strip()
        
        # Content filtering (if enabled)
        if self.config.content_filter:
            processed = self._apply_content_filter(processed)
        
        return processed
    
    def _postprocess_response(self, response: str, prompt: str) -> str:
        """Post-process generated response for quality and safety."""
        # Remove the prompt from response if it was included
        if response.startswith(prompt):
            processed = response[len(prompt):].strip()
        else:
            processed = response.strip()
        
        # Apply stop sequences
        for stop_seq in self.config.stop_sequences:
            if stop_seq in processed:
                processed = processed.split(stop_seq)[0]
        
        # Length validation
        if len(processed) < self.config.min_response_length:
            processed = f"[Response too short: {len(processed)} chars]"
        
        if (self.config.max_response_length and 
            len(processed) > self.config.max_response_length):
            processed = processed[:self.config.max_response_length] + "..."
        
        return processed
    
    def _apply_content_filter(self, text: str) -> str:
        """Apply content filtering to input text."""
        # Basic content filtering - can be extended with more sophisticated filters
        filtered = text
        
        # Remove or replace potentially problematic content
        # This is a placeholder for more sophisticated filtering
        
        return filtered
    
    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limits."""
        if not self.config.rate_limit_requests:
            return True
        
        current_time = time.time()
        window_start = current_time - self.config.rate_limit_window
        
        # Remove old requests outside window
        self.request_times = [t for t in self.request_times if t > window_start]
        
        # Check if under limit
        if len(self.request_times) >= self.config.rate_limit_requests:
            return False
        
        # Record this request
        self.request_times.append(current_time)
        return True
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        base_stats = self.metrics.get_stats()
        
        # Add engine-specific stats
        base_stats.update({
            "model_loaded": self.model is not None,
            "model_path": self.model_path,
            "adapter_path": self.adapter_path,
            "last_request_time": self.last_request_time,
            "idle_time": time.time() - self.last_request_time,
            "current_memory_gb": mx.metal.get_active_memory() / (1024**3) if MLX_AVAILABLE else 0,
        })
        
        return base_stats
    
    def start_server(
        self,
        model_path: Union[str, Path],
        adapter_path: Optional[Union[str, Path]] = None,
        host: str = "localhost",
        port: int = 8080,
        max_concurrent: int = 4,
        enable_metrics: bool = True,
        console: Optional[Console] = None
    ) -> None:
        """
        Start a FastAPI server for inference.
        
        This creates a production-ready server with OpenAI-compatible
        endpoints, request queuing, and comprehensive monitoring.
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not available - install with: pip install fastapi uvicorn")
        
        if console is None:
            console = Console()
        
        # Load model
        console.print(f"[blue]Loading model from {model_path}...[/blue]")
        load_result = self.load_model(model_path, adapter_path)
        
        if not load_result["success"]:
            raise RuntimeError(f"Failed to load model: {load_result['error']}")
        
        console.print(f"[green]✓ Model loaded in {load_result['loading_time']:.2f}s[/green]")
        
        # Create FastAPI app
        app = self._create_fastapi_app(enable_metrics)
        
        # Setup graceful shutdown
        self._setup_shutdown_handlers()
        
        # Start server
        console.print(f"[blue]Starting server on {host}:{port}...[/blue]")
        console.print("[yellow]Press Ctrl+C to stop[/yellow]")
        
        try:
            uvicorn.run(
                app,
                host=host,
                port=port,
                access_log=False,  # We handle our own logging
                log_level="error"  # Reduce uvicorn noise
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Server shutdown requested[/yellow]")
        finally:
            self.shutdown_requested = True
    
    def _create_fastapi_app(self, enable_metrics: bool = True) -> FastAPI:
        """Create and configure FastAPI application."""
        app = FastAPI(
            title="MLX Inference Server",
            description="High-performance inference server for MLX models",
            version="1.0.0"
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Define request/response models
        class ChatMessage(BaseModel):
            role: str
            content: str
        
        class ChatCompletionRequest(BaseModel):
            model: str = "mlx-model"
            messages: List[ChatMessage]
            max_tokens: Optional[int] = None
            temperature: Optional[float] = None
            top_p: Optional[float] = None
            stream: bool = False
        
        class CompletionRequest(BaseModel):
            model: str = "mlx-model"
            prompt: str
            max_tokens: Optional[int] = None
            temperature: Optional[float] = None
            top_p: Optional[float] = None
            stream: bool = False
        
        # Health check endpoint
        @app.get("/health")
        async def health_check():
            stats = self.get_performance_stats()
            return {
                "status": "healthy" if stats["model_loaded"] else "no_model",
                "memory_gb": stats["current_memory_gb"],
                "requests_served": stats.get("total_requests", 0)
            }
        
        # Chat completions endpoint (OpenAI compatible)
        @app.post("/v1/chat/completions")
        async def create_chat_completion(request: ChatCompletionRequest):
            try:
                # Convert messages to prompt
                prompt = self._format_chat_messages(request.messages)
                
                # Prepare config override
                config_override = {}
                if request.max_tokens:
                    config_override["max_tokens"] = request.max_tokens
                if request.temperature is not None:
                    config_override["temperature"] = request.temperature
                if request.top_p is not None:
                    config_override["top_p"] = request.top_p
                
                if request.stream:
                    return StreamingResponse(
                        self._stream_chat_completion(prompt, config_override),
                        media_type="text/event-stream"
                    )
                else:
                    result = self.generate_response(prompt, config_override)
                    
                    if not result["success"]:
                        raise HTTPException(status_code=500, detail=result["error"])
                    
                    return {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": result["response"]
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": len(self.tokenizer.encode(prompt)),
                            "completion_tokens": result["metadata"]["tokens_generated"],
                            "total_tokens": len(self.tokenizer.encode(prompt)) + result["metadata"]["tokens_generated"]
                        }
                    }
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        # Text completions endpoint
        @app.post("/v1/completions")
        async def create_completion(request: CompletionRequest):
            try:
                config_override = {}
                if request.max_tokens:
                    config_override["max_tokens"] = request.max_tokens
                if request.temperature is not None:
                    config_override["temperature"] = request.temperature
                if request.top_p is not None:
                    config_override["top_p"] = request.top_p
                
                if request.stream:
                    return StreamingResponse(
                        self._stream_completion(request.prompt, config_override),
                        media_type="text/event-stream"
                    )
                else:
                    result = self.generate_response(request.prompt, config_override)
                    
                    if not result["success"]:
                        raise HTTPException(status_code=500, detail=result["error"])
                    
                    return {
                        "id": f"cmpl-{int(time.time())}",
                        "object": "text_completion",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": [{
                            "text": result["response"],
                            "index": 0,
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": len(self.tokenizer.encode(request.prompt)),
                            "completion_tokens": result["metadata"]["tokens_generated"],
                            "total_tokens": len(self.tokenizer.encode(request.prompt)) + result["metadata"]["tokens_generated"]
                        }
                    }
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        # Models endpoint
        @app.get("/v1/models")
        async def list_models():
            return {
                "object": "list",
                "data": [{
                    "id": "mlx-model",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "local"
                }]
            }
        
        # Performance stats endpoint
        @app.get("/stats")
        async def get_stats():
            return self.get_performance_stats()
        
        # Metrics endpoint (Prometheus format)
        if enable_metrics and PROMETHEUS_AVAILABLE:
            @app.get("/metrics")
            async def get_metrics():
                from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
                return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
        
        return app
    
    def _format_chat_messages(self, messages: List) -> str:
        """Convert chat messages to a single prompt string."""
        prompt_parts = []
        
        for message in messages:
            role = message.role
            content = message.content
            
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts)
    
    async def _stream_chat_completion(self, prompt: str, config_override: Dict[str, Any]):
        """Stream chat completion responses."""
        try:
            async for chunk in self.generate_response_stream(prompt, config_override):
                if chunk["type"] == "token":
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk['token']}}]})}\n\n"
                elif chunk["type"] == "complete":
                    yield f"data: {json.dumps({'choices': [{'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"
                elif chunk["type"] == "error":
                    yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                    
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    async def _stream_completion(self, prompt: str, config_override: Dict[str, Any]):
        """Stream text completion responses."""
        try:
            async for chunk in self.generate_response_stream(prompt, config_override):
                if chunk["type"] == "token":
                    yield f"data: {json.dumps({'choices': [{'text': chunk['token']}]})}\n\n"
                elif chunk["type"] == "complete":
                    yield f"data: {json.dumps({'choices': [{'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"
                elif chunk["type"] == "error":
                    yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                    
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    def _setup_shutdown_handlers(self):
        """Setup graceful shutdown handlers."""
        def signal_handler(signum, frame):
            self.shutdown_requested = True
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
