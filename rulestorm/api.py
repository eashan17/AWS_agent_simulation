"""HTTP API served from the EC2 instance."""

from fastapi import FastAPI

app = FastAPI(title="RuleStorm")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}
