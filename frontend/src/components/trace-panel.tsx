"use client";

import { useEffect, useState } from "react";
import { CheckIcon, XIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { Trace } from "@/lib/types";

const fmt = (v: number | null | undefined, d = 3) => (v == null ? "—" : Number(v).toFixed(d));

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border p-2">
      <span className="text-muted-foreground text-[0.7rem] tracking-wide uppercase">{k}</span>
      <span className="text-sm break-words">{v}</span>
    </div>
  );
}

/** Explainability trace: query rewriting, filters, per-stage latency, retrieval scores, NLI checks. */
export function TracePanel({ traceId, onClose }: { traceId: string | null; onClose: () => void }) {
  return (
    <Sheet open={!!traceId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto p-0 data-[side=right]:sm:max-w-3xl">
        <SheetHeader className="border-b p-4 pr-12">
          <SheetTitle>Answer trace</SheetTitle>
          <SheetDescription>Every pipeline step for this answer, with scores and timings.</SheetDescription>
        </SheetHeader>
        {traceId && <TraceBody key={traceId} traceId={traceId} />}
      </SheetContent>
    </Sheet>
  );
}

function TraceBody({ traceId }: { traceId: string }) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Trace>(`/api/traces/${traceId}`)
      .then(setTrace)
      .catch((e) => setError(String(e.message ?? e)));
  }, [traceId]);

  const steps = trace?.data.steps ?? [];
  const total = steps.reduce((a, s) => a + s.ms, 0) || 1;
  const inContext = new Set(trace?.data.sources.map((s) => s.chunk_id));

  return (
    <>
      {error && <p className="text-destructive p-4 text-sm">{error}</p>}
      {!trace && !error && <Skeleton className="m-4 h-96" />}
      {trace && (
        <div className="space-y-6 p-4 text-sm">
          <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <KV k="Intent" v={trace.intent} />
            <KV k="Model" v={`${trace.provider} · ${trace.model}`} />
            <KV k="Prompt" v={trace.prompt_version} />
            <KV k="Role" v={trace.role} />
            <KV k="Tokens in / out" v={`${trace.input_tokens} / ${trace.output_tokens}`} />
            <KV k="Latency" v={`${(trace.latency_ms / 1000).toFixed(2)} s`} />
            <KV k="Relevance gate" v={fmt(trace.data.gate)} />
            <KV k="LLM cache" v={trace.data.llm_cached ? "hit" : "miss"} />
          </section>

          <section className="space-y-2">
            <h3 className="font-medium">Query understanding</h3>
            <KV k="Question" v={trace.question} />
            <KV k="Standalone (condensed)" v={trace.standalone} />
            <KV k="Expanded for retrieval" v={trace.data.expanded} />
            <KV
              k="Extracted filters"
              v={
                <span className="flex flex-wrap gap-1">
                  {Object.keys(trace.data.filters).length === 0 && "none"}
                  {Object.entries(trace.data.filters).map(([k, v]) => (
                    <Badge key={k} variant="secondary">
                      {k}: {Array.isArray(v) ? v.join(", ") : String(v)}
                    </Badge>
                  ))}
                  {trace.data.filters_relaxed && <Badge variant="destructive">relaxed (no match)</Badge>}
                </span>
              }
            />
          </section>

          <section className="space-y-2">
            <h3 className="font-medium">Latency per stage</h3>
            <div className="space-y-1">
              {steps.map((s) => (
                <div key={s.name} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-2">
                  <span className="text-muted-foreground">{s.name}</span>
                  <div className="bg-muted h-2 rounded">
                    <div
                      className="bg-primary h-2 rounded"
                      style={{ width: `${Math.max(1, (s.ms / total) * 100)}%` }}
                    />
                  </div>
                  <span className="text-right tabular-nums">{s.ms.toFixed(0)} ms</span>
                </div>
              ))}
            </div>
          </section>

          {trace.data.sql && (
            <section className="space-y-2">
              <h3 className="font-medium">Structured query (text-to-SQL)</h3>
              <pre className="bg-muted overflow-x-auto rounded-md p-3 text-xs">{trace.data.sql.query}</pre>
            </section>
          )}

          <section className="space-y-2">
            <h3 className="font-medium">Retrieved chunks ({trace.data.retrieved.length})</h3>
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>Document</TableHead>
                    <TableHead className="text-right">Dense</TableHead>
                    <TableHead className="text-right">BM25</TableHead>
                    <TableHead className="text-right">RRF</TableHead>
                    <TableHead className="text-right">Rerank</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {trace.data.retrieved.slice(0, 20).map((r, i) => (
                    <TableRow key={r.chunk_id} className={inContext.has(r.chunk_id) ? "bg-primary/5" : ""}>
                      <TableCell>{i + 1}</TableCell>
                      <TableCell className="max-w-64">
                        <div className="font-medium">
                          {r.doc_id} <span className="text-muted-foreground">Rev {r.revision}</span>
                          {inContext.has(r.chunk_id) && (
                            <Badge className="ml-1" variant="secondary">
                              in context
                            </Badge>
                          )}
                        </div>
                        <div className="text-muted-foreground truncate text-xs" title={r.snippet}>
                          {r.section || r.snippet}
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(r.dense)} <span className="text-muted-foreground">#{r.dense_rank ?? "–"}</span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(r.bm25, 1)} <span className="text-muted-foreground">#{r.bm25_rank ?? "–"}</span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{fmt(r.fused, 4)}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmt(r.rerank, 2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="font-medium">
              Faithfulness check (NLI)
              {trace.data.verification.faithfulness != null &&
                ` · ${Math.round(trace.data.verification.faithfulness * 100)}% of sentences supported`}
            </h3>
            {trace.data.verification.sentences.length === 0 && (
              <p className="text-muted-foreground">No sentences were checked for this answer.</p>
            )}
            <ul className="space-y-1.5">
              {trace.data.verification.sentences.map((s, i) => (
                <li key={i} className="flex gap-2 rounded-md border p-2">
                  {s.supported ? (
                    <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-label="supported" />
                  ) : (
                    <XIcon className="text-destructive mt-0.5 size-4 shrink-0" aria-label="not supported" />
                  )}
                  <span className="flex-1">{s.text}</span>
                  <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                    entail {Math.round(s.entailment * 100)}%
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
