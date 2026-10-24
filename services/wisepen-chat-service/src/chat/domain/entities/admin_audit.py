from datetime import datetime, timezone
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class AdminAuditLog(Document):
    actor_user_id: str
    action: str
    target_type: str
    target_id: str
    changed_fields: list[str]
    before_version: int | None = None
    after_version: int
    reason: str
    request_id: str
    changes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "wisepen_admin_audit_logs"
        indexes = [
            IndexModel([("target_type", ASCENDING), ("target_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("actor_user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("created_at", DESCENDING), ("_id", DESCENDING)]),
        ]
