# TalentMatch AI

**Resume ↔ Job Description ATS Match Scorer**

Upload a resume PDF and paste a job description — get back a 0–1 match score, a plain-English explanation of the strongest signals, and a breakdown of matched, missing, and partially-matched skills.

---

## Overview

TalentMatch AI simulates how an Applicant Tracking System (ATS) evaluates a candidate against a job posting. Instead of a black-box score, it surfaces *why* a resume matches (or doesn't) — the experience signals, skill overlaps, and feature-level scoring that drove the result — so both recruiters and candidates can understand the outcome.

This is the containerized, production-ready version of an original research notebook (`Projects.ipynb`), rebuilt from the ground up per `TalentMatch-AI-Execution-Plan.md`.

## How It Works

1. **Parse** — The resume PDF is parsed and structured using an LLM (Groq).
2. **Extract skills** — Skills are extracted and normalized against a canonical taxonomy.
3. **Engineer features** — Experience, seniority, education, and skill-match signals are computed.
4. **Embed** — Resume and job description text are embedded into vector space.
5. **Rank** — A heuristic ranker combines embedding similarity with the engineered features into a single 0–1 score.
6. **Explain** — A narrative summary and feature breakdown are generated alongside the score.

## Project Structure

```
src/
├── parsing/          # PDF extraction + LLM-based resume structuring
├── skills/           # Skill extraction and taxonomy matching
├── features/         # Feature engineering (experience, education, skill ratios)
├── embeddings/        # Resume/JD text embedding generation
├── ranking/           # HeuristicRanker — combines embeddings + features into a score
├── explainability/     # Human-readable narrative summaries
├── pipeline.py         # Wires all stages together end-to-end
├── config.py            # Environment/config loading (API keys, etc.)
└── devices.py            # Device management (CPU/GPU)
tests/
└── test_pipeline.py       # End-to-end pipeline test
api.py                       # FastAPI backend
frontend/                    # Vite + Vanilla JS frontend application
```

## What Changed vs. the Original Notebook

This project started as a Google Colab notebook and was fully de-Colab'd for production use:

- **No Colab dependencies** — `drive.mount`, `userdata.get`, `files.upload` removed entirely.
- **Single source of truth** — `DeviceManager`, `ProjectConfig`, `DirectoryManager`, secrets access, and `get_logger` were each redefined 3–6 times across the notebook's phase bootstrap cells. Each now has exactly one canonical implementation, in `src/devices.py` and `src/config.py`.
- **Fixed an ordering bug** — `deployment_summary = run_phase10()` was previously called one cell before `run_phase10` was even defined.
- **Modularized** — Phases 1–8 of the notebook are now separate, testable modules (`src/parsing`, `src/skills`, `src/features`, `src/embeddings`, `src/ranking`, `src/explainability`), wired together by `src/pipeline.py`.
- **Simplified ranking for v1** — Phase 6 (FAISS retrieval) and the LightGBM ranker were dropped. A single upload-one-resume/score-against-one-JD flow doesn't need a vector index or a learning-to-rank model trained on candidate pools. `src/ranking/ranker.py`'s `HeuristicRanker` is the default (and only) ranker: **60% cosine similarity** between resume and JD embeddings, **40% spread across fused numeric features**.
- **Dropped offline tooling** — Phases 9–10 (offline evaluation, model pickling/deployment packaging) were batch tooling, not part of the live request-response path, and were removed from the app.

## Getting Started

### Local Development

#### Backend (FastAPI)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key
python api.py
```
*API runs on **http://localhost:8000***

#### Frontend (Vite)
Open a second terminal window:
```bash
cd frontend
npm install
npm run dev
```
*Frontend runs on the local Vite port (usually **http://localhost:5173**)*

Open **http://localhost:5173**.

> **Windows users:** activate the venv with `.venv\Scripts\activate` instead, and set the key with `$env:GROQ_API_KEY="your_key"` (PowerShell) or via a `.env` file (see below).

### Using a `.env` File (recommended)

```bash
cp .env.example .env   # then fill in your real GROQ_API_KEY
```

The app and tests will automatically load this file — no need to `export`/`set` the key manually each session.

### Containerized (Docker)

```bash
cp .env.example .env   # fill in your real GROQ_API_KEY
docker build -t talentmatch .
docker compose up
```

### Deploy to Hugging Face Spaces

1. **New Space** → SDK: **Docker** → Hardware: **CPU basic** (free).
2. Connect it to this GitHub repo, or `git push space main`.
3. **Space Settings → Repository secrets** → add `GROQ_API_KEY`.

> Free CPU Spaces sleep after inactivity and take ~20–40s to cold-start on the next visit — that's expected, not a bug.

## Requirements

- Python 3.11+
- A [Groq API key](https://console.groq.com/keys) (free tier available)

## Documentation

See `TalentMatch-AI-Execution-Plan.md` for the full stage-by-stage build plan this repo was implemented from.

## License

*(Add your license here, e.g. MIT.)*
