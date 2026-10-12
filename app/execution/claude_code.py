"""Deprecated shim — execution now uses Antigravity CLI (`agy`)."""

from app.execution.antigravity import run_antigravity, run_claude_code

__all__ = ["run_antigravity", "run_claude_code"]
