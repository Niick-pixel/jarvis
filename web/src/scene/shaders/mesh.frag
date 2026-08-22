precision highp float;

varying vec2 vUv;

#define BLOBS 6

uniform vec3 uBase;
uniform vec3 uColors[BLOBS];
uniform vec3 uBlobs[BLOBS];    // x, y, falloff - positions come from mesh.ts each frame
uniform float uWeights[BLOBS];

uniform float uTime;
uniform float uEnergy;    // 0..1, spring-driven by the app state machine
uniform float uPulse;     // decays after each arriving token
uniform float uError;     // 0..1, desaturates toward red
uniform float uMaxLuma;   // hard ceiling; scripts/contrast_check.py depends on this existing
uniform float uAspect;
uniform float uBaseWeight;
uniform vec2 uPointer;

// Simplex noise by Ashima Arts / Stefan Gustavson (MIT). Used only to bend the field a little so
// the blobs read as fluid rather than as six circles; two octaves, not a fractal cascade.
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

float snoise(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
  vec2 i = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod289(i);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
  m = m * m;
  m = m * m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
  vec3 g;
  g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

// Cheap hash, used to dither the output. Smooth gradients band badly in 8 bits without it.
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
  vec2 uv = vUv;
  float t = uTime * 0.03;

  // Two octaves of low-frequency warp: enough to make the boundaries organic, cheap enough to
  // stay inside the frame budget while the GPU is also running the model.
  vec2 warp = vec2(
    snoise(uv * 1.7 + vec2(t, 0.0)) + 0.5 * snoise(uv * 3.4 - vec2(t * 1.3, 0.0)),
    snoise(uv * 1.7 + vec2(31.4, -t)) + 0.5 * snoise(uv * 3.4 + vec2(0.0, t * 1.1))
  ) * (0.030 + 0.045 * uEnergy);

  // A weighted average, so the result is always a convex combination of uBase and uColors.
  // That is what lets the contrast check prove a luminance bound instead of sampling frames.
  vec3 accum = uBase * uBaseWeight;
  float total = uBaseWeight;

  for (int i = 0; i < BLOBS; i++) {
    vec2 centre = uBlobs[i].xy;
    // The pointer nudges the field slightly, so the background feels touchable, not painted on.
    centre += (uPointer - 0.5) * 0.05 * uEnergy;
    vec2 d = vec2((uv.x - centre.x) * uAspect, uv.y - centre.y) + warp;
    float w = exp(-dot(d, d) * uBlobs[i].z) * uWeights[i];
    accum += uColors[i] * w;
    total += w;
  }

  vec3 col = accum / total;

  // Ambient status glow: a slow sweep of light across the field while the model is working, and
  // a soft swell on each arriving token. Both ride on top of the colour, neither changes it.
  float sweep = 0.5 + 0.5 * sin((uv.x * 1.4 + uv.y * 0.6) * 3.0 - uTime * 0.85);
  col *= 1.0 + 0.07 * uEnergy * sweep + 0.10 * uPulse;

  float grey = dot(col, vec3(0.299, 0.587, 0.114));
  col = mix(col, mix(vec3(grey), vec3(0.42, 0.10, 0.12), 0.65), uError);

  // Hard luminance ceiling. Section 5.5 requires body text to clear 4.5:1 against the brightest
  // frame this shader can produce, so the shader is not allowed to produce a brighter one.
  float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
  if (luma > uMaxLuma) {
    col *= uMaxLuma / luma;
  }

  // Dither by well under one 8-bit step: kills the banding that soft gradients otherwise show.
  col += (hash(gl_FragCoord.xy) - 0.5) * (1.0 / 512.0);

  gl_FragColor = vec4(col, 1.0);
}
