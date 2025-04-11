# app/schemas/task.py
from pydantic import BaseModel, Field
from typing import Optional

class TaskStatus(BaseModel):
    """
    Схема для статуса задачи.
    """
    task_id: int
    status: str  # running/completed/failed
    progress: int = Field(ge=0, le=100)
    result: Optional[str] = Field(default=None)
