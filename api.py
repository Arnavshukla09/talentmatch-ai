from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import shutil
from pathlib import Path
import os

from src.pipeline import InferencePipeline

app = FastAPI(title="TalentMatch AI API", description="API for scoring resumes against job descriptions")

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = InferencePipeline()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.post("/api/score")
async def score_resume(
    pdf_file: UploadFile = File(...),
    job_description: str = Form(...)
):
    if not pdf_file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    if not job_description or not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description cannot be empty.")

    # Save uploaded file temporarily
    temp_path = UPLOAD_DIR / pdf_file.filename
    try:
        with temp_path.open("wb") as buffer:
            shutil.copyfileobj(pdf_file.file, buffer)

        # Run pipeline
        result = pipeline.run(temp_path, job_description)
        
        return JSONResponse(content={
            "score": result["score"],
            "explanation": result["explanation"]
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        if temp_path.exists():
            os.remove(temp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
