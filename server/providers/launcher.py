"""Starting llama.cpp with the app, and stopping it with the app.

Three things make this worth doing in the server rather than in the Makefile: it waits for the
model to actually load before saying it started, it reports the server's own words when it does
not, and it never starts a second copy over one you are already running. `make dev` gets all of
that for free because it runs this process.

The server is spawned in its own session, so a Ctrl-C in the terminal reaches the app and the app
decides what happens to the model - rather than both being torn down mid-write by the same signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import signal
import time
from pathlib import Path
from typing import IO

import httpx

from server.db.connection import Database
from server.models.launch import LaunchStatus
from server.providers import launch_args
from server.settings import Settings

log = logging.getLogger("jarvis.llamacpp")
LOG_NAME = "llama-server.log"
POLL_S = 0.5
TAIL_LINES = 12
TERM_GRACE_S = 10.0


class LlamaServer:
    """Owns at most one child process. Safe to start twice; the second call is a no-op."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.status = LaunchStatus(autostart=settings.providers.llamacpp.autostart, started=False)
        self._process: asyncio.subprocess.Process | None = None
        self._log: IO[bytes] | None = None
        self._log_from = 0
        """Byte offset where this run's output starts. The log is appended across runs, and a
        failure explained by the previous run's last words is worse than no explanation."""

    @property
    def log_path(self) -> Path:
        return self.settings.paths.data_dir / LOG_NAME

    async def start(self) -> LaunchStatus:
        cfg = self.settings.providers.llamacpp
        if not cfg.enabled or not cfg.autostart:
            return self._note("autostart is off - start llama-server yourself, or set autostart")
        if self._process is not None:
            return self.status
        if await healthy(cfg.base_url):
            return self._note(f"a server is already listening on {cfg.base_url}, left alone")

        binary = shutil.which(cfg.binary) or (cfg.binary if Path(cfg.binary).is_file() else "")
        if not binary:
            return self._note(
                f"{cfg.binary!r} is not on PATH. Build llama.cpp (README step 3) or set "
                "providers.llamacpp.binary to its full path."
            )

        model_path, ctx_len = self._resolve()
        if not model_path:
            return self._note(
                f"no GGUF found in {self.settings.paths.models_dir} - run `make models` first"
            )

        argv = [binary, *launch_args.command(self.settings, model_path, ctx_len)[1:]]
        self.status = LaunchStatus(
            autostart=True,
            started=False,
            model_path=model_path,
            ctx_len=ctx_len,
            command=argv,
            log_path=str(self.log_path),
            detail="starting llama-server and loading the model",
        )
        return await self._spawn(argv, cfg.startup_timeout_s)

    def _resolve(self) -> tuple[str, int]:
        cfg = self.settings.providers.llamacpp
        if cfg.model_path:
            return cfg.model_path, cfg.ctx_len or launch_args.FALLBACK_CTX
        with self.db.session() as conn:
            models = launch_args.registered_models(conn, self.settings.paths.models_dir)
        model, ctx = launch_args.choose(models, self.settings)
        if model is None:
            return "", 0
        return model.file_path or "", cfg.ctx_len or ctx

    async def _spawn(self, argv: list[str], timeout: float) -> LaunchStatus:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("ab")
        self._log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(argv)}\n".encode())
        self._log.flush()
        self._log_from = self._log.tell()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=self._log,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            self._close_log()
            return self._note(f"could not run {argv[0]}: {exc}")
        log.info("started llama-server pid=%s", self._process.pid)

        deadline = time.monotonic() + timeout
        base_url = self.settings.providers.llamacpp.base_url
        while time.monotonic() < deadline:
            if self._process.returncode is not None:
                code = self._process.returncode
                self._process = None
                self._close_log()
                return self._note(f"llama-server exited with code {code}: {self._tail()}")
            if await healthy(base_url):
                self.status = self.status.model_copy(
                    update={
                        "started": True,
                        "pid": self._process.pid,
                        "detail": f"serving {Path(self.status.model_path).name} at "
                        f"{self.status.ctx_len} context",
                    }
                )
                return self.status
            await asyncio.sleep(POLL_S)

        await self.stop()
        return self._note(f"llama-server did not answer within {timeout:.0f}s: {self._tail()}")

    async def stop(self) -> None:
        """Only ever kills a process this object started. A server you ran yourself is yours."""
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            self._close_log()
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=TERM_GRACE_S)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            await process.wait()
        log.info("stopped llama-server pid=%s", process.pid)
        self._close_log()
        self.status = self.status.model_copy(update={"started": False, "pid": None})

    def _note(self, detail: str) -> LaunchStatus:
        self.status = self.status.model_copy(update={"detail": detail})
        return self.status

    def _tail(self) -> str:
        """This run's own last words, which are almost always the actual explanation."""
        try:
            with self.log_path.open("rb") as handle:
                handle.seek(self._log_from)
                lines = handle.read().decode(errors="replace").splitlines()
        except OSError:
            return f"see {self.log_path}"
        return " / ".join(line.strip() for line in lines[-TAIL_LINES:] if line.strip())[-600:]

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None


async def healthy(base_url: str) -> bool:
    """llama.cpp answers /health with 200 once the model is loaded, 503 while it still is not."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/health")
        return response.status_code == 200
    except httpx.HTTPError:
        return False
