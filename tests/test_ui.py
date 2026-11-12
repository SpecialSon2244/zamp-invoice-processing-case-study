"""Smoke test: every screen of the Streamlit app renders without an exception."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AP_AGENT_DB", str(tmp_path / "test.db"))


def test_all_screens_render():
    for screen in ["Live run", "Review queue", "Dashboard"]:
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        at.sidebar.radio[0].set_value(screen).run()
        assert not at.exception, f"{screen}: {at.exception}"


def test_live_run_processes_an_invoice():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.checkbox[0].uncheck().run()
    at.button[0].click().run()
    assert not at.exception
    assert any("Auto-approve" in m.value for m in at.markdown)
