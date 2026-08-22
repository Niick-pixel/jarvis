// The shader canvas itself, in its own module so it becomes its own chunk. Performance mode and
// reduced motion never import it, which means those users never download three.js at all.
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useSession, type VisualState } from "../store/session";
import { EnergySpring } from "./energy";
import { BACKGROUND_DPR, TARGET_FPS, useIdleAfter } from "./perf";
import { PRESETS, type PresetName } from "./presets";
import fragmentShader from "./shaders/warp.frag?raw";
import vertexShader from "./shaders/warp.vert?raw";

interface PlaneProps {
  preset: PresetName;
  visual: VisualState;
  tokenTick: number;
}

function WarpPlane({ preset, visual, tokenTick }: PlaneProps) {
  const spring = useRef(new EnergySpring());
  const pointer = useRef(new THREE.Vector2(0.5, 0.5));
  const lastTick = useRef(tokenTick);
  const { size } = useThree();

  const uniforms = useMemo(() => {
    const stops = PRESETS[preset].stops;
    return {
      uTime: { value: 0 },
      uEnergy: { value: 0.12 },
      uPulse: { value: 0 },
      uError: { value: 0 },
      uMaxLuma: { value: PRESETS[preset].maxLuma },
      uResolution: { value: new THREE.Vector2(1, 1) },
      uPointer: { value: new THREE.Vector2(0.5, 0.5) },
      uC0: { value: new THREE.Vector3(...stops[0]!) },
      uC1: { value: new THREE.Vector3(...stops[1]!) },
      uC2: { value: new THREE.Vector3(...stops[2]!) },
      uC3: { value: new THREE.Vector3(...stops[3]!) },
      uC4: { value: new THREE.Vector3(...stops[4]!) },
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
    uniforms.uTime.value += delta;
    uniforms.uEnergy.value = spring.current.value;
    uniforms.uPulse.value = spring.current.pulse;
    uniforms.uError.value = spring.current.error;
    uniforms.uResolution.value.set(size.width, size.height);
    uniforms.uPointer.value.lerp(pointer.current, 0.08);
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

export default function WarpCanvas({ preset }: { preset: PresetName }) {
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
        <WarpPlane preset={preset} visual={visual} tokenTick={tokenTick} />
      </Canvas>
    </div>
  );
}
