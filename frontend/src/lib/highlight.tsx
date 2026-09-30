import type { ReactNode } from "react";

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Wrap every occurrence of the given terms (case-insensitive) in <mark>. */
export function highlightTerms(text: string, terms: string[]): ReactNode[] {
  const t = terms.filter((x) => x.trim().length > 1);
  if (!t.length) return [text];
  const re = new RegExp(`(${t.map(esc).join("|")})`, "gi");
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded-sm bg-highlight px-0.5 text-foreground">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

/** Highlight one passage (the retrieved chunk) inside a longer text (the parent section). */
export function highlightPassage(text: string, passage: string): ReactNode[] {
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  const t = norm(text);
  const p = norm(passage);
  const i = p ? t.indexOf(p.slice(0, 200)) : -1;
  if (i < 0) return [t];
  const end = Math.min(t.length, i + p.length);
  return [
    t.slice(0, i),
    <mark key="m" className="rounded-sm bg-highlight px-0.5 text-foreground">
      {t.slice(i, end)}
    </mark>,
    t.slice(end),
  ];
}
