"""The fixed schemas sent to Bedrock with structured output, and their warm-up (slice M7d).

Bedrock compiles a grammar the first time it sees a schema (up to about 90 s; cached 24 hours), so
the 5 fixed schemas are warmed once when the server starts, in the background, so no blueprint
or variants request waits for a compile. A warm call asks for 16 tokens: the compile is what is
wanted, not the reply. `RULESTORM_WARM_SCHEMAS=0` turns it off (tests, local work).

Agent decisions and the comparison don't use structured output: each action's `params` is an
open object, which a strict schema forbids, and the comparison's schema changes with each
blueprint, so each call would compile anew (docs/ARCHITECTURE.md, Structured output).
"""

import logging
import threading
import time

from pydantic import BaseModel

from rulestorm import config, llm

log = logging.getLogger("rulestorm.structured")
WARM_TOKENS = 16
WARM_TIMEOUT_S = 120.0  # a first compile can take about 90 s


def fixed_schemas() -> dict[str, type[BaseModel]]:
    """Every schema the pick, fill, variants and search calls send (the search reuses variants)."""
    from rulestorm.blueprint import fill_schema
    from rulestorm.core.model import TEMPLATES_DIR, load_template
    from rulestorm.explore import variants_schema
    from rulestorm.policy import pick_schema

    names = sorted(p.stem for p in TEMPLATES_DIR.glob("*.json"))
    schemas: dict[str, type[BaseModel]] = {"pick": pick_schema(names)}
    for name in names:
        template = load_template(name)
        schemas[f"fill {name}"] = fill_schema(template)
        schemas[f"variants {name}"] = variants_schema(template)
    return schemas


def schema_lines() -> list[str]:
    """One line per schema: its optional and union counts against Bedrock's limits."""
    lines = []
    for name, model in fixed_schemas().items():
        optional, unions = llm.schema_counts(llm.strict_schema(model))
        ok = optional <= llm.MAX_OPTIONAL and unions <= llm.MAX_UNIONS
        lines.append(f"{name}: optional {optional} of {llm.MAX_OPTIONAL}, unions {unions} of {llm.MAX_UNIONS}"
                     f" -> {'ok' if ok else 'OVER THE LIMIT'}")
    return lines


def warm(model: llm.Model) -> list[str]:
    """One short call per schema, so Bedrock compiles each grammar now. Never raises."""
    lines = []
    for name, schema in fixed_schemas().items():
        started = time.monotonic()
        try:
            model.complete("Reply with an example of this JSON.", WARM_TOKENS, WARM_TIMEOUT_S,
                           schema=llm.strict_schema(schema))
            lines.append(f"warmed {name}: {time.monotonic() - started:.1f} s")
        except Exception as exc:  # a warm-up failure only means the first real call compiles it
            lines.append(f"not warmed {name}: {type(exc).__name__}")
            log.warning("schema warm-up failed for %s: %s", name, exc)
    return lines


def warm_in_background() -> threading.Thread | None:
    """At server start: warm every schema in a daemon thread, unless turned off or on the fake model."""
    if config.setting("RULESTORM_WARM_SCHEMAS", "1") == "0" or config.model_id() == "fake":
        return None

    def go() -> None:
        try:
            for line in warm(llm.get_model(max_attempts=1)):
                log.info(line)
        except Exception as exc:  # no model access at start: the first real calls compile instead
            log.warning("schema warm-up skipped: %s", exc)

    thread = threading.Thread(target=go, name="warm-schemas", daemon=True)
    thread.start()
    return thread
