import Link from "next/link";
import { Card } from "@/components/ui";

export default function DisclaimerPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 pb-16 pt-12">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight">Medical Disclaimer</h1>
        <Link className="text-xs font-semibold text-white/70 hover:text-white" href="/">
          ← Home
        </Link>
      </div>

      <Card className="mt-6">
        <div className="text-sm leading-7 text-white/75">
          <p>
            DermIQ is not a medical diagnosis tool. Results can be wrong and may be affected by lighting, camera quality, skin tone variation,
            makeup, and image angle.
          </p>
          <p className="mt-3">
            If you have severe pain, swelling, fever, spreading rash, rapid changes, bleeding, or you are worried, seek a licensed clinician
            promptly.
          </p>
          <p className="mt-3">
            Product suggestions are general and may not be suitable for you. Patch test new products and stop use if irritation occurs.
          </p>
        </div>
      </Card>
    </main>
  );
}

