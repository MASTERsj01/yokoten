"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Metrics = Record<string, number | null>;
export type Headline = { label: string; value: number | null; format: "pct" | "ms" | "num"; hint: string };
export type Ablation = { group: string; variant: string; metrics: Metrics; note?: string; chosen?: boolean };
export type GenConfig = {
  name: string;
  provider: string;
  model: string;
  prompt_version: string;
  n: number;
  metrics: Metrics;
  by_category: Record<string, Metrics>;
};
export type Failure = { id: string; category: string; question: string; expected: string; got: string; reason: string };
export type EvalRun = {
  run_id: string;
  created_at: string;
  split: string;
  n_questions: number;
  config: Record<string, unknown>;
  headline: Headline[];
  retrieval: { overall: Metrics; by_category: Record<string, Metrics>; ablations: Ablation[] };
  generation: { configs: GenConfig[]; judge: string | null; note?: string };
  system: {
    latency: Record<string, { p50: number; p95: number }>;
    tokens_per_answer: { input: number | null; output: number | null };
    index: Record<string, number | string>;
  };
  ocr?: { engines: Record<string, Metrics>; note?: string };
  failures: Failure[];
};

const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const num = (v: number | null | undefined, d = 3) => (v == null ? "—" : v.toFixed(d));
const AXIS = { fontSize: 11, fill: "var(--muted-foreground)" };

function fmtHeadline(h: Headline) {
  if (h.value == null) return "not yet measured";
  if (h.format === "pct") return pct(h.value);
  if (h.format === "ms") return `${(h.value / 1000).toFixed(2)} s`;
  return String(h.value);
}

function ChartCard({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {desc && <CardDescription>{desc}</CardDescription>}
      </CardHeader>
      <CardContent className="h-72">{children}</CardContent>
    </Card>
  );
}

