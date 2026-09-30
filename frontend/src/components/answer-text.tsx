"use client";

import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Range = { start: number; end: number };

function inline(text: string, onCite?: (n: number) => void, citeLabel?: (n: number) => string): ReactNode[] {
  return text.split(/(\[\d+\]|\*\*[^*]+\*\*)/g).map((part, i) => {
    const cite = part.match(/^\[(\d+)\]$/);
    if (cite) {
      const n = Number(cite[1]);
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCite?.(n)}
          title={citeLabel?.(n) ?? `Source ${n}`}
          className="bg-primary/12 text-primary hover:bg-primary hover:text-primary-foreground focus-visible:ring-ring mx-0.5 inline-flex h-4.5 min-w-4.5 translate-y-[-1px] items-center justify-center rounded px-1 align-baseline text-[0.7rem] font-semibold focus-visible:ring-2 focus-visible:outline-none"
        >
          {n}
        </button>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** Renders an answer: paragraphs + bullet lists, clickable [n] citations, unsupported sentences underlined. */
export function AnswerText({
  text,
  unsupported = [],
  onCite,
  citeLabel,
  streaming,
}: {
  text: string;
  unsupported?: string[];
  onCite?: (n: number) => void;
  citeLabel?: (n: number) => string;
  streaming?: boolean;
}) {
  const ranges: Range[] = unsupported
    .map((s) => ({ start: text.indexOf(s), end: text.indexOf(s) + s.length }))
    .filter((r) => r.start >= 0);
  const lines = text.split("\n");
  let offset = 0;
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length)
      blocks.push(
        <ul key={`ul${blocks.length}`} className="my-1 ml-5 list-disc space-y-1">
          {list}
        </ul>,
      );
    list = [];
  };
  lines.forEach((line, li) => {
    const start = offset;
    offset += line.length + 1;
    const trimmed = line.trim();
    if (!trimmed) {
      flush();
      return;
    }
    // split the line at unsupported-range boundaries
    const cuts = new Set<number>([start, start + line.length]);
    ranges.forEach((r) => {
      if (r.start > start && r.start < start + line.length) cuts.add(r.start);
      if (r.end > start && r.end < start + line.length) cuts.add(r.end);
    });
    const points = [...cuts].sort((a, b) => a - b);
    const parts: ReactNode[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const seg = text.slice(points[i], points[i + 1]);
      const bad = ranges.some((r) => points[i] >= r.start && points[i + 1] <= r.end);
      parts.push(
        <span
          key={i}
          className={cn(bad && "decoration-destructive/70 underline decoration-wavy underline-offset-4")}
          title={bad ? "Not supported by the cited sources (NLI check)" : undefined}
        >
          {inline(seg, onCite, citeLabel)}
        </span>,
      );
    }
    const bullet = /^\s*([-*•]|\d+\.)\s+/.exec(line);
    if (bullet) {
      parts[0] = <Fragment key="b0">{inline(line.slice(bullet[0].length), onCite, citeLabel)}</Fragment>;
      list.push(<li key={li}>{parts.length > 1 ? parts : parts[0]}</li>);
    } else {
      flush();
      blocks.push(
        <p key={li} className="leading-relaxed">
          {parts}
        </p>,
      );
    }
  });
  flush();
  return (
    <div className="space-y-2 text-[0.95rem]">
      {blocks}
      {streaming && <span className="bg-foreground/60 ml-0.5 inline-block h-4 w-1.5 animate-pulse align-middle" />}
    </div>
  );
}
