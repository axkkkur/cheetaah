from __future__ import annotations

import json
import traceback

from app.config import settings
from app.db import audit, db, now
from app.execution.antigravity import run_antigravity
from app.execution.git_ops import cleanup, create_worktree, git, make_branch_name
from app.execution.handlers import HANDLERS
from app.execution.verify import llm_verify, rule_checks


def execute_item(item_id: int) -> None:
    with db() as conn:
        item = conn.execute("SELECT * FROM action_items WHERE id = ?", (item_id,)).fetchone()
        approval = conn.execute(
            "SELECT * FROM approvals WHERE item_id = ? AND decision = 'approved' ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()

    if item is None:
        audit("action_item", item_id, "execute_refused", {"reason": "missing_item"})
        return

    if item["status"] != "approved" or approval is None:
        audit(
            "action_item",
            item_id,
            "execute_refused",
            {
                "reason": "not_approved",
                "status": item["status"],
                "has_approval": approval is not None,
            },
        )
        return

    handler = HANDLERS.get(item["kind"])
    if handler is None:
        with db() as conn:
            conn.execute(
                "UPDATE action_items SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                (
                    "failed",
                    json.dumps({"error": f"No handler for kind {item['kind']}"}),
                    now(),
                    item_id,
                ),
            )
            audit("action_item", item_id, "execute_failed", {"reason": "no_handler"}, conn=conn)
        return

    branch = make_branch_name(int(item["meeting_id"]), item_id)
    wt = settings.worktrees_dir / branch.replace("/", "_")
    target_paths = json.loads(item["target_paths"] or "[]")

    with db() as conn:
        conn.execute(
            "UPDATE action_items SET status = ?, branch = ?, updated_at = ? WHERE id = ?",
            ("executing", branch, now(), item_id),
        )
        audit("action_item", item_id, "execute_start", {"branch": branch}, conn=conn)

    try:
        create_worktree(branch, wt)
        agent_result = run_antigravity(
            worktree=wt,
            title=item["title"] or "",
            instruction=item["instruction"] or "",
            target_paths=target_paths,
            quote=item["quote"] or "",
            handler=handler,
        )
        files, staged_diff = rule_checks(wt, handler)
        verdict = llm_verify(item["instruction"] or "", staged_diff)

        msg = (
            f"cheetaah: {item['title']}\n\n"
            f"meeting_id={item['meeting_id']} item_id={item_id}\n"
            f"instruction: {item['instruction']}\n"
            f"quote: {item['quote']}\n"
        )
        git("-c", "user.name=CHEETAAH", "-c", "user.email=cheetaah@localhost", "commit", "-m", msg, cwd=wt)
        sha = git("rev-parse", "HEAD", cwd=wt).stdout.strip()
        diff = git("show", "--stat", "--patch", "HEAD", cwd=wt).stdout

        with db() as conn:
            conn.execute(
                """
                UPDATE action_items
                SET status = ?, commit_sha = ?, diff = ?, result = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "done",
                    sha,
                    diff,
                    json.dumps(
                        {
                            "files": files,
                            "agent": agent_result,
                            "verdict": verdict.model_dump(),
                        }
                    ),
                    now(),
                    item_id,
                ),
            )
            audit(
                "action_item",
                item_id,
                "execute_done",
                {"branch": branch, "sha": sha},
                conn=conn,
            )
        cleanup(wt, branch, drop_branch=False)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        diff = ""
        try:
            if wt.exists():
                git("add", "-A", cwd=wt, check=False)
                diff = git("diff", "--cached", cwd=wt, check=False).stdout or ""
        except Exception:
            pass
        with db() as conn:
            conn.execute(
                """
                UPDATE action_items
                SET status = ?, diff = ?, result = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "failed",
                    diff,
                    json.dumps({"error": err, "trace": traceback.format_exc()}),
                    now(),
                    item_id,
                ),
            )
            audit("action_item", item_id, "execute_failed", {"error": err}, conn=conn)
        try:
            cleanup(wt, branch, drop_branch=True)
        except Exception:
            pass
