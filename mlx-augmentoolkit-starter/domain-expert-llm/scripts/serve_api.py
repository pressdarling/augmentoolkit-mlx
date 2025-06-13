"""FastAPI OpenAI-compatible endpoint using MLX-LM"""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"msg": "MLX-LM local API is running."}
