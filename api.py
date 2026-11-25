"""
api.py  —  TalentMatch v2 FastAPI endpoint.

Python responsibilities here:
  - Receive multipart/form-data request
  - Validate inputs
  - Save/cleanup temporary PDF
  - Call InferencePipeline (which calls C++ engine)
  - Return JSON response

Python does NOT compute any scores, rank, or explain anything.
"""

from dotenv import load_dotenv
load_dotenv()

from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import logging
import tempfile
from pathlib import Path

from src.pipeline import InferencePipeline

app = FastAPI(
    title="TalentMatch AI v2",
    description=(
        "Resume Ranking Engine — deterministic ML scoring via a native C++ engine. "
        "Local scoring with optional AI coaching."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = InferencePipeline()

@app.on_event("startup")
async def startup_event():
    from src.embeddings.generator import _EmbeddingModelProvider
    import logging
    logger = logging.getLogger("api")
    logger.info("Pre-warming embedding model on startup...")
    _EmbeddingModelProvider.get()
    logger.info("Embedding model pre-warmed and ready.")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_PDF_BYTES = 2 * 1024 * 1024
MAX_RESUME_CHARS = 100_000
MAX_JD_CHARS = 15_000
logger = logging.getLogger("api")


@app.post("/api/score")
async def score_resume(
    pdf_file: Optional[UploadFile] = File(None),
    job_description: str = Form(...),
    resume_text: Optional[str] = Form(None),
    return_resume_text: bool = Form(False),
):
    """
    Score a resume against a job description.

    Request: multipart/form-data
      - pdf_file (file, optional)    : PDF resume upload
      - job_description (str)        : Job description text
      - resume_text (str, optional)  : Plain text resume (alternative to PDF)
      - return_resume_text (bool)    : Return extracted text for local profile saving

    Response: application/json
    {
      "overall_score":        float,   // 0–100
      "scores": {
        "skills":             float,
        "experience":         float,
        "education":          float,
        "projects":           float,
        "semantic":           float,
        "resume_quality":     float
      },
      "matched_skills":       [str],
      "missing_skills":       [str],
      "partial_skills":       [{"jd_skill": str, "matched_as": str, "confidence": float}],
      "top_positive_factors": [str],
      "top_negative_factors": [str],
      "ranking_method":       str      // "xgboost" | "linear_fallback"
    }
    """
    if not job_description or not job_description.strip():
        raise HTTPException(status_code=400, detail="job_description cannot be empty.")

    if not pdf_file and not resume_text:
        raise HTTPException(status_code=400, detail="Must provide either pdf_file or resume_text.")
    if pdf_file and resume_text:
        raise HTTPException(status_code=400, detail="Provide a PDF or resume text, not both.")
    if len(job_description) > MAX_JD_CHARS:
        raise HTTPException(status_code=413, detail="Job description exceeds 15000 characters.")
    if resume_text is not None and not resume_text.strip():
        raise HTTPException(status_code=400, detail="Resume text cannot be empty.")
    if resume_text and len(resume_text) > MAX_RESUME_CHARS:
        raise HTTPException(status_code=413, detail="Resume text exceeds 100000 characters.")

    temp_path = None
    try:
        if pdf_file:
            if not (pdf_file.filename or "").lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Only PDF files are supported.")
            # Never use a client-supplied filename as a filesystem path.
            with tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, suffix=".pdf", delete=False) as buffer:
                temp_path = Path(buffer.name)
                size = 0
                while chunk := await pdf_file.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise HTTPException(status_code=413, detail="PDF exceeds the 2MB limit.")
                    if size == len(chunk) and not chunk.startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="Upload must contain a valid PDF.")
                    buffer.write(chunk)
                if size == 0:
                    raise HTTPException(status_code=400, detail="PDF cannot be empty.")
            result = pipeline.run(
                resume_pdf_path=temp_path,
                job_description_text=job_description,
                return_resume_text=return_resume_text,
            )
        else:
            result = pipeline.run(
                resume_text=resume_text,
                job_description_text=job_description,
                return_resume_text=return_resume_text,
            )

        # Return the full structured response
        payload = {
            "overall_score":        result.get("overall_score", 0.0),
            "scores":               result.get("scores", {}),
            "matched_skills":       result.get("matched_skills", []),
            "missing_skills":       result.get("missing_skills", []),
            "partial_skills":       result.get("partial_skills", []),
            "top_positive_factors": result.get("top_positive_factors", []),
            "top_negative_factors": result.get("top_negative_factors", []),
            "ranking_method":       result.get("ranking_method", "unknown"),
            "feature_vector":       result.get("feature_vector", {}),
            "match_summary":        result.get("match_summary", ""),
            "suggestions":          result.get("suggestions", []),
        }
        if return_resume_text:
            payload["extracted_resume_text"] = result.get("extracted_resume_text", "")
        return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Resume analysis failed")
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if pdf_file:
            await pdf_file.close()


@app.get("/api/health")
async def health():
    """Health check and engine version."""
    try:
        from src.bridge import engine_version
        version = engine_version()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "api_version": "2.0.0"})
    return {"status": "ok", "engine_version": version, "api_version": "2.0.0"}

# ── Serve built Vite frontend ─────────────────────────────────────────────────
# Falls back to the public files in frontend/ for deployments without a Vite build.

FRONTEND_DIST = BASE_DIR / "frontend/dist"
FRONTEND_RAW  = BASE_DIR / "frontend"

if FRONTEND_DIST.exists():
    _serve_dir = FRONTEND_DIST
elif FRONTEND_RAW.exists():
    _serve_dir = FRONTEND_RAW
else:
    _serve_dir = None

if _serve_dir:
    # Mount static assets subfolder if it exists
    _assets = _serve_dir / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(_serve_dir / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        root = _serve_dir.resolve()
        file_path = (root / full_path).resolve()
        if not file_path.is_relative_to(root) or any(part.startswith(".") or ":" in part for part in Path(full_path).parts):
            raise HTTPException(status_code=404, detail="Not found.")
        # Raw deployments expose only the actual site assets, never source/config files.
        if _serve_dir == FRONTEND_RAW and full_path not in {
            "index.html", "privacy.html", "main.js", "style.css", "favicon.svg"
        }:
            raise HTTPException(status_code=404, detail="Not found.")
        if file_path.is_file():
            return FileResponse(str(file_path))
        raise HTTPException(status_code=404, detail="Not found.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
