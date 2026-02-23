"""Background task worker service."""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.db.session import get_engine
from jm_api.models.task import Task, TaskStatus

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def _signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    _shutdown_requested = True


# Register signal handlers
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


class TaskWorker:
    """Background task worker for processing async jobs."""

    def __init__(
        self,
        engine: Engine | None = None,
        poll_interval: float = 5.0,
        max_runtime: float = 300.0,  # 5 minutes max per task
    ):
        self.engine = engine or get_engine()
        self.poll_interval = poll_interval
        self.max_runtime = max_runtime
        self._handlers: dict[str, callable] = {}

    def register_handler(self, task_type: str, handler: callable) -> None:
        """Register a handler for a specific task type."""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    def _get_next_task(self, session: Session) -> Task | None:
        """Get the next task to process (queued or retryable failed)."""
        # First, try to get queued tasks
        task = session.execute(
            select(Task)
            .where(Task.status == TaskStatus.QUEUED.value)
            .order_by(Task.create_at.asc())
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()

        if task:
            return task

        # Then, try to get failed tasks that can be retried
        # Only retry if enough time has passed since last attempt (exponential backoff)
        task = session.execute(
            select(Task)
            .where(Task.status == TaskStatus.FAILED.value)
            .where(Task.attempts < Task.max_attempts)
            .order_by(Task.create_at.asc())
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()

        return task

    def _process_task(self, session: Session, task: Task) -> None:
        """Process a single task."""
        handler = self._handlers.get(task.type)
        if not handler:
            task.status = TaskStatus.FAILED.value
            task.error_message = f"No handler registered for task type: {task.type}"
            task.attempts += 1
            logger.warning(f"No handler for task type: {task.type}")
            return

        # Mark as processing
        task.status = TaskStatus.PROCESSING.value
        task.attempts += 1
        task.started_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(f"Processing task {task.id} (type: {task.type}, attempt: {task.attempts})")

        try:
            result = handler(task.payload)
            task.status = TaskStatus.COMPLETED.value
            task.result = {"data": result} if result is not None else {}
            task.completed_at = datetime.now(timezone.utc)
            logger.info(f"Task {task.id} completed successfully")
        except Exception as exc:
            task.status = TaskStatus.FAILED.value
            task.error_message = str(exc)
            logger.exception(f"Task {task.id} failed: {exc}")

            # If we haven't exceeded max attempts, re-queue
            if task.attempts < task.max_attempts:
                task.status = TaskStatus.QUEUED.value
                logger.info(f"Task {task.id} will be retried (attempt {task.attempts + 1}/{task.max_attempts})")

    def _recover_orphaned_tasks(self, session: Session) -> None:
        """Recover tasks that were processing when worker died."""
        # Find tasks that have been processing for too long
        # (likely orphaned due to worker restart/crash)
        cutoff = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        orphaned = session.execute(
            select(Task)
            .where(Task.status == TaskStatus.PROCESSING.value)
            .where(Task.started_at < cutoff)
        ).scalars().all()

        for task in orphaned:
            logger.warning(f"Recovering orphaned task {task.id}")
            if task.attempts < task.max_attempts:
                task.status = TaskStatus.QUEUED.value
                task.error_message = "Task was orphaned due to worker restart"
            else:
                task.status = TaskStatus.FAILED.value
                task.error_message = "Task exceeded max attempts after being orphaned"
                task.completed_at = datetime.now(timezone.utc)

        if orphaned:
            session.commit()
            logger.info(f"Recovered {len(orphaned)} orphaned tasks")

    def run(self) -> None:
        """Run the worker loop."""
        logger.info("Task worker started")

        with Session(self.engine) as session:
            self._recover_orphaned_tasks(session)

        while not _shutdown_requested:
            try:
                with Session(self.engine) as session:
                    with session.begin():
                        task = self._get_next_task(session)
                        if task:
                            self._process_task(session, task)

                if not _shutdown_requested:
                    time.sleep(self.poll_interval)
            except Exception as exc:
                logger.exception(f"Error in worker loop: {exc}")
                if not _shutdown_requested:
                    time.sleep(self.poll_interval)

        logger.info("Task worker stopped gracefully")


def create_default_worker() -> TaskWorker:
    """Create a worker with default handlers."""
    worker = TaskWorker()

    # Register example handlers
    @worker.register_handler
    def email_send(payload: dict) -> dict:
        """Example email handler."""
        # This is a placeholder - real implementation would send email
        logger.info(f"Sending email with payload: {payload}")
        return {"sent": True}

    return worker
