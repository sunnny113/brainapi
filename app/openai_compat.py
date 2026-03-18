from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import time
import uuid

from app.services import generate_text
from app.auth import verify_user_api_key

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 200


@router.post("/v1/chat/completions", tags=["OpenAI Compatible"])
async def chat_completions(
    req: ChatRequest,
    authorization: str | None = Header(None),
):

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth format")

    api_key = authorization.replace("Bearer ", "", 1)

    if not verify_user_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    prompt = req.messages[-1].content

    text, model_used, provider_used = generate_text(
        prompt,
        temperature=req.temperature if req.temperature is not None else 0.7,
        max_output_tokens=req.max_tokens if req.max_tokens is not None else 200,
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }