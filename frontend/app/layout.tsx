import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "DermIQ — AI Skin Intelligence",
  description: "AI-powered skin intelligence. Upload or take a photo for non-diagnostic possibilities and product suggestions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL || "support@example.com";
  const githubUrl = process.env.NEXT_PUBLIC_GITHUB_URL || "";
  return (
    <html lang="en">
      <body>
        {children}
        <footer className="mx-auto max-w-6xl px-4 pb-10 pt-6 text-xs text-white/60">
          <div className="flex flex-col gap-3 border-t border-white/10 pt-6 sm:flex-row sm:items-center sm:justify-between">
            <div>© {new Date().getFullYear()} DermIQ — Not medical advice.</div>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              <Link className="hover:text-white" href="/privacy">Privacy</Link>
              <Link className="hover:text-white" href="/terms">Terms</Link>
              <Link className="hover:text-white" href="/disclaimer">Disclaimer</Link>
              <a className="hover:text-white" href={`mailto:${contactEmail}`}>Contact</a>
              {githubUrl ? <a className="hover:text-white" href={githubUrl} target="_blank" rel="noreferrer noopener">GitHub</a> : null}
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
