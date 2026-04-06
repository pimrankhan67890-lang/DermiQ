"use client";

import Image from "next/image";
import type { PredictResponse } from "@/components/predict/types";
import { Badge, Button, Card } from "@/components/ui";
import { motion } from "framer-motion";

function labelTitle(label: string) {
  return label.replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function pct(p: number) {
  const x = Number.isFinite(p) ? Math.max(0, Math.min(1, p)) : 0;
  return `${(x * 100).toFixed(1)}%`;
}

export function ResultView(props: { result: PredictResponse }) {
  const { result } = props;
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm text-slate-600">Possible condition (non-diagnostic)</div>
            <div className="mt-1 text-2xl font-extrabold tracking-tight">{labelTitle(result.top_label)}</div>
          </div>
          <div className="flex items-center gap-2">
            <Badge>Confidence: {pct(result.top_prob)}</Badge>
            <Badge>Backend: {result.model_backend}</Badge>
          </div>
        </div>
        <div className="mt-3 text-sm text-slate-600">{result.notes}</div>
      </Card>

      <Card>
        <div className="text-sm font-bold">Top 3 possibilities</div>
        <div className="mt-3 space-y-3">
          {result.top3.map((t, idx) => (
            <div key={t.label} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <div className="font-semibold">{idx + 1}. {labelTitle(t.label)}</div>
                <div className="text-slate-600">{pct(t.prob)}</div>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200/70">
                <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.max(0, Math.min(1, t.prob)) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <div className="text-sm font-bold">Safety</div>
        <div className="mt-2 text-sm text-slate-700">{result.safety}</div>
      </Card>

      <Card>
        <div className="text-sm font-bold">What you can do</div>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
          {result.advice.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-bold">Recommended products</div>
          <div className="text-xs text-slate-600">Based on the top label</div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {result.products.map((p) => (
            <motion.div key={p.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4">
                <div className="relative aspect-[16/10] w-full overflow-hidden rounded-xl bg-slate-100">
                  <Image src={p.image || "/products/placeholder.svg"} alt={p.name} fill className="object-cover" />
                </div>
                <div className="mt-3 font-bold">{p.name}</div>
                <div className="mt-1 text-sm text-slate-600">{p.reason}</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {p.buy_links.slice(0, 3).map((l) => (
                    <a key={l.url} href={l.url} target="_blank" rel="noreferrer">
                      <Button type="button" variant="ghost">{l.name}</Button>
                    </a>
                  ))}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

        {result.disclaimer ? <div className="mt-3 text-xs text-slate-600">{result.disclaimer}</div> : null}
      </Card>
    </div>
  );
}

