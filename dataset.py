from jobspy import scrape_jobs
from pymongo import MongoClient
from datetime import date, datetime
import time
import os
import json
from openai import OpenAI
import time
from openai import RateLimitError

SITE_NAMES = ["indeed", "linkedin", "zip_recruiter"]

SEARCH_TERMS = [
    "software engineer",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "backend developer",
    "frontend developer",
]

COUNTRIES = {
    "united states": ["New York, NY", "San Francisco, CA", "Austin, TX"],
    "united kingdom": ["London", "Manchester"],
    "india": ["Bangalore", "Hyderabad", "Delhi"],
    "canada": ["Toronto", "Vancouver"],
    "australia": ["Sydney", "Melbourne"],
    "germany": ["Berlin", "Munich"],
}

RESULTS_WANTED = 25
HOURS_OLD = 72
SLEEP_SECONDS = 5

MAX_CHARS = 3000
LLM_MODEL = "gpt-4o-mini"

llm = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MONGODB
mongo = MongoClient("mongodb://localhost:27017")
db = mongo["jobspy"]
jobs_col = db["enriched_jobs"]

def remove_datetime(obj):
    if isinstance(obj, dict):
        return {
            k: remove_datetime(v)
            for k, v in obj.items()
            if not isinstance(v, (datetime, date))
        }
    elif isinstance(obj, list):
        return [remove_datetime(v) for v in obj]
    return obj


SYSTEM_PROMPT = """
You extract structured job information.
Return ONLY valid JSON.
Do NOT hallucinate.
Use null if missing.
"""

def build_prompt(description: str) -> str:
    description = description[:MAX_CHARS]

    return f"""
Extract structured information from this job description.

Return JSON in this format:

{{
  "skills": {{
    "programming_languages": [],
    "frameworks": [],
    "databases": [],
    "cloud": [],
    "tools": []
  }},
  "education": {{
    "degree_required": "bachelor | master | phd | none | null"
  }},
  "experience": {{
    "years_min": number | null,
    "years_max": number | null
  }},
  "compensation": {{
    "base_salary_min": number | null,
    "base_salary_max": number | null,
    "currency": "USD | EUR | INR | GBP | null",
    "period": "hourly | monthly | yearly | null",
    "bonus": true | false | null,
    "equity": true | false | null
  }},
  "job_details": {{
    "seniority": "intern | junior | mid | senior | lead | principal | null",
    "employment_type": "full-time | contract | internship | null",
    "contract_length_months": number | null,
    "remote_type": "remote | hybrid | on-site | null",
    "term": "short-term | long-term | permanent | null"
  }},
  "eligibility": {{
    "visa_sponsorship": true | false | null,
    "work_authorization_required": true | false | null
  }}
}}

Job Description:
\"\"\"
{description}
\"\"\"
"""

def extract_with_llm(description, retries=5):
    for attempt in range(retries):
        try:
            response = llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Extract structured job information as JSON."},
                    {"role": "user", "content": description}
                ],
                temperature=0
            )
            return response.choices[0].message.content

        except RateLimitError:
            wait = 20 * (attempt + 1)
            print(f" Rate limited. Sleeping {wait}s")
            time.sleep(wait)

    return None


for country, locations in COUNTRIES.items():
    for location in locations:
        for term in SEARCH_TERMS:
            print(f"\n {country} | {location} | {term}")

            jobs_df = scrape_jobs(
                site_name=SITE_NAMES,
                search_term=term,
                google_search_term=f"{term} jobs in {location}",
                location=location,
                results_wanted=RESULTS_WANTED,
                hours_old=HOURS_OLD,
                country_indeed=country,
            )

            if jobs_df is None or jobs_df.empty:
                print(" No jobs found")
                continue

            records = jobs_df.to_dict(orient="records")

            for job in records:
                job = remove_datetime(job)

                title = job.get("title")
                company = job.get("company")
                description = job.get("description")

                if not isinstance(title, str) or not isinstance(description, str):
                    continue

                # Dedup check
                if jobs_col.find_one({
                    "title": title.lower(),
                    "company": company.lower() if isinstance(company, str) else "",
                    "location": location.lower(),
                    "country": country
                }):
                    continue

                llm_data = extract_with_llm(description)
                if not llm_data:
                    continue

                enriched_doc = {
                    "title": title.lower(),
                    "company": company.lower() if isinstance(company, str) else "",
                    "location": location.lower(),
                    "country": country,
                    "search_term": term,

                    "skills": llm_data.get("skills"),
                    "education": llm_data.get("education"),
                    "experience": llm_data.get("experience"),
                    "compensation": llm_data.get("compensation"),
                    "job_details": llm_data.get("job_details"),
                    "eligibility": llm_data.get("eligibility"),
                }

                jobs_col.insert_one(enriched_doc)

            print(f" Inserted enriched jobs from {location}")
            time.sleep(SLEEP_SECONDS)