export function EvalDashboard({ run }: { run: EvalRun }) {
  const cats = Object.entries(run.retrieval.by_category).map(([cat, m]) => ({
    cat,
    "Recall@5": m["recall@5"],
    MRR: m.mrr,
  }));
  const groups = [...new Set(run.retrieval.ablations.map((a) => a.group))];
  const latency = Object.entries(run.system.latency).map(([stage, v]) => ({ stage, p50: v.p50, p95: v.p95 }));
  const gen = run.generation.configs;
  const genCats = gen.length
    ? Object.keys(gen[0].by_category).map((cat) => ({
        cat,
        ...Object.fromEntries(gen.map((g) => [g.name, g.by_category[cat]?.correctness ?? null])),
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {run.headline.map((h) => (
          <Card key={h.label} className="py-4" title={h.hint}>
            <CardContent className="px-4">
              <div className="text-2xl font-semibold tabular-nums">{fmtHeadline(h)}</div>
              <div className="text-sm text-muted-foreground">{h.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Run {run.run_id} · {new Date(run.created_at).toLocaleString()} · {run.split} split · {run.n_questions} questions
      </p>

      <Tabs defaultValue="retrieval">
        <TabsList className="flex-wrap">
          <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
          <TabsTrigger value="ablations">Ablations</TabsTrigger>
          <TabsTrigger value="generation">Generation</TabsTrigger>
          <TabsTrigger value="system">Latency & index</TabsTrigger>
          {run.ocr && <TabsTrigger value="ocr">OCR</TabsTrigger>}
          <TabsTrigger value="failures">Error analysis</TabsTrigger>
        </TabsList>

        <TabsContent value="retrieval" className="grid gap-4 pt-3 lg:grid-cols-2">
          <ChartCard title="Retrieval quality by question category" desc="Recall@5 and MRR of the final (reranked) ranking">
            <ResponsiveContainer>
              <BarChart data={cats} margin={{ left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="cat" tick={AXIS} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis domain={[0, 1]} tick={AXIS} />
                <Tooltip formatter={(v) => pct(Number(v))} />
                <Legend />
                <Bar dataKey="Recall@5" fill="var(--chart-1)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="MRR" fill="var(--chart-2)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Overall (chosen configuration)</CardTitle>
              <CardDescription>Doc-level hits; multi-hop questions need every hop covered.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableBody>
                  {Object.entries(run.retrieval.overall).map(([k, v]) => (
                    <TableRow key={k}>
                      <TableCell>{k}</TableCell>
                      <TableCell className="text-right tabular-nums">{k === "n" ? v : pct(v)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ablations" className="grid gap-4 pt-3 lg:grid-cols-2">
          {groups.map((g) => {
            const rows = run.retrieval.ablations.filter((a) => a.group === g);
            return (
              <Card key={g}>
                <CardHeader>
                  <CardTitle className="text-base capitalize">{g.replace("_", " ")}</CardTitle>
                  <CardDescription>One variable changed at a time; everything else = chosen config.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="h-44">
                    <ResponsiveContainer>
                      <BarChart data={rows.map((r) => ({ v: r.variant, "Recall@5": r.metrics["recall@5"], MRR: r.metrics.mrr }))} margin={{ left: -10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="v" tick={AXIS} />
                        <YAxis domain={[0, 1]} tick={AXIS} />
                        <Tooltip formatter={(v) => pct(Number(v))} />
                        <Bar dataKey="Recall@5" fill="var(--chart-1)" radius={[3, 3, 0, 0]} />
                        <Bar dataKey="MRR" fill="var(--chart-3)" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Variant</TableHead>
                        <TableHead className="text-right">R@5</TableHead>
                        <TableHead className="text-right">R@10</TableHead>
                        <TableHead className="text-right">MRR</TableHead>
                        <TableHead className="text-right">nDCG@10</TableHead>
                        <TableHead className="text-right">p50 ms</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((r) => (
                        <TableRow key={r.variant} className={r.chosen ? "bg-primary/5" : ""}>
                          <TableCell>
                            {r.variant} {r.chosen && <Badge variant="secondary">chosen</Badge>}
                            {r.note && <div className="text-xs text-muted-foreground">{r.note}</div>}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{pct(r.metrics["recall@5"])}</TableCell>
                          <TableCell className="text-right tabular-nums">{pct(r.metrics["recall@10"])}</TableCell>
                          <TableCell className="text-right tabular-nums">{num(r.metrics.mrr)}</TableCell>
                          <TableCell className="text-right tabular-nums">{num(r.metrics["ndcg@10"])}</TableCell>
                          <TableCell className="text-right tabular-nums">{num(r.metrics.latency_p50_ms, 0)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        <TabsContent value="generation" className="space-y-4 pt-3">
          {gen.length === 0 && (
            <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              Generation metrics not yet measured. {run.generation.note}
            </p>
          )}
          {gen.length > 0 && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Answer quality per configuration</CardTitle>
                  <CardDescription>
                    Correctness = share of reference facts present; faithfulness = sentences entailed by cited passages
                    (NLI){run.generation.judge ? `; judge = ${run.generation.judge}` : ""}.
                  </CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Configuration</TableHead>
                        {Object.keys(gen[0].metrics).map((k) => (
                          <TableHead key={k} className="text-right">
                            {k.replaceAll("_", " ")}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {gen.map((g) => (
                        <TableRow key={g.name}>
                          <TableCell>
                            <div className="font-medium">{g.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {g.provider} · {g.model} · prompt {g.prompt_version} · n={g.n}
                            </div>
                          </TableCell>
                          {Object.entries(g.metrics).map(([k, v]) => (
                            <TableCell key={k} className="text-right tabular-nums">
                              {k.includes("tokens") || k.includes("_ms") ? num(v, 0) : pct(v)}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
              <ChartCard title="Answer correctness by category">
                <ResponsiveContainer>
                  <BarChart data={genCats} margin={{ left: -10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="cat" tick={AXIS} interval={0} angle={-20} textAnchor="end" height={50} />
                    <YAxis domain={[0, 1]} tick={AXIS} />
                    <Tooltip formatter={(v) => pct(Number(v))} />
                    <Legend />
                    {gen.map((g, i) => (
                      <Bar key={g.name} dataKey={g.name} fill={`var(--chart-${(i % 5) + 1})`} radius={[3, 3, 0, 0]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </>
          )}
        </TabsContent>

        <TabsContent value="system" className="grid gap-4 pt-3 lg:grid-cols-2">
          <ChartCard title="Latency per pipeline stage" desc="p50 and p95 in milliseconds">
            <ResponsiveContainer>
              <BarChart data={latency} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis type="number" tick={AXIS} />
                <YAxis type="category" dataKey="stage" tick={AXIS} width={80} />
                <Tooltip formatter={(v) => `${Number(v).toFixed(0)} ms`} />
                <Legend />
                <Bar dataKey="p50" fill="var(--chart-1)" />
                <Bar dataKey="p95" fill="var(--chart-4)" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Index & cost</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableBody>
                  <TableRow>
                    <TableCell>Tokens per answer (in / out)</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {num(run.system.tokens_per_answer.input, 0)} / {num(run.system.tokens_per_answer.output, 0)}
                    </TableCell>
                  </TableRow>
                  {Object.entries(run.system.index).map(([k, v]) => (
                    <TableRow key={k}>
                      <TableCell>{k.replaceAll("_", " ")}</TableCell>
                      <TableCell className="text-right tabular-nums">{String(v)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {run.ocr && (
          <TabsContent value="ocr" className="pt-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">OCR engines on the scanned documents</CardTitle>
                {run.ocr.note && <CardDescription>{run.ocr.note}</CardDescription>}
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Engine / setting</TableHead>
                      {Object.keys(Object.values(run.ocr.engines)[0] ?? {}).map((k) => (
                        <TableHead key={k} className="text-right">
                          {k.replaceAll("_", " ")}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(run.ocr.engines).map(([name, m]) => (
                      <TableRow key={name}>
                        <TableCell>{name}</TableCell>
                        {Object.entries(m).map(([k, v]) => (
                          <TableCell key={k} className="text-right tabular-nums">
                            {k.endsWith("_s") ? num(v, 1) : pct(v)}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        <TabsContent value="failures" className="space-y-3 pt-3">
          {run.failures.length === 0 && <p className="text-sm text-muted-foreground">No failures recorded.</p>}
          {run.failures.map((f) => (
            <Card key={f.id} className="gap-2 py-4">
              <CardContent className="space-y-1.5 px-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{f.id}</Badge>
                  <Badge variant="secondary">{f.category}</Badge>
                </div>
                <p className="font-medium">{f.question}</p>
                <p>
                  <span className="text-muted-foreground">Expected:</span> {f.expected}
                </p>
                <p>
                  <span className="text-muted-foreground">Got:</span> {f.got}
                </p>
                <p className="text-amber-700 dark:text-amber-400">
                  <span className="text-muted-foreground">Why:</span> {f.reason}
                </p>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
