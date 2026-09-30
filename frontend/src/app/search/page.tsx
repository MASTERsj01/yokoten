"use client";

import { useEffect, useState } from "react";
import { FilterIcon, Loader2Icon, SearchIcon, XIcon } from "lucide-react";
import { SourceViewer, type ViewerTarget } from "@/components/source-viewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { highlightTerms } from "@/lib/highlight";
import type { Catalog, Facet, SearchResult } from "@/lib/types";

type Facets = Record<string, Facet[]> & { doc_type_labels?: Record<string, string> };
const FACETS: { key: string; label: string }[] = [
  { key: "doc_type", label: "Document type" },
  { key: "product_line", label: "Product line" },
  { key: "component", label: "Component" },
  { key: "project", label: "Project" },
  { key: "year", label: "Year" },
  { key: "plant", label: "Plant" },
];
const EXAMPLES = ["solder voiding power module", "INV-70455", "seal compression set", "SWAAT corrosion test"];

function Score({ label, value, rank, hint }: { label: string; value: string; rank?: number | null; hint: string }) {
  return (
    <div className="rounded border px-2 py-1" title={hint}>
      <div className="text-[0.65rem] text-muted-foreground uppercase">{label}</div>
      <div className="tabular-nums">
        {value}
        {rank != null && <span className="text-muted-foreground"> #{rank}</span>}
      </div>
    </div>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [rerank, setRerank] = useState(true);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<Record<string, (string | number)[]>>({});
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [terms, setTerms] = useState<string[]>([]);
  const [took, setTook] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [showFacets, setShowFacets] = useState(false);

  useEffect(() => {
    api<Facets>("/api/facets").then(setFacets).catch((e) => setError(e.message));
    api<Catalog>("/api/catalog").then(setCatalog).catch(() => {});
  }, []);

  const label = (key: string, v: string | number) => {
    if (key === "doc_type") return catalog?.doc_types[String(v)] ?? String(v);
    if (key === "component") {
      const n = catalog?.components[String(v)]?.name ?? String(v);
      return n.charAt(0).toUpperCase() + n.slice(1);
    }
    if (key === "product_line") return catalog?.product_lines[String(v)] ?? String(v);
    if (key === "plant") return catalog?.plants[String(v)] ?? String(v);
    return String(v);
  };

  async function run(q = query, sel = selected) {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    const filters: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(sel)) {
      if (!v.length) continue;
      if (k === "year") {
        filters.year_min = Math.min(...(v as number[]));
        filters.year_max = Math.max(...(v as number[]));
      } else filters[k] = v;
    }
    try {
      const r = await api<{ results: SearchResult[]; terms: string[]; took_ms: number }>("/api/search", {
        method: "POST",
        body: JSON.stringify({ query: q, mode, rerank, k: 20, filters }),
      });
      setResults(r.results);
      setTerms(r.terms);
      setTook(r.took_ms);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function toggle(key: string, value: string | number) {
    const cur = selected[key] ?? [];
    const next = { ...selected, [key]: cur.includes(value) ? cur.filter((x) => x !== value) : [...cur, value] };
    setSelected(next);
    if (query.trim()) run(query, next);
  }

  const active = Object.entries(selected).flatMap(([k, vs]) => vs.map((v) => [k, v] as const));

  return (
    <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
      <div className="mb-4 space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Semantic search</h1>
        <p className="text-sm text-muted-foreground">
          Hybrid retrieval: dense embeddings + BM25, fused with Reciprocal Rank Fusion, re-ranked by a cross-encoder.
        </p>
      </div>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div className="relative flex-1">
          <SearchIcon className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search failures, parts, suppliers, tests…"
            className="pl-8"
            aria-label="Search query"
          />
        </div>
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger className="w-full sm:w-36" aria-label="Retrieval mode">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="hybrid">Hybrid</SelectItem>
            <SelectItem value="dense">Dense only</SelectItem>
            <SelectItem value="bm25">BM25 only</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2 px-1">
          <Switch id="rerank" checked={rerank} onCheckedChange={setRerank} />
          <Label htmlFor="rerank">Rerank</Label>
        </div>
        <Button type="submit" disabled={loading || !query.trim()}>
          {loading ? <Loader2Icon className="animate-spin" /> : <SearchIcon />} Search
        </Button>
        <Button type="button" variant="outline" className="md:hidden" onClick={() => setShowFacets((s) => !s)}>
          <FilterIcon /> Filters
        </Button>
      </form>

      {active.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {active.map(([k, v]) => (
            <Badge key={`${k}${v}`} variant="secondary" className="gap-1">
              {label(k, v)}
              <button onClick={() => toggle(k, v)} aria-label={`Remove filter ${label(k, v)}`}>
                <XIcon className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      <div className="mt-4 grid gap-6 md:grid-cols-[15rem_1fr]">
        <aside className={`${showFacets ? "block" : "hidden"} space-y-4 md:block`} aria-label="Filters">
          {!facets && <Skeleton className="h-96" />}
          {facets &&
            FACETS.map(({ key, label: title }) => (
              <fieldset key={key} className="space-y-1.5">
                <legend className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</legend>
                <div className="max-h-44 space-y-1 overflow-y-auto pr-1">
                  {(facets[key] ?? []).map((f) => {
                    const id = `f-${key}-${f.value}`;
                    return (
                      <div key={id} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          id={id}
                          checked={(selected[key] ?? []).includes(f.value)}
                          onCheckedChange={() => toggle(key, f.value)}
                        />
                        <Label htmlFor={id} className="flex-1 truncate font-normal">
                          {label(key, f.value)}
                        </Label>
                        <span className="text-xs text-muted-foreground tabular-nums">{f.count}</span>
                      </div>
                    );
                  })}
                </div>
              </fieldset>
            ))}
        </aside>

        <section className="min-w-0 space-y-3" aria-live="polite">
          {error && <p className="text-sm text-destructive">Search failed: {error}</p>}
          {results === null && !loading && (
            <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              <p>Try a query such as</p>
              <div className="mt-2 flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((q) => (
                  <Button
                    key={q}
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setQuery(q);
                      run(q);
                    }}
                  >
                    {q}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {loading && Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-32" />)}
          {results && !loading && (
            <p className="text-xs text-muted-foreground">
              {results.length} results in {took.toFixed(0)} ms
            </p>
          )}
          {results && !loading && results.length === 0 && (
            <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              No matching passages. Remove a filter or rephrase the query.
            </p>
          )}
          {!loading &&
            results?.map((r) => (
              <article key={r.chunk_id} className="space-y-2 rounded-lg border bg-card p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <button
                    className="text-left font-medium text-primary hover:underline"
                    onClick={() =>
                      setViewer({ ...r, snippet: r.text, text: r.text, superseded_by: null })
                    }
                  >
                    {r.title}
                  </button>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="outline">{r.doc_id}</Badge>
                    <Badge variant="secondary">{r.doc_type_label}</Badge>
                    {!r.is_latest && <Badge variant="destructive">superseded</Badge>}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  {[r.section, r.page && `page ${r.page}`, r.year, r.project, r.plant && label("plant", r.plant)]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="line-clamp-4 text-sm whitespace-pre-line">{highlightTerms(r.text, terms)}</p>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  <Score label="Dense" value={r.scores.dense?.toFixed(3) ?? "—"} rank={r.scores.dense_rank} hint="Cosine similarity (Sentence Transformers)" />
                  <Score label="BM25" value={r.scores.bm25?.toFixed(1) ?? "—"} rank={r.scores.bm25_rank} hint="Lexical BM25 score" />
                  <Score label="RRF" value={r.scores.fused.toFixed(4)} hint="Reciprocal Rank Fusion of dense + BM25 ranks" />
                  <Score
                    label="Relevance"
                    value={r.scores.relevance != null ? `${Math.round(r.scores.relevance * 100)}%` : "—"}
                    hint="Cross-encoder rerank score (sigmoid)"
                  />
                </div>
              </article>
            ))}
        </section>
      </div>
      <SourceViewer target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}
