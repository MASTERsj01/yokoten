"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIcon,
  BadgeCheckIcon,
  DatabaseIcon,
  PencilLineIcon,
  FileTextIcon,
  Loader2Icon,
  MessageSquarePlusIcon,
  SearchXIcon,
  SendIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import { toast } from "sonner";
import { AnswerText } from "@/components/answer-text";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { SourceViewer, type ViewerTarget } from "@/components/source-viewer";
import { TracePanel } from "@/components/trace-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { SME_ROLES, useRole } from "@/lib/role";
import { postSSE } from "@/lib/sse";
import type { Done, Meta, Source, SqlResult, Trace, Verification, VerifiedMatch } from "@/lib/types";
import { cn } from "@/lib/utils";

type Turn = {
  key: string;
  question: string;
  answer: string;
  streaming: boolean;
  meta?: Meta;
  sources: Source[];
  verification?: Verification;
  done?: Done;
  error?: string;
  feedback?: number;
  sql?: SqlResult;
  verified?: VerifiedMatch;
  sme?: string;
};

const viewable = (s: Source) => s.doc_type !== "sql" && s.doc_type !== "verified";

function SqlTable({ sql }: { sql: SqlResult }) {
  return (
    <div className="bg-muted/30 space-y-2 rounded-md border p-3">
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
        <DatabaseIcon className="size-3.5" /> Answered from structured data (text-to-SQL, read-only)
      </p>
      <div className="max-h-64 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {sql.columns.map((c) => (
                <TableHead key={c}>{c}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sql.rows.slice(0, 20).map((r, i) => (
              <TableRow key={i}>
                {r.map((v, j) => (
                  <TableCell key={j} className="whitespace-normal">
                    {v == null ? "—" : String(v)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <details className="text-xs">
        <summary className="text-muted-foreground cursor-pointer">Show SQL</summary>
        <pre className="bg-muted mt-1 overflow-x-auto rounded p-2">{sql.query}</pre>
      </details>
    </div>
  );
}

function SmeActions({ turn, onDone }: { turn: Turn; onDone: (status: string) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(turn.answer);
  const [note, setNote] = useState("");
  const submit = async (status: "verified" | "corrected") => {
    try {
      await api("/api/verify", {
        method: "POST",
        body: JSON.stringify({
          trace_id: turn.done!.trace_id,
          status,
          corrected_answer: status === "corrected" ? text : null,
          note,
        }),
      });
      onDone(status);
      setOpen(false);
      toast.success(
        status === "verified" ? "Answer verified - it will be reused for similar questions" : "Correction saved",
      );
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  if (turn.sme) return <Badge variant="secondary">SME {turn.sme}</Badge>;
  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => submit("verified")} title="Mark as expert-verified">
        <BadgeCheckIcon /> Verify
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)} title="Correct this answer">
        <PencilLineIcon /> Correct
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Correct the answer</DialogTitle>
            <DialogDescription>
              Your corrected answer is shown as an SME-verified source for similar questions.
            </DialogDescription>
          </DialogHeader>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} aria-label="Corrected answer" />
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="Note (optional)"
            aria-label="Note"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => submit("corrected")} disabled={!text.trim()}>
              Save correction
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

type SessionRow = { id: string; title: string; created_at: string };

const EXAMPLES = [
  "What was the root cause of the inverter power module solder fatigue on project P-INV-2104?",
  "Which quality issues involved Seacrest Seals?",
  "What is the current specification for power module mounting and torque at the Chennai Plant?",
  "What material is specified on the drawing of part RAD-30512?",
  "Which wiper motor lessons learned were recorded after 2021?",
  "What was the annual PPM of Brandt-Ostwald Magnetics in 2022?",
];

function toTarget(s: Source): ViewerTarget {
  return { ...s, text: s.text };
}

function FeedbackBar({ turn, onDone }: { turn: Turn; onDone: (rating: number) => void }) {
  const [rating, setRating] = useState<number | null>(turn.feedback ?? null);
  const [comment, setComment] = useState("");
  const [open, setOpen] = useState(false);
  const send = async (r: number, c = "") => {
    try {
      await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({ trace_id: turn.done!.trace_id, rating: r, comment: c }),
      });
      setRating(r);
      onDone(r);
      toast.success("Thanks - feedback saved");
    } catch (e) {
      toast.error(`Feedback failed: ${(e as Error).message}`);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Button
        variant={rating === 1 ? "secondary" : "ghost"}
        size="icon-sm"
        aria-label="Helpful"
        onClick={() => send(1)}
      >
        <ThumbsUpIcon />
      </Button>
      <Button
        variant={rating === -1 ? "secondary" : "ghost"}
        size="icon-sm"
        aria-label="Not helpful"
        onClick={() => {
          setOpen(true);
          send(-1);
        }}
      >
        <ThumbsDownIcon />
      </Button>
      {open && (
        <form
          className="flex w-full gap-2 sm:w-auto"
          onSubmit={(e) => {
            e.preventDefault();
            send(-1, comment);
            setOpen(false);
          }}
        >
          <input
            className="bg-background h-7 min-w-0 flex-1 rounded-md border px-2 text-sm sm:w-64"
            placeholder="What was wrong? (optional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            aria-label="Feedback comment"
          />
          <Button size="sm" type="submit">
            Send
          </Button>
        </form>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const role = useRole();
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  const loadSessions = useCallback(() => {
    api<SessionRow[]>("/api/sessions")
      .then(setSessions)
      .catch(() => {});
  }, []);
  useEffect(loadSessions, [loadSessions]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const patch = (key: string, fn: (t: Turn) => Partial<Turn>) =>
    setTurns((ts) => ts.map((t) => (t.key === key ? { ...t, ...fn(t) } : t)));

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const key = crypto.randomUUID();
    setTurns((ts) => [...ts, { key, question: q, answer: "", streaming: true, sources: [] }]);
    setInput("");
    setBusy(true);
    abort.current = new AbortController();
    try {
      await postSSE(
        "/api/chat",
        { question: q, session_id: sessionId },
        (event, data) => {
          if (event === "session") setSessionId((data as { session_id: string }).session_id);
          else if (event === "meta") patch(key, () => ({ meta: data as Meta }));
          else if (event === "sources") patch(key, () => ({ sources: data as Source[] }));
          else if (event === "sql") patch(key, () => ({ sql: data as SqlResult }));
          else if (event === "verified") patch(key, () => ({ verified: data as VerifiedMatch }));
          else if (event === "token") patch(key, (t) => ({ answer: t.answer + (data as { text: string }).text }));
          else if (event === "verification") patch(key, () => ({ verification: data as Verification }));
          else if (event === "done")
            patch(key, () => ({ done: data as Done, answer: (data as Done).answer, streaming: false }));
          else if (event === "error")
            patch(key, () => ({ error: (data as { message: string }).message, streaming: false }));
        },
        abort.current.signal,
      );
    } catch (e) {
      patch(key, () => ({ error: (e as Error).message, streaming: false }));
    } finally {
      patch(key, () => ({ streaming: false }));
      setBusy(false);
      loadSessions();
    }
  }

  async function openSession(id: string) {
    const msgs = await api<{ role: string; content: string; trace_id: string | null }[]>(`/api/sessions/${id}`);
    const restored: Turn[] = [];
    for (let i = 0; i < msgs.length; i++) {
      const m = msgs[i];
      if (m.role !== "user") continue;
      const a = msgs[i + 1];
      const t: Turn = {
        key: `${id}-${i}`,
        question: m.content,
        answer: a?.content ?? "",
        streaming: false,
        sources: [],
      };
      if (a?.trace_id) {
        try {
          const tr = await api<Trace>(`/api/traces/${a.trace_id}`);
          t.sources = tr.data.sources;
          t.verification = {
            ...tr.data.verification,
            confidence: tr.confidence ?? 0,
            confidence_label: tr.confidence_label,
          };
          t.done = {
            trace_id: tr.id,
            answer: tr.answer,
            abstained: tr.abstained,
            citations: [],
            suggestions: [],
            related: [],
            confidence: tr.confidence ?? 0,
            confidence_label: tr.confidence_label,
            latency_ms: tr.latency_ms,
          };
        } catch {}
      }
      restored.push(t);
    }
    setSessionId(id);
    setTurns(restored);
  }

  function newChat() {
    abort.current?.abort();
    setSessionId(null);
    setTurns([]);
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 gap-4 px-4 py-4">
      <aside className="hidden w-60 shrink-0 flex-col gap-2 md:flex" aria-label="Conversations">
        <Button variant="outline" onClick={newChat}>
          <MessageSquarePlusIcon /> New chat
        </Button>
        <div className="flex-1 space-y-0.5 overflow-y-auto text-sm">
          {sessions.length === 0 && <p className="text-muted-foreground p-2">No conversations yet.</p>}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => openSession(s.id)}
              className={cn(
                "hover:bg-accent w-full truncate rounded-md px-2 py-1.5 text-left",
                s.id === sessionId && "bg-accent",
              )}
              title={s.title}
            >
              {s.title}
            </button>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-6 pb-4">
          {turns.length === 0 && (
            <div className="mx-auto max-w-2xl space-y-6 py-10">
              <div className="space-y-2">
                <h1 className="text-2xl font-semibold tracking-tight">Ask the engineering record</h1>
                <p className="text-muted-foreground">
                  Answers come only from Norvane&apos;s 8D reports, lessons learned, FMEAs, test reports, design
                  reviews, ECNs, supplier quality reports and scanned drawings — each sentence cited to the exact page.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="hover:border-primary/50 hover:bg-accent rounded-lg border p-3 text-left text-sm transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((t) => {
            const unsupported = t.verification?.sentences.filter((s) => !s.supported).map((s) => s.text) ?? [];
            const bySource = new Map(t.sources.map((s) => [s.n, s]));
            return (
              <article key={t.key} className="space-y-3">
                <div className="bg-primary text-primary-foreground ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm px-4 py-2">
                  {t.question}
                </div>
                <div className="bg-card space-y-3 rounded-2xl rounded-bl-sm border p-4">
                  {t.meta && t.meta.standalone !== t.question && (
                    <p className="text-muted-foreground text-xs">Interpreted as: {t.meta.standalone}</p>
                  )}
                  {t.error ? (
                    <p className="text-destructive text-sm">Something went wrong: {t.error}</p>
                  ) : t.answer ? (
                    <AnswerText
                      text={t.answer}
                      unsupported={t.streaming ? [] : unsupported}
                      streaming={t.streaming}
                      onCite={(n) => {
                        const src = bySource.get(n);
                        if (src && viewable(src)) setViewer(toTarget(src));
                      }}
                      citeLabel={(n) => bySource.get(n)?.title ?? `Source ${n}`}
                    />
                  ) : (
                    <p className="text-muted-foreground flex items-center gap-2 text-sm">
                      <Loader2Icon className="size-4 animate-spin" />
                      {t.meta
                        ? `Reading ${t.sources.length || ""} sources with ${t.meta.model}…`
                        : "Searching the knowledge base…"}
                    </p>
                  )}

                  {t.verified && (
                    <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
                      <BadgeCheckIcon className="size-4" /> Uses an SME-{t.verified.status} answer to a similar question
                      ({Math.round(t.verified.similarity * 100)}% match)
                    </p>
                  )}
                  {t.sql && <SqlTable sql={t.sql} />}

                  {t.done?.abstained && (
                    <div className="bg-muted/50 space-y-2 rounded-md p-3 text-sm">
                      <p className="flex items-center gap-1.5 font-medium">
                        <SearchXIcon className="size-4" /> Not answered — this is not in the knowledge base.
                      </p>
                      {t.done.related.length > 0 && (
                        <>
                          <p className="text-muted-foreground">Closest related documents:</p>
                          <ul className="space-y-1">
                            {t.done.related.map((r) => (
                              <li key={r.rev_key}>
                                <Link
                                  className="text-primary hover:underline"
                                  href={`/library/${encodeURIComponent(r.rev_key)}`}
                                >
                                  {r.doc_id}
                                </Link>{" "}
                                — {r.title}
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  )}

                  {t.sources.length > 0 && !t.done?.abstained && (
                    <div className="flex flex-wrap gap-1.5">
                      {t.sources.filter(viewable).map((s) => (
                        <button
                          key={s.n}
                          onClick={() => setViewer(toTarget(s))}
                          className="hover:bg-accent flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-xs"
                          title={s.title}
                        >
                          <span className="text-primary font-semibold">{s.n}</span>
                          <FileTextIcon className="text-muted-foreground size-3 shrink-0" />
                          <span className="truncate">
                            {s.doc_id}
                            {s.page ? ` p.${s.page}` : ""}
                          </span>
                          {!s.is_latest && <Badge variant="destructive">old rev</Badge>}
                        </button>
                      ))}
                    </div>
                  )}

                  {t.done && (
                    <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <ConfidenceBadge label={t.done.confidence_label} value={t.done.confidence} />
                        {unsupported.length > 0 && (
                          <Badge variant="outline" className="border-red-500/40 text-red-700 dark:text-red-400">
                            {unsupported.length} unsupported sentence{unsupported.length > 1 ? "s" : ""}
                          </Badge>
                        )}
                        <Button variant="ghost" size="sm" onClick={() => setTraceId(t.done!.trace_id)}>
                          <ActivityIcon /> Trace
                        </Button>
                        <span className="text-muted-foreground text-xs">{(t.done.latency_ms / 1000).toFixed(1)} s</span>
                        {SME_ROLES.includes(role) && !t.done.abstained && (
                          <SmeActions turn={t} onDone={(st) => patch(t.key, () => ({ sme: st }))} />
                        )}
                      </div>
                      <FeedbackBar turn={t} onDone={(r) => patch(t.key, () => ({ feedback: r }))} />
                    </div>
                  )}

                  {t.done && t.done.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {t.done.suggestions.map((s) => (
                        <button
                          key={s}
                          onClick={() => send(s)}
                          disabled={busy}
                          className="text-muted-foreground hover:bg-accent hover:text-foreground rounded-full border px-3 py-1 text-xs"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
          <div ref={bottom} />
        </div>

        <form
          className="bg-background/95 sticky bottom-0 flex items-end gap-2 border-t py-3 backdrop-blur"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask about a failure, a lesson learned, a test result, a supplier…"
            aria-label="Question"
            rows={2}
            className="min-h-11 resize-none"
          />
          <Button type="submit" disabled={busy || !input.trim()} aria-label="Send">
            {busy ? <Loader2Icon className="animate-spin" /> : <SendIcon />}
          </Button>
        </form>
      </section>

      <SourceViewer target={viewer} onClose={() => setViewer(null)} />
      <TracePanel traceId={traceId} onClose={() => setTraceId(null)} />
    </div>
  );
}
