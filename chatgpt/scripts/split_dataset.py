#!/usr/bin/env python3
import random
from pathlib import Path
import typer

app = typer.Typer()

@app.command()
def split(input_file: str = "data/train.jsonl", train_ratio: float = 0.8, seed: int = 42):
    """Split JSONL data into train.jsonl and valid.jsonl"""
    random.seed(seed)
    lines = Path(input_file).read_text().splitlines()
    random.shuffle(lines)
    split_point = int(len(lines) * train_ratio)
    train_lines = lines[:split_point]
    valid_lines = lines[split_point:]
    Path("data/train.jsonl").write_text("\n".join(train_lines) + "\n")
    Path("data/valid.jsonl").write_text("\n".join(valid_lines) + "\n")
    print(f"train.jsonl: {len(train_lines)} examples; valid.jsonl: {len(valid_lines)} examples")

if __name__ == "__main__":
    app()
