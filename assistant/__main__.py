"""GreenOps assistant (bonus A1).

    .venv/bin/python -m assistant ask "How many AI seats were unused in August 2026?"
    .venv/bin/python -m assistant serve [--port 8787]
    .venv/bin/python -m assistant classify [--force]     # free-text risk → pipeline/bonus/text_risk.json
    .venv/bin/python -m assistant eval [--only ID ...]   # attack suite + example questions
    .venv/bin/python -m assistant energy [LOG ...] [--advisor-estimate]   # energy of our own AI use

Needs OPENAI_API_KEY in .env and a pipeline run (python -m pipeline.run).
"""
from __future__ import annotations

import argparse
import json
import sys

from .settings import load_settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m assistant", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask one question, print the JSON answer")
    a.add_argument("question")
    a.add_argument("--trace", action="store_true", help="also print the tool results")
    sv = sub.add_parser("serve", help="run the HTTP API for the frontend")
    sv.add_argument("--port", type=int)
    c = sub.add_parser("classify", help="classify free texts (prompt-injection screening)")
    c.add_argument("--force", action="store_true", help="re-classify texts already in the cache")
    e = sub.add_parser("eval", help="run the attack suite and the example questions")
    e.add_argument("--only", nargs="*", help="case ids")
    en = sub.add_parser("energy", help="energy and CO2 of our own AI use (token logs + advisor estimate)")
    en.add_argument("logs", nargs="*", help="usage.jsonl files (default: this machine's log)")
    en.add_argument("--advisor-estimate", action="store_true", help="add the saved advisor run, rebuilt from output/advisor/")
    args = p.parse_args(argv)
    s = load_settings()

    if args.cmd == "ask":
        from .agent import Assistant
        ans = Assistant(s).ask(args.question)
        print(json.dumps(ans, ensure_ascii=False, indent=2, default=str))
        return 0 if ans["verified"] else 1
    if args.cmd == "serve":
        import uvicorn
        from .server import create_app
        uvicorn.run(create_app(s), host=s.host, port=args.port or s.port)
        return 0
    if args.cmd == "classify":
        from .classify_text import classify_all
        print(classify_all(s, force=args.force))
        return 0
    if args.cmd == "energy":
        from pathlib import Path
        from .energy import advisor_estimate, energy, from_logs
        logs = [Path(x) for x in args.logs] or [s.usage_log]
        parts = [from_logs([p for p in logs if p.exists()])]
        if args.advisor_estimate:
            parts.append(advisor_estimate())
        print(json.dumps(energy(parts), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "eval":
        from .evals.run import run_suite
        return run_suite(s, only=args.only)
    return 2


if __name__ == "__main__":
    sys.exit(main())
