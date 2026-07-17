# TalentMatch AI — Full Execution Plan
### From Colab Notebook → Containerized, Live Website

This is the complete, ordered plan to take `Projects.py` (the Colab export) to a live, public
ATS-scoring website. Follow it top to bottom. Each stage has a **goal**, **actions**, and a
**checkpoint** (how you know it worked before moving on).

---

## Stage 0 — Prerequisites

- [ ] Docker Desktop installed and running
- [ ] Git + GitHub account
- [ ] Hugging Face account (free) — for hosting
- [ ] Groq API key (you have this) — keep it out of any file that gets committed
- [ ] Python 3.11 installed locally (for running things outside Docker when convenient)

**Checkpoint:** `docker --version` and `git --version` both work in your terminal.

---

## Stage 1 — Repository Skeleton

**Goal:** Create the target structure before moving any code into it.

```
talentmatch-ai/
├── app.py
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .env.example
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── devices.py
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── llm_parser.py
│   │   └── schema.py
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── taxonomy.py
│   │   └── extractor.py
│   ├── features/
│   │   ├── __init__.py
│   │   └── engineering.py
│   ├── embeddings/
│   │   ├── __init__.py
│   │   └── generator.py
│   ├── ranking/
│   │   ├── __init__.py
│   │   └── ranker.py
│   ├── explainability/
│   │   ├── __init__.py
│   │   └── explainer.py
│   └── pipeline.py
├── data/                  # gitignored — runtime storage
└── tests/
    └── test_pipeline.py
```

**Actions:**
1. `mkdir talentmatch-ai && cd talentmatch-ai && git init`
2. Create all folders/empty `__init__.py` files above.
3. `.gitignore`:
   ```
   .env
   data/
   __pycache__/
   *.pyc
   .venv/
   ```

**Checkpoint:** `git status` shows a clean skeleton, no secrets tracked.

---

## Stage 2 — Strip Colab Coupling, Fix Known Bugs

**Goal:** Make the code runnable as plain Python, with the two concrete bugs fixed.

**Actions:**
1. Delete every occurrence of:
   - `from google.colab import drive` / `drive.mount(...)`
   - `from google.colab import files` / `files.upload()`
   - `from google.colab import userdata` / `userdata.get(...)`
2. Replace secrets access everywhere with:
   ```python
   import os
   GROQ_API_KEY = os.environ["GROQ_API_KEY"]
   ```
3. Replace every hardcoded `/content/drive/MyDrive/...` path with:
   ```python
   from pathlib import Path
   import os
   PROJECT_ROOT = Path(os.environ.get("DATA_DIR", "./data"))
   ```
4. **Fix the ordering bug:** remove the stray `deployment_summary = run_phase10()` call that
   appears *before* `def run_phase10()` is defined (line ~5744 in the original file). Keep only
   the call that comes after the definition.
5. **De-duplicate**: `DeviceManager`, `ProjectConfig`, `SecretsManager`, `DirsAccessor` each
   appear 4-6 times across phases. Keep exactly one canonical version of each in
   `src/devices.py` and `src/config.py`. Delete the rest; update every phase to import from there.
6. Remove all `!pip install ...` notebook-magic lines — consolidate into `requirements.txt`
   (Stage 4).

**Checkpoint:** `python -c "import ast; ast.parse(open('app.py').read())"` style sanity —
no `google.colab` string anywhere: `grep -r "colab" src/ app.py` returns nothing.

---

## Stage 3 — Modularize the 10 Phases into Callable Functions

**Goal:** Each phase becomes a pure function/class with explicit inputs and outputs — no
reliance on notebook global state or files silently written by a "previous cell."

