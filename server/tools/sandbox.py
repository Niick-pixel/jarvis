"""Where a tool is allowed to look, and the much smaller place it is allowed to write.

Every path a tool is given is resolved to its real location first, symlinks included, and then
checked against the roots. Resolving before checking is the whole point: `workspace/notes/../../..`
and a symlink pointing at `/etc` both stop being clever once the path is real.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SECRET_NAMES = {".env", ".netrc", ".htpasswd", "credentials", "secrets.json", ".git-credentials"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
SECRET_PARTS = {".ssh", ".gnupg", ".aws", ".config/gcloud"}
"""Refused even inside an allowed root. The brief says never log secrets; reading them into a
prompt is the same mistake one step earlier."""


class Denied(RuntimeError):
    """A tool asked for something outside its sandbox. The message is shown to the user as-is."""


@dataclass(frozen=True)
class Sandbox:
    read_roots: tuple[Path, ...]
    write_root: Path | None
    """None means this job may not write at all, the default for a job with no workspace."""

    def resolve_read(self, raw: str) -> Path:
        path = _real(raw)
        if not any(_within(path, root) for root in self.read_roots):
            raise Denied(
                f"{path} is outside this job's readable roots "
                f"({', '.join(str(r) for r in self.read_roots) or 'none'})."
            )
        _refuse_secrets(path)
        return path

    def resolve_write(self, raw: str) -> Path:
        if self.write_root is None:
            raise Denied("This job has no workspace, so it cannot write anywhere.")
        path = _real(raw)
        if not _within(path, self.write_root):
            raise Denied(f"{path} is outside this job's workspace ({self.write_root}).")
        _refuse_secrets(path)
        return path

    @property
    def cwd(self) -> Path:
        """Where a shell command starts. The workspace when there is one, else the first root."""
        if self.write_root is not None:
            return self.write_root
        return self.read_roots[0] if self.read_roots else Path.cwd()


def build(read_roots: list[Path], workspace: str) -> Sandbox:
    """Read roots come from what you already pointed the app at; writes stay in the workspace."""
    roots = tuple(dict.fromkeys(_real(str(r)) for r in read_roots if str(r)))
    write_root: Path | None = None
    if workspace.strip():
        write_root = _real(workspace)
        write_root.mkdir(parents=True, exist_ok=True)
        roots = tuple(dict.fromkeys((*roots, write_root)))
    return Sandbox(read_roots=roots, write_root=write_root)


def _real(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _refuse_secrets(path: Path) -> None:
    lowered = path.name.lower()
    if lowered in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES:
        raise Denied(f"{path.name} looks like a secret, so it is refused even inside the sandbox.")
    parts = {p.lower() for p in path.parts}
    if parts & {p.split("/")[0] for p in SECRET_PARTS}:
        raise Denied(f"{path} is inside a credential directory, which tools never read.")
