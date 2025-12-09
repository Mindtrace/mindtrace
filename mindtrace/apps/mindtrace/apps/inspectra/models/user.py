from dataclasses import dataclass


@dataclass
class User:
    id: str
    username: str
    password_hash: str
    role_id: str
    is_active: bool = True
