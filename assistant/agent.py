"""The assistant: tool loop on the OpenAI Responses API, numbers verified
against the tool results before an answer leaves (A1).

    Assistant().ask("How many AI seats were unused in August 2026?")
"""
from __future__ import annotations

import json
from typing import Any, Callable

from pipeline.energy.ai_footprint import footprint, usage_row

from .data import DataStore
from .llm import LLM
from .prompts import ANSWER_SCHEMA, SYSTEM, VERIFY_FEEDBACK
from .settings import Settings, load_settings
from .tools import openai_tools, run_tool
from .verify import check

MAX_HISTORY = 10


class Assistant:
    def __init__(self, settings: Settings | None = None, store: DataStore | None = None, llm: LLM | None = None,
                 tool_runner: Callable[[DataStore, str, dict], Any] = run_tool):
        self.s = settings or load_settings()
        self.store = store or DataStore(self.s)
        self.llm = llm or LLM(self.s)
        self.tools = openai_tools()
        self.run_tool = tool_runner  # the attack suite swaps in a runner that plants injections

    def ask(self, question: str, history: list[dict] | None = None) -> dict:
        """history: earlier turns [{role: user|assistant, content: text}] (text only)."""
        inp: list[dict] = [{"role": h["role"], "content": str(h["content"])}
                           for h in (history or [])[-MAX_HISTORY:] if h.get("role") in ("user", "assistant")]
        inp.append({"role": "user", "content": question})
        trace: list[dict] = []
        usage: list[dict] = []                 # token usage of this answer's LLM calls (→ ai_footprint)
        retries = self.s.verify_retries
        problems: list[str] = []

        for rounds in range(1, self.s.max_tool_rounds + 1):
            last = rounds == self.s.max_tool_rounds  # last round: answer with what is there, no more tools
            resp = self.llm.respond(input=inp, instructions=SYSTEM, schema=ANSWER_SCHEMA, tools=self.tools,
                                    tool_choice="none" if last else "auto")
            if getattr(resp, "usage", None) is not None:
                usage.append(usage_row(self.s.chat_model, "chat", resp.usage))
            inp += [o.model_dump(exclude_none=True) for o in resp.output]
            calls = [o for o in resp.output if o.type == "function_call"]
            if calls:
                for c in calls:
                    inp.append(self._call_tool(c, trace))
                continue
            answer = json.loads(resp.output_text)
            problems = check(answer, trace)
            if problems and retries > 0:
                retries -= 1
                inp.append({"role": "developer", "content": VERIFY_FEEDBACK.format(
                    problems="\n".join(f"- {p}" for p in problems))})
                continue
            return self._finish(answer, trace, problems, rounds, usage)
        return self._finish({"answer": "I could not complete the answer within the allowed number of steps.",
                             "formula": "", "numbers": [], "sources": [], "focus_entity_ids": [],
                             "caveats": [], "ignored_data_instructions": False},
                            trace, ["tool round limit reached"], self.s.max_tool_rounds, usage)

    def _call_tool(self, call: Any, trace: list[dict]) -> dict:
        ref = f"R{len(trace) + 1}"
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        result = self.run_tool(self.store, call.name, args)
        trace.append({"ref": ref, "tool": call.name, "args": args, "result": result})
        return {"type": "function_call_output", "call_id": call.call_id,
                "output": json.dumps({"ref": ref, "tool": call.name, "result": result}, ensure_ascii=False,
                                     default=str)}

    def _finish(self, answer: dict, trace: list[dict], problems: list[str], rounds: int, usage: list[dict]) -> dict:
        known = self.store.entity_ids()
        return {
            **answer,
            "focus_entity_ids": [e for e in answer.get("focus_entity_ids", []) if e in known],
            "verified": not problems,
            "warnings": problems,
            "trace": [{"ref": t["ref"], "tool": t["tool"], "args": t["args"]} for t in trace],
            "model": self.s.chat_model,
            "rounds": rounds,
            # energy of THIS answer, from the token usage the API returned (same factors as the company's AI)
            "ai_footprint": footprint(usage, "measured for this answer (token usage returned by the API)") if usage else None,
        }
