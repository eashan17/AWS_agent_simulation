"""HTTP API served from the EC2 instance."""

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from rulestorm import llm
from rulestorm.policy import (
    BlueprintInvalid,
    BlueprintNotApproved,
    BlueprintNotFound,
    BlueprintRecord,
    Policy,
    PolicyInput,
    PolicyNotFound,
    approve_blueprint,
    create_blueprint,
    require_approved,
)
from rulestorm.store import Store

app = FastAPI(title="RuleStorm")


@lru_cache
def get_store() -> Store:
    return Store()


def get_blueprint_model() -> llm.Model:
    # Blueprint calls get no boto retries: 2 model calls in total (docs/ARCHITECTURE.md).
    return llm.get_model(max_attempts=1)


class BlueprintRequest(BaseModel):
    policy_id: str = Field(min_length=1, max_length=64)


class RunRequest(BaseModel):
    blueprint_id: str = Field(min_length=1, max_length=64)


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/policies", response_model=Policy)
def create_policy(body: PolicyInput, store: Store = Depends(get_store)) -> Policy:
    return store.save_policy(body)


@app.post("/api/blueprints", response_model=BlueprintRecord)
def post_blueprint(
    body: BlueprintRequest,
    store: Store = Depends(get_store),
    model: llm.Model = Depends(get_blueprint_model),
) -> BlueprintRecord:
    try:
        return create_blueprint(store, body.policy_id, model)
    except PolicyNotFound:
        raise HTTPException(status_code=404, detail="policy not found")


@app.post("/api/blueprints/{blueprint_id}/approve", response_model=BlueprintRecord)
def post_approve(blueprint_id: str, store: Store = Depends(get_store)) -> BlueprintRecord:
    try:
        return approve_blueprint(store, blueprint_id)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintInvalid:
        raise HTTPException(status_code=409, detail="blueprint not valid")


@app.post("/api/blueprints/{blueprint_id}/variants")
def post_variants(
    blueprint_id: str,
    store: Store = Depends(get_store),
    model: llm.Model = Depends(get_blueprint_model),
):
    """Stress variants of an approved blueprint (slice 6c). Each must be approved before it runs."""
    from rulestorm.explore import propose_variants

    try:
        return propose_variants(store, blueprint_id, model)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintNotApproved:
        raise HTTPException(status_code=409, detail="blueprint not approved")


@app.post("/api/runs")
def post_run(body: RunRequest, store: Store = Depends(get_store)) -> dict:
    try:
        require_approved(store, body.blueprint_id)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintNotApproved:
        raise HTTPException(status_code=409, detail="blueprint not approved")
    # Placeholder until slice 7a adds the background runner.
    raise HTTPException(status_code=501, detail="runs not built yet (slice 7a)")
