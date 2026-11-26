"""Slice 14: each finished run reports its model calls, tokens and duration as one CloudWatch
embedded-metric log line; sending never breaks a run, and nothing leaves a laptop or a test."""

import configparser
import json
import logging
from pathlib import Path

from rulestorm import telemetry
from rulestorm.runner import run_now
from rulestorm.telemetry import METRICS, NAMESPACE, report_run, run_line
from test_agents import NOTHING, RoutedModel
from test_runner import approved, store  # noqa: F401 - fixtures

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = {"llm_calls": 28, "input_tokens": 40000, "output_tokens": 5000, "llm_errors": 0, "cap_hits": 0}


def test_a_run_line_carries_the_three_metrics_in_the_embedded_metric_format() -> None:
    line = run_line("L-1", "attendance@1", "completed", 27.04, SUMMARY, now_ms=1_700_000_000_000)
    assert (line["LLMCalls"], line["Tokens"], line["RunDurationSeconds"]) == (28, 45000, 27.0)
    spec = line["_aws"]["CloudWatchMetrics"][0]
    assert spec["Namespace"] == NAMESPACE == "RuleStorm"
    assert spec["Dimensions"] == [[]]  # no dimensions: exactly 3 custom metrics
    assert [m["Name"] for m in spec["Metrics"]] == list(METRICS)
    assert line["_aws"]["Timestamp"] == 1_700_000_000_000


def test_a_failed_run_reports_only_its_duration() -> None:
    line = run_line("L-2", "attendance@1", "failed", 3.0, None)
    assert "LLMCalls" not in line and line["status"] == "failed"
    assert [m["Name"] for m in line["_aws"]["CloudWatchMetrics"][0]["Metrics"]] == ["RunDurationSeconds"]


def test_a_cloudwatch_failure_is_logged_and_never_raised(caplog) -> None:
    def broken(line):
        raise ConnectionError("no route to logs.ap-southeast-2.amazonaws.com")

    with caplog.at_level(logging.WARNING, logger="rulestorm.telemetry"):
        line = report_run("L-3", "attendance@1", "completed", 1.0, SUMMARY, send=broken)
    assert line["LLMCalls"] == 28
    assert "CloudWatch send failed for run L-3: ConnectionError" in caplog.text


def test_nothing_is_sent_in_tests_even_with_a_log_group_set(monkeypatch) -> None:
    monkeypatch.setenv("RULESTORM_LOG_GROUP", "/rulestorm/app")
    assert telemetry._default_sender() is None


def test_a_finished_run_sends_one_line_with_its_own_counts(store, approved, monkeypatch, tmp_path) -> None:  # noqa: F811
    sent = []
    monkeypatch.setattr(telemetry, "_default_sender", lambda: sent.append)
    run_id = run_now(store, approved.id, RoutedModel(lambda person, prompt: NOTHING), out_dir=str(tmp_path))
    run = store.get_run(run_id)
    # Only this run's lines: a background run another test started may finish meanwhile and
    # report too (seen 26 Nov, once terms grew by the check-result decisions).
    mine = [line for line in sent if line["run_id"] == run_id]
    assert len(mine) == 1
    line = mine[0]
    assert (line["run_id"], line["status"]) == (run_id, run["status"])
    assert line["LLMCalls"] == run["summary"]["llm_calls"] > 0
    assert line["Tokens"] == run["summary"]["input_tokens"] + run["summary"]["output_tokens"]
    json.dumps(line)  # one JSON message


def test_the_server_names_the_log_group() -> None:
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(ROOT / "deploy" / "rulestorm.service", encoding="utf-8")
    env = dict(pair.split("=", 1) for pair in unit["Service"]["Environment"].split())
    assert env["RULESTORM_LOG_GROUP"] == "/rulestorm/app"
