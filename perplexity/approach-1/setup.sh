#!/bin/bash
# Setup script for Augmentoolkit-MLX integration repository

set -e

echo "Setting up Augmentoolkit-MLX Integration Repository..."

# Check if we're in the right directory
if [ ! -f "setup.sh" ]; then
    echo "Error: Please run this script from the repository root"
    exit 1
fi

# Initialize git submodules
echo "Initializing git submodules..."
git submodule add https://github.com/e-p-armstrong/augmentoolkit.git submodules/augmentoolkit
git submodule add https://github.com/chimezie/mlx-tuning-fork.git submodules/mlx-tuning-fork  
git submodule add https://github.com/apeatling/simple-guide-to-mlx-finetuning.git submodules/simple-guide-mlx

# Update submodules
git submodule update --init --recursive

# Create directory structure
echo "Creating directory structure..."
mkdir -p data/augmentoolkit_output
mkdir -p data/mlx_format
mkdir -p models/adapters
mkdir -p models/checkpoints  
mkdir -p models/final
mkdir -p logs
mkdir -p input_docs
mkdir -p examples/quickstart_tutorial

# Install Python dependencies
echo "Installing Python dependencies..."
pip install mlx>=0.5.0
pip install mlx-lm>=0.2.3
pip install transformers>=4.41.0
pip install datasets>=2.19.0
pip install tqdm>=4.66
pip install pyyaml>=6.0

# Install mlx-tuning-fork if available
echo "Installing mlx-tuning-fork..."
cd submodules/mlx-tuning-fork
pip install -e .
cd ../..

# Make scripts executable
echo "Making scripts executable..."
chmod +x pipeline-orchestrator.py
chmod +x converters/augmentoolkit-mlx-converter.py

# Create example input document
echo "Creating example input document..."
cat > input_docs/example.txt << 'EOF'
# Machine Learning on Apple Silicon

Apple Silicon, based on ARM architecture, provides unique advantages for machine learning workloads. The unified memory architecture allows for efficient data transfer between CPU and GPU operations.

## MLX Framework

MLX is Apple's machine learning framework designed specifically for Apple Silicon. It provides:
- Unified memory model
- Lazy computation
- Automatic differentiation
- Multi-device support

The framework is particularly well-suited for training and inference of neural networks on Mac devices.

## Fine-tuning with MLX

Fine-tuning large language models on Apple Silicon is now practical thanks to MLX. The framework supports:
- LoRA (Low-Rank Adaptation) training
- Quantized model support
- Efficient memory usage
- Integration with Hugging Face models

This makes it possible to customize models for specific tasks while maintaining good performance on consumer hardware.
EOF

# Create quickstart example
echo "Creating quickstart example..."
cat > examples/quickstart_tutorial/README.md << 'EOF'
# Quickstart Tutorial

This tutorial shows how to use the Augmentoolkit-MLX pipeline to create a custom fine-tuned model.

## Steps

1. Place your documents in `input_docs/`
2. Configure `pipeline-config.yaml` for your needs
3. Run: `python pipeline-orchestrator.py pipeline-config.yaml`
4. Find your trained model in `models/final/`

## Example Commands

```bash
# Convert existing Augmentoolkit output
python converters/augmentoolkit-mlx-converter.py data/augmentoolkit_output/simplified_data_no_R.jsonl data/mlx_format/training_data

# Run just the MLX training part
python -m mlx_lm.lora --train --model mlx-community/Qwen2.5-7B-Instruct-4bit --data data/mlx_format --batch-size 2 --iters 1000
```
EOF

# Create .gitignore
echo "Creating .gitignore..."
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/

# Data and models
data/
models/
logs/
*.jsonl
*.npz
*.safetensors
*.ckpt

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# MLX specific
*.mlx
adapters/
checkpoints/
EOF

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Add your documents to input_docs/"
echo "2. Configure pipeline-config.yaml for your use case"
echo "3. Run: python pipeline-orchestrator.py pipeline-config.yaml"
echo ""
echo "For a quick test, you can use the example document already created in input_docs/example.txt"