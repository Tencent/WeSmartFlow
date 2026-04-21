"""
Pydantic 模型公共基础
"""

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
