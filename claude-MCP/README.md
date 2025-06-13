# MLX Complete Pipeline

A comprehensive toolkit for end-to-end LLM development on Apple Silicon using MLX. This project provides everything you need to go from raw data to deployed models, with a focus on practical usability and production readiness.

## 🚀 Features

- **Complete Pipeline**: Environment setup → Data preparation → Model selection → Fine-tuning → Quantization → Deployment
- **Apple Silicon Optimized**: Built specifically for M1/M2/M3 Macs with unified memory architecture
- **Production Ready**: Comprehensive error handling, monitoring, and deployment options
- **Framework Independent**: No LangChain or LlamaIndex dependencies
- **Extensible Architecture**: Modular design allows using individual components or complete workflows

## 🏗️ Architecture

The pipeline consists of seven core modules, each handling a specific aspect of the ML workflow:

1. **Setup** (`mlx_pipeline.setup`): Environment validation and configuration
2. **Data Processing** (`mlx_pipeline.data`): Data preparation and format conversion
3. **Model Management** (`mlx_pipeline.models`): Model downloading and validation
4. **Training** (`mlx_pipeline.training`): LoRA and full fine-tuning with MLX
5. **Quantization** (`mlx_pipeline.quantization`): Model optimization and compression
6. **Inference** (`mlx_pipeline.inference`): Deployment and serving
7. **Benchmarking** (`mlx_pipeline.benchmark`): Performance testing and validation

## 📋 Requirements

### Hardware
- Apple Silicon Mac (M1, M2, or M3 series)
- 16GB+ RAM recommended (32GB+ for larger models)
- 50GB+ free disk space

### Software
- macOS 13.5+ (Ventura) or macOS 14+ (Sonoma) recommended
- Python 3.9-3.12
- Xcode Command Line Tools

## 🛠️ Installation

1. **Clone and setup the project:**
```bash
cd /path/to/your/projects
git clone <this-repo-url>  # Or create from this codebase
cd mlx-complete-pipeline
```

2. **Install with uv (recommended):**
```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv sync
```

3. **Alternative installation with pip:**
```bash
python -m venv mlx-env
source mlx-env/bin/activate
pip install -e .
```

4. **Verify installation:**
```bash
mlx-setup
```

## 🚦 Quick Start

### 1. Environment Validation
First, ensure your system is properly configured:

```bash
mlx-setup --validate-metal --check-memory
```

### 2. Prepare Training Data
Convert your data to MLX-compatible format:

```bash
# From CSV
mlx-prepare-data input.csv ./data --format-type csv

# From Augmentoolkit output
mlx-prepare-data augmentoolkit_output.jsonl ./data --format-type augmentoolkit

# From raw text
mlx-prepare-data documents.txt ./data --format-type text
```

### 3. Download a Model
Get an MLX-compatible model:

```bash
# Download a pre-converted model (recommended)
mlx-download-model mlx-community/Mistral-7B-Instruct-v0.3-4bit ./models

# Or download and convert automatically
mlx-download-model mistralai/Mistral-7B-v0.1 ./models --quantization 4bit
```

### 4. Fine-tune the Model
Train your model on your specific data:

```bash
mlx-finetune ./models/Mistral-7B-v0.1 ./data ./fine-tuned-model \
  --lora-rank 8 \
  --learning-rate 1e-4 \
  --max-iters 1000 \
  --batch-size 4
```

### 5. Quantize for Deployment
Optimize the model for efficient serving:

```bash
mlx-quantize ./fine-tuned-model ./quantized-model --bits 4 --validate-quality
```

### 6. Deploy as a Server
Start an OpenAI-compatible API server:

```bash
mlx-serve ./quantized-model --host 0.0.0.0 --port 8080
```

### 7. Benchmark Performance
Test your model's performance:

```bash
mlx-benchmark ./quantized-model --output-file benchmark_results.json
```

## 📖 Detailed Usage

### Data Preparation

The data processor handles multiple input formats and converts them to MLX-compatible JSONL:

```python
from mlx_pipeline import DataProcessor

processor = DataProcessor()
results = processor.process_data(
    input_path="input_data.csv",
    output_path="./processed_data",
    format_type="csv",  # auto-detected if not specified
    split_ratio=0.8,
    validate_output=True
)
```

**Supported formats:**
- **CSV/Excel**: Automatic column mapping for prompts and responses
- **JSONL**: Chat, completions, and Augmentoolkit formats
- **Text**: Raw text for continued pretraining
- **Augmentoolkit**: Direct compatibility with Augmentoolkit 3.0 output

### Model Management

The model manager handles downloading, caching, and validation:

```python
from mlx_pipeline import ModelManager

manager = ModelManager(cache_dir="./models")

# Download with automatic format detection
model_path = manager.download_model(
    "mlx-community/Mistral-7B-Instruct-v0.3-4bit",
    quantization="4bit"
)

# Get recommendations based on your hardware
recommendations = manager.get_model_recommendations(
    task_type="general",
    memory_limit_gb=64
)
```

### Fine-tuning

The trainer supports both LoRA and full fine-tuning:

```python
from mlx_pipeline import MLXTrainer, TrainingConfig

config = TrainingConfig(
    model_path="./models/mistral-7b",
    data_path="./data",
    output_path="./fine-tuned",
    learning_rate=1e-4,
    lora_rank=8,
    max_iters=1000,
    batch_size=4
)

trainer = MLXTrainer()
results = trainer.train(config)
```

### Inference and Deployment

