"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BookOpenIcon, GraduationCapIcon, Loader2Icon, SparklesIcon } from "lucide-react";
import { AnswerText } from "@/components/answer-text";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { Catalog } from "@/lib/types";

type Ref = { doc_id: string; rev_key: string; title: string; doc_type_label: string; year: number | null };
type Digest = {
  documents: number;
  issues: (Ref & { project: string | null; plant: string | null; suppliers: string[] })[];
  lessons: (Ref & { lesson: string })[];
  failure_modes: {
    failure_mode: string;
    item: string;
    effect: string;
    cause: string;
    severity: number;
    occurrence: number;
    detection: number;
    action_priority: string;
    status: string;
    doc_id: string;
    revised_action_priority: string | null;
  }[];
  must_read: Ref[];
  glossary: { term: string; meaning: string; mentions: number }[];
};
type Summary = { text: string; sources: { n: number; doc_id: string; rev_key: string; title: string }[]; model: string | null };

const docLink = (r: { rev_key: string; doc_id: string }) => (
  <Link href={`/library/${encodeURIComponent(r.rev_key)}`} className="text-primary hover:underline">
    {r.doc_id}
  </Link>
);

export default function OnboardingPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [choice, setChoice] = useState("c:INV");
  const [digest, setDigest] = useState<Digest | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [summarising, setSummarising] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Catalog>("/api/catalog").then(setCatalog).catch((e) => setError(e.message));
  }, []);

  const body = () => (choice.startsWith("c:") ? { component: choice.slice(2) } : { product_line: choice.slice(2) });
  const name = catalog
    ? choice.startsWith("c:")
      ? catalog.components[choice.slice(2)]?.name
      : catalog.product_lines[choice.slice(2)]
    : "";

  async function generate() {
    setLoading(true);
    setError(null);
    setSummary(null);
    try {
      const d = await api<Digest>("/api/onboarding", { method: "POST", body: JSON.stringify(body()) });
      setDigest(d);
      setLoading(false);
      setSummarising(true);
      const s = await api<Summary>("/api/onboarding/summary", { method: "POST", body: JSON.stringify(body()) });
      setSummary(s);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
      setSummarising(false);
    }
  }

  const sourceByN = new Map(summary?.sources.map((s) => [s.n, s]));

  return (
    <div className="mx-auto w-full max-w-6xl flex-1 space-y-6 px-4 py-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <GraduationCapIcon className="size-6" /> Onboarding digest
        </h1>
        <p className="text-sm text-muted-foreground">
          New to a product? Get the recurring failure modes, the lessons the team learned the hard way, the documents to
          read first and the acronyms you will hear - all cited.
        </p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Select value={choice} onValueChange={setChoice}>
          <SelectTrigger className="w-full sm:w-72" aria-label="Product">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Components</SelectLabel>
              {Object.entries(catalog?.components ?? {}).map(([k, v]) => (
                <SelectItem key={k} value={`c:${k}`}>
                  {v.name}
                </SelectItem>
              ))}
            </SelectGroup>
            <SelectGroup>
              <SelectLabel>Product lines</SelectLabel>
              {Object.entries(catalog?.product_lines ?? {}).map(([k, v]) => (
                <SelectItem key={k} value={`l:${k}`}>
                  {v}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Button onClick={generate} disabled={loading || !catalog}>
          {loading ? <Loader2Icon className="animate-spin" /> : <BookOpenIcon />} Build my brief
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {loading && <Skeleton className="h-96" />}

      {!digest && !loading && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          Choose a component or product line and build the brief.
        </p>
      )}

      {digest && !loading && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <SparklesIcon className="size-4" /> What a new {name} engineer must know
              </CardTitle>
              <CardDescription>
                Written by {summary?.model ?? "the LLM"} from {digest.lessons.length} lessons learned and the top DFMEA
                items; every bullet is cited.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {summarising && (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2Icon className="size-4 animate-spin" /> Writing the brief…
                </p>
              )}
              {summary && summary.text && (
                <AnswerText
                  text={summary.text}
                  citeLabel={(n) => sourceByN.get(n)?.title ?? `Source ${n}`}
                  onCite={(n) => {
                    const s = sourceByN.get(n);
                    if (s) router.push(`/library/${encodeURIComponent(s.rev_key)}`);
                  }}
                />
              )}
              {summary && !summary.text && <p className="text-sm text-muted-foreground">Not enough material for a brief.</p>}
              {summary && summary.sources.length > 0 && (
                <ol className="mt-4 space-y-0.5 text-xs text-muted-foreground">
                  {summary.sources.map((s) => (
                    <li key={s.n}>
                      [{s.n}] {s.doc_id} — {s.title}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Recurring failure modes (DFMEA, highest priority first)</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Failure mode</TableHead>
                    <TableHead>Cause</TableHead>
                    <TableHead>S/O/D</TableHead>
                    <TableHead>AP</TableHead>
                    <TableHead>Source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {digest.failure_modes.map((f, i) => (
                    <TableRow key={i}>
                      <TableCell className="max-w-48 whitespace-normal">{f.failure_mode}</TableCell>
                      <TableCell className="max-w-56 whitespace-normal text-xs">{f.cause}</TableCell>
                      <TableCell className="tabular-nums">
                        {f.severity}/{f.occurrence}/{f.detection}
                      </TableCell>
                      <TableCell>
                        <Badge variant={f.action_priority === "H" ? "destructive" : "secondary"}>{f.action_priority}</Badge>
                        {f.revised_action_priority && <span className="ml-1 text-xs text-muted-foreground">→ {f.revised_action_priority}</span>}
                      </TableCell>
                      <TableCell className="text-xs">{f.doc_id}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Read these first</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm">
                {digest.must_read.map((r) => (
                  <li key={r.rev_key}>
                    {docLink(r)} <span className="text-xs text-muted-foreground">{r.doc_type_label}</span>
                    <div className="text-xs text-muted-foreground">{r.title}</div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Lessons learned ({digest.lessons.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {digest.lessons.map((l) => (
                <div key={l.rev_key} className="rounded-md border p-3 text-sm">
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {docLink(l)} <span>{l.year}</span>
                  </div>
                  <p className="font-medium">{l.title.replace("Lesson learned: ", "")}</p>
                  <p className="text-muted-foreground">{l.lesson}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Acronyms you will hear</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-1.5 text-sm">
                {digest.glossary.map((g) => (
                  <div key={g.term} className="grid grid-cols-[4.5rem_1fr] gap-2">
                    <dt className="font-mono font-semibold">{g.term}</dt>
                    <dd className="text-muted-foreground">{g.meaning}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>

          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle className="text-base">Past issues ({digest.issues.length} 8D reports)</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>8D</TableHead>
                    <TableHead>Issue</TableHead>
                    <TableHead>Year</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Supplier</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {digest.issues.map((i) => (
                    <TableRow key={i.rev_key}>
                      <TableCell>{docLink(i)}</TableCell>
                      <TableCell className="whitespace-normal">{i.title}</TableCell>
                      <TableCell>{i.year}</TableCell>
                      <TableCell>{i.project}</TableCell>
                      <TableCell className="text-xs">{i.suppliers.join(", ") || "internal"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
