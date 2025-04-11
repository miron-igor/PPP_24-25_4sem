# app/db/database.py
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String
from databases import Database

DATABASE_URL = "sqlite:///./test.db"

metadata = MetaData()

task_table = Table(
    "tasks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("hash", String),  # Для /brut_hash
    Column("file_path", String),  # Для /brut_rar
    Column("charset", String),
    Column("max_length", Integer),
    Column("status", String),
    Column("progress", Integer),
    Column("result", String, nullable=True),
)
engine = create_engine(DATABASE_URL)
database = Database(DATABASE_URL)
