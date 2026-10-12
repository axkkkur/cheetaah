from __future__ import annotations

import json
import subprocess
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable

import yaml

from app.config import settings

ALWAYS_FORBIDDEN = [
    ".git/*",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*secret*",
    "*credentials*",
    ".github/workflows/*",
]


def verify_py(wt: Path, files: list[str]) -> None:
    for f in files:
        if f.endswith(".py"):
            subprocess.run(
                ["python", "-m", "py_compile", f],
                cwd=str(wt),
                check=True,
                capture_output=True,
            )
    if settings.cheetaah_test_cmd.strip():
        subprocess.run(
            settings.cheetaah_test_cmd,
            cwd=str(wt),
            shell=True,
            check=True,
            capture_output=True,
        )


def verify_config(wt: Path, files: list[str]) -> None:
    for f in files:
        path = wt / f
        text = path.read_text(encoding="utf-8")
        lower = f.lower()
        if lower.endswith(".json"):
            json.loads(text)
        elif lower.endswith(".toml"):
            tomllib.loads(text)
        elif lower.endswith((".yml", ".yaml")):
            yaml.safe_load(text)


def verify_doc(wt: Path, files: list[str]) -> None:
    for f in files:
        if not (wt / f).read_text(encoding="utf-8").strip():
            raise RuntimeError(f"Doc file empty: {f}")


@dataclass
class Handler:
    kind: str
    path_globs: list[str]
    max_files: int
    max_diff_lines: int
    verify: Callable[[Path, list[str]], None]
    tools: list[str]
    max_turns: int


HANDLERS: dict[str, Handler] = {
    "code_change": Handler(
        kind="code_change",
        path_globs=[
            "*.py",
            "*.js",
            "*.ts",
            "*.tsx",
            "*.jsx",
            "*.go",
            "*.rs",
            "*.java",
            "*.css",
            "*.html",
            "tests/*",
            "test_*",
        ],
        max_files=8,
        max_diff_lines=400,
        verify=verify_py,
        tools=["Read", "Glob", "Grep", "Edit", "Write"],
        max_turns=30,
    ),
    "config_change": Handler(
        kind="config_change",
        path_globs=[
            "*.json",
            "*.yml",
            "*.yaml",
            "*.toml",
            "*.ini",
            "*.cfg",
            "*.env.example",
        ],
        max_files=3,
        max_diff_lines=80,
        verify=verify_config,
        tools=["Read", "Glob", "Grep", "Edit", "Write"],
        max_turns=12,
    ),
    "doc_change": Handler(
        kind="doc_change",
        path_globs=["*.md", "*.rst", "*.txt", "docs/*"],
        max_files=5,
        max_diff_lines=300,
        verify=verify_doc,
        tools=["Read", "Glob", "Grep", "Edit", "Write"],
        max_turns=12,
    ),
}


def _norm_path(path: str) -> str:
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _forbidden(path: str) -> bool:
    norm = _norm_path(path)
    for pat in ALWAYS_FORBIDDEN:
        if fnmatch(norm, pat) or fnmatch(Path(norm).name, pat):
            return True
        for part in norm.split("/"):
            if fnmatch(part, pat):
                return True
    return False


def in_scope(path: str, handler: Handler) -> bool:
    norm = _norm_path(path)
    if _forbidden(norm):
        return False
    name = Path(norm).name
    for g in handler.path_globs:
        if fnmatch(norm, g) or fnmatch(name, g):
            return True
    return False
