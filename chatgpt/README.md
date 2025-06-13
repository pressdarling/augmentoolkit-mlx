# Domain Expert LLM Pipeline (MLX × Augmentoolkit)

This repository demonstrates a complete **on-device** pipeline for creating domain-expert LLMs on Apple Silicon. It uses:

- **Augmentoolkit 3.0** (synthetic dataset generation)
- **MLX / MLX-LM** (fine-tuning & inference)
- **FastAPI** for an OpenAI-compatible local endpoint
- **uv** for reproducible environment & CLI shortcuts

---

## Quick Start

```bash
# 1. Init & activate environment
uv init --name domain-expert-llm
source .venv/bin/activate

# 2. Add submodule and install deps
git submodule add https://github.com/e-p-armstrong/augmentoolkit libs/augmentoolkit
uv pip install

# 3. Generate dataset
uv run generate  # wraps Augmentoolkit → data/train.jsonl

# 4. Split train/valid (optional)
uv run split

# 5. Fine-tune
uv run train

# 6. Serve API
uv run serve  # http://localhost:8080/v1/chat/completions

# 7. Verify & test
uv run verify        # MLX + Metal smoke test
uv run test_inference  # sample prompt generation
```

---

## Repo Layout

```
.
├── pyproject.toml
├── README.md
├── .gitignore
├── .gitmodules
├── libs/
│   └── augmentoolkit/
├── scripts/
│   ├── verify_env.py
│   ├── generate_dataset.py
│   ├── split_dataset.py
│   ├── finetune.py
│   ├── test_inference.py
│   └── serve_api.py
├── config/
│   ├── at_config.yaml
│   └── lora.yaml
└── data/
    ├── raw.jsonl
    ├── train.jsonl
    └── valid.jsonl
```
