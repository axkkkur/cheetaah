from __future__ import annotations

import json
from typing import Any, Optional

from google import genai
from google.genai import types

from app.config import settings

_gemini: Optional[genai.Client] = None


def get_gemini() -> genai.Client:
    global _gemini
    if _gemini is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is empty")
        _gemini = genai.Client(api_key=settings.gemini_api_key)
    return _gemini


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy JSON schema into a Gemini-friendly shape."""
    s = json.loads(json.dumps(schema))
    s.pop("title", None)
    s.pop("$schema", None)
    return s


def llm_structured(
    system: str,
    user: str,
    tool_name: str,
    schema: dict[str, Any],
    max_tokens: int = 4096,
) -> dict:
    """Structured JSON via Gemini (replaces Claude tool_use)."""
    client = get_gemini()
    prompt = (
        f"Produce a JSON object for `{tool_name}` that matches the response schema exactly.\n\n"
        f"{user}"
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_json_schema=_gemini_schema(schema),
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError(f"Empty Gemini structured response for {tool_name!r}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned invalid JSON for {tool_name!r}: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object for {tool_name!r}, got {type(data).__name__}")
    return data


# Back-compat alias used by older call sites / docs
claude_structured = llm_structured
