from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [("release_scenario.py", "RELEASE_SCENARIOS_PASS"),("accounting_scenario.py", "ACCOUNTING_REPORTS_PASS"),("stress_scenario.py", "STRESS_20_ON_10_PASS"),("admin_import_scenario.py", "ADMIN_IMPORT_PERMISSIONS_PASS"),("hardening_scenario.py", "HARDENING_VAT_ROLLBACK_PASS"),("upgrade_features_scenario.py", "UPGRADE_FEATURES_PASS")]
@pytest.mark.parametrize(("script", "marker"), SCENARIOS)
def test_release_scenario(script: str, marker: str):
    env = os.environ.copy(); env["PYTHONDONTWRITEBYTECODE"] = "1"; env.setdefault("TERM", "xterm"); env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cp = subprocess.run([sys.executable, str(ROOT / "tests" / "scenarios" / script)], cwd=ROOT, env=env, text=True, capture_output=True, timeout=90)
    assert cp.returncode == 0, f"STDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}"
    assert marker in cp.stdout
