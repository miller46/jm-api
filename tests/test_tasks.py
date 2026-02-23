"""Tests for Task API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from jm_api.models.task import Task, TaskStatus


# --- Create Task Tests ---


class TestCreateTask:
    """Test POST /api/v1/tasks."""

    def test_create_task_success(self, client: TestClient, user_headers: dict) -> None:
        """Creating a task returns 201 with task details."""
        # Arrange
        payload = {
            "type": "email.send",
            "payload": {"to": "user@example.com", "subject": "Hello"}
        }

        # Act
        response = client.post("/api/v1/tasks", json=payload, headers=user_headers)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "email.send"
        assert data["status"] == "queued"
        assert data["payload"] == {"to": "user@example.com", "subject": "Hello"}
        assert "id" in data
        assert "created_at" in data
        assert data["result"] is None
        assert data["error"] is None
        assert data["retry_count"] == 0
        assert data["completed_at"] is None

    def test_create_task_without_payload(self, client: TestClient, user_headers: dict) -> None:
        """Creating a task without payload is valid."""
        # Arrange
        payload = {"type": "cleanup.old_data"}

        # Act
        response = client.post("/api/v1/tasks", json=payload, headers=user_headers)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "cleanup.old_data"
        assert data["status"] == "queued"
        assert data["payload"] is None

    def test_create_task_requires_auth(self, client: TestClient) -> None:
        """Creating a task without authentication returns 401."""
        # Arrange
        payload = {"type": "email.send"}

        # Act
        response = client.post("/api/v1/tasks", json=payload)

        # Assert
        assert response.status_code == 401

    def test_create_task_invalid_type_empty(self, client: TestClient, user_headers: dict) -> None:
        """Creating a task with empty type returns 422."""
        # Arrange
        payload = {"type": ""}

        # Act
        response = client.post("/api/v1/tasks", json=payload, headers=user_headers)

        # Assert
        assert response.status_code == 422

    def test_create_task_missing_type(self, client: TestClient, user_headers: dict) -> None:
        """Creating a task without type returns 422."""
        # Arrange
        payload = {"payload": {"key": "value"}}

        # Act
        response = client.post("/api/v1/tasks", json=payload, headers=user_headers)

        # Assert
        assert response.status_code == 422


# --- Get Task Tests ---


class TestGetTask:
    """Test GET /api/v1/tasks/:id."""

    def test_get_task_success(self, client: TestClient, user_headers: dict, db_session: Session) -> None:
        """Getting a task returns task details."""
        # Arrange
        task = Task(type="email.send", payload={"to": "test@example.com"})
        db_session.add(task)
        db_session.commit()

        # Act
        response = client.get(f"/api/v1/tasks/{task.id}", headers=user_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task.id
        assert data["type"] == "email.send"
        assert data["status"] == "queued"
        assert data["payload"] == {"to": "test@example.com"}

    def test_get_task_not_found(self, client: TestClient, user_headers: dict) -> None:
        """Getting a non-existent task returns 404."""
        # Act
        response = client.get("/api/v1/tasks/nonexistent123", headers=user_headers)

        # Assert
        assert response.status_code == 404

    def test_get_task_requires_auth(self, client: TestClient) -> None:
        """Getting a task without authentication returns 401."""
        # Act
        response = client.get("/api/v1/tasks/someid123")

        # Assert
        assert response.status_code == 401

    def test_get_completed_task(self, client: TestClient, user_headers: dict, db_session: Session) -> None:
        """Getting a completed task returns result."""
        # Arrange
        task = Task(
            type="email.send",
            payload={"to": "test@example.com"},
            status=TaskStatus.COMPLETED.value,
            result={"message_id": "msg_123"},
        )
        db_session.add(task)
        db_session.commit()

        # Act
        response = client.get(f"/api/v1/tasks/{task.id}", headers=user_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"] == {"message_id": "msg_123"}

    def test_get_failed_task(self, client: TestClient, user_headers: dict, db_session: Session) -> None:
        """Getting a failed task returns error."""
        # Arrange
        task = Task(
            type="email.send",
            status=TaskStatus.FAILED.value,
            error="SMTP connection failed",
            retry_count=2,
        )
        db_session.add(task)
        db_session.commit()

        # Act
        response = client.get(f"/api/v1/tasks/{task.id}", headers=user_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "SMTP connection failed"
        assert data["retry_count"] == 2


# --- Worker Processing Tests ---


@pytest.mark.asyncio
class TestWorkerProcessing:
    """Test task worker processing."""

    async def test_process_task_success(self, db_session: Session) -> None:
        """Worker successfully processes a task."""
        from jm_api.services.worker import process_task, register_task_handler

        # Register a test handler
        @register_task_handler("test.success")
        async def handle_success(payload: dict) -> dict:
            return {"processed": True, "data": payload.get("value")}

        # Arrange
        task = Task(type="test.success", payload={"value": 42})
        db_session.add(task)
        db_session.commit()

        # Act
        result = await process_task(db_session, task.id)

        # Assert
        assert result is True
        db_session.refresh(task)
        assert task.status == TaskStatus.COMPLETED.value
        assert task.result == {"processed": True, "data": 42}
        assert task.error is None
        assert task.completed_at is not None

    async def test_process_task_failure(self, db_session: Session) -> None:
        """Worker handles task failure."""
        from jm_api.services.worker import process_task, register_task_handler

        # Register a failing handler
        @register_task_handler("test.failure")
        async def handle_failure(payload: dict) -> dict:
            raise ValueError("Something went wrong")

        # Arrange
        task = Task(type="test.failure", payload={})
        db_session.add(task)
        db_session.commit()

        # Act
        result = await process_task(db_session, task.id)

        # Assert
        assert result is False
        db_session.refresh(task)
        assert task.status == TaskStatus.FAILED.value
        assert task.error == "Something went wrong"
        assert task.retry_count == 1
        assert task.completed_at is not None

    async def test_process_task_no_handler(self, db_session: Session) -> None:
        """Worker handles missing handler."""
        from jm_api.services.worker import process_task

        # Arrange
        task = Task(type="test.unknown", payload={})
        db_session.add(task)
        db_session.commit()

        # Act
        result = await process_task(db_session, task.id)

        # Assert
        assert result is False
        db_session.refresh(task)
        assert task.status == TaskStatus.FAILED.value
        assert "No handler registered" in task.error

    async def test_process_task_wrong_status(self, db_session: Session) -> None:
        """Worker skips tasks that are not queued or failed."""
        from jm_api.services.worker import process_task

        # Arrange
        task = Task(type="test.any", status=TaskStatus.PROCESSING.value)
        db_session.add(task)
        db_session.commit()

        # Act
        result = await process_task(db_session, task.id)

        # Assert
        assert result is False

    async def test_process_task_not_found(self, db_session: Session) -> None:
        """Worker handles non-existent task."""
        from jm_api.services.worker import process_task

        # Act
        result = await process_task(db_session, "nonexistent")

        # Assert
        assert result is False

    async def test_retry_failed_task(self, db_session: Session) -> None:
        """Worker retries failed tasks."""
        from jm_api.services.worker import process_task, register_task_handler

        # Register a handler that succeeds
        @register_task_handler("test.retry_success")
        async def handle_retry_success(payload: dict) -> dict:
            return {"retry": "succeeded"}

        # Arrange - start with a failed task (under retry limit)
        task = Task(type="test.retry_success", status=TaskStatus.FAILED.value, retry_count=1)
        db_session.add(task)
        db_session.commit()

        # Act
        result = await process_task(db_session, task.id)

        # Assert
        assert result is True
        db_session.refresh(task)
        assert task.status == TaskStatus.COMPLETED.value
        assert task.result == {"retry": "succeeded"}


# --- Worker Iteration Tests ---


@pytest.mark.asyncio
class TestWorkerIteration:
    """Test worker iteration logic."""

    async def test_run_worker_iteration_processes_tasks(self, db_session: Session) -> None:
        """Worker iteration processes queued tasks."""
        from jm_api.services.worker import register_task_handler, run_worker_iteration

        processed_tasks = []

        @register_task_handler("test.batch")
        async def handle_batch(payload: dict) -> dict:
            processed_tasks.append(payload.get("id"))
            return {"processed": payload.get("id")}

        # Arrange
        for i in range(3):
            task = Task(type="test.batch", payload={"id": i})
            db_session.add(task)
        db_session.commit()

        # Act
        count = await run_worker_iteration(db_session, max_tasks=10)

        # Assert
        assert count == 3
        assert sorted(processed_tasks) == [0, 1, 2]

    async def test_run_worker_iteration_respects_max_tasks(self, db_session: Session) -> None:
        """Worker iteration respects max_tasks limit."""
        from jm_api.services.worker import register_task_handler, run_worker_iteration

        @register_task_handler("test.limited")
        async def handle_limited(payload: dict) -> dict:
            return {"processed": True}

        # Arrange
        for i in range(5):
            task = Task(type="test.limited", payload={"id": i})
            db_session.add(task)
        db_session.commit()

        # Act
        count = await run_worker_iteration(db_session, max_tasks=2)

        # Assert
        assert count == 2

    async def test_run_worker_iteration_fifo_order(self, db_session: Session) -> None:
        """Worker processes tasks in FIFO order."""
        from jm_api.services.worker import register_task_handler, run_worker_iteration

        processed_order = []

        @register_task_handler("test.order")
        async def handle_order(payload: dict) -> dict:
            processed_order.append(payload.get("name"))
            return {"processed": payload.get("name")}

        # Arrange
        task1 = Task(type="test.order", payload={"name": "first"})
        task2 = Task(type="test.order", payload={"name": "second"})
        task3 = Task(type="test.order", payload={"name": "third"})
        db_session.add(task1)
        db_session.add(task2)
        db_session.add(task3)
        db_session.commit()

        # Act
        await run_worker_iteration(db_session, max_tasks=10)

        # Assert
        assert processed_order == ["first", "second", "third"]

    async def test_run_worker_iteration_skips_processing_tasks(self, db_session: Session) -> None:
        """Worker iteration skips tasks already in processing state."""
        from jm_api.services.worker import register_task_handler, run_worker_iteration

        @register_task_handler("test.processing")
        async def handle_processing(payload: dict) -> dict:
            return {"processed": True}

        # Arrange
        task1 = Task(type="test.processing", status=TaskStatus.PROCESSING.value)
        task2 = Task(type="test.processing", status=TaskStatus.QUEUED.value)
        db_session.add(task1)
        db_session.add(task2)
        db_session.commit()

        # Act
        count = await run_worker_iteration(db_session, max_tasks=10)

        # Assert
        assert count == 1

    async def test_run_worker_iteration_includes_failed_under_retry_limit(self, db_session: Session) -> None:
        """Worker iteration includes failed tasks under retry limit."""
        from jm_api.services.worker import register_task_handler, run_worker_iteration

        @register_task_handler("test.retryable")
        async def handle_retryable(payload: dict) -> dict:
            return {"retry": True}

        # Arrange
        task = Task(type="test.retryable", status=TaskStatus.FAILED.value, retry_count=1)
        db_session.add(task)
        db_session.commit()

        # Act
        count = await run_worker_iteration(db_session, max_tasks=10)

        # Assert
        assert count == 1

    async def test_run_worker_iteration_excludes_failed_over_retry_limit(self, db_session: Session) -> None:
        """Worker iteration excludes failed tasks over retry limit."""
        from jm_api.services.worker import register_task_handler, run_worker_iteration

        @register_task_handler("test.exhausted")
        async def handle_exhausted(payload: dict) -> dict:
            return {"should_not_run": True}

        # Arrange
        task = Task(type="test.exhausted", status=TaskStatus.FAILED.value, retry_count=3)
        db_session.add(task)
        db_session.commit()

        # Act
        count = await run_worker_iteration(db_session, max_tasks=10)

        # Assert
        assert count == 0


# --- Reset Stale Tasks Tests ---


class TestResetStaleTasks:
    """Test reset of stale tasks."""

    def test_reset_stale_tasks(self, db_session: Session) -> None:
        """Reset stale processing tasks to queued."""
        from jm_api.services.worker import reset_stale_tasks

        # Arrange
        task = Task(type="test.stale", status=TaskStatus.PROCESSING.value)
        db_session.add(task)
        db_session.commit()

        # Act
        count = reset_stale_tasks(db_session)

        # Assert
        assert count == 1
        db_session.refresh(task)
        assert task.status == TaskStatus.QUEUED.value
        assert task.processing_started_at is None

    def test_reset_stale_tasks_only_processing(self, db_session: Session) -> None:
        """Reset only affects processing tasks."""
        from jm_api.services.worker import reset_stale_tasks

        # Arrange
        processing_task = Task(type="test.proc", status=TaskStatus.PROCESSING.value)
        queued_task = Task(type="test.queued", status=TaskStatus.QUEUED.value)
        completed_task = Task(type="test.completed", status=TaskStatus.COMPLETED.value)
        failed_task = Task(type="test.failed", status=TaskStatus.FAILED.value)
        db_session.add_all([processing_task, queued_task, completed_task, failed_task])
        db_session.commit()

        # Act
        count = reset_stale_tasks(db_session)

        # Assert
        assert count == 1
