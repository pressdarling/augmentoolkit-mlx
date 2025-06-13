#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from mlx_lm import load, generate

class ChatMessage(BaseModel):
    role: str
    content: str

class CompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9

app = FastAPI()
models_cache = {}

@app.post("/v1/models/load")
def load_model(model_id: str):
    try:
        model, tokenizer = load(model_id)
        models_cache[model_id] = {"model": model, "tokenizer": tokenizer}
        return {"status": "loaded", "model": model_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/chat/completions")
def chat_completion(req: CompletionRequest):
    if req.model not in models_cache:
        raise HTTPException(status_code=404, detail="Model not loaded")
    entry = models_cache[req.model]
    prompt = "\n\n".join(f"{m.role.capitalize()}: {m.content}" for m in req.messages) + "\nAssistant:"
    try:
        resp = generate(
            entry["model"], entry["tokenizer"],
            prompt=prompt, max_tokens=req.max_tokens,
            temperature=req.temperature, top_p=req.top_p
        )
        return {"choices": [{"message": {"role": "assistant", "content": resp}}]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
