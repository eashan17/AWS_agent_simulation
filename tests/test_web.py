"""The UI phase: the built UI (web/dist, committed) is served by FastAPI from the same origin, and
the server finds it even though the package runs from the release's venv."""

import configparser
import re
from pathlib import Path

from fastapi.testclient import TestClient

from rulestorm.api import app

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"


def test_the_built_ui_is_committed_and_its_assets_exist() -> None:
    html = (DIST / "index.html").read_text(encoding="utf-8")
    assets = re.findall(r'(?:src|href)="/(assets/[^"]+)"', html)
    assert assets, "index.html names no built assets"
    for asset in assets:
        assert (DIST / asset).is_file(), asset


def test_the_page_is_served_at_the_root_and_the_api_still_answers() -> None:
    http = TestClient(app)
    page = http.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert '<div id="root">' in page.text
    health = http.get("/api/health")
    assert health.status_code == 200 and health.json() == {"ok": True}
    assert http.get("/api/runs/nope").headers["content-type"].startswith("application/json")


def test_the_server_unit_points_the_app_at_this_releases_ui() -> None:
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(ROOT / "deploy" / "rulestorm.service", encoding="utf-8")
    env = unit["Service"]["Environment"]
    assert env == "RULESTORM_WEB_DIST=/opt/rulestorm/current/web/dist"
    assert unit["Service"]["ExecStart"].startswith("/opt/rulestorm/current/.venv/")
