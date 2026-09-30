"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRightIcon,
  BookOpenCheckIcon,
  FileSearchIcon,
  GaugeIcon,
  LayersIcon,
  ScanTextIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";

type Headline = { label: string; value: number | null; format: "pct" | "ms" | "num"; hint: string };
type Summary = { run_id: string; created_at: string; headline: Headline[]; split: string; config: string };

const PIPELINE = [
  "Condense follow-up",
  "Expand acronyms",
  "Extract filters",
  "Route intent",
  "Dense + BM25 → RRF",
  "Cross-encoder rerank",
  "Relevance gate",
  "Small-to-big context",
  "Versioned prompt",
  "Streamed answer",
  "NLI check per sentence",
  "Confidence + trace",
];

const FEATURES = [
  {
    icon: BookOpenCheckIcon,
    title: "Cited answers",
    text: "Every sentence links to the page and passage it came from; the viewer highlights it.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Knows when it doesn't know",
    text: "A calibrated relevance gate abstains instead of guessing, and shows the closest documents.",
  },
  {
    icon: FileSearchIcon,
    title: "Hybrid semantic search",
    text: "Dense embeddings + BM25 fused with RRF, cross-encoder reranking, facets, score breakdown.",
  },
  {
    icon: ScanTextIcon,
    title: "Scans and drawings",
    text: "OpenCV denoise, deskew and threshold before OCR; title-block fields become metadata.",
  },
  {
    icon: LayersIcon,
    title: "Revision aware",
    text: "Prefers the latest revision of a document and tells you when an older one said otherwise.",
  },
  {
    icon: GaugeIcon,
    title: "Measured, not claimed",
    text: "A golden set of 129 questions, ablations and hallucination checks - numbers on the Evaluation page.",
  },
];

const STACK = [
  "Python",
  "FastAPI",
  "LangChain",
  "Sentence Transformers",
  "Hugging Face Transformers",
  "FAISS",
  "ChromaDB",
  "BM25",
  "OpenCV",
  "EasyOCR / Tesseract",
  "SQLite / SQLModel",
  "Groq · Gemini · Ollama",
  "Next.js",
  "TypeScript",
  "Tailwind",
  "shadcn/ui",
];

function fmt(h: Headline) {
  if (h.value == null) return "not yet measured";
  if (h.format === "pct") return `${(h.value * 100).toFixed(1)}%`;
  if (h.format === "ms") return `${(h.value / 1000).toFixed(2)} s`;
  return String(h.value);
}

