"""Endpoints for the barem builder's AI assistant — see app/services/barem_assistant.py.

Both are stateless: the browser holds the chat history and the draft barem
and sends them with every request, and nothing here writes to the library.
"""

from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services import barem_assistant

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    exam: dict[str, Any]
    document_text: str | None = None


@router.post("/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File quá lớn (tối đa 20 MB).")
    try:
        text = barem_assistant.extract_document_text(file.filename or "", data)
    except barem_assistant.AssistantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"filename": file.filename, "chars": len(text), "text": text}


@router.post("/chat")
def chat(body: ChatRequest) -> dict:
    # Plain `def`: the LLM call blocks for up to a few minutes and FastAPI runs
    # sync handlers in its threadpool, so it doesn't stall the event loop.
    try:
        return barem_assistant.chat(
            [m.model_dump() for m in body.messages], body.exam, body.document_text
        )
    except barem_assistant.AssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
