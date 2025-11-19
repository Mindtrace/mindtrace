from inspectra.config.db import db
from inspectra.schemas.user_schema import UserSchema
from inspectra.utils.security import hash_password

users_collection = db["users"]


def get_user_by_username(username: str):
    user = users_collection.find_one({"username": username})
    return UserSchema(**user) if user else None


def create_user(data: dict):
    data["password"] = hash_password(data["password"])
    result = users_collection.insert_one(data)
    user = users_collection.find_one({"_id": result.inserted_id})
    return UserSchema(**user)
