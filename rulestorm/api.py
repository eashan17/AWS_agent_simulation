"""HTTP API served from the EC2 instance."""

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from rulestorm import llm
from rulestorm.core.model import shipped_templates
from rulestorm.policy import (
    BlueprintInvalid,
    BlueprintNotApproved,
    BlueprintNotFound,
    BlueprintRecord,
    DailyCapReached,
    Policy,
    PolicyInput,
    PolicyNotFound,
    approve_blueprint,
    create_blueprint,
    require_approved,
)
from rulestorm.store import Store

@lru_cache
def get_store() -> Store:
    return Store()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """At startup, a run left `running` by a restart becomes failed (interrupted) (slice 7b)."""
    from rulestorm.runner import recover_interrupted

    recover_interrupted(app.dependency_overrides.get(get_store, get_store)())
    yield


app = FastAPI(title="RuleStorm", lifespan=lifespan)


def get_blueprint_model() -> llm.Model:
    # Blueprint calls get no boto retries: 2 model calls in total (docs/ARCHITECTURE.md).
    return llm.get_model(max_attempts=1)


def get_agent_model() -> llm.Model | None:
    """The model for a run's people; None means the configured one (tests override this)."""
    return None


def get_runs_dir() -> str:
    return "runs"


class BlueprintRequest(BaseModel):
    policy_id: str = Field(min_length=1, max_length=64)


class RunRequest(BaseModel):
    blueprint_id: str = Field(min_length=1, max_length=64)


class ValuesRequest(BaseModel):
    changes: dict[str, Any] = Field(max_length=30,
        description="value name -> new value; a person's own value (e.g. slack_min) takes {person: value}")


class SearchRequest(BaseModel):
    max_runs: int = Field(6, ge=3, le=9, description="runs the search may use, confirming reruns included")


class ComparisonRequest(BaseModel):
    blueprint_id: str = Field(min_length=1, max_length=64)


class CounterfactualRequest(BaseModel):
    parameter: str = Field(min_length=1, max_length=64)
    value: bool | int | str = Field(description="the new value; checked against the template's range or choices")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/templates")
def get_templates() -> list[dict]:
    """What each template can model, so the input screen shows only supported rules."""
    return [
        {"id": t.id, "version": t.version, "title": t.title, "scope": t.scope,
         "example_input": t.example_input.model_dump()}
        for t in shipped_templates()
    ]


@app.get("/api/templates/{template_id}")
def get_template(template_id: str) -> dict:
    """One template's display words, calendar labels, people, roles and parameter specs (slice U0),
    so every screen reads in that template's own terms."""
    from rulestorm.catalog import TemplateNotFound, template_info

    try:
        return template_info(template_id)
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail="template not found")


@app.get("/api/blueprints/{blueprint_id}", response_model=BlueprintRecord)
def get_blueprint(blueprint_id: str, store: Store = Depends(get_store)) -> BlueprintRecord:
    """A stored blueprint record (slice U0): to reopen the review screen, or show a run's people
    and conditions (a run gives only its `blueprint_id`)."""
    record = store.get_blueprint(blueprint_id)
    if record is None:
        raise HTTPException(status_code=404, detail="blueprint not found")
    return record


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
    except DailyCapReached:
        raise HTTPException(status_code=429, detail="daily blueprint limit reached, try again tomorrow")


