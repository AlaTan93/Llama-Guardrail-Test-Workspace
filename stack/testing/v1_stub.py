"""Temporary OpenAI-compatible stub for end-to-end plumbing tests.

- Target calls (no scoring prompt) -> a plain refusal string.
- Judge calls (messages mention score_value) -> valid PyRIT scorer JSON.
"""
import json

from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/v1/chat/completions")
async def completions(request: Request) -> dict:
    body = await request.json()
    messages = body.get("messages", [])
    text = json.dumps(messages)
    if "score_value" in text:
        content = json.dumps(
            {
                "score_value": "false",
                "score_type": "true_false",
                "rationale": "stub judge verdict",
            }
        )
    else:
        content = "I'm sorry, but I can't assist with that request."
    return {
        "id": "stub-1",
        "object": "chat.completion",
        "model": body.get("model", "stub"),
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
