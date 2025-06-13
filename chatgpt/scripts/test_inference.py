#!/usr/bin/env python3
import time
import typer
from mlx_lm import load, generate

app = typer.Typer()

@app.command()
def test(model_id: str = "mistralai/Mistral-7B-Instruct-v0.3"):
    """Load model and generate a sample response"""
    print(f"Loading model {model_id}...")
    model, tok = load(model_id)
    prompt = "Hello, world!"
    start = time.time()
    response = generate(model, tok, prompt=prompt, max_tokens=50)
    duration = time.time() - start
    print(f"Response: {response}")
    print(f"Time taken: {duration:.2f}s; Tokens generated: {len(tok.encode(response))}")

if __name__ == "__main__":
    app()
