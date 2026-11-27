"""Slice M10: the pre-registered evaluation report over a repeat (fake models; no Bedrock)."""

import time

import pytest

from rulestorm.cli import main
from rulestorm.evaluation import JobNotFound, report, report_lines
from rulestorm.repeats import start_repeats
from test_agents import RoutedModel
from test_repeats import harsh, store  # noqa: F401 - fixtures


@pytest.fixture
def repeat(store, harsh, tmp_path):  # noqa: F811
    record = start_repeats(store, harsh.id, 2, agent_model=RoutedModel(), out_dir=str(tmp_path / "runs"))
    end = time.monotonic() + 60
    while store.get_repeat(record["id"])["status"] == "running":
        assert time.monotonic() < end, "repeat still running"
        time.sleep(0.05)
    return store.get_repeat(record["id"])


def test_report_counts_every_run_and_passes_a_clean_repeat(store, repeat) -> None:  # noqa: F811
    rep = report(store, repeat["id"])
    assert rep["kind"] == "repeat" and len(rep["runs"]) == 2
    assert rep["decisions"] == sum(r["decisions"] for r in rep["runs"]) > 0
    for r in rep["runs"]:
        assert r["status"] == "completed" and r["llm_calls"] is not None
        assert {p["person"] for p in r["people"]} >= {"working"}
        # harsh: the working student fails the check in every run, and the harm says why
        assert any(h["person"] == "working" and h["cause_class"] for h in r["harms"])
    assert set(rep["pass_lines"]) == {"integrity", "calls", "failed_runs", "fill_time"}
    assert rep["passed"] is True
    # 15 sampled decisions at most, the same each time (seeded by the repeat ID), each with its reason
    assert 0 < len(rep["sample"]) <= 15 and all(d["reason"] for d in rep["sample"])
    assert report(store, repeat["id"])["sample"] == rep["sample"]
    out = report_lines(rep)
    assert out[1].startswith("AI-mistake rate:") and out[-1] == "result: PASS"


def test_a_miss_on_any_pass_line_fails_the_report(store, repeat) -> None:  # noqa: F811
    first, second = (r["run_id"] for r in repeat["runs"])
    summary = store.get_run(first)["summary"]
    store.update_run(first, summary={**summary, "llm_calls": 151})
    assert report(store, repeat["id"])["pass_lines"]["calls"]["passed"]  # v2's line: 300
    rep = report(store, repeat["id"], max_calls=150)  # v1's line
    assert rep["pass_lines"]["calls"] == {"value": 151, "limit": 150, "passed": False} and not rep["passed"]

    # false claims plus no-reply over 10% of all decisions
    store.update_run(first, summary={**summary, "false_claims": summary["decisions"], "llm_errors": 1})
    rep = report(store, repeat["id"])
    assert rep["pass_lines"]["integrity"]["passed"] is False and rep["pass_lines"]["calls"]["passed"]

    # a degraded run is a failed run
    store.update_run(first, summary=summary)
    store.update_run(second, status="degraded")
    repeat["runs"][1]["status"] = "degraded"
    store.update_repeat(repeat)
    rep = report(store, repeat["id"])
    assert rep["pass_lines"]["failed_runs"] == {"value": [second], "passed": False}
    assert report_lines(rep)[-1] == "result: FAIL"


def test_unknown_job_and_the_cli(store, repeat, monkeypatch, capsys) -> None:  # noqa: F811
    with pytest.raises(JobNotFound):
        report(store, "R-00000000")
    monkeypatch.setattr("rulestorm.cli.Store", lambda: store)
    main(["eval", "report", repeat["id"]])
    printed = capsys.readouterr().out
    assert f"repeat {repeat['id']}" in printed and "pass lines:" in printed and "result: PASS" in printed
    main(["eval", "report", repeat["id"], "--max-calls", "1"])
    assert "calls: FAIL" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="no repeat or search"):
        main(["eval", "report", "S-00000000"])
