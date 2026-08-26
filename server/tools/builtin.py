"""What the tools actually do. Every one of them is small, boring, and confined by the sandbox."""

from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from server.settings import Settings
from server.tools.sandbox import Denied, Sandbox

MAX_ENTRIES = 200


@dataclass(frozen=True)
class ToolContext:
    sandbox: Sandbox
    settings: Settings


@dataclass(frozen=True)
class ToolResult:
    output: str
    """What goes back to the model, already truncated to the configured budget."""
    target: str
    bytes: int = 0


def _cap(text: str, settings: Settings) -> str:
    limit = settings.agents.max_output_chars
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… truncated at {limit} characters"


async def list_dir(ctx: ToolContext, args: dict[str, object]) -> ToolResult:
    path = ctx.sandbox.resolve_read(str(args.get("path", "")))
    if not path.is_dir():
        raise Denied(f"{path} is not a directory.")
    lines = []
    for entry in sorted(path.iterdir())[:MAX_ENTRIES]:
        kind = "dir " if entry.is_dir() else "file"
        size = entry.stat().st_size if entry.is_file() else 0
        lines.append(f"{kind} {size:>10}  {entry.name}")
    return ToolResult(_cap("\n".join(lines) or "(empty)", ctx.settings), str(path))


async def read_file(ctx: ToolContext, args: dict[str, object]) -> ToolResult:
    path = ctx.sandbox.resolve_read(str(args.get("path", "")))
    if not path.is_file():
        raise Denied(f"{path} is not a file.")
    raw = await asyncio.to_thread(path.read_bytes)
    text = raw.decode("utf-8", errors="replace")
    return ToolResult(_cap(text, ctx.settings), str(path), len(raw))


async def write_file(ctx: ToolContext, args: dict[str, object]) -> ToolResult:
    path = ctx.sandbox.resolve_write(str(args.get("path", "")))
    content = str(args.get("content", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, content)
    return ToolResult(f"wrote {len(content.encode())} bytes to {path}", str(path), len(content))


async def run_shell(ctx: ToolContext, args: dict[str, object]) -> ToolResult:
    command = str(args.get("command", "")).strip()
    if not command:
        raise Denied("An empty command is not a command.")
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=str(ctx.sandbox.cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(), timeout=ctx.settings.agents.shell_timeout_s
        )
    except TimeoutError:
        process.kill()
        raise Denied(
            f"Command exceeded {ctx.settings.agents.shell_timeout_s}s and was killed."
        ) from None
    body = stdout.decode("utf-8", errors="replace")
    return ToolResult(
        _cap(f"exit {process.returncode}\n{body}", ctx.settings), command, len(stdout)
    )


async def http_get(ctx: ToolContext, args: dict[str, object]) -> ToolResult:
    url = str(args.get("url", ""))
    host = _public_host(url)
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "jarvis/0.1 (local agent)"})
    text = response.text
    return ToolResult(
        _cap(f"HTTP {response.status_code}\n{text}", ctx.settings), host, len(text.encode())
    )


def _public_host(url: str) -> str:
    """Refuse the machine's own services. A tool that can GET loopback can drive this app."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise Denied("Only http and https URLs can be fetched.")
    host = parsed.hostname
    if host in ("localhost", "localhost.localdomain"):
        raise Denied("Fetching loopback would let a tool drive this machine's own services.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A hostname that resolves to a private address is not caught here; the check is on the
        # literal, which is what makes it something you can read and verify.
        return host
    if address.is_loopback or address.is_private or address.is_link_local:
        raise Denied(f"{host} is a private address, which tools do not fetch.")
    return host
