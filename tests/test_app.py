"""Smoke test for app.py — launches the real Streamlit process headless and
checks it serves a healthy page. This is the only reliable way to catch
script-level errors (e.g. bad st.* calls) without a browser driver.
"""
import subprocess
import sys
import time
import urllib.request

import pytest

from tests.conditions import has_network

TEST_PORT = 8765


@pytest.mark.skipif(not has_network(), reason="Streamlit's headless server needs to resolve/bind a local port; skip if sandboxed")
def test_app_serves_healthy_page():
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless", "true", "--server.port", str(TEST_PORT),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        health_url = f"http://localhost:{TEST_PORT}/_stcore/health"
        deadline = time.time() + 30
        healthy = False
        last_output = ""
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(health_url, timeout=2) as resp:
                    healthy = resp.status == 200
                    if healthy:
                        break
            except Exception:
                time.sleep(1)

        if not healthy and proc.poll() is not None:
            last_output = proc.stdout.read()

        assert healthy, f"app.py did not become healthy; process output:\n{last_output}"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
