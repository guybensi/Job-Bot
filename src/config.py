from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _bool_env(key: str, default: bool = False) -> bool:
    """Read an environment variable and interpret it as a boolean.

    Examples:
        >>> # env: ARBEITNOW_ENABLED=true
        >>> _bool_env("ARBEITNOW_ENABLED", False)
        True

        >>> # env: REMOTIVE_ENABLED=0
        >>> _bool_env("REMOTIVE_ENABLED", True)
        False
    """
    val = os.getenv(key, str(default)).strip().lower()
    return val in ("1", "true", "yes")


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str

    arbeitnow_enabled: bool = True
    remotive_enabled: bool = True

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "il"

    search_interval_hours: int = 2
    log_level: str = "INFO"

    db_path: str = "job_bot.sqlite"

    @property
    def adzuna_enabled(self) -> bool:
        """Return True only when both Adzuna API credentials are configured.

        Examples:
            >>> Config(telegram_bot_token="t", adzuna_app_id="id1", adzuna_app_key="key1").adzuna_enabled
            True

            >>> Config(telegram_bot_token="t", adzuna_app_id="", adzuna_app_key="key1").adzuna_enabled
            False
        """
        return bool(self.adzuna_app_id and self.adzuna_app_key)


def load_config() -> Config:
    """Load application configuration from environment variables (.env file).

    Validates that TELEGRAM_BOT_TOKEN is present and exits if missing.

    Examples:
        >>> # env: TELEGRAM_BOT_TOKEN=123:ABC  ARBEITNOW_ENABLED=true
        >>> cfg = load_config()
        >>> cfg.telegram_bot_token
        '123:ABC'

        >>> # env: TELEGRAM_BOT_TOKEN=   (empty)
        >>> load_config()  # prints error and calls sys.exit(1)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    return Config(
        telegram_bot_token=token,
        arbeitnow_enabled=_bool_env("ARBEITNOW_ENABLED", True),
        remotive_enabled=_bool_env("REMOTIVE_ENABLED", True),
        adzuna_app_id=os.getenv("ADZUNA_APP_ID", "").strip(),
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY", "").strip(),
        adzuna_country=os.getenv("ADZUNA_COUNTRY", "il").strip(),
        search_interval_hours=int(os.getenv("SEARCH_INTERVAL_HOURS", "2")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        db_path=os.getenv("DB_PATH", "job_bot.sqlite").strip(),
    )
