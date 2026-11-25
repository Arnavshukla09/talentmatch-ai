"""Optional coaching must tolerate malformed model output without external calls."""
import json

import pytest


@pytest.fixture
def coaching(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    from src.suggestions import generator
    return generator


def test_mock_coaching_does_not_require_api_key(coaching, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = coaching.generate_ai_insights([], ["Python"], "Example resume", "Example job")
    assert result["suggestions"][0]["priority"] == "medium"


def test_coaching_validates_fields_and_priority(coaching, monkeypatch):
    monkeypatch.setattr(coaching, "_call_groq", lambda *_: json.dumps({
        "match_summary": "Summary",
        "suggestions": [None, {"issue": 123, "suggestion": "Invalid"},
                        {"issue": "Gap", "suggestion": "Rewrite", "priority": "bad-class"}],
    }))
    result = coaching.generate_ai_insights([], [], "Example resume", "Example job")
    assert result["suggestions"] == [{"issue": "Gap", "suggestion": "Rewrite", "priority": "medium"}]


@pytest.mark.parametrize("output", ["[]", "not json", '{"match_summary": [], "suggestions": "bad"}'])
def test_malformed_coaching_keeps_scoring_available(coaching, monkeypatch, output):
    monkeypatch.setattr(coaching, "_call_groq", lambda *_: output)
    assert coaching.generate_ai_insights([], [], "Example resume", "Example job")["suggestions"] == []
