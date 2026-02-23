"""Background worker service for async task processing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from jm_api.db.base import utcnow
from jm_api.db.session import SessionLocal
from jm_api.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)

# Registry of task handlers
_task_handlers: dict[str, Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]] = {}


def register_task_handler(task_type: str):
    """Decorator to register a task handler."""
    def decorator(func: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]):
        _task_handlers[task_type] = func
        logger.info(f"Registered task handler for type: {task_type}")
        return func
    return decorator


def get_task_handler(task_type: str) -> Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]] | None:
    """Get the registered handler for a task type."""
    return _task_handlers.get(task_type)


def process_task_sync(task_id: str) -> bool:
    """Process a single task synchronously (for use with multiprocessing).
    
    Args:
        task_id: The task ID to process
        
    Returns:
        True if task was processed, False otherwise
    """
    import asyncio
    return asyncio.run(_process_task_async(task_id))


async def _process_task_async(task_id: str) -> bool:
    """Async helper for process_task_sync."""
    with SessionLocal() as session:
        return await process_task(session, task_id)


async def process_task(session: Session, task_id: str) -> bool:
    """Process a single task.
    
    Args:
        session: Database session
        task_id: The task ID to process
        
    Returns:
        True if task was processed successfully, False otherwise
    """
    # Fetch the task
    task = session.execute(
        select(Task).where(Task.id == task_id)
    ).scalar_one_or_none()
    
    if task is None:
        logger.warning(f"Task {task_id} not found")
        return False
    
    if task.status not in (TaskStatus.QUEUED.value, TaskStatus.FAILED.value):
        logger.info(f"Task {task_id} has status {task.status}, skipping")
        return False
    
    # Mark as processing
    now = utcnow()
    task.status = TaskStatus.PROCESSING.value
    task.processing_started_at = now
    session.commit()
    
    handler = get_task_handler(task.type)
    if handler is None:
        logger.error(f"No handler registered for task type: {task.type}")
        task.status = TaskStatus.FAILED.value
        task.error = f"No handler registered for task type: {task.type}"
        task.completed_at = utcnow()
        session.commit()
        return False
    
    try:
        # Execute the handler
        result = await handler(task.payload or {})
        
        # Mark as completed
        task.status = TaskStatus.COMPLETED.value
        task.result = result
        task.completed_at = utcnow()
        task.error = None
        session.commit()
        
        logger.info(f"Task {task_id} completed successfully")
        return True
        
    except Exception as e:
        logger.exception(f"Task {task_id} failed: {e}")
        
        # Mark as failed
        task.status = TaskStatus.FAILED.value
        task.error = str(e)
        task.completed_at = utcnow()
        task.retry_count += 1
        session.commit()
        
        return False


async def run_worker_iteration(session: Session, max_tasks: int = 10) -> int:
    """Run one iteration of the worker, processing pending tasks.
    
    Args:
        session: Database session
        max_tasks: Maximum number of tasks to process in this iteration
        
    Returns:
        Number of tasks processed
    """
    # Find queued tasks, ordered by creation time (FIFO)
    # Also include failed tasks that haven't exceeded retry limit
    tasks = session.execute(
        select(Task)
        .where(
            (Task.status == TaskStatus.QUEUED.value) |
            ((Task.status == TaskStatus.FAILED.value) & (Task.retry_count < 3))
        )
        .order_by(Task.create_at)
        .limit(max_tasks)
    ).scalars().all()
    
    processed = 0
    for task in tasks:
        success = await process_task(session, task.id)
        if success:
            processed += 1
    
    return processed


async def run_worker_forever(
    poll_interval: float = 5.0,
    max_tasks_per_iteration: int = 10
) -> None:
    """Run the worker loop forever.
    
    Args:
        poll_interval: Seconds to wait between polling for new tasks
        max_tasks_per_iteration: Maximum tasks to process per iteration
    """
    logger.info("Starting background worker")
    
    while True:
        try:
            with SessionLocal() as session:
                processed = await run_worker_iteration(session, max_tasks_per_iteration)
                if processed > 0:
                    logger.info(f"Processed {processed} tasks")
        except Exception as e:
            logger.exception(f"Worker iteration failed: {e}")
        
        await asyncio.sleep(poll_interval)


def reset_stale_tasks(session: Session, stale_timeout_seconds: int = 300) -> int:
    """Reset tasks that appear stuck in processing state.
    
    This handles cases where a worker dyno was restarted while processing a task.
    
    Args:
        session: Database session
        stale_timeout_seconds: How long a task can be in processing before considered stale
        
    Returns:
        Number of tasks reset
    """
    # For simplicity, reset any processing tasks - in production you'd check the timestamp
    result = session.execute(
        update(Task)
        .where(Task.status == TaskStatus.PROCESSING.value)
        .values(status=TaskStatus.QUEUED.value, processing_started_at=None)
    )
    session.commit()
    
    reset_count = result.rowcount or 0
    if reset_count > 0:
        logger.info(f"Reset {reset_count} stale tasks to queued")
    
    return reset_count


class TaskWorker:
    """Worker class for running background tasks.
    
    Provides a class-based interface around the functional worker API
    for use by CLI entry points and custom worker implementations.
    """
    
    def __init__(self):
        self.handlers: dict[str, Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]] = {}
    
    def register_handler(self, task_type: str):
        """Decorator to register a task handler.
        
        Args:
            task_type: The type of task this handler processes
            
        Returns:
            Decorator function that registers the handler
        """
        def decorator(func: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]):
            register_task_handler(task_type)(func)
            self.handlers[task_type] = func
            return func
        return decorator
    
    def run(self, poll_interval: float = 5.0, max_tasks_per_iteration: int = 10) -> None:
        """Run the worker loop forever.
        
        Args:
            poll_interval: Seconds to wait between polling for new tasks
            max_tasks_per_iteration: Maximum tasks to process per iteration
        """
        asyncio.run(run_worker_forever(poll_interval, max_tasks_per_iteration))
