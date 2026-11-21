"""HTTP API of the assistant for the frontend chat panel (contract: ChatRequest / ChatResponse).

    .venv/bin/python -m assistant serve        # http://127.0.0.1:8787
    POST /api/chat   {"message": "...", "history": [{"role": "user", "content": "..."}, ...]}
    GET  /api/health
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agent import Assistant
from .settings import Settings, load_settings


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or load_settings()
    assistant = Assistant(s)
    app = FastAPI(title="GreenOps assistant", version="0.1")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "model": s.chat_model, "data": s.duckdb_file.exists()}

    @app.post("/api/chat")
    async def chat(req: ChatRequest) -> dict:
        try:
            return await run_in_threadpool(assistant.ask, req.message, [t.model_dump() for t in req.history])
        except Exception as exc:  # noqa: BLE001 (never leak a stack trace to the browser)
            raise HTTPException(status_code=502, detail=f"assistant error: {type(exc).__name__}") from exc

    return app
