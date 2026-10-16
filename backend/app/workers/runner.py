"""Tiny in-process job queue (Celery-shaped, but zero extra infrastructure).

Jobs are persisted in the `jobs` table so nothing is lost on restart, retries use
exponential backoff, and every handler is idempotent.
"""

import queue
import threading
import time
import traceback
from typing import Callable, Optional

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.db.models import Job

log = get_logger("workers.runner")

Handler = Callable[[dict], None]


class JobRunner:
    def __init__(self, concurrency: Optional[int] = None):
        self.queue: "queue.Queue[int]" = queue.Queue()
        self.concurrency = int(concurrency or settings.WORKER_CONCURRENCY)
        self._handlers: dict[str, Handler] = {}
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._started = False

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def submit(self, kind: str, payload: Optional[dict] = None) -> int:
        db = SessionLocal()
        try:
            job = Job(kind=kind, payload_json=payload or {}, status="queued")
            db.add(job)
            db.commit()
            db.refresh(job)
            job_id = job.id
        finally:
            db.close()
        self.queue.put(job_id)
        return job_id

    def start(self) -> None:
        if self._started:
            return
        self._recover()
        self._stop.clear()
        for idx in range(self.concurrency):
            thread = threading.Thread(target=self._loop, name=f"job-worker-{idx}", daemon=True)
            thread.start()
            self._threads.append(thread)
        self._started = True
        log.info("job runner started (%d workers, handlers=%s)", self.concurrency, list(self._handlers))

    def stop(self) -> None:
        self._stop.set()
        self._started = False

    def drain(self, timeout: float = 60.0) -> bool:
        """Wait until the queue is empty and no job is running (used by tests/scripts)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.queue.unfinished_tasks == 0:
                return True
            time.sleep(0.1)
        return False

    def _recover(self) -> None:
        db = SessionLocal()
        try:
            jobs = list(db.scalars(select(Job).where(Job.status.in_(["running", "queued"]))))
            for job in jobs:
                if job.status == "running":
                    job.status = "queued"
                    job.error = ((job.error or "") + " | requeued after restart").strip(" |")
                self.queue.put(job.id)
            db.commit()
            if jobs:
                log.info("recovered %d unfinished job(s)", len(jobs))
        finally:
            db.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._handle(job_id)
            except Exception:
                log.exception("unexpected error handling job %s", job_id)
            finally:
                self.queue.task_done()

    def _handle(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job is None or job.status != "queued":
                return
            job.status = "running"
            job.attempts = (job.attempts or 0) + 1
            db.commit()

            handler = self._handlers.get(job.kind)
            payload = dict(job.payload_json or {})
            attempts = job.attempts
            max_attempts = job.max_attempts or 3

            if handler is None:
                raise RuntimeError(f"no handler registered for job kind '{job.kind}'")

            handler(payload)

            job = db.get(Job, job_id)
            job.status = "done"
            job.error = None
            db.commit()
            log.info("job %s (%s) done", job_id, job.kind)
        except Exception as exc:
            log.warning("job %s failed: %s", job_id, exc)
            db.rollback()
            job = db.get(Job, job_id)
            if job is None:
                return
            job.error = f"{exc}\n{traceback.format_exc()[-800:]}"[:2000]
            if (job.attempts or 0) < (job.max_attempts or 3):
                job.status = "queued"
                db.commit()
                delay = min(30.0, 2.0 ** job.attempts)
                threading.Timer(delay, lambda: self.queue.put(job_id)).start()
            else:
                job.status = "failed"
                db.commit()
        finally:
            db.close()


runner = JobRunner()
