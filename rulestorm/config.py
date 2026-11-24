"""Settings from the environment, with .env as a local fallback.

.env holds settings only, never AWS keys. Values already in the environment win.
"""

import os
from pathlib import Path

DEFAULT_REGION = "ap-southeast-2"
# Team choice after the day-0 smoke test (24 Nov): Mistral Large 3 took 13–84 s per call.
DEFAULT_MODEL_ID = "deepseek.v3.2"
# DeepSeek V3.2's slowest measured call was 9.0 s (docs/BRIEF.md), so 25 s leaves ~3x headroom.
DEFAULT_READ_TIMEOUT_S = 25


def load_env_file(path: str = ".env") -> None:
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


def region() -> str:
    return setting("AWS_REGION", DEFAULT_REGION)


def model_id() -> str:
    """`fake` selects the scripted test model; anything else is a Bedrock model ID."""
    return setting("RULESTORM_MODEL") or setting("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)


def is_test_env() -> bool:
    return setting("RULESTORM_ENV") == "test"


def read_timeout_s() -> float:
    return float(setting("BEDROCK_READ_TIMEOUT", str(DEFAULT_READ_TIMEOUT_S)))


load_env_file()
