precision highp float;

varying vec2 vUv;

uniform float uTime;
uniform float uEnergy;   // 0..1, spring-driven by the app state machine
uniform float uPulse;    // decays after each arriving token
uniform float uError;    // 0..1, desaturates toward red
uniform float uMaxLuma;  // luminance ceiling that keeps body text above 4.5:1
uniform vec2 uResolution;
uniform vec2 uPointer;
uniform vec3 uC0;
uniform vec3 uC1;
uniform vec3 uC2;
uniform vec3 uC3;
uniform vec3 uC4;

// Simplex noise by Ashima Arts / Stefan Gustavson (MIT). Kept verbatim so it stays recognisable
// against the original rather than being subtly "improved" into something unverifiable.
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

float fbm(vec2 p) {
  float sum = 0.0;
  float amp = 0.5;
  for (int i = 0; i < 4; i++) {
    sum += amp * snoise(p);
    p *= 2.02;
    amp *= 0.5;
  }
  return sum;
}

vec3 palette(float v) {
  float t = clamp(v * 0.5 + 0.5, 0.0, 1.0);
  vec3 c = mix(uC0, uC1, smoothstep(0.00, 0.30, t));
  c = mix(c, uC2, smoothstep(0.25, 0.55, t));
  c = mix(c, uC3, smoothstep(0.50, 0.78, t));
  c = mix(c, uC4, smoothstep(0.74, 1.00, t));
  return c;
}

void main() {
  vec2 aspect = vec2(uResolution.x / max(uResolution.y, 1.0), 1.0);
  vec2 p = (vUv - 0.5) * aspect * 2.2;

  // Warp field rotates slowly; energy makes it faster, never jumpier.
  float t = uTime * (0.020 + uEnergy * 0.085);
  p += (uPointer - 0.5) * 0.20 * uEnergy;

  vec2 q = vec2(fbm(p + t), fbm(p + vec2(5.2, 1.3) - t * 0.7));
  vec2 r = vec2(
    fbm(p + 2.0 * q + vec2(1.7, 9.2) + 0.15 * t),
    fbm(p + 2.0 * q + vec2(8.3, 2.8) + 0.126 * t)
  );

  // Chromatic separation only at high energy: the "thinking" tell.
  float sep = 0.020 * uEnergy + 0.035 * uPulse;
  float n = fbm(p + 1.8 * r);
  float nr = fbm(p + 1.8 * r + vec2(sep, 0.0));
  float nb = fbm(p + 1.8 * r - vec2(sep, 0.0));

  vec3 base = palette(n);
  vec3 col = vec3(palette(nr).r, base.g, palette(nb).b);
  col = mix(base, col, uEnergy);

  // Token pulse: a gentle breath, not a flash.
  col *= 1.0 + 0.10 * uPulse;

  // Error: desaturate toward red.
  float grey = dot(col, vec3(0.299, 0.587, 0.114));
  col = mix(col, mix(vec3(grey), vec3(0.42, 0.10, 0.12), 0.65), uError);

  // Hard luminance ceiling. Section 5.5 requires body text to clear 4.5:1 against the brightest
  // frame this shader can produce, so the shader is not allowed to produce a brighter one.
  float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
  if (luma > uMaxLuma) {
    col *= uMaxLuma / luma;
  }

  gl_FragColor = vec4(col, 1.0);
}
