from datetime import datetime

from inspectra.config.db import db
from inspectra.schemas.inspection_schema import InspectionSchema

inspection_collection = db["inspections"]


def create_inspection(data: dict) -> InspectionSchema:
    data["created_at"] = datetime.utcnow()
    result = inspection_collection.insert_one(data)
    doc = inspection_collection.find_one({"_id": result.inserted_id})
    return InspectionSchema(**doc)


def get_inspections_for_user(user_id):
    docs = inspection_collection.find({"inspector_id": user_id})
    return [InspectionSchema(**d) for d in docs]
