"""Slice 11: the deploy files. The real proof runs on the instance (docs/DEPLOY.md); these check
what can go wrong before it gets there."""

import configparser
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
KEY_NAMES = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE")


def settings(path: Path) -> dict[str, str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return dict(ln.split("=", 1) for ln in lines if ln and not ln.startswith("#"))


def test_the_service_runs_as_a_normal_user_on_port_80_with_the_settings_file() -> None:
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(DEPLOY / "rulestorm.service", encoding="utf-8")
    svc = unit["Service"]
    assert svc["User"] == "rulestorm" != "root"
    assert "--port 80" in svc["ExecStart"] and "--workers 1" in svc["ExecStart"]
    assert svc["AmbientCapabilities"] == svc["CapabilityBoundingSet"] == "CAP_NET_BIND_SERVICE"
    assert svc["EnvironmentFile"] == "/etc/rulestorm.env"
    db_dir = str(Path(settings(DEPLOY / "rulestorm.env")["RULESTORM_DB_PATH"]).parent).replace("\\", "/")
    assert svc["WorkingDirectory"] == svc["ReadWritePaths"] == db_dir


def test_the_server_settings_hold_no_keys_and_only_names_the_app_reads() -> None:
    server = settings(DEPLOY / "rulestorm.env")
    assert not set(server) & set(KEY_NAMES)
    known = set(settings(ROOT / ".env.example"))
    assert set(server) <= known, set(server) - known
    assert server["AWS_REGION"] == "ap-southeast-2"


def test_the_installed_package_carries_the_demo_run_and_templates() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert {"templates/*.json", "fixtures/*.json"} <= set(data["tool"]["setuptools"]["package-data"]["rulestorm"])


@pytest.mark.skipif(shutil.which("bash") is None, reason="no bash on this machine")
def test_the_deploy_script_parses_and_refuses_a_missing_or_odd_tag() -> None:
    script = str(DEPLOY / "deploy.sh")
    assert subprocess.run(["bash", "-n", script]).returncode == 0
    for args in ([], ["bad tag; rm -rf /"]):
        done = subprocess.run(["bash", script, *args], capture_output=True, text=True)
        assert done.returncode == 2, done.stderr