export default function Home() {
  const [summary, setSummary] = useState<Summary | null | "none">(null);
  useEffect(() => {
    api<Summary>("/api/eval/summary")
      .then(setSummary)
      .catch(() => setSummary("none"));
  }, []);
  const github = process.env.NEXT_PUBLIC_GITHUB_URL;
  const video = process.env.NEXT_PUBLIC_DEMO_VIDEO_URL;

  return (
    <div className="flex-1">
      <section className="from-primary/8 border-b bg-gradient-to-b to-transparent">
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-20">
          <p className="text-primary text-sm font-medium">横展 · Yokoten — spread the lesson sideways</p>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            New engineers find the lesson before they repeat the failure.
          </h1>
          <p className="text-muted-foreground max-w-2xl text-lg">
            An AI copilot over an automotive supplier&apos;s engineering record — 8D reports, lessons learned, FMEAs,
            test reports, design reviews, change notices, supplier quality data and scanned drawings. Natural-language
            questions, cited answers, measured accuracy.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/chat">
                Ask a question <ArrowRightIcon />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/search">Try semantic search</Link>
            </Button>
            <Button asChild size="lg" variant="ghost">
              <Link href="/eval">See the evaluation</Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-8 px-4 py-16 md:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-muted-foreground text-xs font-semibold tracking-widest uppercase">The problem</h2>
          <p className="text-lg">
            Engineering knowledge lives in hundreds of reports, spreadsheets and scans. New engineers spend hours
            searching for past failures and the lessons behind them — and some lessons are only rediscovered after the
            same failure happens again.
          </p>
        </div>
        <div className="space-y-3">
          <h2 className="text-muted-foreground text-xs font-semibold tracking-widest uppercase">The approach</h2>
          <p className="text-lg">
            A retrieval-augmented chatbot that searches the whole record in natural language, answers only from the
            documents, cites every claim, checks its own sentences for support and says so when the answer is not there.
          </p>
        </div>
      </section>

      <section className="bg-muted/30 border-y">
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-16">
          <h2 className="text-2xl font-semibold tracking-tight">Measured on a 129-question golden set</h2>
          {summary === null && <p className="text-muted-foreground text-sm">Loading evaluation results…</p>}
          {summary === "none" && (
            <p className="text-muted-foreground text-sm">
              Not yet measured — run <code className="bg-muted rounded px-1">.\tasks.ps1 eval</code> to produce the
              numbers.
            </p>
          )}
          {summary && summary !== "none" && (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {summary.headline.map((h) => (
                  <Card key={h.label} className="py-4" title={h.hint}>
                    <CardContent className="px-4">
                      <div className="text-2xl font-semibold tabular-nums">{fmt(h)}</div>
                      <div className="text-muted-foreground text-sm">{h.label}</div>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">
                {summary.split} split · {summary.config} · run {summary.run_id} (
                {new Date(summary.created_at).toLocaleDateString()})
              </p>
            </>
          )}
        </div>
      </section>

      <section className="mx-auto max-w-6xl space-y-6 px-4 py-16">
        <h2 className="text-2xl font-semibold tracking-tight">What it does</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="space-y-2 rounded-lg border p-5">
              <f.icon className="text-primary size-5" />
              <h3 className="font-medium">{f.title}</h3>
              <p className="text-muted-foreground text-sm">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-muted/30 border-t">
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-16">
          <h2 className="text-2xl font-semibold tracking-tight">Architecture: every step is visible in the trace</h2>
          <ol className="flex flex-wrap items-center gap-2 text-sm">
            {PIPELINE.map((p, i) => (
              <li key={p} className="flex items-center gap-2">
                <span className="bg-background rounded-md border px-3 py-2 shadow-xs">
                  <span className="text-muted-foreground mr-1.5 text-xs">{i + 1}</span>
                  {p}
                </span>
                {i < PIPELINE.length - 1 && <ArrowRightIcon className="text-muted-foreground size-4" aria-hidden />}
              </li>
            ))}
          </ol>
          <p className="text-muted-foreground max-w-3xl text-sm">
            Ingestion parses PDF, Word, Excel, CSV, Markdown and images into layout elements with page coordinates, runs
            OCR on scans, chunks four ways and indexes into FAISS (flat and HNSW), ChromaDB and BM25. Answers come from
            Groq, Gemini, a local Ollama server or an in-process Hugging Face model.
          </p>
        </div>
      </section>

      {video && (
        <section className="mx-auto max-w-4xl px-4 py-16">
          <h2 className="mb-4 text-2xl font-semibold tracking-tight">3-minute demo</h2>
          <div className="aspect-video overflow-hidden rounded-lg border">
            <iframe src={video} title="Yokoten demo video" className="h-full w-full" allowFullScreen />
          </div>
        </section>
      )}

      <section className="mx-auto max-w-6xl space-y-4 px-4 py-16">
        <h2 className="text-2xl font-semibold tracking-tight">Built with</h2>
        <div className="flex flex-wrap gap-2">
          {STACK.map((s) => (
            <span key={s} className="rounded-full border px-3 py-1 text-sm">
              {s}
            </span>
          ))}
        </div>
        <p className="text-muted-foreground pt-4 text-sm">
          Built by Ashwani Yadav as a portfolio project for an AI chatbot for engineering knowledge management
          internship. All documents describe a fictional supplier, Norvane Automotive Systems.
          {github && (
            <>
              {" "}
              Source code on{" "}
              <a href={github} className="text-primary hover:underline">
                GitHub
              </a>
              .
            </>
          )}
        </p>
      </section>
    </div>
  );
}