Deploy models with comprehensive monitoring:

```python
from mlx_pipeline import InferenceEngine, InferenceConfig

config = InferenceConfig(
    max_tokens=512,
    temperature=0.7,
    rate_limit_requests=100
)

engine = InferenceEngine(config)
engine.load_model("./fine-tuned-model")

# Generate single response
result = engine.generate_response(
    "Explain quantum computing",
    config_override={"temperature": 0.5}
)

# Start server
engine.start_server(
    model_path="./fine-tuned-model",
    host="0.0.0.0",
    port=8080
)
```

## 🔧 Configuration

### Training Configuration

Detailed control over the fine-tuning process:

```yaml
# training_config.yaml
model_path: "./models/mistral-7b"
data_path: "./data"
output_path: "./fine-tuned"

# LoRA parameters
lora_rank: 8
lora_alpha: 16
lora_dropout: 0.05
lora_layers: 16

# Training parameters
learning_rate: 1e-4
batch_size: 4
max_iters: 1000
warmup_steps: 100

# Memory management
gradient_checkpointing: false
max_sequence_length: 2048

# Evaluation
eval_every: 100
save_every: 200
early_stopping_patience: 5
```

### Inference Configuration

Production-ready serving options:

```yaml
# inference_config.yaml
max_tokens: 512
temperature: 0.7
top_p: 0.9
repetition_penalty: 1.1

# Performance
batch_size: 1
use_cache: true
max_memory_gb: 32

# Safety
content_filter: false
rate_limit_requests: 100
stop_sequences: ["</response>", "[END]"]
```

## 🔬 Integration with Augmentoolkit

Perfect compatibility with Augmentoolkit 3.0 for synthetic data generation:

```bash
# 1. Generate training data with Augmentoolkit
augmentoolkit --input ./documents --output ./raw_data

# 2. Process for MLX
mlx-prepare-data ./raw_data ./mlx_data --format-type augmentoolkit

# 3. Fine-tune on generated data
mlx-finetune ./models/base-model ./mlx_data ./domain-expert
```

## 📊 Benchmarking

Comprehensive performance testing across multiple dimensions:

```python
from mlx_pipeline import BenchmarkRunner, BenchmarkConfig

config = BenchmarkConfig(
    speed_test=True,
    memory_test=True,
    quality_test=True,
    stress_test=True,
    context_test=True
)

runner = BenchmarkRunner()
results = runner.run_benchmark(
    model_path="./fine-tuned-model",
    config=config
)

# Results include:
# - Tokens per second across different parameters
# - Memory usage patterns and efficiency
# - Response quality and consistency
# - Reliability under sustained load
# - Performance scaling with context length
```

## 🏭 Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential

# Copy and install application
COPY . /app
WORKDIR /app
RUN pip install -e .

# Start server
CMD ["mlx-serve", "./model", "--host", "0.0.0.0", "--port", "8080"]
```

### API Compatibility

The server provides OpenAI-compatible endpoints:

```bash
# Chat completions
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mlx-model",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "temperature": 0.7,
    "max_tokens": 150
  }'

# Text completions
curl -X POST http://localhost:8080/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mlx-model", 
    "prompt": "The future of AI is",
    "max_tokens": 100
  }'
```

### Monitoring

Built-in Prometheus metrics:

```bash
# Get metrics
curl http://localhost:8080/metrics

# Get performance stats
curl http://localhost:8080/stats
```

## 🎯 Performance Expectations

### Mac Studio M1 Ultra (64GB)

| Model Size | Quantization | Memory Usage | Speed (tokens/sec) | Fine-tuning Time (1000 steps) |
|------------|-------------|--------------|-------------------|-------------------------------|
| 1.5B       | 4-bit       | 1-2 GB       | 100-150          | 5-10 minutes                  |
| 7B         | 4-bit       | 4-5 GB       | 50-80            | 20-30 minutes                 |
| 13B        | 4-bit       | 8-10 GB      | 30-40            | 45-60 minutes                 |
| 32B        | 4-bit       | 18-22 GB     | 15-25            | 2-3 hours                     |

## 🐛 Troubleshooting

### Common Issues

**Environment Problems:**
```bash
# Verify Python architecture
python -c "import platform; print(platform.processor())"
# Should return "arm" not "i386"

# Check MLX installation
python -c "import mlx.core as mx; print(mx.metal.get_active_memory())"
```

**Memory Issues:**
```bash
# Check available memory
mlx-setup --check-memory

# Use smaller batch sizes
mlx-finetune ... --batch-size 1 --gradient-accumulation-steps 4
```

**Model Loading Issues:**
```bash
# Validate model format
mlx-download-model ... --validate-model

# Check model compatibility
python -c "from mlx_lm import load; load('model_path')"
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md] for guidelines.

## 📄 License

This project is licensed under the MIT License - see [LICENSE] for details.

## 🙏 Acknowledgments

- **MLX Team** for the excellent framework
- **Augmentoolkit** for inspiration and compatibility
- **Apple** for the M-series chips that make this possible
- **Hugging Face** for model hosting and ecosystem

## 📚 Further Reading

- [MLX Documentation](https://ml-explore.github.io/mlx/build/html/index.html)
- [Augmentoolkit 3.0 Release](https://promptingweekly.substack.com/p/augmentoolkit-30-released)
- [Apple Silicon ML Best Practices](https://developer.apple.com/machine-learning/)

---

**Built for the Apple Silicon AI community 🍎🤖**
