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
# BRIEF cost check: a 150-call run is about USD 0.28 on DeepSeek V3.2. Reset from measured runs.
DEFAULT_MAX_LLM_CALLS_PER_RUN = 150
# One unit per blueprint or stress-variant request (each up to 2 model calls per step). Set from
# BRIEF's cost check: a blueprint request costs well under USD 0.01 on DeepSeek V3.2.
DEFAULT_MAX_BLUEPRINT_CALLS_PER_DAY = 50
# Daily spend guard for runs (slice 7b): a curfew or attendance term takes 19-23 calls (24 Nov), so
# 20 runs fit well inside 2,000 calls. At about USD 0.002 a call, a full day costs about USD 4.
DEFAULT_MAX_RUNS_PER_DAY = 20
DEFAULT_MAX_LLM_CALLS_PER_DAY = 2000


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



def max_llm_calls_per_run() -> int:
    return int(setting("MAX_LLM_CALLS_PER_RUN", str(DEFAULT_MAX_LLM_CALLS_PER_RUN)))


def _daily_cap(name: str, default: int) -> int:
    """0 is a real value (none today), so only an unset variable takes the default."""
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def max_blueprint_calls_per_day() -> int:
    return _daily_cap("MAX_BLUEPRINT_CALLS_PER_DAY", DEFAULT_MAX_BLUEPRINT_CALLS_PER_DAY)


def max_runs_per_day() -> int:
    return _daily_cap("MAX_RUNS_PER_DAY", DEFAULT_MAX_RUNS_PER_DAY)


def max_llm_calls_per_day() -> int:
    return _daily_cap("MAX_LLM_CALLS_PER_DAY", DEFAULT_MAX_LLM_CALLS_PER_DAY)


load_env_file()
