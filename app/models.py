from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ActionKind = Literal["code_change", "config_change", "doc_change", "task_only"]


class Decision(BaseModel):
    topic: str
    decision: str
    quote: str
    speaker: Optional[str] = None


class ActionItem(BaseModel):
    title: str
    owner: Optional[str] = None
    due: Optional[str] = None
    kind: ActionKind
    target_paths: list[str] = Field(default_factory=list)
    instruction: str
    quote: str


class Extraction(BaseModel):
    summary: str
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class Match(BaseModel):
    prior_id: int
    relation: Literal["reversal", "reaffirmation", "refinement", "unrelated"]
    confidence: float
    explanation: str
    new_quote: str
    prior_quote: str


class JudgeResult(BaseModel):
    matches: list[Match] = Field(default_factory=list)


class Verdict(BaseModel):
    satisfies_instruction: bool
    scope_creep: bool
    issues: list[str] = Field(default_factory=list)
