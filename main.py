import os
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from bson.objectid import ObjectId
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="JobSpy Unified API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError(" MONGO_URI Render Environment Variables mai set karle")

client = MongoClient(MONGO_URI)
db = client["jobspy"]
COLLECTION = db["clean_jobs"]

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY Render Environment Variables mai set karle")

llm = Groq(api_key=GROQ_API_KEY)
MODEL = "llama-3.1-8b-instant"

class JobQuery(BaseModel):
    months: int = 1
    limit: int = 50

class SuggestRequest(BaseModel):
    job_id: str
    parsed_resume: Optional[Dict[str, Any]] = None

def objectid_from_days(days: int):
    cutoff_datetime = datetime.utcnow() - timedelta(days=days)
    return ObjectId.from_datetime(cutoff_datetime) 

@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "JobSpy API is live on Render",
        "endpoints": ["/jobs", "/suggest"]
    }

@app.post("/jobs")
def get_jobs(query: JobQuery):
    days = query.months * 30
    cutoff_id = objectid_from_days(days)

    jobs = []
    cursor = COLLECTION.find({"_id": {"$gte": cutoff_id}}).limit(query.limit)
    for job in cursor:
        job_id = str(job.get("_id"))
        job["_id"] = job_id
        if "id" not in job:
            job["id"] = job_id
        jobs.append(job)

    return {
        "months_requested": query.months,
        "limit": query.limit,
        "returned": len(jobs),
        "jobs": jobs
    }

@app.post("/suggest")
def suggest(req: SuggestRequest):

    try:
        job_obj_id = ObjectId(req.job_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    job = COLLECTION.find_one(
        {"_id": job_obj_id},
        {"_id": 0}
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_desc = job.get("description", "")

    resume_text = (
        json.dumps(req.parsed_resume, indent=2)
        if req.parsed_resume
        else "No resume provided"
    )

    prompt = f"""
You are a career coach.

JOB DESCRIPTION:
{job_desc[:2000]}

RESUME (may be empty):
{resume_text}

Return STRICT JSON ONLY:

{{
  "skills_to_add": [strings],
  "projects_to_build": [strings],
  "keywords_to_include": [strings],
  "resume_improvements": [strings]
}}
"""

    try:
        response = llm.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        suggestions_json = response.choices[0].message.content

        suggestions = json.loads(suggestions_json)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "job_title": job.get("title"),
        "company": job.get("company"),
        "suggestions": suggestions
    }
