"""API boundary regressions; scoring is mocked so tests never send resume data out."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    calls = []

    class Pipeline:
        def run(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("resume_pdf_path"):
                assert kwargs["resume_pdf_path"].read_bytes().startswith(b"%PDF-")
            result = {
                "overall_score": 75,
                "match_summary": "Example summary",
                "suggestions": [{"issue": "Example", "suggestion": "Rewrite", "priority": "low"}],
            }
            if kwargs.get("return_resume_text"):
                result["extracted_resume_text"] = "Example resume text"
            return result

    stub = types.ModuleType("src.pipeline")
    stub.InferencePipeline = Pipeline
    monkeypatch.setitem(sys.modules, "src.pipeline", stub)
    spec = importlib.util.spec_from_file_location("review_api", ROOT / "api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "UPLOAD_DIR", tmp_path)
    return TestClient(module.app), module, calls


@pytest.mark.parametrize("url", [
    "/..%2FREADME.md", "/..%5CREADME.md", "/..%2F.env", "/%2Egit/config",
    "/package.json", "/src/main.js", "/api/missing",
])
def test_static_route_rejects_non_public_files(api_client, url):
    client, _, _ = api_client
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("url", ["/", "/main.js", "/style.css", "/privacy.html", "/favicon.svg"])
def test_public_site_still_loads(api_client, url):
    client, _, _ = api_client
    assert client.get(url).status_code == 200


def test_coaching_fields_and_resume_text_opt_in(api_client):
    client, _, _ = api_client
    form = {"resume_text": "Example resume", "job_description": "Example job"}
    response = client.post("/api/score", data=form)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["match_summary"] == "Example summary"
    assert response.json()["suggestions"][0]["suggestion"] == "Rewrite"
    assert "extracted_resume_text" not in response.json()
    response = client.post("/api/score", data={**form, "return_resume_text": "true"})
    assert response.json()["extracted_resume_text"] == "Example resume text"


def test_upload_path_is_generated_and_cleaned(api_client):
    client, module, calls = api_client
    paths = []
    for _ in range(2):
        response = client.post("/api/score", data={"job_description": "Example job"},
                               files={"pdf_file": ("../../outside.pdf", b"%PDF-1.7 example", "application/pdf")})
        assert response.status_code == 200
        path = calls[-1]["resume_pdf_path"]
        assert path.parent == module.UPLOAD_DIR
        assert not path.exists()
        paths.append(path)
    assert paths[0] != paths[1]


@pytest.mark.parametrize("filename,content,status", [
    ("resume.txt", b"text", 400), ("resume.pdf", b"not a PDF", 400),
    ("resume.pdf", b"", 400), ("resume.pdf", b"%PDF-" + b"x" * (2 * 1024 * 1024), 413),
], ids=["text-file", "fake-pdf", "empty-pdf", "oversized-pdf"])
def test_invalid_uploads_are_rejected_and_cleaned(api_client, filename, content, status):
    client, module, calls = api_client
    response = client.post("/api/score", data={"job_description": "Example job"},
                           files={"pdf_file": (filename, content, "application/pdf")})
    assert response.status_code == status
    assert not calls
    assert not list(module.UPLOAD_DIR.iterdir())


@pytest.mark.parametrize("form,status", [
    ({"resume_text": "  ", "job_description": "Example job"}, 400),
    ({"resume_text": "resume", "job_description": "x" * 15001}, 413),
    ({"resume_text": "x" * 100001, "job_description": "Example job"}, 413),
])
def test_server_enforces_text_limits(api_client, form, status):
    client, _, calls = api_client
    assert client.post("/api/score", data=form).status_code == status
    assert not calls


def test_internal_errors_do_not_expose_details_and_cleanup(api_client, monkeypatch):
    client, module, _ = api_client

    def fail(**kwargs):
        raise RuntimeError("private-server-path-and-secret")

    monkeypatch.setattr(module.pipeline, "run", fail)
    response = client.post("/api/score", data={"job_description": "Example job"},
                           files={"pdf_file": ("resume.pdf", b"%PDF-1.7 example", "application/pdf")})
    assert response.status_code == 500
    assert "private-server" not in response.text
    assert not list(module.UPLOAD_DIR.iterdir())


def test_health_reports_unavailable_without_exposing_internal_error(api_client, monkeypatch):
    client, _, _ = api_client
    bridge = types.ModuleType("src.bridge")

    def fail():
        raise RuntimeError("private-library-path")

    bridge.engine_version = fail
    monkeypatch.setitem(sys.modules, "src.bridge", bridge)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert "private-library" not in response.text
