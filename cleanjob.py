from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["jobspy"]

FIELDS_TO_REMOVE = {
    "company_revenue": "",
    "company_description": "",
}

result = db.clean_jobs.update_many(
    {},
    {"$unset": FIELDS_TO_REMOVE}
)

print(f"Updated {result.modified_count} documents")