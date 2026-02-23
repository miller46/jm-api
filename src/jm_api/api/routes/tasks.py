"""Task API endpoints for background job management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.api.deps import get_current_active_user
from jm_api.db.session import get_db
from jm_api.models.task import Task
from jm_api.models.user import User
from jm_api.schemas.task import TaskCreate, TaskResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new background task",
    response_description="The created task",
)
async def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Task:
    """Create a new background task.
    
    The task will be queued for async processing by the worker.
    """
    task = Task(
        type=task_in.type,
        payload=task_in.payload,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    logger.info(
        f"Task created: id={task.id}, type={task.type}, user={current_user.id}"
    )
    return task


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task status and result",
    response_description="Task details including status and result",
)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Task:
    """Get the status and result of a background task."""
    task = db.execute(
        select(Task).where(Task.id == task_id)
    ).scalar_one_or_none()
    
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    
    return task
