# app/models/task.py
from sqlalchemy import Column, Integer, String
from app.db.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    hash = Column(String, index=True)
    charset = Column(String)
    max_length = Column(Integer)
    status = Column(String)
    progress = Column(Integer)
    result = Column(String, nullable=True)

