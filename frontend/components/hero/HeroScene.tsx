"use client";

import { useEffect, useMemo, useRef } from "react";

function clamp(n: number, a: number, b: number) {
  return Math.max(a, Math.min(b, n));
}

function prefersReducedMotion() {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

type HeroSceneProps = {
  className?: string;
};

export function HeroScene({ className }: HeroSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const shaders = useMemo(() => {
    const vs = `
      attribute vec2 aPos;
      varying vec2 vUv;
      void main(){
        vUv = aPos*0.5+0.5;
        gl_Position = vec4(aPos, 0.0, 1.0);
      }
    `;

    const fs = `
      precision highp float;

      varying vec2 vUv;
      uniform vec2 uRes;
      uniform float uTime;
      uniform vec2 uPointer;
      uniform float uScroll;
      uniform float uQuality;

      float hash11(float p){ p = fract(p*0.1031); p *= p + 33.33; p *= p + p; return fract(p); }
      float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*0.1031); p3 += dot(p3, p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }

      vec3 rotY(vec3 p, float a){ float c=cos(a), s=sin(a); return vec3(c*p.x + s*p.z, p.y, -s*p.x + c*p.z); }
      vec3 rotX(vec3 p, float a){ float c=cos(a), s=sin(a); return vec3(p.x, c*p.y - s*p.z, s*p.y + c*p.z); }

      float sdSphere(vec3 p, float r){ return length(p) - r; }
      float sdTorus(vec3 p, vec2 t){ vec2 q = vec2(length(p.xz)-t.x, p.y); return length(q)-t.y; }
      float sdBox(vec3 p, vec3 b){ vec3 q = abs(p)-b; return length(max(q,0.0)) + min(max(q.x,max(q.y,q.z)),0.0); }

      float smin(float a, float b, float k){
        float h = clamp(0.5 + 0.5*(b-a)/k, 0.0, 1.0);
        return mix(b, a, h) - k*h*(1.0-h);
      }

      float map(vec3 p){
        float t = uTime * 0.55;
        vec3 q = p;
        q = rotY(q, 0.65 + 0.25*sin(t*0.7));
        q = rotX(q, 0.25 + 0.2*sin(t*0.6));

        float d1 = sdTorus(q + vec3(0.0, 0.05*sin(t), 0.0), vec2(0.62, 0.16));
        float d2 = sdSphere(q - vec3(0.52, 0.18, 0.20), 0.34);
        float d3 = sdSphere(q - vec3(-0.50, -0.08, -0.24), 0.30);
        float d4 = sdBox(q - vec3(0.0, -0.35, 0.08), vec3(0.35, 0.16, 0.22));

        float d = smin(d1, d2, 0.28);
        d = smin(d, d3, 0.28);
        d = smin(d, d4, 0.22);
        return d;
      }

      vec3 normal(vec3 p){
        float e = 0.0018;
        vec2 h = vec2(e, 0.0);
        float dx = map(p + vec3(h.x,h.y,h.y)) - map(p - vec3(h.x,h.y,h.y));
        float dy = map(p + vec3(h.y,h.x,h.y)) - map(p - vec3(h.y,h.x,h.y));
        float dz = map(p + vec3(h.y,h.y,h.x)) - map(p - vec3(h.y,h.y,h.x));
        return normalize(vec3(dx,dy,dz));
      }

      float raymarch(vec3 ro, vec3 rd, out vec3 p){
        float t = 0.0;
        float maxT = 8.5;
        float eps = mix(0.0025, 0.0045, 1.0-uQuality);
        for(int i=0;i<96;i++){
          p = ro + rd*t;
          float d = map(p);
          if(d < eps) return t;
          t += d * 0.85;
          if(t > maxT) break;
        }
        return -1.0;
      }

      vec3 palette(float x){
        vec3 a = vec3(0.08, 0.10, 0.18);
        vec3 b = vec3(0.08, 0.12, 0.20);
        vec3 c = vec3(0.40, 0.52, 0.96);
        vec3 d = vec3(0.20, 0.88, 0.84);
        return a + b*cos(6.28318*(c*x + d));
      }

      float particles(vec2 uv){
        vec2 g = uv*vec2(60.0, 34.0);
        vec2 id = floor(g);
        vec2 f = fract(g) - 0.5;
        float rnd = hash12(id);
        vec2 o = vec2(hash11(rnd+2.1), hash11(rnd+7.7)) - 0.5;
        float d = length(f - o*0.7);
        float a = smoothstep(0.10, 0.0, d);
        a *= smoothstep(0.55, 0.05, abs(rnd-0.5));
        a *= 0.55 + 0.45*sin(uTime*0.5 + rnd*6.28);
        return a;
      }

      void main(){
        vec2 px = (gl_FragCoord.xy - 0.5*uRes.xy) / uRes.y;
        float t = uTime;

        vec2 pointer = uPointer * vec2(1.0, 0.75);
        float sc = clamp(uScroll, 0.0, 1.0);
        float camZ = mix(2.65, 2.25, sc);
        vec3 ro = vec3(0.15*pointer.x, 0.10*pointer.y, camZ);
        vec3 ta = vec3(0.0, -0.04*sc, 0.0);
        vec3 ww = normalize(ta - ro);
        vec3 uu = normalize(cross(vec3(0.0,1.0,0.0), ww));
        vec3 vv = cross(ww, uu);
        vec3 rd = normalize(px.x*uu + px.y*vv + 1.55*ww);

        float v = vUv.y;
        vec3 bg = mix(vec3(0.03,0.04,0.08), vec3(0.02,0.03,0.07), v);
        bg += 0.20*vec3(0.06,0.10,0.22) * (0.65 + 0.35*sin(t*0.12 + v*2.2));
        bg += 0.12*vec3(0.08,0.40,0.55) * smoothstep(0.0, 0.55, 1.0 - length(px*vec2(1.1, 0.9)));
        bg += 0.08*vec3(0.40,0.18,0.62) * smoothstep(0.0, 0.55, 1.0 - length((px-vec2(0.35,0.08))*vec2(1.3, 1.0)));

        float p0 = particles(vUv + vec2(0.0, 0.02*t));
        float p1 = particles(vUv*1.35 + vec2(0.02*t, -0.01*t));
        bg += (0.10*p0 + 0.07*p1) * vec3(0.75, 0.9, 1.0);

        vec3 pos;
        float hit = raymarch(ro, rd, pos);

        vec3 col = bg;
        float glow = 0.0;

        if(hit > 0.0){
          vec3 n = normal(pos);
          vec3 l1 = normalize(vec3(0.45, 0.85, 0.35));
          vec3 l2 = normalize(vec3(-0.65, 0.35, -0.25));

          float diff = max(dot(n, l1), 0.0)*0.9 + max(dot(n, l2), 0.0)*0.6;
          vec3 vdir = normalize(ro - pos);
          vec3 h1 = normalize(l1 + vdir);
          float spec = pow(max(dot(n, h1), 0.0), 72.0);

          float fres = pow(1.0 - max(dot(n, vdir), 0.0), 4.0);
          vec3 rim = mix(vec3(0.10,0.55,1.0), vec3(0.70,0.30,0.95), 0.55 + 0.45*sin(t*0.3));

          float ref = 0.55 + 0.45*sin(6.0*pos.y + 2.0*pos.x + t*0.25);
          vec3 base = mix(vec3(0.10,0.12,0.22), palette(ref), 0.35);

          col = base * (0.18 + 0.82*diff) + 0.9*spec*vec3(0.9,0.96,1.0) + rim*(0.18 + 0.68*fres);

          float fog = smoothstep(0.0, 1.0, hit / 7.0);
          col = mix(col, bg, fog*0.65);

          glow = (0.35 + 0.65*fres) * (0.6 + 0.4*spec);
          glow += 0.15*diff;
        }

        vec2 c = px*vec2(0.95, 0.88);
        float center = smoothstep(0.92, 0.0, length(c));
        vec3 neon = vec3(0.12, 0.75, 0.95) * 0.75 + vec3(0.75, 0.35, 0.95) * 0.55;
        col += neon * (0.06 + 0.20*glow) * center;

        float vig = smoothstep(1.1, 0.25, dot(px, px));
        col *= 0.82 + 0.18*vig;
        col = pow(col, vec3(0.92));
        gl_FragColor = vec4(col, 1.0);
      }
    `;

    return { vs, fs };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reduceMotion = prefersReducedMotion();
    const gl =
      canvas.getContext("webgl2", {
        alpha: true,
        antialias: false,
        premultipliedAlpha: true,
        powerPreference: "high-performance",
      }) ??
      canvas.getContext("webgl", {
        alpha: true,
        antialias: false,
        premultipliedAlpha: true,
        powerPreference: "high-performance",
      });

    if (!gl) return;

    function compile(type: number, src: string) {
      const s = gl.createShader(type);
      if (!s) return null;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        gl.deleteShader(s);
        return null;
      }
      return s;
    }

    function link(vsSrc: string, fsSrc: string) {
      const v = compile(gl.VERTEX_SHADER, vsSrc);
      const f = compile(gl.FRAGMENT_SHADER, fsSrc);
      if (!v || !f) return null;
      const p = gl.createProgram();
      if (!p) return null;
      gl.attachShader(p, v);
      gl.attachShader(p, f);
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return null;
      return p;
    }

    const prog = link(shaders.vs, shaders.fs);
    if (!prog) return;
    gl.useProgram(prog);

    const aPos = gl.getAttribLocation(prog, "aPos");
    const uRes = gl.getUniformLocation(prog, "uRes");
    const uTime = gl.getUniformLocation(prog, "uTime");
    const uPointer = gl.getUniformLocation(prog, "uPointer");
    const uScroll = gl.getUniformLocation(prog, "uScroll");
    const uQuality = gl.getUniformLocation(prog, "uQuality");

    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    let w = 0;
    let h = 0;
    let pointerX = 0;
    let pointerY = 0;
    let targetX = 0;
    let targetY = 0;
    let last = performance.now();
    let t = 0;

    const quality = reduceMotion ? 0.72 : 1.0;

    function resize() {
      const dpr = clamp(window.devicePixelRatio || 1, 1, reduceMotion ? 1.25 : 1.6);
      const nw = Math.floor(canvas.clientWidth * dpr);
      const nh = Math.floor(canvas.clientHeight * dpr);
      if (nw === w && nh === h) return;
      w = nw;
      h = nh;
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }

    function readScroll() {
      const y = window.scrollY || 0;
      const max = Math.max(1, window.innerHeight * 1.2);
      return clamp(y / max, 0, 1);
    }

    function onPointer(e: PointerEvent) {
      const x = e.clientX / Math.max(1, window.innerWidth);
      const y = e.clientY / Math.max(1, window.innerHeight);
      targetX = (x - 0.5) * 2.0;
      targetY = (0.5 - y) * 2.0;
    }

    function frame(now: number) {
      resize();
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!reduceMotion) t += dt;

      pointerX += (targetX - pointerX) * (reduceMotion ? 0.08 : 0.12);
      pointerY += (targetY - pointerY) * (reduceMotion ? 0.08 : 0.12);

      gl.uniform2f(uRes, w, h);
      gl.uniform1f(uTime, t);
      gl.uniform2f(uPointer, pointerX, pointerY);
      gl.uniform1f(uScroll, readScroll());
      gl.uniform1f(uQuality, quality);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      raf = requestAnimationFrame(frame);
    }

    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("resize", resize, { passive: true });
    let raf = requestAnimationFrame(frame);

    return () => {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(raf);
      try {
        gl.deleteProgram(prog);
      } catch {}
    };
  }, [shaders.fs, shaders.vs]);

  return <canvas ref={canvasRef} className={className ?? ""} aria-hidden="true" />;
}

