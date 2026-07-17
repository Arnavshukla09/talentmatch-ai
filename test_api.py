import fitz
import httpx
from pathlib import Path
import json

SAMPLE_RESUME_TEXT = """Jordan Ellis
Email: jordan.ellis@example.com | Phone: 555-201-4477
Location: Austin, TX | LinkedIn: linkedin.com/in/jordanellis

SUMMARY
Backend engineer with 6 years building distributed systems in fintech.

EXPERIENCE
Senior Backend Engineer, Northwind Payments, Austin, TX
Jan 2022 - Present
- Led migration of the ledger service from monolith to microservices
- Reduced p99 latency by 40 percent using Redis caching layer

Backend Engineer, Fintech Labs, Austin, TX
Jun 2019 - Dec 2021
- Built the fraud detection pipeline using Kafka and PostgreSQL

EDUCATION
B.S. Computer Science, University of Texas at Austin, 2015 - 2019

SKILLS
Python, Golang, PostgreSQL, Kafka, Redis, AWS, Docker, Node JS

PROJECTS
OpenLedger - Open source double-entry ledger library. github.com/jellis/openledger

CERTIFICATIONS
AWS Certified Solutions Architect - Associate, Amazon, 2023
"""

SAMPLE_JD_TEXT = (
    "Senior Backend Engineer with experience in distributed systems, "
    "Python or Go, PostgreSQL, and cloud deployment on AWS."
)

def create_pdf(filename="demo_resume.pdf"):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 50), SAMPLE_RESUME_TEXT, fontsize=10, fontname="helv")
    document.save(filename)
    document.close()
    return filename

if __name__ == "__main__":
    pdf_path = create_pdf()
    url = "http://localhost:8000/api/score"
    print(f"Testing API at {url}...")
    
    with open(pdf_path, "rb") as f:
        files = {"pdf_file": (pdf_path, f, "application/pdf")}
        data = {"job_description": SAMPLE_JD_TEXT}
        
        # We need a longer timeout for LLM inference (e.g. 60 seconds)
        response = httpx.post(url, files=files, data=data, timeout=60.0)
        
    print(f"Status Code: {response.status_code}")
    try:
        result = response.json()
        print("Full response:", json.dumps(result, indent=2))
    except Exception as e:
        print("Failed to parse JSON response:", response.text)