| Phase | Original | New module | Function signature |
|---|---|---|---|
| 1-2 | PDF extraction + LLM parsing | `src/parsing/extractor.py`, `llm_parser.py` | `parse_resume(pdf_path: Path) -> ResumeSchema` |
| 3 | Skill extraction | `src/skills/extractor.py` | `extract_skills(resume: ResumeSchema) -> SkillExtractionResult` |
| 4 | Feature engineering | `src/features/engineering.py` | `build_features(resume, skills) -> CandidateFeatureVector` |
| 5 | Embeddings | `src/embeddings/generator.py` | `embed(text: str) -> np.ndarray` |
| 6 | FAISS retrieval | *(optional, see note)* | only needed for multi-candidate ranking pools |
| 7 | Ranking | `src/ranking/ranker.py` | `rank(features, resume_emb, jd_emb) -> float` |
| 8 | Explainability | `src/explainability/explainer.py` | `explain(score, features) -> dict` |
| 9-10 | Evaluation / model pickling | **dropped from live app** | offline/batch use only |

**Note on Phase 6 (FAISS):** for a single "upload one resume, score against one JD" use case,
you don't need a FAISS index at all — a direct cosine similarity between `resume_emb` and
`jd_emb` is sufficient and much lighter. Keep FAISS only if you plan to rank a resume against
a *pool* of stored candidates. Default: **skip it for v1**, add later if needed.

**Actions:**
1. Move each phase's logic into its module, keyed to the signature above.
2. Default `rank()` to `HeuristicRanker` (LightGBM needs ≥3 JD groups with ≥3 candidates each
   to train meaningfully — not your single-upload case).
3. Write `src/pipeline.py`:
   ```python
   from pathlib import Path
   from src.parsing.llm_parser import parse_resume
   from src.skills.extractor import extract_skills
   from src.features.engineering import build_features
   from src.embeddings.generator import embed
   from src.ranking.ranker import rank
   from src.explainability.explainer import explain

   class InferencePipeline:
       def run(self, resume_pdf_path: Path, job_description_text: str) -> dict:
           resume = parse_resume(resume_pdf_path)
           skills = extract_skills(resume)
           features = build_features(resume, skills)
           resume_emb = embed(resume.raw_text)
           jd_emb = embed(job_description_text)
           score = rank(features, resume_emb, jd_emb)
           explanation = explain(score, features)
           return {
               "score": score,
               "explanation": explanation,
               "parsed_resume": resume.dict(),
           }
   ```

**Checkpoint:** Write `tests/test_pipeline.py` with one real sample PDF and a sample JD string;
run it locally (outside Docker, in a venv) and confirm it returns a score without exceptions:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key
python -m pytest tests/ -v
```

---

## Stage 4 — Trim `requirements.txt`

```
gradio
pymupdf>=1.24.10
easyocr>=1.7.2
groq>=1.5.0
sentence-transformers>=3.0.1
rapidfuzz>=3.9.6
pydantic
pydantic-settings
python-dotenv
numpy
pandas
```
Leave out `faiss-cpu`, `lightgbm`, `shap` for v1 (heavy, not needed for single-candidate
heuristic scoring) — add back later if you expand to multi-candidate ranking pools.

**Checkpoint:** fresh venv install completes without conflicts:
```bash
pip install -r requirements.txt
```

---

## Stage 5 — Build the Gradio UI (`app.py`)

```python
import gradio as gr
from pathlib import Path
from src.pipeline import InferencePipeline

pipeline = InferencePipeline()

def score_resume(pdf_file, job_description):
    if pdf_file is None or not job_description.strip():
        return None, {"error": "Please upload a PDF and paste a job description."}
    result = pipeline.run(Path(pdf_file.name), job_description)
    return result["score"], result["explanation"]

