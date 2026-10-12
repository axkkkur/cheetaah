from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import audit, db, init_db, now
from app.execution.executor import execute_item
from app.pipeline.orchestrator import run_intake

STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="CHEETAAH")


def require_token(x_token: Annotated[Optional[str], Header()] = None) -> None:
    if not settings.cheetaah_token or x_token != settings.cheetaah_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


TokenDep = Depends(require_token)


@app.on_event("startup")
def startup() -> None:
    if not settings.cheetaah_token:
        raise RuntimeError("CHEETAAH_TOKEN is empty — refuse to start")
    repo = settings.repo_path
    if not repo.exists() or not (repo / ".git").exists():
        # also accept bare/worktree where .git is a file
        git_meta = repo / ".git"
        if not git_meta.exists():
            raise RuntimeError(f"CHEETAAH_REPO is not a git repo: {repo}")
    init_db()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/meetings", dependencies=[TokenDep])
async def create_meeting(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    title: str = Form(""),
):
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio.filename or "rec.webm").suffix or ".webm"
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO meetings (title, audio_path, status, created_at) VALUES (?, ?, ?, ?)",
            (title or "Untitled", None, "uploaded", now()),
        )
        meeting_id = cur.lastrowid
        dest = settings.audio_dir / f"m{meeting_id}{suffix}"
        conn.execute(
            "UPDATE meetings SET audio_path = ? WHERE id = ?",
            (str(dest), meeting_id),
        )
        audit("meeting", meeting_id, "uploaded", {"title": title}, conn=conn)

    with dest.open("wb") as f:
        shutil.copyfileobj(audio.file, f)

    background_tasks.add_task(run_intake, meeting_id)
    return {"id": meeting_id}


@app.get("/api/meetings", dependencies=[TokenDep])
def list_meetings():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, status, error, created_at, summary FROM meetings ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/meetings/{meeting_id}", dependencies=[TokenDep])
def get_meeting(meeting_id: int):
    with db() as conn:
        m = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not m:
            raise HTTPException(404, "Meeting not found")
        decisions = conn.execute(
            "SELECT * FROM decisions WHERE meeting_id = ? ORDER BY id",
            (meeting_id,),
        ).fetchall()
        items = conn.execute(
            "SELECT * FROM action_items WHERE meeting_id = ? ORDER BY id",
            (meeting_id,),
        ).fetchall()

        out_decisions = []
        for d in decisions:
            revs = conn.execute(
                """
                SELECT r.*,
                       pd.decision AS prior_decision,
                       pd.quote AS prior_decision_quote,
                       pd.decided_at AS prior_date,
                       pd.meeting_id AS prior_meeting_id,
                       pm.title AS prior_meeting_title
                FROM reversals r
                JOIN decisions pd ON pd.id = r.prior_decision_id
                LEFT JOIN meetings pm ON pm.id = pd.meeting_id
                WHERE r.new_decision_id = ?
                """,
                (d["id"],),
            ).fetchall()
            dd = dict(d)
            dd["reversals"] = [dict(r) for r in revs]
            out_decisions.append(dd)

        out_items = []
        for it in items:
            ii = dict(it)
            try:
                ii["target_paths"] = json.loads(it["target_paths"] or "[]")
            except json.JSONDecodeError:
                ii["target_paths"] = []
            try:
                ii["result"] = json.loads(it["result"]) if it["result"] else None
            except json.JSONDecodeError:
                ii["result"] = it["result"]
            out_items.append(ii)

    return {
        **dict(m),
        "decisions": out_decisions,
        "action_items": out_items,
    }


@app.get("/api/meetings/{meeting_id}/audit", dependencies=[TokenDep])
def meeting_audit(meeting_id: int):
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM audit
            WHERE (entity = 'meeting' AND entity_id = ?)
               OR (entity = 'action_item' AND entity_id IN
                   (SELECT id FROM action_items WHERE meeting_id = ?))
               OR (entity = 'decision' AND entity_id IN
                   (SELECT id FROM decisions WHERE meeting_id = ?))
            ORDER BY id
            """,
            (meeting_id, meeting_id, meeting_id),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/items/{item_id}/approve", dependencies=[TokenDep])
def approve_item(item_id: int):
    with db() as conn:
        item = conn.execute("SELECT * FROM action_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")
        if item["status"] != "proposed":
            raise HTTPException(400, f"Cannot approve from status {item['status']}")
        conn.execute(
            "INSERT INTO approvals (item_id, decision, ts) VALUES (?, 'approved', ?)",
            (item_id, now()),
        )
        conn.execute(
            "UPDATE action_items SET status = 'approved', updated_at = ? WHERE id = ?",
            (now(), item_id),
        )
        audit("action_item", item_id, "approved", conn=conn)
    return {"ok": True}


@app.post("/api/items/{item_id}/reject", dependencies=[TokenDep])
def reject_item(item_id: int):
    with db() as conn:
        item = conn.execute("SELECT * FROM action_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")
        conn.execute(
            "INSERT INTO approvals (item_id, decision, ts) VALUES (?, 'rejected', ?)",
            (item_id, now()),
        )
        conn.execute(
            "UPDATE action_items SET status = 'rejected', updated_at = ? WHERE id = ?",
            (now(), item_id),
        )
        audit("action_item", item_id, "rejected", conn=conn)
    return {"ok": True}


@app.post("/api/items/{item_id}/execute", dependencies=[TokenDep])
def execute_route(item_id: int, background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_item, item_id)
    return {"ok": True, "queued": True}


@app.get("/api/items/{item_id}/diff", dependencies=[TokenDep])
def item_diff(item_id: int):
    with db() as conn:
        item = conn.execute(
            "SELECT id, branch, commit_sha, diff, status FROM action_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")
    return dict(item)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
