"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { HeroScene } from "@/components/hero";
import { Badge, Button, Card } from "@/components/ui";
import { CameraCapture } from "@/components/camera/CameraCapture";
import { predictImage } from "@/components/predict/api";
import type { PredictResponse } from "@/components/predict/types";
import { ResultView } from "@/components/predict/ResultView";

type Tab = "upload" | "camera";

function blobUrl(blob: Blob | null) {
  if (!blob) return "";
  return URL.createObjectURL(blob);
}

export default function Page() {
  const [tab, setTab] = useState<Tab>("upload");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PredictResponse | null>(null);

  const preview = useMemo(() => blobUrl(blob), [blob]);

  useEffect(() => {
    const els = Array.from(document.querySelectorAll("[data-reveal]"));
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) (e.target as HTMLElement).classList.add("is-visible");
        }
      },
      { threshold: 0.12 },
    );
    for (const el of els) io.observe(el);
    return () => io.disconnect();
  }, []);

  async function run() {
    if (!blob) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await predictImage(blob);
      setResult(r);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Prediction failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen">
      <div className="pointer-events-none fixed inset-0 -z-10">
        <HeroScene className="h-full w-full opacity-95" />
        <div className="absolute inset-0 bg-grid" />
        <div className="absolute inset-0 bg-vignette" />
      </div>

      <header className="sticky top-0 z-40 px-4 pt-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 rounded-full border border-white/10 bg-white/5 px-4 py-3 backdrop-blur-xl">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-gradient-to-br from-cyan-300 to-violet-400 shadow-neon" />
            <div className="text-sm font-extrabold tracking-tight">DermIQ</div>
            <Badge className="hidden sm:inline-flex">AI Skin Intelligence</Badge>
          </div>
          <nav className="hidden items-center gap-2 md:flex">
            <a className="rounded-full px-3 py-2 text-xs font-semibold text-white/70 hover:bg-white/5 hover:text-white" href="#features">
              Features
            </a>
            <a className="rounded-full px-3 py-2 text-xs font-semibold text-white/70 hover:bg-white/5 hover:text-white" href="#analyzer">
              Analyzer
            </a>
            <a className="rounded-full px-3 py-2 text-xs font-semibold text-white/70 hover:bg-white/5 hover:text-white" href="#safety">
              Safety
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" onClick={() => document.getElementById("analyzer")?.scrollIntoView({ behavior: "smooth" })}>
              Try demo
            </Button>
            <Button type="button" onClick={() => document.getElementById("analyzer")?.scrollIntoView({ behavior: "smooth" })}>
              Start
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl gap-6 px-4 pb-8 pt-14 lg:pt-20">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className="gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.32)]" />
            Privacy-friendly • Free MVP • Non-diagnostic
          </Badge>
        </div>

        <h1 className="max-w-4xl text-4xl font-extrabold tracking-tight sm:text-6xl">
          A futuristic skin photo check
          <span className="mt-2 block bg-gradient-to-r from-cyan-300 via-violet-300 to-emerald-300 bg-clip-text text-transparent">
            with cinematic depth
          </span>
        </h1>

        <p className="max-w-2xl text-sm leading-7 text-white/72 sm:text-base">
          Upload or take a photo. Get top-3 educational possibilities, confidence, safe next steps, and product ideas — wrapped in a premium,
          production-ready experience.
        </p>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => document.getElementById("analyzer")?.scrollIntoView({ behavior: "smooth" })}>
            Start analysis
          </Button>
          <Button type="button" variant="ghost" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>
            See what’s inside
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="reveal" data-reveal>
            <div className="text-xs font-extrabold text-white/70">Atmosphere</div>
            <div className="mt-2 text-base font-extrabold tracking-tight">Neon glass UI</div>
            <div className="mt-2 text-sm leading-6 text-white/70">Soft glow, subtle motion, and a dark futuristic palette tuned for focus.</div>
          </Card>
          <Card className="reveal" data-reveal>
            <div className="text-xs font-extrabold text-white/70">Performance</div>
            <div className="mt-2 text-base font-extrabold tracking-tight">Adaptive rendering</div>
            <div className="mt-2 text-sm leading-6 text-white/70">Dynamic resolution + reduced-motion support for low-end devices.</div>
          </Card>
          <Card className="reveal" data-reveal>
            <div className="text-xs font-extrabold text-white/70">Confidence</div>
            <div className="mt-2 text-base font-extrabold tracking-tight">Safety-first</div>
            <div className="mt-2 text-sm leading-6 text-white/70">Clear disclaimers and escalation advice — never presented as diagnosis.</div>
          </Card>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-6xl px-4 pb-10 pt-10">
        <div className="grid gap-3">
          <div className="text-sm font-extrabold tracking-tight">Features</div>
          <div className="text-sm leading-7 text-white/70">
            Hover and scroll to steer the camera. The 3D stays smooth, tasteful, and performance-aware.
          </div>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <Card className="reveal" data-reveal>
            <div className="text-base font-extrabold tracking-tight">Floating forms</div>
            <div className="mt-2 text-sm leading-6 text-white/70">Raymarched geometry with reflective rims, fog, and soft highlights.</div>
          </Card>
          <Card className="reveal" data-reveal>
            <div className="text-base font-extrabold tracking-tight">Particles & depth</div>
            <div className="mt-2 text-sm leading-6 text-white/70">Subtle atmospheric particles create cinematic scale without clutter.</div>
          </Card>
          <Card className="reveal" data-reveal>
            <div className="text-base font-extrabold tracking-tight">Scroll-synced camera</div>
            <div className="mt-2 text-sm leading-6 text-white/70">The hero responds to scroll position — slow, smooth, intentional.</div>
          </Card>
        </div>
      </section>

      <section id="analyzer" className="mx-auto max-w-6xl px-4 pb-16 pt-8">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <Card className="reveal" data-reveal>
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-extrabold">Analyzer</div>
                <div className="flex gap-2">
                  <button
                    className={`rounded-full px-3 py-1 text-xs font-extrabold border transition ${
                      tab === "upload" ? "bg-white/10 text-white border-white/15" : "bg-white/5 text-white/70 border-white/10 hover:bg-white/10"
                    }`}
                    onClick={() => setTab("upload")}
                    type="button"
                  >
                    Upload
                  </button>
                  <button
                    className={`rounded-full px-3 py-1 text-xs font-extrabold border transition ${
                      tab === "camera" ? "bg-white/10 text-white border-white/15" : "bg-white/5 text-white/70 border-white/10 hover:bg-white/10"
                    }`}
                    onClick={() => setTab("camera")}
                    type="button"
                  >
                    Camera
                  </button>
                </div>
              </div>

              <div className="mt-4">
                {tab === "upload" ? (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="text-sm font-semibold">Upload a skin photo</div>
                    <div className="mt-2 text-xs text-white/60">JPG/PNG. On mobile, it can open your camera/gallery.</div>
                    <input
                      className="mt-3 block w-full text-sm text-white/70 file:mr-4 file:rounded-full file:border-0 file:bg-white/10 file:px-4 file:py-2 file:text-xs file:font-extrabold file:text-white hover:file:bg-white/15"
                      type="file"
                      accept="image/*"
                      capture="environment"
                      onChange={(e) => {
                        const f = e.target.files?.[0] || null;
                        setResult(null);
                        setError("");
                        setBlob(f);
                      }}
                    />
                  </div>
                ) : (
                  <CameraCapture
                    onCapture={(b) => {
                      setBlob(b);
                      setResult(null);
                      setError("");
                    }}
                  />
                )}
              </div>

              <div className="mt-4">
                {preview ? (
                  <div className="relative aspect-[16/10] w-full overflow-hidden rounded-2xl border border-white/10 bg-black/20">
                    <Image src={preview} alt="Preview" fill className="object-cover" />
                  </div>
                ) : (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-6 text-sm text-white/70">
                    Select an image to preview it here.
                  </div>
                )}
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button type="button" onClick={run} disabled={!blob || loading}>
                  {loading ? "Analyzing..." : "Analyze"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setBlob(null);
                    setResult(null);
                    setError("");
                  }}
                >
                  Reset
                </Button>
                <div className="text-xs text-white/60">If you see CORS/network errors, start the backend API first.</div>
              </div>

              {error ? <div className="mt-3 text-sm text-red-300">{error}</div> : null}
            </Card>
          </div>

          <div className="space-y-4">
            <div className="text-sm font-extrabold tracking-tight">Output</div>
            {result ? (
              <ResultView result={result} />
            ) : (
              <div className="reveal rounded-2xl border border-white/10 bg-black/20 p-6 text-sm text-white/70" data-reveal>
                Upload/take a photo and click <b>Analyze</b> to see results and product suggestions.
              </div>
            )}
          </div>
        </div>
      </section>

      <section id="safety" className="mx-auto max-w-6xl px-4 pb-14">
        <Card className="reveal" data-reveal>
          <div className="text-sm font-extrabold tracking-tight">Safety note</div>
          <div className="mt-2 text-sm leading-6 text-white/70">
            Not medical advice. If symptoms are severe, spreading, painful, bleeding, rapidly changing, or you’re concerned — seek a licensed
            clinician.
          </div>
        </Card>
      </section>

      <footer className="mx-auto max-w-6xl px-4 pb-10 text-xs text-white/55">
        Built with Next.js + a small FastAPI backend. No paid APIs.
      </footer>
    </main>
  );
}
