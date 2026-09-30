"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Analytics = {
  total: number;
  up: number;
  down: number;
  questions_answered: number;
  abstained: number;
  verified_answers: number;
  mean_confidence: { up: number | null; down: number | null };
  by_day: { day: string; up: number; down: number }[];
  by_intent: { intent: string; up: number; down: number }[];
  recent_negative: { trace_id: string; question: string; answer: string; comment: string; created_at: string }[];
};

const AXIS = { fontSize: 11, fill: "var(--muted-foreground)" };

/** Live usage signals from the feedback + SME verification loop (not part of the offline eval). */
export function FeedbackAnalytics() {
  const [a, setA] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Analytics>("/api/feedback/analytics")
      .then(setA)
      .catch((e) => setError(e.message));
  }, []);
  if (error) return <p className="text-destructive text-sm">Feedback analytics unavailable: {error}</p>;
  if (!a) return null;
  const stats = [
    { label: "Questions answered", value: a.questions_answered },
    { label: "Abstained", value: a.abstained },
    { label: "Thumbs up / down", value: `${a.up} / ${a.down}` },
    { label: "SME-verified answers", value: a.verified_answers },
    {
      label: "Confidence: liked vs disliked",
      value:
        a.mean_confidence.up != null || a.mean_confidence.down != null
          ? `${a.mean_confidence.up != null ? Math.round(a.mean_confidence.up * 100) : "—"}% / ${
              a.mean_confidence.down != null ? Math.round(a.mean_confidence.down * 100) : "—"
            }%`
          : "—",
    },
  ];
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Live feedback & SME verification</h2>
        <p className="text-muted-foreground text-sm">
          Signals from real use of this deployment: thumbs up/down, comments and answers verified or corrected by
          quality SMEs (verified answers are reused as boosted sources for similar questions).
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {stats.map((s) => (
          <Card key={s.label} className="py-3">
            <CardContent className="px-3">
              <div className="text-xl font-semibold tabular-nums">{s.value}</div>
              <div className="text-muted-foreground text-xs">{s.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      {a.total > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Feedback by intent</CardTitle>
            </CardHeader>
            <CardContent className="h-56">
              <ResponsiveContainer>
                <BarChart data={a.by_intent} margin={{ left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="intent" tick={AXIS} />
                  <YAxis allowDecimals={false} tick={AXIS} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="up" stackId="a" fill="var(--chart-2)" />
                  <Bar dataKey="down" stackId="a" fill="var(--chart-5)" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent negative feedback</CardTitle>
              <CardDescription>What to fix next.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {a.recent_negative.length === 0 && <p className="text-muted-foreground">None yet.</p>}
              {a.recent_negative.map((n) => (
                <div key={n.trace_id + n.created_at} className="rounded-md border p-2">
                  <p className="font-medium">{n.question}</p>
                  {n.comment && <p className="text-muted-foreground">“{n.comment}”</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  );
}