@app.patch("/api/blueprints/{blueprint_id}/values", response_model=BlueprintRecord)
def patch_values(blueprint_id: str, body: ValuesRequest, store: Store = Depends(get_store)) -> BlueprintRecord:
    """Correct values of a blueprint before approval (slice 18): each new value is checked by the
    template and becomes the policymaker's fact. An approved blueprint is frozen (409)."""
    from rulestorm.editing import EditRefused, correct_values
    from rulestorm.policy import BlueprintFrozen

    try:
        return correct_values(store, blueprint_id, body.changes)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintFrozen:
        raise HTTPException(status_code=409, detail="blueprint is approved and frozen; build a new one to change it")
    except BlueprintInvalid:
        raise HTTPException(status_code=409, detail="blueprint not valid")
    except EditRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))


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
    """Stress variants of an approved blueprint (slices 6c, L8): only its template's environment
    values change. Each variant must be approved before it runs."""
    from rulestorm.explore import propose_variants

    try:
        return propose_variants(store, blueprint_id, model)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintNotApproved:
        raise HTTPException(status_code=409, detail="blueprint not approved")
    except DailyCapReached:
        raise HTTPException(status_code=429, detail="daily blueprint limit reached, try again tomorrow")
    except ValueError as exc:  # the template changed since the blueprint was made
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/runs")
def post_run(body: RunRequest, store: Store = Depends(get_store),
             model: llm.Model | None = Depends(get_agent_model), runs_dir: str = Depends(get_runs_dir)):
    """Starts a run in the background and answers at once; one run at a time (slice 7a)."""
    from rulestorm.runner import RunActive, start_run

    try:
        run_id = start_run(store, body.blueprint_id, model=model, out_dir=runs_dir)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintNotApproved:
        raise HTTPException(status_code=409, detail="blueprint not approved")
    except RunActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a run is already running", "run_id": exc.run_id})
    except DailyCapReached:
        raise HTTPException(status_code=429, detail="daily run limit reached, try again tomorrow")
    except ValueError as exc:  # the template changed since the blueprint was made
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run_id": run_id, "status": "running"}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, after: int = Query(0, ge=0, description="only timeline events after this seq"),
            store: Store = Depends(get_store)) -> dict:
    """Status, period and the timeline of events so far (pass `after` to get only new ones)."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    run["run_id"] = run.pop("id")  # the same name the POST answers with
    return {**run, "timeline": store.run_events(run_id, after_seq=after)}


@app.post("/api/runs/{run_id}/counterfactual")
def post_counterfactual(run_id: str, body: CounterfactualRequest, store: Store = Depends(get_store),
                        model: llm.Model | None = Depends(get_agent_model), runs_dir: str = Depends(get_runs_dir)):
    """Reruns the run's term with one environment condition changed, everything else matched
    (slice 13). Answers at once with the new run's ID, like POST /api/runs."""
    from rulestorm.counterfactual import CounterfactualRefused, RunNotFound, start_counterfactual
    from rulestorm.runner import RunActive

    try:
        return start_counterfactual(store, run_id, body.parameter, body.value, model=model, out_dir=runs_dir)
    except RunNotFound:
        raise HTTPException(status_code=404, detail="run not found")
    except CounterfactualRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RunActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a run is already running", "run_id": exc.run_id})
    except DailyCapReached:
        raise HTTPException(status_code=429, detail="daily run limit reached, try again tomorrow")
    except ValueError as exc:  # the template changed since the blueprint was made
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/runs/{run_id}/compare/{other_run_id}")
def get_compare(run_id: str, other_run_id: str, store: Store = Depends(get_store)) -> dict:
    """Two finished runs side by side: queue length, waiting time and check results, and every
    value their blueprints differ in (slice 13). Labelled within-model evidence."""
    from rulestorm.counterfactual import CounterfactualRefused, RunNotFinished, RunNotFound, compare

    try:
        return compare(store, run_id, other_run_id)
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {exc}")
    except RunNotFinished as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CounterfactualRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/comparisons")
def post_comparison(body: ComparisonRequest, store: Store = Depends(get_store),
                    model: llm.Model = Depends(get_blueprint_model),
                    agent_model: llm.Model | None = Depends(get_agent_model),
                    runs_dir: str = Depends(get_runs_dir)) -> dict:
    """Strict, flexible and progressive versions of an approved blueprint's policy, run one after
    another under its environment and people (slice 15). Answers after the one model call (15-30 s)
    that proposes them; the runs go on in the background. Follow it with GET /api/comparisons/{id}."""
    from rulestorm.comparison import ComparisonActive, start_comparison
    from rulestorm.runner import RunActive

    try:
        return start_comparison(store, body.blueprint_id, model=model, agent_model=agent_model, out_dir=runs_dir)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintNotApproved:
        raise HTTPException(status_code=409, detail="blueprint not approved")
    except ComparisonActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a comparison is already running",
                                                      "comparison_id": exc.comparison_id})
    except RunActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a run is already running", "run_id": exc.run_id})
    except DailyCapReached as exc:
        raise HTTPException(status_code=429, detail=f"daily limit reached ({exc}), try again tomorrow")
    except ValueError as exc:  # the template changed since the blueprint was made
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/comparisons/{comparison_id}")
def get_comparison_route(comparison_id: str, store: Store = Depends(get_store)) -> dict:
    """The comparison as it stands: each version's policy changes and run, then a trade-off table
    with one column per version and no overall score (slice 15). Labelled within-model evidence."""
    from rulestorm.comparison import ComparisonNotFound, get_comparison

    try:
        return get_comparison(store, comparison_id)
    except ComparisonNotFound:
        raise HTTPException(status_code=404, detail="comparison not found")


