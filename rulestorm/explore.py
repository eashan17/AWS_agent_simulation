"""Stress variants (slice 6c), waiting for their port to the template format (slice L8).

Slice 6c built them on the old attendance blueprint and the old engine, both removed in slice
L7. Until L8 ports them (variants of the template's `environment` parameters only, the queue
maths and a general "misses until the check fails" figure in the prompt, `outcome()` on general
event types), both entry points refuse clearly instead of running on the wrong format. The 6c
code is at git tag `pre-level2` and in commit 1ee7c39.
"""

from pydantic import BaseModel, Field

from rulestorm.agents import NotPortedYet
from rulestorm.policy import BlueprintRecord, require_approved

NOT_YET = "stress variants on the template format come with slice L8"


class VariantsResult(BaseModel):
    parent_id: str
    status: str  # "valid" (variants proposed; each has its own status) or "invalid"
    errors: list[str] = Field(default_factory=list)
    variants: list[BlueprintRecord] = Field(default_factory=list)
    attempts: int
    seconds: float


class VariantRow(BaseModel):
    blueprint_id: str
    variant: str
    run_id: str | None = None
    status: str
    requests_filed: int = 0
    queue_over_capacity: int = 0
    pending_at_checkpoint: int = 0
    not_eligible: list[str] = Field(default_factory=list)
    broke: bool = False


def propose_variants(store, parent_id: str, model=None) -> VariantsResult:
    require_approved(store, parent_id)  # unknown or unapproved blueprints still get their own answer
    raise NotPortedYet(NOT_YET)


def run_variants(store, parent_id: str, out_dir: str = "runs", on_variant=None) -> list[VariantRow]:
    require_approved(store, parent_id)
    raise NotPortedYet(NOT_YET)
