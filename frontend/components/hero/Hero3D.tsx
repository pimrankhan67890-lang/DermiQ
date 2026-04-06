"use client";

export function Hero3D({ kind }: { kind: "bottle" | "jar" }) {
  // Use a WebGL canvas directly (no react-three-fiber) to avoid SSR/runtime issues.
  // This keeps the site reliable even on constrained environments.
  return (
    <div className="relative h-[320px] w-full overflow-hidden rounded-2xl border border-slate-200/70 shadow-glow">
      <Hero3DCanvas kind={kind} />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_400px_at_20%_30%,rgba(59,130,246,0.20),transparent_55%),radial-gradient(700px_380px_at_80%_35%,rgba(16,185,129,0.14),transparent_55%),radial-gradient(900px_450px_at_55%_100%,rgba(99,102,241,0.14),transparent_60%)]" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/0 via-white/0 to-white/65" />
    </div>
  );
}

import { useEffect, useRef } from "react";

function Hero3DCanvas({ kind }: { kind: "bottle" | "jar" }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl", { antialias: true, alpha: true, premultipliedAlpha: true });
    if (!gl) return;

    const mat4 = {
      identity: () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
      multiply: (a: number[], b: number[]) => {
        const o = new Array<number>(16);
        for (let c = 0; c < 4; c++) {
          for (let r = 0; r < 4; r++) {
            o[c * 4 + r] =
              a[0 * 4 + r] * b[c * 4 + 0] +
              a[1 * 4 + r] * b[c * 4 + 1] +
              a[2 * 4 + r] * b[c * 4 + 2] +
              a[3 * 4 + r] * b[c * 4 + 3];
          }
        }
        return o;
      },
      perspective: (fovy: number, aspect: number, near: number, far: number) => {
        const f = 1.0 / Math.tan(fovy / 2);
        const nf = 1 / (near - far);
        return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, (2 * far * near) * nf, 0];
      },
      translate: (m: number[], v: [number, number, number]) => {
        const [x, y, z] = v;
        const t = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1];
        return mat4.multiply(m, t);
      },
      rotateY: (m: number[], a: number) => {
        const c = Math.cos(a),
          s = Math.sin(a);
        const r = [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, 0, 0, 0, 1];
        return mat4.multiply(m, r);
      },
      rotateX: (m: number[], a: number) => {
        const c = Math.cos(a),
          s = Math.sin(a);
        const r = [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, 0, 0, 0, 0, 1];
        return mat4.multiply(m, r);
      },
    };

    const vs = `
      attribute vec3 aPos;
      attribute vec3 aNor;
      uniform mat4 uMVP;
      uniform mat4 uModel;
      varying vec3 vNor;
      varying vec3 vPos;
      void main() {
        vec4 world = uModel * vec4(aPos, 1.0);
        vPos = world.xyz;
        vNor = mat3(uModel) * aNor;
        gl_Position = uMVP * vec4(aPos, 1.0);
      }
    `;

    const fs = `
      precision mediump float;
      varying vec3 vNor;
      varying vec3 vPos;
      uniform vec2 uRes;
      uniform float uTime;
      void main() {
        vec2 uv = gl_FragCoord.xy / uRes.xy;
        vec3 bgA = vec3(0.145, 0.388, 0.922);
        vec3 bgB = vec3(0.388, 0.400, 0.945);
        vec3 bgC = vec3(0.063, 0.725, 0.506);
        float t = 0.5 + 0.5*sin(uTime*0.35 + uv.x*3.1415);
        vec3 bg = mix(mix(bgA, bgB, uv.y), bgC, 0.35*t);
        vec2 p = uv - 0.5;
        float vig = smoothstep(0.75, 0.18, dot(p,p));
        bg *= (0.72 + 0.28*vig);

        vec3 n = normalize(vNor);
        vec3 lightDir = normalize(vec3(0.6, 0.8, 0.4));
        float diff = max(dot(n, lightDir), 0.0);
        vec3 viewDir = normalize(vec3(0.0, 0.0, 1.2) - vPos);
        vec3 halfDir = normalize(lightDir + viewDir);
        float spec = pow(max(dot(n, halfDir), 0.0), 64.0);

        vec3 tint = vec3(0.95, 0.98, 1.0);
        float fres = pow(1.0 - max(dot(n, viewDir), 0.0), 3.0);
        vec3 rim = vec3(0.35, 0.55, 1.0) * (0.45 + 0.55*fres);

        float band = smoothstep(-0.05, 0.05, sin((vPos.y + 0.15) * 7.0));
        vec3 labelCol = mix(vec3(0.20, 0.25, 0.34), vec3(0.92, 0.95, 1.0), 0.55);
        vec3 baseCol = tint * (0.18 + 0.82*diff) + 0.70*spec + rim;
        vec3 col = mix(baseCol, baseCol * (0.78 + 0.22*labelCol), 0.18 * band);

        vec3 outCol = mix(bg, col, 0.82);
        gl_FragColor = vec4(outCol, 1.0);
      }
    `;

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

    const prog = link(vs, fs);
    if (!prog) return;
    gl.useProgram(prog);

    function normalize3(x: number, y: number, z: number) {
      const l = Math.hypot(x, y, z) || 1;
      return [x / l, y / l, z / l] as const;
    }

    function latheMesh(profile: Array<[number, number]>, segments: number) {
      const verts: number[] = [];
      const segs = Math.max(18, Math.min(96, segments | 0));
      const n = profile.length;

      const nr = new Array<number>(n);
      const ny = new Array<number>(n);
      for (let i = 0; i < n; i++) {
        const p0 = profile[Math.max(0, i - 1)];
        const p1 = profile[Math.min(n - 1, i + 1)];
        const dr = p1[0] - p0[0];
        const dy = p1[1] - p0[1];
        const nn = normalize3(dy, -dr, 0);
        nr[i] = nn[0];
        ny[i] = nn[1];
      }

      function pushVert(r: number, y: number, theta: number, nRad: number, nY: number) {
        const c = Math.cos(theta),
          s = Math.sin(theta);
        const x = r * c;
        const z = r * s;
        const nx = nRad * c;
        const nz = nRad * s;
        const nn = normalize3(nx, nY, nz);
        verts.push(x, y, z, nn[0], nn[1], nn[2]);
      }

      for (let si = 0; si < segs; si++) {
        const t0 = (si / segs) * Math.PI * 2;
        const t1 = ((si + 1) / segs) * Math.PI * 2;
        for (let pi = 0; pi < n - 1; pi++) {
          const [r00, y00] = profile[pi];
          const [r01, y01] = profile[pi + 1];
          const n0r = nr[pi],
            n0y = ny[pi];
          const n1r = nr[pi + 1],
            n1y = ny[pi + 1];

          pushVert(r00, y00, t0, n0r, n0y);
          pushVert(r01, y01, t0, n1r, n1y);
          pushVert(r01, y01, t1, n1r, n1y);

          pushVert(r00, y00, t0, n0r, n0y);
          pushVert(r01, y01, t1, n1r, n1y);
          pushVert(r00, y00, t1, n0r, n0y);
        }
      }

      const [rBot, yBot] = profile[0];
      const [rTop, yTop] = profile[n - 1];
      for (let si = 0; si < segs; si++) {
        const t0 = (si / segs) * Math.PI * 2;
        const t1 = ((si + 1) / segs) * Math.PI * 2;
        verts.push(0, yBot, 0, 0, -1, 0);
        verts.push(rBot * Math.cos(t1), yBot, rBot * Math.sin(t1), 0, -1, 0);
        verts.push(rBot * Math.cos(t0), yBot, rBot * Math.sin(t0), 0, -1, 0);
        verts.push(0, yTop, 0, 0, 1, 0);
        verts.push(rTop * Math.cos(t0), yTop, rTop * Math.sin(t0), 0, 1, 0);
        verts.push(rTop * Math.cos(t1), yTop, rTop * Math.sin(t1), 0, 1, 0);
      }

      return new Float32Array(verts);
    }

    const bottleProfile: Array<[number, number]> = [
      [0.46, -1.2],
      [0.52, -1.05],
      [0.56, -0.65],
      [0.56, 0.1],
      [0.48, 0.48],
      [0.3, 0.7],
      [0.22, 0.95],
      [0.24, 1.18],
    ];
    const jarProfile: Array<[number, number]> = [
      [0.62, -1.15],
      [0.66, -0.95],
      [0.7, -0.3],
      [0.7, 0.45],
      [0.66, 0.75],
      [0.64, 0.98],
      [0.68, 1.12],
    ];

    let mesh = latheMesh(kind === "jar" ? jarProfile : bottleProfile, 72);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, mesh, gl.STATIC_DRAW);

    const aPos = gl.getAttribLocation(prog, "aPos");
    const aNor = gl.getAttribLocation(prog, "aNor");
    gl.enableVertexAttribArray(aPos);
    gl.enableVertexAttribArray(aNor);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 24, 0);
    gl.vertexAttribPointer(aNor, 3, gl.FLOAT, false, 24, 12);

    const uMVP = gl.getUniformLocation(prog, "uMVP");
    const uModel = gl.getUniformLocation(prog, "uModel");
    const uRes = gl.getUniformLocation(prog, "uRes");
    const uTime = gl.getUniformLocation(prog, "uTime");

    let w = 0,
      h = 0;
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = Math.max(1, Math.floor(rect.width));
      h = Math.max(1, Math.floor(rect.height));
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener("resize", resize);

    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0, 0, 0, 0);

    const start = performance.now();
    let raf = 0;
    const draw = (now: number) => {
      const t = (now - start) * 0.001;
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, t);

      const aspect = w / Math.max(1, h);
      const proj = mat4.perspective(0.9, aspect, 0.1, 20.0);
      let model = mat4.identity();
      model = mat4.translate(model, [0, Math.sin(t * 0.8) * 0.06, -4.4]);
      model = mat4.rotateY(model, t * 0.45);
      model = mat4.rotateX(model, 0.55 + Math.sin(t * 0.6) * 0.06);
      const mvp = mat4.multiply(proj, model);

      gl.uniformMatrix4fv(uMVP, false, new Float32Array(mvp));
      gl.uniformMatrix4fv(uModel, false, new Float32Array(model));
      gl.drawArrays(gl.TRIANGLES, 0, mesh.length / 6);
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [kind]);

  return <canvas ref={canvasRef} className="h-full w-full" />;
}
