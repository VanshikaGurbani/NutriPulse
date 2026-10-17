"""Starts the mock API and the Streamlit app for UI capture/measurement.

The mock exists only so screenshots and click counts do not spend real API quota. It is never used for
accuracy or latency numbers.
"""
import contextlib
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIEWPORTS = {"375": {"width": 375, "height": 812}, "1280": {"width": 1280, "height": 800}}


def wait_http(url, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


@contextlib.contextmanager
def running_app(app_port=8601, mock_port=8765, use_mock=True, extra_env=None, script="nutrition_tracker.py"):
    env = dict(os.environ, PYTHONUTF8="1", STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
    tmp = tempfile.mkdtemp(prefix="nutripulse_ux_")
    env["NUTRIPULSE_DB"] = str(Path(tmp) / "feedback.sqlite")
    env["NUTRIPULSE_STATE_DB"] = str(Path(tmp) / "state.sqlite")
    procs = []
    if use_mock:
        env.update(USDA_API_KEY="mock-usda", CALORIENINJAS_KEY="mock-cn",
                   NUTRIPULSE_USDA_BASE=f"http://127.0.0.1:{mock_port}/fdc/v1",
                   NUTRIPULSE_CN_URL=f"http://127.0.0.1:{mock_port}/v1/nutrition")
        procs.append(subprocess.Popen([sys.executable, str(ROOT / "tools/ux/mock_api.py"), str(mock_port)], env=env))
    env.update(extra_env or {})
    procs.append(subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", script, "--server.port", str(app_port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    try:
        wait_http(f"http://127.0.0.1:{app_port}/_stcore/health")
        yield f"http://127.0.0.1:{app_port}"
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            with contextlib.suppress(Exception):
                p.wait(timeout=10)


def wait_app_ready(page, timeout=45000):
    page.wait_for_selector('[data-testid="stApp"]', timeout=timeout)
    page.wait_for_selector('[data-testid="stTabs"], [data-testid="stException"], [data-testid="stAlert"]', timeout=timeout)
    page.wait_for_timeout(800)
