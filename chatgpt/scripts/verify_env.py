#!/usr/bin/env python3
import platform
import subprocess
import mlx
import mlx.core as mx
from transformers import AutoTokenizer

def main():
    print(f"Python processor: {platform.processor()}")
    arch = subprocess.check_output(['uname', '-p']).decode().strip()
    print(f"System architecture: {arch}")

    # Test MLX import and version
    print(f"MLX version: {mlx.__version__}")

    # Simple tensor operation
    a = mx.array([1, 2, 3], dtype=mx.float32)
    b = mx.array([4, 5, 6], dtype=mx.float32)
    c = a + b
    print(f"MX array addition: {c.tolist()}")

    # Test Metal memory availability
    try:
        metal_mem = mx.metal.get_active_memory()
        print(f"Active Metal memory: {metal_mem / 1e9:.2f} GB")
    except Exception as e:
        print(f"Could not retrieve Metal memory: {e}")

    # Test tokenizer load
    try:
        tok = AutoTokenizer.from_pretrained("mistralai/Mistral-7B-Instruct-v0.3")
        tokens = tok.encode("Hello world")
        print(f"Tokenizer loaded, sample tokens: {tokens[:5]}")
    except Exception as e:
        print(f"Tokenizer test failed: {e}")

if __name__ == "__main__":
    main()
