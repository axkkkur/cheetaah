from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    cheetaah_token: str = ""
    cheetaah_repo: str = ""
    cheetaah_data: str = "./data"
    # Best Flash model for transcription + structured extract/judge/verify.
    # If unavailable on your free tier, set GEMINI_MODEL=gemini-2.5-flash
    gemini_model: str = "gemini-3.8-flash"
    cheetaah_test_cmd: str = ""
    # Approve & run executor: Antigravity CLI (agy)
    agent_bin: str = "agy"
    agent_timeout: int = 600
    # Optional: pin agy --model (leave empty to use CLI default)
    agy_model: str = ""

    @property
    def data_dir(self) -> Path:
        return Path(self.cheetaah_data).resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cheetaah.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def worktrees_dir(self) -> Path:
        return self.data_dir / "worktrees"

    @property
    def repo_path(self) -> Path:
        return Path(self.cheetaah_repo).resolve()


settings = Settings()
