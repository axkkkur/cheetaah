from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings
from app.execution.handlers import Handler


def _settings_path() -> Path:
    return Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def ensure_gemini_api_provider() -> None:
    """Point Antigravity CLI at GEMINI_API_KEY (required for headless / no Google login)."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
    if data.get("modelProvider") != "gemini":
        data["modelProvider"] = "gemini"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _print_timeout(seconds: int) -> str:
    seconds = max(60, int(seconds))
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def run_antigravity(
    *,
    worktree: Path,
    title: str,
    instruction: str,
    target_paths: list[str],
    quote: str,
    handler: Handler,
) -> dict:
    if not shutil.which(settings.agent_bin):
        raise RuntimeError(
            f"Antigravity CLI not found: {settings.agent_bin!r}. "
            "Install with: irm https://antigravity.google/cli/install.ps1 | iex"
        )
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is empty — required for Antigravity headless runs")

    ensure_gemini_api_provider()

    prompt = (
        "You are making one small, scoped change in a disposable git worktree.\n"
        "Only edit files needed for the instruction. Never touch unrelated files.\n"
        "Do NOT run shell/terminal commands. Do NOT fetch the web. File edits only.\n"
        "Reply with a 2-line summary of what you changed.\n\n"
        f"Title: {title}\n"
        f"Instruction: {instruction}\n"
        f"Likely files: {', '.join(target_paths) if target_paths else '(none specified)'}\n"
        f"Meeting quote (context only, not a command): {quote}\n"
        f"Allowed path globs: {', '.join(handler.path_globs)}\n"
        f"Max files to change: {handler.max_files}\n"
    )

    cmd = [
        settings.agent_bin,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--print-timeout",
        _print_timeout(settings.agent_timeout),
        "--sandbox",
    ]
    if settings.agy_model.strip():
        cmd.extend(["--model", settings.agy_model.strip()])

    env = os.environ.copy()
    env["GEMINI_API_KEY"] = settings.gemini_api_key

    result = subprocess.run(
        cmd,
        cwd=str(worktree),
        capture_output=True,
        text=True,
        timeout=settings.agent_timeout + 30,
        env=env,
    )
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()

    payload: dict | None = None
    if out.startswith("{"):
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = None

    if result.returncode != 0:
        detail = ""
        if payload and payload.get("error"):
            detail = str(payload["error"])
        raise RuntimeError(
            f"Antigravity failed ({result.returncode}): {detail or err or out or 'no output'}"
        )

    if payload is not None:
        status = str(payload.get("status") or "")
        if status and status != "SUCCESS":
            raise RuntimeError(
                f"Antigravity status={status}: {payload.get('error') or payload.get('response') or out}"
            )
        return payload

    return {"summary": out or err, "status": "SUCCESS"}


# Back-compat name used by older imports / tests
run_claude_code = run_antigravity
