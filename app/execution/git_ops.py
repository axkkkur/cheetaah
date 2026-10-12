from __future__ import annotations

import secrets
import subprocess
import threading
from pathlib import Path

from app.config import settings

_lock = threading.Lock()


def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else str(settings.repo_path),
        check=check,
        capture_output=True,
        text=True,
    )


def current_branch(repo: Path | None = None) -> str:
    r = git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo or settings.repo_path)
    return r.stdout.strip()


def make_branch_name(meeting_id: int, item_id: int) -> str:
    return f"cheetaah/m{meeting_id}-i{item_id}-{secrets.token_hex(3)}"


def create_worktree(branch: str, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        base = current_branch()
        git("worktree", "add", "-b", branch, str(path), base)
    return path


def cleanup(wt: Path, branch: str, drop_branch: bool) -> None:
    with _lock:
        git("worktree", "remove", "--force", str(wt), check=False)
        if drop_branch:
            git("branch", "-D", branch, check=False)
