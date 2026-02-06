import os
import time
import json
from pymongo import MongoClient
from groq import Groq

BATCH_SIZE = 3
BASE_SLEEP = 2
MAX_RETRIES = 3
MODEL = "llama-3.1-8b-instant"

llm = Groq(api_key=os.getenv("GROQ_API_KEY"))

client = MongoClient("mongodb://localhost:27017")
db = client["jobspy"]
cleaned_jobs = db["clean_jobs"]

def extract_llm_batch(jobs):
    blocks = []
    for i, job in enumerate(jobs):
        desc = (job.get("description_clean") or "")[:1200]
        blocks.append(f"JOB {i+1}:\n{desc}")

    prompt = f"""
You will receive multiple job descriptions.

For EACH job return a JSON object with:
- skills (array)
- experience_years (number or null)
- degree_required (string or null)
- languages (array)
- salary_min (number or null)
- salary_max (number or null)
- employment_type (full-time / part-time / contract / internship / unknown)
- seniority (junior / mid / senior / lead / unknown)
- remote_type (remote / hybrid / onsite / unknown)

Return STRICT JSON ARRAY only.
No explanation.

{chr(10).join(blocks)}
"""

    for attempt in range(MAX_RETRIES):
        try:
            response = llm.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Return STRICT JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=500
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            wait = BASE_SLEEP * (attempt + 1)
            print(f" LLM error , retrying in {wait}s | {e}")
            time.sleep(wait)

    return None

def enrich_llm():
    while True:
        jobs = list(
            cleaned_jobs.find(
                {"llm_enriched": {"$ne": True}},
                limit=BATCH_SIZE
            )
        )

        if not jobs:
            print(" All jobs enriched")
            break

        print(f" Enriching {len(jobs)} jobs")

        data = extract_llm_batch(jobs)
        if not data or len(data) != len(jobs):
            print(" Batch skipped")
            time.sleep(BASE_SLEEP)
            continue

        for job, llm_data in zip(jobs, data):
            cleaned_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {**llm_data, "llm_enriched": True}}
            )

        time.sleep(BASE_SLEEP)

if __name__ == "__main__":
    enrich_llm()
