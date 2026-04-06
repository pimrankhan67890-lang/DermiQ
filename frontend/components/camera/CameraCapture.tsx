"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui";

export function CameraCapture(props: { onCapture: (blob: Blob) => void }) {
  const { onCapture } = props;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string>("");

  const supported = useMemo(() => {
    return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
  }, []);

  useEffect(() => {
    return () => {
      if (stream) {
        for (const t of stream.getTracks()) t.stop();
      }
    };
  }, [stream]);

  async function start() {
    setError("");
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      setStream(s);
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play();
      }
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Camera permission denied or unavailable.");
    }
  }

  function stop() {
    if (stream) {
      for (const t of stream.getTracks()) t.stop();
    }
    setStream(null);
  }

  async function snap() {
    const v = videoRef.current;
    if (!v) return;
    const w = v.videoWidth || 1280;
    const h = v.videoHeight || 720;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(v, 0, 0, w, h);
    const blob: Blob | null = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (blob) onCapture(blob);
  }

  if (!supported) {
    return (
      <div className="rounded-2xl border border-slate-200/70 bg-white/60 p-4 text-sm text-slate-700">
        Camera isn’t supported in this browser. Use upload instead.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/60 p-4">
      <div className="aspect-video w-full overflow-hidden rounded-xl bg-slate-950/90">
        <video ref={videoRef} className="h-full w-full object-cover" playsInline muted />
      </div>
      {error ? <div className="mt-3 text-sm text-red-600">{error}</div> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        {!stream ? (
          <Button onClick={start} type="button">
            Start camera
          </Button>
        ) : (
          <>
            <Button onClick={snap} type="button">
              Take photo
            </Button>
            <Button onClick={stop} type="button" variant="ghost">
              Stop
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

