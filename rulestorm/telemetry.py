"""Run metrics and logs in CloudWatch (slice 14).

When a run ends, one JSON line goes to the CloudWatch Logs group named by RULESTORM_LOG_GROUP
(`/rulestorm/app` on the server). The line is in CloudWatch's embedded metric format, so
CloudWatch reads three metrics out of it in the `RuleStorm` namespace: `LLMCalls`, `Tokens` and
`RunDurationSeconds`. No dimensions, so they stay 3 of the 10 free custom metrics, and the server
needs only permission to write to that one log group (no cloudwatch:PutMetricData).

With no log group set (a laptop, the tests), nothing leaves the machine; the line goes to the
local log only. Sending never breaks a run: any CloudWatch error is logged and dropped.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from rulestorm import config

NAMESPACE = "RuleStorm"
METRICS = ("LLMCalls", "Tokens", "RunDurationSeconds")
log = logging.getLogger("rulestorm.telemetry")


def run_line(run_id: str, template: str, status: str, seconds: float, summary: dict | None,
             now_ms: int | None = None) -> dict:
    """The one log line for a finished run. A failed run has no summary: only its duration counts."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    line = {"event": "run_finished", "run_id": run_id, "template": template, "status": status,
            "RunDurationSeconds": round(seconds, 1)}
    units = [{"Name": "RunDurationSeconds", "Unit": "Seconds"}]
    if summary is not None:
        line["LLMCalls"] = summary["llm_calls"]
        line["Tokens"] = summary["input_tokens"] + summary["output_tokens"]
        line["llm_errors"] = summary["llm_errors"]
        line["cap_hits"] = summary["cap_hits"]
        units = [{"Name": "LLMCalls", "Unit": "Count"}, {"Name": "Tokens", "Unit": "Count"}, *units]
    line["_aws"] = {"Timestamp": now_ms,
                    "CloudWatchMetrics": [{"Namespace": NAMESPACE, "Dimensions": [[]], "Metrics": units}]}
    return line


class CloudWatchLogs:
    """Writes lines to one log group, one stream per day (`runs-2026-11-25`)."""

    def __init__(self, group: str) -> None:
        import boto3

        self.group = group
        self.client = boto3.client("logs", region_name=config.region())
        self._streams: set[str] = set()

    def send(self, line: dict) -> None:
        stream = "runs-" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if stream not in self._streams:
            try:
                self.client.create_log_stream(logGroupName=self.group, logStreamName=stream)
            except self.client.exceptions.ResourceAlreadyExistsException:
                pass
            self._streams.add(stream)
        self.client.put_log_events(logGroupName=self.group, logStreamName=stream,
                                   logEvents=[{"timestamp": line["_aws"]["Timestamp"],
                                               "message": json.dumps(line)}])


_sender: Callable[[dict], None] | None = None


def _default_sender() -> Callable[[dict], None] | None:
    global _sender
    group = config.setting("RULESTORM_LOG_GROUP")
    if not group or config.is_test_env():
        return None
    if _sender is None:
        _sender = CloudWatchLogs(group).send
    return _sender


def report_run(run_id: str, template: str, status: str, seconds: float, summary: dict | None,
               send: Callable[[dict], None] | None = None) -> dict:
    """Log the run's line locally and, if a log group is set, in CloudWatch. Never raises."""
    line = run_line(run_id, template, status, seconds, summary)
    log.info("run finished %s", json.dumps({k: v for k, v in line.items() if k != "_aws"}))
    try:
        sender = send or _default_sender()
        if sender is not None:
            sender(line)
    except Exception as exc:  # noqa: BLE001 - metrics must never fail a run
        log.warning("CloudWatch send failed for run %s: %s", run_id, type(exc).__name__)
    return line
