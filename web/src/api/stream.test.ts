// The one frontend test (rule 0.7, subject 3: the streaming interrupt/resume path).
//
// It exists because this parser already shipped a bug that nothing else could have caught: it
// split on "\n\n" while sse-starlette emits CRLF, so every live event silently failed to parse
// and the app still looked correct - the transcript refreshes from the database when a stream
// closes, so the text appeared a beat late and nobody noticed. The backend test pins the wire
// format from its own side; only this pins the client's reading of it.
//
// The fixtures below are bytes captured from a running server, not bytes I invented. Note the
// field order on a token frame: sse-starlette writes `id` first, then `event`, then `data`.
import { describe, expect, it } from "vitest";
import { parseFrames } from "./stream";

const ASSEMBLY = 'event: assembly\r\ndata: {"type":"assembly","assembly":{"ctx_len":8192}}\r\n\r\n';
const RUN = 'event: run\r\ndata: {"type":"run","run_id":"run_01a0","message_id":"msg_01a0"}\r\n\r\n';
const TOKEN_0 =
  'id: run_01a0:0\r\nevent: token\r\ndata: {"type":"token","i":0,"text":"model "}\r\n\r\n';
const TOKEN_1 =
  'id: run_01a0:1\r\nevent: token\r\ndata: {"type":"token","i":1,"text":"runs "}\r\n\r\n';
const DONE = 'event: done\r\ndata: {"type":"done","stop_reason":"eos"}\r\n\r\n';

describe("parseFrames", () => {
  it("reads the CRLF frames the server actually sends", () => {
    const { frames, rest } = parseFrames(ASSEMBLY + RUN + TOKEN_0 + DONE);
    expect(frames.map((f) => f.event)).toEqual(["assembly", "run", "token", "done"]);
    expect(rest).toBe("");
    expect(JSON.parse(frames[2]!.data)).toMatchObject({ type: "token", i: 0, text: "model " });
  });

  it("reads LF frames too, since the separator is either per the spec", () => {
    const { frames } = parseFrames(ASSEMBLY.replaceAll("\r\n", "\n"));
    expect(frames).toHaveLength(1);
    expect(frames[0]!.event).toBe("assembly");
  });

  it("keeps the id, because resuming a run depends on it", () => {
    const { frames } = parseFrames(TOKEN_0);
    expect(frames[0]!.id).toBe("run_01a0:0");
  });

  it("holds an incomplete frame back instead of emitting half of it", () => {
    const split = 40;
    const first = parseFrames(TOKEN_0.slice(0, split));
    expect(first.frames).toEqual([]);
    expect(first.rest).toBe(TOKEN_0.slice(0, split));

    // What the reader loop does: keep the tail, prepend it to the next chunk.
    const second = parseFrames(first.rest + TOKEN_0.slice(split) + TOKEN_1);
    expect(second.frames.map((f) => f.id)).toEqual(["run_01a0:0", "run_01a0:1"]);
    expect(second.rest).toBe("");
  });

  it("emits each token exactly once across an arbitrary chunk boundary", () => {
    const wire = TOKEN_0 + TOKEN_1 + DONE;
    for (let cut = 1; cut < wire.length; cut += 1) {
      const first = parseFrames(wire.slice(0, cut));
      const second = parseFrames(first.rest + wire.slice(cut));
      const events = [...first.frames, ...second.frames].map((f) => f.event);
      expect(events, `split at ${cut}`).toEqual(["token", "token", "done"]);
    }
  });

  it("joins a multi-line data payload with newlines, not by dropping lines", () => {
    const { frames } = parseFrames("event: error\r\ndata: line one\r\ndata: line two\r\n\r\n");
    expect(frames[0]!.data).toBe("line one\nline two");
  });

  it("ignores keepalives and comments, which carry no data", () => {
    const { frames } = parseFrames(`: ping\r\n\r\n${DONE}`);
    expect(frames.map((f) => f.event)).toEqual(["done"]);
  });
});
