"""HTTP API served from the EC2 instance."""

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from rulestorm import llm
from rulestorm.policy import BlueprintRecord, Policy, PolicyInput, PolicyNotFound, create_blueprint
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
