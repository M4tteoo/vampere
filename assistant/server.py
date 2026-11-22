"""HTTP API of the assistant for the frontend chat panel (contract: ChatRequest / ChatResponse).

    .venv/bin/python -m assistant serve        # http://127.0.0.1:8787
    POST /api/chat   {"message": "...", "history": [{"role": "user", "content": "..."}, ...]}
    GET  /api/health
"""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
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


class RateLimit:
    """In-memory caps so a public deployment can't run up the OpenAI bill:
    ASSISTANT_RATE_PER_IP requests per IP per hour (default 30), ASSISTANT_RATE_DAILY in total per day (default 500)."""

    def __init__(self) -> None:
        self.per_ip = int(os.environ.get("ASSISTANT_RATE_PER_IP", 30))
        self.daily = int(os.environ.get("ASSISTANT_RATE_DAILY", 500))
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.day, self.today = "", 0

    def check(self, ip: str) -> None:
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if day != self.day:
            self.day, self.today = day, 0
            self.hits.clear()
        if self.today >= self.daily:
            raise HTTPException(status_code=429, detail="daily question limit reached, try again tomorrow")
        q = self.hits[ip]
        while q and q[0] < now - 3600:
            q.popleft()
        if len(q) >= self.per_ip:
            raise HTTPException(status_code=429, detail="too many questions, try again in a while")
        q.append(now)
        self.today += 1


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or load_settings()
    assistant = Assistant(s)
    limit = RateLimit()
    app = FastAPI(title="GreenOps assistant", version="0.1")
    # "https://*.vampere.pages.dev" style entries allow every subdomain (Cloudflare Pages preview deploys).
    exact = [o for o in s.cors_origins if "*" not in o]
    wild = [re.escape(o).replace(r"\*", "[a-z0-9-]+") for o in s.cors_origins if "*" in o]
    app.add_middleware(CORSMiddleware, allow_origins=exact, allow_origin_regex="|".join(wild) or None,
                       allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "model": s.chat_model, "data": s.duckdb_file.exists()}

    @app.post("/api/chat")
    async def chat(req: ChatRequest, request: Request) -> dict:
        limit.check(client_ip(request))
        try:
            return await run_in_threadpool(assistant.ask, req.message, [t.model_dump() for t in req.history])
        except Exception as exc:  # noqa: BLE001 (never leak a stack trace to the browser)
            raise HTTPException(status_code=502, detail=f"assistant error: {type(exc).__name__}") from exc

    return app
