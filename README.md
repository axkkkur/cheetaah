# CHEETAAH

Meeting-to-Execution Agent: record a meeting → Hinglish transcript (Gemini) → decisions & action items (Gemini) → memory/reversal check → human approval → scoped **Antigravity CLI** change on an isolated git worktree → independent verify (Gemini) → commit.

All LLM + execution steps use **one Gemini key**.

## Setup

```bash
cd cheetaah
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`:

- `GEMINI_API_KEY` — required ([AI Studio](https://aistudio.google.com/apikey))
- `GEMINI_MODEL` — default `gemini-3.8-flash` (fallback: `gemini-2.5-flash`)
- `CHEETAAH_TOKEN` — long random string (phone sends it as `X-Token`)
- `CHEETAAH_REPO` — absolute path to the **target** git repo for Approve & run
- Optional: `CHEETAAH_TEST_CMD`, `AGENT_BIN=agy`, `AGENT_TIMEOUT`

### Antigravity CLI (Approve & run)

Windows PowerShell:

```powershell
irm https://antigravity.google/cli/install.ps1 | iex
agy --version
```

CHEETAAH auto-sets `~/.gemini/antigravity-cli/settings.json` → `"modelProvider": "gemini"` and passes your `GEMINI_API_KEY` into `agy` headless runs. No Claude credits needed.

Optional: `ffmpeg` for audio normalization.

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open the URL on your phone. Enter the token once. Record a meeting, watch status, approve action items.

## Demo script (scratch repo)

```bash
# 1. Scratch target repo
mkdir -p /tmp/cheetaah-demo && cd /tmp/cheetaah-demo
git init && echo "# Demo" > README.md && git add README.md && git commit -m init

# 2. Point CHEETAAH_REPO at that path in .env, set CHEETAAH_TOKEN + GEMINI_API_KEY, start server

# 3. From the phone UI: record a meeting that asks to update the README

# 4. When status is awaiting_approval → Approve & run on the doc_change item

# 5. Confirm a cheetaah/m*-i*-* branch exists with one commit; View diff in the UI
```

## Tests

```bash
pytest -q
```

Tests mock Gemini / agent / git — no live API keys required.

## Pipeline

Hard-coded order: `transcribe → extract → memory_check → [APPROVAL GATE] → execute → verify → commit`.

`execute_item()` refuses unless status is `approved` **and** an `approvals` row with `decision='approved'` exists.
