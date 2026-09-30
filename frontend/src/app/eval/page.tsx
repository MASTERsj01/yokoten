"use client";

import { useEffect, useState } from "react";
import { EvalDashboard, type EvalRun } from "@/components/eval-dashboard";
import { FeedbackAnalytics } from "@/components/feedback-analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export default function EvalPage() {
  const [run, setRun] = useState<EvalRun | null | "none">(null);
  useEffect(() => {
    api<EvalRun>("/api/eval/latest")
      .then(setRun)
      .catch(() => setRun("none"));
  }, []);
  return (
    <div className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Evaluation</h1>
        <p className="text-muted-foreground text-sm">
          Real measurements on the golden set (dev split for tuning, test split for reported numbers). Reproduce with{" "}
          <code className="bg-muted rounded px-1">.\tasks.ps1 eval</code>.
        </p>
      </div>
      {run === null && <Skeleton className="h-96" />}
      {run === "none" && (
        <p className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
          Not yet measured - no evaluation run has been recorded.
        </p>
      )}
      {run && run !== "none" && <EvalDashboard run={run} />}
      <FeedbackAnalytics />
    </div>
  );
}
