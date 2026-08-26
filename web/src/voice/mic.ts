// The microphone, opened only while the button is held and closed the moment it is released.
// Nothing is buffered before you press it and nothing is kept after the clip is sent.
import { drive, rms } from "./level";

const PREFERRED = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

export interface Recording {
  /** Stop, release the device, and resolve with what was captured. */
  stop: () => Promise<Blob>;
  /** Stop and throw the audio away. */
  cancel: () => void;
}

export class MicError extends Error {}

function mimeType(): string {
  const supported = PREFERRED.find((type) => MediaRecorder.isTypeSupported(type));
  if (!supported) throw new MicError("This browser's MediaRecorder offers no audio format.");
  return supported;
}

export async function record(): Promise<Recording> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new MicError("This browser exposes no microphone API.");
  }
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    throw new MicError(describe(error));
  }

  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  context.createMediaStreamSource(stream).connect(analyser);
  const window = new Float32Array(analyser.fftSize);
  let frame = requestAnimationFrame(function tick() {
    analyser.getFloatTimeDomainData(window);
    drive.set(rms(window));
    frame = requestAnimationFrame(tick);
  });

  const type = mimeType();
  const recorder = new MediaRecorder(stream, { mimeType: type });
  const parts: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) parts.push(event.data);
  };
  recorder.start(250);

  const release = () => {
    cancelAnimationFrame(frame);
    drive.set(0);
    for (const track of stream.getTracks()) track.stop();
    void context.close();
  };

  return {
    stop: () =>
      new Promise<Blob>((resolve) => {
        recorder.onstop = () => {
          release();
          resolve(new Blob(parts, { type }));
        };
        recorder.stop();
      }),
    cancel: () => {
      recorder.onstop = release;
      recorder.stop();
    },
  };
}

function describe(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError") return "Microphone permission was denied for this page.";
  if (name === "NotFoundError") return "No microphone is attached to this machine.";
  if (name === "NotReadableError") return "The microphone is busy in another application.";
  return error instanceof Error ? error.message : "The microphone could not be opened.";
}
