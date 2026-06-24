from __future__ import annotations

import importlib


def test_default_headless_es_true(monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_HEADLESS", raising=False)
    import app.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.Config.PLAYWRIGHT_HEADLESS is True


def test_headless_false_por_env(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "false")
    import app.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.Config.PLAYWRIGHT_HEADLESS is False


def test_headless_true_por_env(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "true")
    import app.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.Config.PLAYWRIGHT_HEADLESS is True
