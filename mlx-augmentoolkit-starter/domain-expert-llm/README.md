# domain-expert-llm: MLX  Augmentoolkit

A reproducible Python workspace for gluing **Augmentoolkit3.0** (synthetic data) to **[MLX](https://github.com/ml-explore/mlx)/[MLX_LM](https://github.com/ml-explore/mlx-lm/)** (fine-tuning + inference) on Apple Silicon.

This repo demonstrates:

* **Synthetic dataset generation** with Augmentoolkit (`scripts/generate_dataset.py`)
* **LoRA fine‑tuning** using MLX‑LM (`scripts/finetune.py`)
* **FastAPI OpenAI‑compatible serving** (`scripts/serve_api.py`)

## Quick Start

```bash
mkdir domain-expert-llm && cd $_
uv init --name domain-expert-llm
# Add Augmentoolkit as submodule
git submodule add https://github.com/e-p-armstrong/augmentoolkit libs/augmentoolkit
uv pip install mlx mlx-lm accelerate transformers
# (add others as needed)
python scripts/verify_env.py
```

See `scripts/` and `config/` for entry points.

This repository is very much a work in progress. 