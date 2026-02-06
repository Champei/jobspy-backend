from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["jobspy"]
col = db["clean_jobs"]   

def convert_array(arr):
    if isinstance(arr, list) and arr and not isinstance(arr[0], list):
        return [[i, str(v)] for i, v in enumerate(arr)]
    return arr

for job in col.find():
    new_skills = convert_array(job.get("skills", []))
    new_langs = convert_array(job.get("languages", []))

    col.update_one(
        {"_id": job["_id"]},
        {"$set": {
            "skills": new_skills,
            "languages": new_langs
        }}
    )

print("Database converted")
