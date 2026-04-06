import { clsx, type ClassValue } from "clsx";
import type React from "react";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const { className, variant = "primary", ...rest } = props;
  const base =
    "inline-flex items-center justify-center rounded-full px-4 py-2 text-sm font-semibold transition will-change-transform focus:outline-none focus:ring-2 focus:ring-cyan-300/25 active:translate-y-[1px]";
  const styles =
    variant === "primary"
      ? "text-slate-950 border border-white/15 bg-[radial-gradient(12px_12px_at_25%_35%,rgba(255,255,255,0.65),rgba(255,255,255,0)_60%),linear-gradient(135deg,rgba(34,211,238,0.92),rgba(167,139,250,0.92))] shadow-neon hover:-translate-y-[1px]"
      : "text-white border border-white/10 bg-white/5 hover:bg-white/10";
  return <button className={cn(base, styles, className)} {...rest} />;
}

export function Card(props: React.HTMLAttributes<HTMLDivElement>) {
  const { className, ...rest } = props;
  return <div className={cn("glass ring-soft rounded-2xl p-5", className)} {...rest} />;
}

export function Badge(props: React.HTMLAttributes<HTMLSpanElement>) {
  const { className, ...rest } = props;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold bg-white/5 border border-white/10 text-white/75",
        className,
      )}
      {...rest}
    />
  );
}
