"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIcon,
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
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { postSSE } from "@/lib/sse";
import type { Done, Meta, Source, Trace, Verification } from "@/lib/types";
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
};

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
            className="h-7 min-w-0 flex-1 rounded-md border bg-background px-2 text-sm sm:w-64"
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
          else if (event === "token") patch(key, (t) => ({ answer: t.answer + (data as { text: string }).text }));
          else if (event === "verification") patch(key, () => ({ verification: data as Verification }));
          else if (event === "done") patch(key, () => ({ done: data as Done, answer: (data as Done).answer, streaming: false }));
          else if (event === "error") patch(key, () => ({ error: (data as { message: string }).message, streaming: false }));
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
      const t: Turn = { key: `${id}-${i}`, question: m.content, answer: a?.content ?? "", streaming: false, sources: [] };
      if (a?.trace_id) {
        try {
          const tr = await api<Trace>(`/api/traces/${a.trace_id}`);
          t.sources = tr.data.sources;
          t.verification = { ...tr.data.verification, confidence: tr.confidence ?? 0, confidence_label: tr.confidence_label };
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
          {sessions.length === 0 && <p className="p-2 text-muted-foreground">No conversations yet.</p>}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => openSession(s.id)}
              className={cn(
                "w-full truncate rounded-md px-2 py-1.5 text-left hover:bg-accent",
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
                  Answers come only from Norvane&apos;s 8D reports, lessons learned, FMEAs, test reports, design reviews,
                  ECNs, supplier quality reports and scanned drawings — each sentence cited to the exact page.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="rounded-lg border p-3 text-left text-sm transition-colors hover:border-primary/50 hover:bg-accent"
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
                <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-primary-foreground">
                  {t.question}
                </div>
                <div className="space-y-3 rounded-2xl rounded-bl-sm border bg-card p-4">
                  {t.meta && t.meta.standalone !== t.question && (
                    <p className="text-xs text-muted-foreground">Interpreted as: {t.meta.standalone}</p>
                  )}
                  {t.error ? (
                    <p className="text-sm text-destructive">Something went wrong: {t.error}</p>
                  ) : t.answer ? (
                    <AnswerText
                      text={t.answer}
                      unsupported={t.streaming ? [] : unsupported}
                      streaming={t.streaming}
                      onCite={(n) => bySource.get(n) && setViewer(toTarget(bySource.get(n)!))}
                      citeLabel={(n) => bySource.get(n)?.title ?? `Source ${n}`}
                    />
                  ) : (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2Icon className="size-4 animate-spin" />
                      {t.meta ? `Reading ${t.sources.length || ""} sources with ${t.meta.model}…` : "Searching the knowledge base…"}
                    </p>
                  )}

                  {t.done?.abstained && (
                    <div className="space-y-2 rounded-md bg-muted/50 p-3 text-sm">
                      <p className="flex items-center gap-1.5 font-medium">
                        <SearchXIcon className="size-4" /> Not answered — this is not in the knowledge base.
                      </p>
                      {t.done.related.length > 0 && (
                        <>
                          <p className="text-muted-foreground">Closest related documents:</p>
                          <ul className="space-y-1">
                            {t.done.related.map((r) => (
                              <li key={r.rev_key}>
                                <Link className="text-primary hover:underline" href={`/library/${encodeURIComponent(r.rev_key)}`}>
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
                      {t.sources.map((s) => (
                        <button
                          key={s.n}
                          onClick={() => setViewer(toTarget(s))}
                          className="flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-xs hover:bg-accent"
                          title={s.title}
                        >
                          <span className="font-semibold text-primary">{s.n}</span>
                          <FileTextIcon className="size-3 shrink-0 text-muted-foreground" />
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
                        <span className="text-xs text-muted-foreground">{(t.done.latency_ms / 1000).toFixed(1)} s</span>
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
                          className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
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
          className="sticky bottom-0 flex items-end gap-2 border-t bg-background/95 py-3 backdrop-blur"
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
