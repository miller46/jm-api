from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.api.deps import get_current_active_user
from jm_api.db.session import get_db
from jm_api.models.task import Task, TaskStatus
from jm_api.models.user import User
from jm_api.schemas.task import TaskCreate, TaskCreateResponse, TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskCreateResponse, status_code=201)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskCreateResponse:
    """Create a new background task."""
    task = Task(
        type=payload.type,
        payload=payload.payload,
        status=TaskStatus.QUEUED,
        attempts=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskCreateResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str = Path(pattern=r"^[a-zA-Z0-9]{32}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskResponse:
    """Get task status and result."""
    task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)
