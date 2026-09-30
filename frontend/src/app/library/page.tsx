"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { UploadIcon } from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { Catalog, DocSummary } from "@/lib/types";

type Report = {
  documents?: number;
  chunks?: Record<string, number>;
  figures?: number;
  fmea_rows?: number;
  ocr?: { documents: number; mean_confidence: number | null; engines: Record<string, number> };
  superseded_revisions?: number;
};

const ACCEPT = ".pdf,.docx,.xlsx,.csv,.md,.txt,.png,.jpg,.jpeg";

export default function LibraryPage() {
  const [docs, setDocs] = useState<DocSummary[] | null>(null);
  const [report, setReport] = useState<Report>({});
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("all");
  const [classification, setClassification] = useState("internal");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api<DocSummary[]>("/api/documents")
      .then(setDocs)
      .catch((e) => setError(e.message));
    api<Report>("/api/ingestion/report").then(setReport).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    api<Catalog>("/api/catalog").then(setCatalog).catch(() => {});
  }, [load]);

  const busy = docs?.some((d) => d.status === "pending" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [busy, load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    for (const f of Array.from(files)) {
      const fd = new FormData();
      fd.append("file", f);
      try {
        await api(`/api/documents?classification=${classification}`, { method: "POST", body: fd });
        toast.success(`${f.name} uploaded - ingesting`);
      } catch (e) {
        toast.error(`${f.name}: ${(e as Error).message}`);
      }
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
    load();
  }

  const shown = (docs ?? []).filter(
    (d) =>
      (type === "all" || d.doc_type === type) &&
      (!q || `${d.doc_id} ${d.title} ${d.project ?? ""}`.toLowerCase().includes(q.toLowerCase())),
  );
  const types = [...new Set((docs ?? []).map((d) => d.doc_type))].sort();
  const stats = [
    { label: "Documents", value: report.documents },
    { label: "Indexed chunks", value: report.chunks?.parent_child },
    { label: "Figures extracted", value: report.figures },
    { label: "FMEA rows (SQL)", value: report.fmea_rows },
    {
      label: "OCR mean confidence",
      value: report.ocr?.mean_confidence != null ? `${Math.round(report.ocr.mean_confidence * 100)}%` : undefined,
    },
    { label: "Superseded revisions", value: report.superseded_revisions },
  ];

  return (
    <div className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Document library</h1>
        <p className="text-sm text-muted-foreground">
          Everything the copilot can cite. Upload PDF, DOCX, XLSX, CSV, Markdown or scanned images - they are parsed,
          OCR&apos;d, chunked and indexed automatically.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {stats.map((s) => (
          <Card key={s.label} className="gap-1 py-3">
            <CardContent className="px-3">
              <div className="text-xl font-semibold tabular-nums">{s.value ?? "—"}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add documents</CardTitle>
          <CardDescription>Max 20 MB per file. Classification controls which roles can retrieve it.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={ACCEPT}
            onChange={(e) => upload(e.target.files)}
            className="text-sm file:mr-3 file:rounded-md file:border file:bg-background file:px-3 file:py-1.5 file:text-sm"
            aria-label="Choose files to upload"
            disabled={uploading}
          />
          <Select value={classification} onValueChange={setClassification}>
            <SelectTrigger className="w-44" aria-label="Classification">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["public", "internal", "confidential", "restricted"].map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {uploading && (
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <UploadIcon className="size-4 animate-bounce" /> Uploading…
            </span>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input placeholder="Filter by ID, title or project" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter documents" />
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="w-full sm:w-60" aria-label="Document type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All document types</SelectItem>
            {types.map((t) => (
              <SelectItem key={t} value={t}>
                {catalog?.doc_types[t] ?? t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error && <p className="text-sm text-destructive">Could not load documents: {error}</p>}
      {!docs && !error && <Skeleton className="h-96" />}
      {docs && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Rev</TableHead>
                <TableHead>Year</TableHead>
                <TableHead>Component</TableHead>
                <TableHead>Access</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Chunks</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    No documents match.
                  </TableCell>
                </TableRow>
              )}
              {shown.map((d) => (
                <TableRow key={d.rev_key}>
                  <TableCell className="max-w-96">
                    <Link href={`/library/${encodeURIComponent(d.rev_key)}`} className="font-medium text-primary hover:underline">
                      {d.doc_id}
                    </Link>
                    <div className="truncate text-xs text-muted-foreground" title={d.title}>
                      {d.title}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">
                    {d.doc_type_label}
                    <span className="ml-1 text-muted-foreground uppercase">{d.format}</span>
                  </TableCell>
                  <TableCell>
                    {d.revision}
                    {!d.is_latest && (
                      <Badge variant="destructive" className="ml-1">
                        old
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{d.year ?? "—"}</TableCell>
                  <TableCell className="text-xs">{d.component ? catalog?.components[d.component]?.name ?? d.component : "—"}</TableCell>
                  <TableCell className="text-xs">{d.classification}</TableCell>
                  <TableCell>
                    <StatusBadge status={d.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{d.n_chunks}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
