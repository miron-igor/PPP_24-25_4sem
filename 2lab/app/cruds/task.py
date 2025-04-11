# app/cruds/task.py
from sqlalchemy import select
from app.db.database import database, task_table
from app.schemas.task import TaskCreate

async def create_task(task: TaskCreate):
    query = task_table.insert().values(
        hash=task.hash,
        status="running"
    )
    return await database.execute(query)

async def get_task(task_id: int):
    query = select(task_table).where(task_table.c.id == task_id)
    return await database.fetch_one(query)
