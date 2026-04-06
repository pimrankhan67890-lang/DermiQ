import Link from "next/link";
import { Card } from "@/components/ui";

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 pb-16 pt-12">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight">Terms of Use</h1>
        <Link className="text-xs font-semibold text-white/70 hover:text-white" href="/">
          ← Home
        </Link>
      </div>

      <Card className="mt-6">
        <div className="text-sm leading-7 text-white/75">
          <p>
            By using DermIQ you agree that it is a non-diagnostic educational demo. It does not provide medical diagnosis or treatment. If you are
            worried, seek a licensed clinician.
          </p>
          <p className="mt-3">
            <span className="font-extrabold text-white">Acceptable use:</span> don’t upload unlawful content, don’t attempt to overload or attack
            the service, and don’t use the output to make medical decisions.
          </p>
          <p className="mt-3">
            <span className="font-extrabold text-white">Third-party links:</span> “Buy” links may lead to third-party sites. We don’t control their
            content or policies.
          </p>
        </div>
      </Card>
    </main>
  );
}