@app.post("/api/blueprints/{blueprint_id}/search")
def post_search(blueprint_id: str, body: SearchRequest | None = None, store: Store = Depends(get_store),
                model: llm.Model = Depends(get_blueprint_model),
                agent_model: llm.Model | None = Depends(get_agent_model),
                runs_dir: str = Depends(get_runs_dir)) -> dict:
    """A guided search for the conditions that break an approved policy (slice 16): rounds of 2
    AI-targeted and 1 random scenario, each round told how close the last runs came, stopping at a
    break a rerun repeats. Answers at once; follow it with GET /api/searches/{id}."""
    from rulestorm.comparison import ComparisonActive
    from rulestorm.runner import RunActive
    from rulestorm.search import SearchActive, start_search

    try:
        return start_search(store, blueprint_id, max_runs=(body or SearchRequest()).max_runs, model=model,
                            agent_model=agent_model, out_dir=runs_dir)
    except BlueprintNotFound:
        raise HTTPException(status_code=404, detail="blueprint not found")
    except BlueprintNotApproved:
        raise HTTPException(status_code=409, detail="blueprint not approved")
    except SearchActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a search is already running",
                                                      "search_id": exc.search_id})
    except ComparisonActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a comparison is already running",
                                                      "comparison_id": exc.comparison_id})
    except RunActive as exc:
        return JSONResponse(status_code=409, content={"detail": "a run is already running", "run_id": exc.run_id})
    except DailyCapReached as exc:
        raise HTTPException(status_code=429, detail=f"daily limit reached ({exc}), try again tomorrow")
    except ValueError as exc:  # the template changed since the blueprint was made
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/searches/{search_id}")
def get_search_route(search_id: str, store: Store = Depends(get_store)) -> dict:
    """A search as it stands: its rounds, each scenario's changes, runs and closeness, and the
    result once it ends (slice 16). Labelled within-model evidence."""
    from rulestorm.search import SearchNotFound, get_search

    try:
        return get_search(store, search_id)
    except SearchNotFound:
        raise HTTPException(status_code=404, detail="search not found")


@app.get("/api/runs/{run_id}/adaptations")
def get_adaptations(run_id: str, store: Store = Depends(get_store)) -> dict:
    """How the AI people adapted (slice 19): a real change to their own value and what it did later,
    first actions, and shifts in their stated strategy. Rules over the run's records, no model call."""
    from rulestorm.adaptation import adaptations
    from rulestorm.evidence import template_named

    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    found = adaptations(template_named(run["template"].split("@")[0]), store.run_events(run_id))
    by_person: dict[str, int] = {}
    for a in found:
        by_person[a["person"]] = by_person.get(a["person"], 0) + 1
    return {"run_id": run_id, "status": run["status"], "adaptations": found, "by_person": by_person}


@app.get("/api/runs/{run_id}/findings")
def get_findings(run_id: str, store: Store = Depends(get_store)) -> dict:
    """The problems found in a finished run (slice 8): checks failed and requests still pending at
    a check, each with its chain of event IDs. Empty while the run is going."""
    from rulestorm.runner import findings_of

    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": run_id, "status": run["status"], "findings": findings_of(store, run)}


@app.get("/api/findings/{finding_id}/evidence")
def get_evidence(finding_id: str, store: Store = Depends(get_store)) -> dict:
    """The finding's chain as ordered steps (slice 9): each event's state change, a sentence in the
    template's terms and a label (recorded fact, calculated, AI interpretation); the check step also
    has its count recomputed from the run's events, as it stood and if pending requests were approved."""
    from rulestorm.evidence import evidence, template_named

    finding = store.get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    run = store.get_run(finding["run_id"])
    template = template_named(run["template"].split("@")[0])
    return evidence(finding, store.run_events(finding["run_id"]), template).model_dump()


# The UI: web/dist is built on a laptop, committed, and served from the same origin, so every
# browser call is a same-origin /api/... request. Mounted last, so no /api route is shadowed.
# On the server the package is installed into the release's venv, so the folder is named by
# RULESTORM_WEB_DIST (set in deploy/rulestorm.service); locally it is the checkout's web/dist.
import os as _os  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_WEB_DIST = _Path(_os.environ.get("RULESTORM_WEB_DIST") or _Path(__file__).resolve().parent.parent / "web" / "dist")
if (_WEB_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
