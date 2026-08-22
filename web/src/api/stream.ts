// SSE client. The POST path needs a request body, which EventSource cannot send, so it is parsed
// from a fetch stream. The resume path is a plain GET, so it uses EventSource and gets
// Last-Event-ID handling from the browser for free.
import type { ErrorBody, SamplingParams, StreamEvent } from "./types";

export interface StreamHandlers {
  onEvent: (event: StreamEvent) => void;
  onFailure: (error: ErrorBody) => void;
  onClose: () => void;
}

export interface ChatRequestBody {
  conversation_id: string;
  content?: string | null;
  parent_id?: string | null;
  model_id?: string | null;
  params?: SamplingParams;
  ctx_len?: number | null;
}

interface Frame {
  event: string;
  data: string;
  id?: string;
}

/** Split an SSE buffer into complete frames, returning the unconsumed tail.
 *
 * The separator is a blank line, which per the SSE spec may be CRLF or LF - sse-starlette emits
 * CRLF. Splitting on "\n\n" alone silently parses nothing at all while the app still looks fine,
 * because the transcript refreshes from the database when the stream closes. */
export function parseFrames(buffer: string): { frames: Frame[]; rest: string } {
  const chunks = buffer.split(/\r?\n\r?\n/);
  const rest = chunks.pop() ?? "";
  const frames: Frame[] = [];
  for (const chunk of chunks) {
    const frame: Frame = { event: "message", data: "" };
    const dataLines: string[] = [];
    for (const line of chunk.split(/\r?\n/)) {
      if (line.startsWith("event:")) frame.event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      else if (line.startsWith("id:")) frame.id = line.slice(3).trim();
    }
    frame.data = dataLines.join("\n");
    if (frame.data) frames.push(frame);
  }
  return { frames, rest };
}

export async function startChatStream(
  body: ChatRequestBody,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    handlers.onFailure({ code: "internal", message: String(cause), remedy: null });
    handlers.onClose();
    return;
  }

  if (!response.ok || !response.body) {
    const error = (await response.json().catch(() => null)) as ErrorBody | null;
    handlers.onFailure(
      error ?? { code: "internal", message: `${response.status} ${response.statusText}`, remedy: null },
    );
    handlers.onClose();
    return;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;
      const { frames, rest } = parseFrames(buffer);
      buffer = rest;
      for (const frame of frames) handlers.onEvent(JSON.parse(frame.data) as StreamEvent);
    }
  } catch (cause) {
    if (!signal?.aborted) {
      handlers.onFailure({ code: "internal", message: String(cause), remedy: null });
    }
  } finally {
    handlers.onClose();
  }
}

/** Reattach to a run after a reload. The browser replays from its own Last-Event-ID. */
export function resumeRun(runId: string, handlers: StreamHandlers): () => void {
  const source = new EventSource(`/api/chat/runs/${runId}/events`);
  const forward = (event: MessageEvent<string>) =>
    handlers.onEvent(JSON.parse(event.data) as StreamEvent);
  for (const name of ["assembly", "run", "token", "usage", "done", "error"]) {
    source.addEventListener(name, forward as EventListener);
  }
  source.addEventListener("done", () => {
    source.close();
    handlers.onClose();
  });
  source.onerror = () => {
    source.close();
    handlers.onClose();
  };
  return () => source.close();
}
