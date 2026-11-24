"""HTTP API served from the EC2 instance."""

from functools import lru_cache

from fastapi import Depends, FastAPI

from rulestorm.policy import Policy, PolicyInput
from rulestorm.store import Store

app = FastAPI(title="RuleStorm")


@lru_cache
def get_store() -> Store:
    return Store()


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/policies", response_model=Policy)
def create_policy(body: PolicyInput, store: Store = Depends(get_store)) -> Policy:
    return store.save_policy(body)
