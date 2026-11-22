"""Thin wrapper around the OpenAI Responses API.

Every call is logged (model, tokens) to settings.usage_log, which feeds the
«energy of our own AI» statement. Requests are not stored by OpenAI
(store=False); reasoning items are passed back encrypted between tool rounds.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from openai import OpenAI

from .settings import Settings


class LLM:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.s = settings
        self.client = client or OpenAI()

    def respond(self, *, input: list[dict], instructions: str, schema: dict | None = None,
                tools: list[dict] | None = None, tool_choice: str = "auto", model: str | None = None,
                reasoning_effort: str | None = None, purpose: str = "chat") -> Any:
        kwargs: dict[str, Any] = dict(
            model=model or self.s.chat_model, input=input, instructions=instructions,
            reasoning={"effort": reasoning_effort or self.s.reasoning_effort},
            store=False, include=["reasoning.encrypted_content"])
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if schema:
            kwargs["text"] = {"format": {"type": "json_schema", "name": schema["name"], "strict": True,
                                         "schema": schema["schema"]}}
        t0 = time.time()
        resp = self.client.responses.create(**kwargs)
        self._log(kwargs["model"], purpose, resp, time.time() - t0)
        return resp

    def _log(self, model: str, purpose: str, resp: Any, secs: float) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        details = getattr(u, "output_tokens_details", None)
        cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
        row = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "model": model,
               "purpose": purpose, "input_tokens": u.input_tokens, "cached_input_tokens": cached,
               "output_tokens": u.output_tokens,
               "reasoning_tokens": getattr(details, "reasoning_tokens", 0) or 0, "seconds": round(secs, 2)}
        self.s.usage_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.s.usage_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
