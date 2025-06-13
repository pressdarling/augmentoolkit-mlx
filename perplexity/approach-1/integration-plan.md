# Augmentoolkit-MLX Integration Plan

## Repository Structure

```
augmentoolkit-mlx-pipeline/
├── submodules/
│   ├── augmentoolkit/                  # Data generation
│   ├── mlx-tuning-fork/               # Enhanced MLX training
│   └── simple-guide-mlx/              # Basic MLX examples
├── converters/
│   └── augmentoolkit_to_mlx.py        # Format conversion
├── pipeline/
│   └── orchestrator.py               # End-to-end automation
├── configs/
│   ├── pipeline.yaml                 # Unified config
│   ├── augmentoolkit.yaml            # Data generation config
│   └── mlx_training.yaml             # Training config
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

## Format Conversion Mapping

| Augmentoolkit (ShareGPT) | MLX (Messages) |
|---------------------------|----------------|
| `'from': 'system'` | `'role': 'system'` |
| `'from': 'human'` | `'role': 'user'` |
| `'from': 'gpt'` | `'role': 'assistant'` |
| `'value': '...'` | `'content': '...'` |

## Key Integration Components

### 1. Submodules to Include
- **augmentoolkit**: `git@github.com:e-p-armstrong/augmentoolkit.git`
- **mlx-tuning-fork**: `git@github.com:chimezie/mlx-tuning-fork.git`
- **simple-guide-mlx**: `git@github.com:apeatling/simple-guide-to-mlx-finetuning.git`

### 2. Core Files to Create
- `pipeline.py` - Main orchestration script
- `converters/augmentoolkit_to_mlx.py` - Format converter
- `configs/pipeline.yaml` - Unified configuration
- `setup.py` - Installation and dependency management

### 3. Integration Challenges
1. Format conversion between ShareGPT and MLX messages
2. Configuration unification across different tools
3. Pipeline orchestration and error handling
4. Model compatibility and parameter optimization
5. Testing and validation of the integrated pipeline

## Implementation Strategy

Rather than building from scratch, leverage existing components:
- Use Augmentoolkit as-is for data generation
- Extend mlx-tuning-fork for enhanced training capabilities
- Build minimal glue code for format conversion and orchestration
- Create unified configuration system that drives the entire pipeline