"""Automated tests always use the fake model, never real Bedrock."""

import os

os.environ["RULESTORM_ENV"] = "test"
os.environ["RULESTORM_MODEL"] = "fake"
