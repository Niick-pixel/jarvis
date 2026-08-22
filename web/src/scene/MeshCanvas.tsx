// The fluid mesh gradient: six drifting colour centres blended with gaussian falloff.
//
// In its own module so it becomes its own chunk - Performance mode and reduced motion never
// import it, and therefore never download three.js.
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useSession, type VisualState } from "../store/session";
import { EnergySpring } from "./energy";
import { blobFrames } from "./mesh";
import { BACKGROUND_DPR, TARGET_FPS, useIdleAfter } from "./perf";
import { BLOB_COUNT, PRESETS, type PresetName } from "./presets";
import fragmentShader from "./shaders/mesh.frag?raw";
import vertexShader from "./shaders/mesh.vert?raw";

function MeshPlane({
  preset,
  visual,
  tokenTick,
}: {
  preset: PresetName;
  visual: VisualState;
  tokenTick: number;
}) {
  const spring = useRef(new EnergySpring());
  const pointer = useRef(new THREE.Vector2(0.5, 0.5));
  const lastTick = useRef(tokenTick);
  const clock = useRef(0);
  const { size } = useThree();

  const uniforms = useMemo(() => {
    const config = PRESETS[preset];
    return {
      uTime: { value: 0 },
      uEnergy: { value: 0.12 },
      uPulse: { value: 0 },
      uError: { value: 0 },
      uMaxLuma: { value: config.maxLuma },
      uAspect: { value: 1 },
      uPointer: { value: new THREE.Vector2(0.5, 0.5) },
      uBase: { value: new THREE.Vector3(...config.base) },
      uBaseWeight: { value: config.baseWeight },
      uColors: { value: config.blobs.map((b) => new THREE.Vector3(...b.color)) },
      uBlobs: { value: config.blobs.map((b) => new THREE.Vector3(b.at[0], b.at[1], b.falloff)) },
      uWeights: { value: config.blobs.map((b) => b.weight) },
    };
  }, [preset]);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      pointer.current.set(event.clientX / window.innerWidth, 1 - event.clientY / window.innerHeight);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, []);

  useFrame((_, delta) => {
    if (tokenTick !== lastTick.current) {
      lastTick.current = tokenTick;
      spring.current.tick();
    }
    spring.current.step(delta, visual);
    clock.current += delta;

    const { value: energy, pulse, error } = spring.current;
    const frames = blobFrames(PRESETS[preset], clock.current, energy, pulse);
    const positions = uniforms.uBlobs.value;
    const weights = uniforms.uWeights.value;
    for (let i = 0; i < BLOB_COUNT; i++) {
      const frame = frames[i]!;
      positions[i]!.set(frame.x, frame.y, frame.falloff);
      weights[i] = frame.weight;
    }

    uniforms.uTime.value = clock.current;
    uniforms.uEnergy.value = energy;
    uniforms.uPulse.value = pulse;
    uniforms.uError.value = error;
    uniforms.uAspect.value = size.width / Math.max(size.height, 1);
    uniforms.uPointer.value.lerp(pointer.current, 0.06);
  });

  return (
    <mesh frustumCulled={false}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        depthTest={false}
        depthWrite={false}
      />
    </mesh>
  );
}

/** Drives the on-demand render loop at the frame rate the current state is allowed. */
function FrameDriver({ visual, paused }: { visual: VisualState; paused: boolean }) {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    if (paused) return;
    const fps = visual === "streaming" ? TARGET_FPS.streaming : TARGET_FPS.idle;
    const interval = 1000 / fps - 1;
    let handle = 0;
    let last = 0;
    const loop = (now: number) => {
      handle = requestAnimationFrame(loop);
      if (now - last >= interval) {
        last = now;
        invalidate();
      }
    };
    handle = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(handle);
  }, [visual, paused, invalidate]);
  return null;
}

export default function MeshCanvas({ preset }: { preset: PresetName }) {
  const visual = useSession((s) => s.visual);
  const tokenTick = useSession((s) => s.tokenTick);
  const idle = useIdleAfter();

  return (
    <div className="pointer-events-none fixed inset-0 -z-10">
      <Canvas
        frameloop="demand"
        dpr={BACKGROUND_DPR}
        gl={{ antialias: false, powerPreference: "low-power", depth: false, stencil: false }}
        orthographic
        camera={{ position: [0, 0, 1] }}
      >
        <FrameDriver visual={visual} paused={idle && visual === "idle"} />
        <MeshPlane preset={preset} visual={visual} tokenTick={tokenTick} />
      </Canvas>
    </div>
  );
}