demo = gr.Interface(
    fn=score_resume,
    inputs=[
        gr.File(label="Upload Resume (PDF)", file_types=[".pdf"]),
        gr.Textbox(label="Job Description", lines=10, placeholder="Paste the JD here..."),
    ],
    outputs=[
        gr.Number(label="ATS Match Score"),
        gr.JSON(label="Explanation / Breakdown"),
    ],
    title="TalentMatch AI — Resume ATS Scorer",
    description="Upload a resume PDF and a job description to get a match score with explanation.",
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
```

**Checkpoint:** `python app.py` locally, open `http://localhost:7860`, upload a real resume PDF
+ paste a JD, confirm you get a score and JSON explanation back with no traceback in the terminal.

---

## Stage 6 — Containerize

**`Dockerfile`:**
```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY app.py .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 7860
CMD ["python", "app.py"]
```

**`.dockerignore`:**
```
data/
*.pyc
__pycache__/
.env
.git
tests/
```

**`docker-compose.yml`** (local dev only):
```yaml
services:
  talentmatch:
    build: .
    ports:
      - "7860:7860"
    env_file: .env
    volumes:
      - ./data:/app/data
```

**`.env`** (local only, never committed):
```
GROQ_API_KEY=your_actual_key_here
DATA_DIR=/app/data
```

**Actions:**
```bash
docker build -t talentmatch .
docker compose up
```
Open `http://localhost:7860` again, run the same test as Stage 5, confirm it works identically
inside the container.

**Checkpoint:** container starts, UI loads, a real resume+JD scoring round-trip succeeds, and
`docker compose down` cleans up without errors.

---

## Stage 7 — Push to GitHub

```bash
git add .
git commit -m "TalentMatch AI: modularized pipeline + Gradio UI + Docker"
git branch -M main
git remote add origin https://github.com/<you>/talentmatch-ai.git
git push -u origin main
```

**Checkpoint:** repo is on GitHub, `.env` and `data/` are *not* present in the pushed tree
(verify on github.com — this matters, it's your API key).

---

## Stage 8 — Deploy to Hugging Face Spaces (Docker SDK)

**Actions:**
1. huggingface.co → New Space
   - SDK: **Docker**
   - Hardware: **CPU basic (free)**
   - Visibility: your choice
2. Either:
   - **Option A (simplest):** connect the Space directly to your GitHub repo (Settings → Repository), so it auto-builds from your Dockerfile, or
   - **Option B:** `git remote add space https://huggingface.co/spaces/<you>/talentmatch-ai` and `git push space main`
3. Space Settings → **Repository secrets** → add `GROQ_API_KEY` = your key.
4. Wait for the build log to finish (first Docker build with `easyocr`/`sentence-transformers`
   can take 5-10 min — this is normal).

**Checkpoint:** Space status shows "Running", and the public URL
`https://huggingface.co/spaces/<you>/talentmatch-ai` loads the Gradio UI. Run the same
resume+JD test there.

---

## Stage 9 — Post-deploy verification

- [ ] Upload a real PDF resume, paste a real JD, confirm score + explanation return correctly
- [ ] Upload a scanned/image-only PDF, confirm OCR path works (this is slower — expect it)
- [ ] Check the build/runtime logs in the Space for any warnings about missing packages
- [ ] Confirm `GROQ_API_KEY` is not visible anywhere in logs or the public repo
- [ ] Share the public Space URL and do a cold-start test (visit after it's been idle) to see
      the wake-up delay

**Known limitation to expect:** free CPU Spaces sleep after inactivity and cold-start
(~20-40s) on the next visit. That's the tradeoff of free hosting — not a bug. If you need
true always-on, upgrade the Space hardware tier (~$0.03/hr) later; no code changes required.

---

## Stage 10 — Optional next steps (only if/when needed)

- Add FAISS + a candidate pool if you want to rank many resumes against one JD, not just 1:1
- Add LightGBM ranking once you have ≥3 JDs with ≥3 labeled candidates each
- Split into FastAPI + separate worker container if you outgrow a single Space
- Add a persistent database (e.g. Supabase free tier) if you want to store past scoring results

---

## Quick reference — command summary

```bash
# local dev
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key
python -m pytest tests/ -v
python app.py

# containerized
docker build -t talentmatch .
docker compose up

# deploy
git push origin main
git push space main   # if using HF git remote directly
```
