"""Environment loading. Secrets are read from ``.env`` and never printed."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Name expected by Inspect AI's OpenRouter provider.
OPENROUTER_ENV = "OPENROUTER_API_KEY"
# Name used in this project's local .env.
LOCAL_OPENROUTER_ENV = "OPEN_ROUTER_KEY"


def load_env(dotenv_path: Path | None = None) -> None:
    load_dotenv(dotenv_path or find_dotenv(usecwd=True) or None, override=False)
    if not os.environ.get(OPENROUTER_ENV) and os.environ.get(LOCAL_OPENROUTER_ENV):
        os.environ[OPENROUTER_ENV] = os.environ[LOCAL_OPENROUTER_ENV]


def openrouter_key_present() -> bool:
    return bool(os.environ.get(OPENROUTER_ENV))
