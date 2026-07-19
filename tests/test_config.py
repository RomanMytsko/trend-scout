import json

from trend_scout import config


def test_feeds_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("RSS_FEEDS_JSON", raising=False)
    assert config.feeds_from_env() == config.DEFAULT_FEEDS


def test_feeds_overridden_from_env(monkeypatch):
    custom = {"My Feed": "https://feed.example.com/rss"}
    monkeypatch.setenv("RSS_FEEDS_JSON", json.dumps(custom))
    assert config.feeds_from_env() == custom


def test_feeds_invalid_json_falls_back(monkeypatch):
    monkeypatch.setenv("RSS_FEEDS_JSON", "{not json")
    assert config.feeds_from_env() == config.DEFAULT_FEEDS


def test_feeds_non_dict_falls_back(monkeypatch):
    monkeypatch.setenv("RSS_FEEDS_JSON", '["just", "a", "list"]')
    assert config.feeds_from_env() == config.DEFAULT_FEEDS
