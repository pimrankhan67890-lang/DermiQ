import type { PredictResponse } from "@/components/predict/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export async function predictImage(blob: Blob): Promise<PredictResponse> {
  if (!API_URL) {
    throw new Error("API not configured. Set NEXT_PUBLIC_API_URL (e.g. https://your-backend.example.com).");
  }
  const fd = new FormData();
  fd.append("file", blob, "image.jpg");
  const res = await fetch(`${API_URL}/predict`, { method: "POST", body: fd });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }
  return (await res.json()) as PredictResponse;
}
