// Plays the WAV stream from /api/voice/speak as it arrives, rather than after it finishes.
//
// MediaSource cannot take WAV, so an <audio> element would have to wait for the whole response.
// The body is plain 16-bit PCM after a 44-byte header, so each block is decoded and scheduled by
// hand: you hear the first sentence while the last is still being synthesised.
import { drive, rms } from "./level";

const HEADER_BYTES = 44;
const LEAD_IN_S = 0.08;

interface Format {
  sampleRate: number;
  channels: number;
}

type Bytes = Uint8Array<ArrayBufferLike>;

function readHeader(head: Bytes): Format {
  const view = new DataView(head.buffer, head.byteOffset, head.byteLength);
  return { channels: view.getUint16(22, true), sampleRate: view.getUint32(24, true) };
}

export interface Playback {
  stop: () => void;
  finished: Promise<void>;
}

export function play(body: ReadableStream<Bytes>): Playback {
  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  analyser.connect(context.destination);
  const window = new Float32Array(analyser.fftSize);
  let frame = requestAnimationFrame(function tick() {
    analyser.getFloatTimeDomainData(window);
    drive.set(rms(window));
    frame = requestAnimationFrame(tick);
  });

  const sources: AudioBufferSourceNode[] = [];
  let stopped = false;
  let cursor = 0;

  const release = () => {
    cancelAnimationFrame(frame);
    drive.set(0);
    void context.close();
  };

  const finished = (async () => {
    const reader = body.getReader();
    let pending: Bytes = new Uint8Array(0);
    let format: Format | null = null;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done || stopped) break;
        pending = concat(pending, value);
        if (!format) {
          if (pending.length < HEADER_BYTES) continue;
          format = readHeader(pending.subarray(0, HEADER_BYTES));
          pending = pending.subarray(HEADER_BYTES);
        }
        // A 16-bit sample never straddles two scheduled buffers: keep any odd trailing byte.
        const usable = pending.length - (pending.length % 2);
        if (usable === 0) continue;
        cursor = schedule(context, analyser, pending.subarray(0, usable), format, cursor, sources);
        pending = pending.subarray(usable);
      }
      if (!stopped && cursor > context.currentTime) {
        await sleep((cursor - context.currentTime) * 1000);
      }
    } finally {
      if (!stopped) release();
    }
  })();

  return {
    stop: () => {
      stopped = true;
      for (const source of sources) source.stop();
      release();
    },
    finished,
  };
}

function schedule(
  context: AudioContext,
  destination: AudioNode,
  bytes: Bytes,
  format: Format,
  cursor: number,
  sources: AudioBufferSourceNode[],
): number {
  const samples = new Int16Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length));
  const frames = Math.floor(samples.length / format.channels);
  const buffer = context.createBuffer(format.channels, frames, format.sampleRate);
  for (let channel = 0; channel < format.channels; channel += 1) {
    const target = buffer.getChannelData(channel);
    for (let index = 0; index < frames; index += 1) {
      target[index] = (samples[index * format.channels + channel] ?? 0) / 32768;
    }
  }
  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(destination);
  const at = Math.max(cursor, context.currentTime + LEAD_IN_S);
  source.start(at);
  sources.push(source);
  return at + buffer.duration;
}

function concat(left: Bytes, right: Bytes): Bytes {
  const out = new Uint8Array(left.length + right.length);
  out.set(left);
  out.set(right, left.length);
  return out;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
