import Link from "next/link";
import type { ReactNode } from "react";

/** Centered single-column layout matching the login/signup screens. */
export function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 bg-bg">
      <Link href="/" className="mb-8 text-center">
        <h1 className="text-4xl font-black text-primary">turnup</h1>
      </Link>
      <div className="w-full max-w-sm space-y-5">
        <h2 className="text-2xl font-black text-text text-center">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function Notice({ tone, children }: { tone: "error" | "success" | "info"; children: ReactNode }) {
  const cls = {
    error: "border-error/30 bg-error/10 text-error",
    success: "border-success/30 bg-success/10 text-success",
    info: "border-border bg-bg-elevated text-text",
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`px-4 py-3 rounded border-2 text-sm ${cls}`}>
      {children}
    </div>
  );
}
