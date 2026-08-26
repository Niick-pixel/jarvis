"""Cron, and nothing more. The schedule lives in APScheduler; the jobs live in SQLite.

APScheduler's own job stores want SQLAlchemy, which is a dependency this project does not have and
does not need: `jobs` is already a table, so the scheduler is rebuilt from it at startup and after
every edit. That also means a job you disable stops firing immediately rather than at next boot.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from server.agents import loop
from server.db import repo
from server.models.agents import Job

log = logging.getLogger("jarvis.agents")


def validate_cron(expression: str) -> str:
    """Returns an empty string when the expression is fine, else the reason it is not."""
    try:
        CronTrigger.from_crontab(expression)
    except ValueError as exc:
        return str(exc)
    return ""


class JobScheduler:
    def __init__(self, runtime: loop.Runtime) -> None:
        self.runtime = runtime
        self._scheduler = AsyncIOScheduler(timezone=None)

    def start(self) -> None:
        self._scheduler.start()
        self.sync()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def sync(self) -> None:
        """Rebuild the schedule from the table. Called at startup and after any job edit."""
        self._scheduler.remove_all_jobs()
        with self.runtime.db.session() as conn:
            jobs = repo.agents.list_jobs(conn)
        for job in jobs:
            if not job.enabled:
                continue
            try:
                trigger = CronTrigger.from_crontab(job.cron)
            except ValueError:
                # A job with an unparseable cron stays visible and simply never fires; the API
                # rejects bad expressions, so this only happens to rows edited by hand.
                log.warning("job %s has an invalid cron %r and will not run", job.id, job.cron)
                continue
            self._scheduler.add_job(
                self._fire, trigger, args=[job.id], id=job.id, replace_existing=True
            )

    def next_run_at(self, job_id: str) -> int | None:
        entry = self._scheduler.get_job(job_id)
        if entry is None or entry.next_run_time is None:
            return None
        return int(entry.next_run_time.timestamp() * 1000)

    def decorate(self, job: Job) -> Job:
        return job.model_copy(update={"next_run_at": self.next_run_at(job.id)})

    async def _fire(self, job_id: str) -> None:
        with self.runtime.db.session() as conn:
            job = repo.agents.get_job(conn, job_id)
        if job is None or not job.enabled:
            return
        log.info("job %s (%s) firing", job.id, job.name)
        await loop.start(self.runtime, job)
