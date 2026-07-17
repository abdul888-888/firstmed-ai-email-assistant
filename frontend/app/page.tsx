import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AuthControls } from "@/components/auth-controls";
import { BackendStatus } from "@/components/backend-status";
import { buttonVariants } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-start justify-center gap-8 px-6 py-16">
      <div className="space-y-3">
        <p className="text-sm font-medium uppercase tracking-wide text-primary">
          FirstMed
        </p>
        <h1 className="text-4xl font-bold tracking-tight">
          FirstMed AI Email Assistant
        </h1>
        <p className="max-w-prose text-muted-foreground">
          AI-assisted triage and drafting for the FirstMed shared clinical
          inbox. Sign in with your Google account to connect the shared inbox;
          the review dashboard and workflow engine arrive in later phases.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Link href="/demo" className={buttonVariants({ size: "lg" })}>
          Open Demo Playground
          <ArrowRight className="h-4 w-4" />
        </Link>
        <a href="/api/health" className={buttonVariants({ variant: "outline" })}>
          View health
        </a>
      </div>

      <BackendStatus />
      <AuthControls />
    </main>
  );
}
