from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text
from databases import Database
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
metadata = MetaData()

task_table = Table(
    "tasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("celery_task_id", String, nullable=True, index=True),
    Column("file_path", String, nullable=False),
    Column("charset", String, nullable=False),
    Column("max_length", Integer, nullable=False),
    Column("status", String, default="pending", nullable=False, index=True),
    Column("progress", Integer, default=0, nullable=False),
    Column("result", Text, nullable=True),
)

engine = create_engine(DATABASE_URL)
database = Database(DATABASE_URL)