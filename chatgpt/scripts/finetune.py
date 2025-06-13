#!/usr/bin/env python3
import yaml
import typer
from mlx_lm import lora

app = typer.Typer()

@app.command()
def train(config_file: str = "config/lora.yaml"):
    """Run LoRA fine-tuning with settings from YAML config."""
    cfg = yaml.safe_load(open(config_file))
    lora(
        model=cfg["model"],
        train=True,
        data=cfg["data"],
        iters=cfg.get("iters", 1000),
        batch_size=cfg.get("batch_size", 4),
        learning_rate=cfg.get("learning_rate", 1e-4),
        lora_layers=cfg.get("lora_layers", 16),
        rank=cfg.get("rank", 8),
        lora_alpha=cfg.get("lora_alpha", 16),
        lora_dropout=cfg.get("lora_dropout", 0.05),
        adapter_path=cfg["adapter_path"]
    )

if __name__ == "__main__":
    app()
