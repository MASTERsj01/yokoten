"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeftIcon, ChevronLeftIcon, ChevronRightIcon, DownloadIcon, RefreshCwIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { API_URL, api } from "@/lib/api";
import type { DocDetail } from "@/lib/types";

const STEPS = ["original", "denoised", "deskewed", "binary"];

function BeforeAfter({ base }: { base: string }) {
  const [before, setBefore] = useState("original");
  const [after, setAfter] = useState("binary");
  const [pos, setPos] = useState(50);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Before</span>
        <Select value={before} onValueChange={setBefore}>
          <SelectTrigger className="w-32" aria-label="Before step">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STEPS.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground">After</span>
        <Select value={after} onValueChange={setAfter}>
          <SelectTrigger className="w-32" aria-label="After step">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STEPS.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="relative overflow-hidden rounded-md border bg-white select-none">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`${base}/image?step=${before}`} alt={`${before} scan`} className="block w-full" />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${base}/image?step=${after}`}
          alt={`${after} scan`}
          className="absolute inset-0 block h-full w-full"
          style={{ clipPath: `inset(0 0 0 ${pos}%)` }}
        />
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-primary" style={{ left: `${pos}%` }} />
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        className="w-full accent-primary"
        aria-label="Before / after position"
      />
    </div>
  );
}

function Field({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="text-sm break-words">{v ?? "—"}</dd>
    </div>
  );
}

export default function DocumentPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const revKey = decodeURIComponent(params.id);
  const [strategy, setStrategy] = useState("parent_child");
  const [data, setData] = useState<DocDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const load = useCallback(
    () =>
      api<DocDetail>(`/api/documents/${encodeURIComponent(revKey)}?strategy=${strategy}`)
        .then(setData)
        .catch((e) => setError(e.message)),
    [revKey, strategy],
  );
  useEffect(() => {
    load();
  }, [load]);
  const pending = data && ["pending", "processing"].includes(data.document.status);
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [pending, load]);

  const base = `${API_URL}/api/documents/${encodeURIComponent(revKey)}`;
  if (error) return <p className="mx-auto max-w-7xl p-6 text-destructive">Could not load document: {error}</p>;
  if (!data) return <Skeleton className="mx-auto m-6 h-[70vh] w-full max-w-7xl" />;
  const d = data.document;
  const extra = d.extra as {
    entities?: Record<string, string[]>;
    organisations?: string[];
    timings?: Record<string, number>;
    ocr?: { engine: string; confidence: number; angle: number; fields: Record<string, string> };
    chunks?: Record<string, number>;
  };
  const isScan = d.format === "png" || d.format === "jpg";

  async function reindex() {
    try {
      await api(`/api/documents/${encodeURIComponent(revKey)}/reindex`, { method: "POST" });
      toast.success("Re-indexing started");
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function remove() {
    try {
      await api(`/api/documents/${encodeURIComponent(revKey)}`, { method: "DELETE" });
      toast.success(`${d.doc_id} deleted`);
      router.push("/library");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl flex-1 space-y-5 px-4 py-6">
      <Link href="/library" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-4" /> Library
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{d.doc_id}</Badge>
            <Badge variant="secondary">{d.doc_type_label}</Badge>
            <Badge variant="outline">Rev {d.revision}</Badge>
            {!d.is_latest && <Badge variant="destructive">Superseded by {d.superseded_by}</Badge>}
            <StatusBadge status={d.status} />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">{d.title}</h1>
          {d.error && <p className="text-sm text-destructive">{d.error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={`${base}/file`}>
              <DownloadIcon /> Original
            </a>
          </Button>
          <Button variant="outline" size="sm" onClick={reindex}>
            <RefreshCwIcon /> Re-index
          </Button>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Trash2Icon /> Delete
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete {d.doc_id} Rev {d.revision}?</DialogTitle>
                <DialogDescription>Its chunks are removed from every index. This cannot be undone.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button variant="destructive" onClick={remove}>
                  Delete
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          {isScan && <TabsTrigger value="ocr">OCR</TabsTrigger>}
          <TabsTrigger value="chunks">Chunks</TabsTrigger>
          {data.figures.length > 0 && <TabsTrigger value="figures">Figures ({data.figures.length})</TabsTrigger>}
          {data.fmea_rows.length > 0 && <TabsTrigger value="fmea">FMEA rows ({data.fmea_rows.length})</TabsTrigger>}
        </TabsList>

        <TabsContent value="overview" className="space-y-6 pt-3">
          <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Field k="Format" v={d.format.toUpperCase()} />
            <Field k="Date" v={d.date} />
            <Field k="Year" v={d.year} />
            <Field k="Classification" v={d.classification} />
            <Field k="Product line" v={d.product_line} />
            <Field k="Component" v={d.component} />
            <Field k="Project" v={d.project} />
            <Field k="Plant" v={d.plant} />
            <Field k="Suppliers" v={d.suppliers.join(", ") || null} />
            <Field k="Part numbers" v={d.part_numbers.join(", ") || null} />
            <Field k="Author" v={d.author} />
            <Field k="Pages" v={d.n_pages} />
            <Field k="Supersedes" v={d.supersedes} />
            <Field k="Collection" v={d.collection} />
            <Field k="Chunks per strategy" v={extra.chunks && Object.entries(extra.chunks).map(([k, n]) => `${k}: ${n}`).join(", ")} />
            <Field
              k="Ingestion time"
              v={extra.timings && `${extra.timings.total_s}s (parse ${extra.timings.parse_s}s, NER ${extra.timings.ner_s}s)`}
            />
          </dl>
          <div className="space-y-2">
            <h2 className="text-sm font-medium">Extracted entities</h2>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(extra.entities ?? {}).flatMap(([k, vs]) =>
                vs.slice(0, 12).map((v) => (
                  <Badge key={`${k}${v}`} variant="outline" title={k}>
                    <span className="text-muted-foreground">{k.replace("_", " ")}:</span> {v}
                  </Badge>
                )),
              )}
              {(extra.organisations ?? []).map((o) => (
                <Badge key={o} variant="secondary" title="Organisation (Hugging Face NER)">
                  ORG: {o}
                </Badge>
              ))}
            </div>
          </div>
          {data.revisions.length > 1 && (
            <div className="space-y-2">
              <h2 className="text-sm font-medium">Revisions</h2>
              <div className="flex gap-2">
                {data.revisions.map((r) => (
                  <Button key={r.rev_key} asChild variant={r.rev_key === d.rev_key ? "default" : "outline"} size="sm">
                    <Link href={`/library/${encodeURIComponent(r.rev_key)}`}>
                      Rev {r.revision}
                      {r.is_latest && " (latest)"}
                    </Link>
                  </Button>
                ))}
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="preview" className="pt-3">
          {d.format === "pdf" ? (
            <div className="mx-auto max-w-3xl space-y-2">
              <div className="flex items-center justify-between text-sm">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  <ChevronLeftIcon /> Previous
                </Button>
                <span className="text-muted-foreground">
                  Page {page} of {d.n_pages}
                </span>
                <Button variant="outline" size="sm" disabled={page >= (d.n_pages ?? 1)} onClick={() => setPage(page + 1)}>
                  Next <ChevronRightIcon />
                </Button>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`${base}/page/${page}`} alt={`Page ${page}`} className="w-full rounded-md border bg-white" />
            </div>
          ) : isScan ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`${base}/image?step=original`} alt="Scan" className="mx-auto max-w-3xl rounded-md border" />
          ) : (
            <div className="space-y-3">
              {data.chunks
                .filter((c) => c.kind === "parent" || strategy !== "parent_child")
                .map((c) => (
                  <section key={c.id} className="rounded-md border p-3">
                    {c.section && <h3 className="mb-1 text-sm font-medium">{c.section}</h3>}
                    <p className="text-sm whitespace-pre-wrap">{c.text}</p>
                  </section>
                ))}
            </div>
          )}
        </TabsContent>

        {isScan && (
          <TabsContent value="ocr" className="grid gap-6 pt-3 lg:grid-cols-[3fr_2fr]">
            <BeforeAfter base={base} />
            <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-3">
                <Field k="OCR engine" v={extra.ocr?.engine} />
                <Field k="Mean confidence" v={extra.ocr && `${Math.round(extra.ocr.confidence * 100)}%`} />
                <Field k="Deskew angle" v={extra.ocr && `${extra.ocr.angle.toFixed(2)}°`} />
              </dl>
              <div className="space-y-1.5">
                <h3 className="text-sm font-medium">Title block / form fields</h3>
                <dl className="grid grid-cols-2 gap-2 rounded-md border p-3">
                  {Object.entries(extra.ocr?.fields ?? {}).map(([k, v]) => (
                    <Field key={k} k={k.replace("_", " ")} v={v} />
                  ))}
                </dl>
              </div>
              <div className="space-y-1.5">
                <h3 className="text-sm font-medium">Recognised text</h3>
                <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">
                  {data.chunks.filter((c) => c.kind !== "parent").map((c) => c.text).join("\n")}
                </pre>
              </div>
            </div>
          </TabsContent>
        )}

        <TabsContent value="chunks" className="space-y-3 pt-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Chunking strategy</span>
            <Select value={strategy} onValueChange={setStrategy}>
              <SelectTrigger className="w-44" aria-label="Chunking strategy">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["fixed", "recursive", "structure", "parent_child"].map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground">{data.chunks.length} chunks</span>
          </div>
          {data.chunks.map((c) => (
            <div key={c.id} className={`rounded-md border p-3 ${c.kind === "parent" ? "bg-muted/40" : ""}`}>
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Badge variant="outline">#{c.idx}</Badge>
                <Badge variant="secondary">{c.kind}</Badge>
                {c.section && <span>{c.section}</span>}
                {c.page && <span>· page {c.page}</span>}
                {c.parent_id && <span>· child of #{c.parent_id.split(":").pop()}</span>}
              </div>
              <p className="text-sm whitespace-pre-wrap">{c.text}</p>
            </div>
          ))}
        </TabsContent>

        {data.figures.length > 0 && (
          <TabsContent value="figures" className="grid gap-4 pt-3 md:grid-cols-2">
            {data.figures.map((f) => (
              <figure key={f.id} className="rounded-md border p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`${API_URL}/api/figures/${encodeURIComponent(f.id)}`} alt={f.caption} className="w-full" />
                <figcaption className="mt-1 text-xs text-muted-foreground">
                  Page {f.page} · {f.caption}
                </figcaption>
              </figure>
            ))}
          </TabsContent>
        )}

        {data.fmea_rows.length > 0 && (
          <TabsContent value="fmea" className="pt-3">
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {["ID", "Failure mode", "Effect", "Cause", "S", "O", "D", "AP", "Status", "Rev. AP"].map((h) => (
                      <TableHead key={h}>{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.fmea_rows.map((r) => (
                    <TableRow key={String(r.item_id)}>
                      <TableCell>{String(r.item_id)}</TableCell>
                      <TableCell className="max-w-56 whitespace-normal">{String(r.failure_mode)}</TableCell>
                      <TableCell className="max-w-48 whitespace-normal">{String(r.effect)}</TableCell>
                      <TableCell className="max-w-56 whitespace-normal">{String(r.cause)}</TableCell>
                      <TableCell>{String(r.severity)}</TableCell>
                      <TableCell>{String(r.occurrence)}</TableCell>
                      <TableCell>{String(r.detection)}</TableCell>
                      <TableCell>
                        <Badge variant={r.action_priority === "H" ? "destructive" : "secondary"}>{String(r.action_priority)}</Badge>
                      </TableCell>
                      <TableCell>{String(r.status)}</TableCell>
                      <TableCell>{r.revised_action_priority ? String(r.revised_action_priority) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
