# Augmentoolkit-MLX Integration

A modular repository that connects Augmentoolkit's data generation capabilities with Apple's MLX training framework for efficient end-to-end LLM fine-tuning on Apple Silicon.

## Key Features

- **End-to-end Pipeline**: From raw documents to fine-tuned MLX models
- **Modular Design**: Uses submodules for maintainability and easy updates
- **Format Conversion**: Automatically bridges ShareGPT and MLX formats
- **Unified Configuration**: Single YAML file controls all components
- **Apple Silicon Optimized**: Takes full advantage of unified memory architecture
- **Minimal Code Approach**: Leverages existing tools with thin integration layer

## Getting Started

### Prerequisites

- macOS running on Apple Silicon (M1/M2/M3 series)
- Python 3.11+ installed
- Git with support for submodules

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/augmentoolkit-mlx-pipeline.git
cd augmentoolkit-mlx-pipeline

# Run the setup script
./setup.sh
```

### Basic Usage

1. **Add your documents**: Place your raw text files in the `input_docs/` directory
2. **Configure the pipeline**: Edit `pipeline-config.yaml` for your needs
3. **Run the pipeline**: Execute `python pipeline-orchestrator.py pipeline-config.yaml`
4. **Find your model**: The fine-tuned model will be in `models/final/`

## Repository Structure

```
augmentoolkit-mlx-pipeline/
├── submodules/
│   ├── augmentoolkit/                  # Data generation
│   ├── mlx-tuning-fork/                # Enhanced MLX training
│   └── simple-guide-mlx/               # Basic MLX examples
├── converters/
│   └── augmentoolkit_to_mlx.py         # Format conversion
├── pipeline/
│   └── orchestrator.py                 # End-to-end automation
├── configs/
│   ├── pipeline.yaml                   # Unified config
│   ├── augmentoolkit.yaml              # Data generation config
│   └── mlx_training.yaml               # Training config
├── examples/
│   └── quickstart_tutorial/
├── scripts/
│   └── setup_environment.sh
└── tests/
    └── integration_tests.py
```

## Data Flow Pipeline

1. **INPUT**: Raw text documents (.txt, .md, .pdf)
2. **GENERATION**: Augmentoolkit → ShareGPT format (.jsonl)
3. **CONVERSION**: Format converter → MLX messages format
4. **TRAINING**: MLX-tuning-fork → LoRA fine-tuning
5. **DEPLOYMENT**: Model fusion → Deployable MLX model

## Format Conversion

The core integration challenge is converting between Augmentoolkit's ShareGPT format and MLX's expected format:

| Augmentoolkit (ShareGPT) | MLX (Messages) |
|---------------------------|----------------|
| `'from': 'system'` | `'role': 'system'` |
| `'from': 'human'` | `'role': 'user'` |
| `'from': 'gpt'` | `'role': 'assistant'` |
| `'value': '...'` | `'content': '...'` |

The `converters/augmentoolkit_to_mlx.py` script handles this transformation automatically.

## Advanced Usage

### Using MLX-tuning-fork for Enhanced Training

For advanced training capabilities, the pipeline integrates with mlx-tuning-fork:

```bash
# Run with mlx-tuning-fork integration
python pipeline-orchestrator.py configs/advanced-tuning-fork.yaml
```

### Direct Conversion of Existing Augmentoolkit Data

If you already have Augmentoolkit output files:

```bash
python converters/augmentoolkit-mlx-converter.py path/to/simplified_data.jsonl data/mlx_format/training_data
```

### Hardware-specific Optimization

Edit the `mlx_training` section in `pipeline-config.yaml` to optimize for your specific hardware:

```yaml
hardware:
  use_metal: true
  memory_limit_gb: 60  # Adjust based on your system
  mixed_precision: true
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Augmentoolkit](https://github.com/e-p-armstrong/augmentoolkit) by e-p-armstrong
- [MLX](https://github.com/ml-explore/mlx) by Apple Machine Learning Research
- [mlx-tuning-fork](https://github.com/chimezie/mlx-tuning-fork) by chimezie
- [simple-guide-to-mlx-finetuning](https://github.com/apeatling/simple-guide-to-mlx-finetuning) by apeatling