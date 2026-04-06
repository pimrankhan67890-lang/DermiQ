import Link from "next/link";
import { Card } from "@/components/ui";

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 pb-16 pt-12">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight">Privacy Policy</h1>
        <Link className="text-xs font-semibold text-white/70 hover:text-white" href="/">
          ← Home
        </Link>
      </div>

      <Card className="mt-6">
        <div className="text-sm leading-7 text-white/75">
          <p>
            DermIQ is an educational, non-diagnostic tool. If you use the analyzer, your uploaded image is sent to our backend service to generate
            results.
          </p>
          <p className="mt-3">
            <span className="font-extrabold text-white">What we collect:</span> uploaded images (for analysis) and basic technical logs (time, IP
            address, user agent) for security and reliability.
          </p>
          <p className="mt-3">
            <span className="font-extrabold text-white">Retention:</span> if you deploy DermIQ publicly, define a clear retention window for any
            stored logs and update this page accordingly.
          </p>
          <p className="mt-3">
            <span className="font-extrabold text-white">Your choice:</span> don’t upload sensitive images. Prefer non-identifying skin photos when
            possible.
          </p>
        </div>
      </Card>
    </main>
  );
}

