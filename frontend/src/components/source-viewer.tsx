"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon, ExternalLinkIcon, ImageIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { API_URL, api } from "@/lib/api";
import { highlightPassage } from "@/lib/highlight";
import type { DocDetail } from "@/lib/types";

export type ViewerTarget = {
  rev_key: string;
  doc_id: string;
  title: string;
  revision: string;
  is_latest: boolean;
  superseded_by?: string | null;
  page: number | null;
  chunk_id: string;
  section: string;
  snippet: string;
  text?: string;
  n?: number;
};

const STEPS = ["original", "denoised", "deskewed", "binary"] as const;

/** Side panel that opens a cited source at the exact page / region with the passage highlighted. */
export function SourceViewer({ target, onClose }: { target: ViewerTarget | null; onClose: () => void }) {
  return (
    <Sheet open={!!target} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto p-0 data-[side=right]:sm:max-w-2xl">
        {target && <ViewerBody key={`${target.rev_key}|${target.chunk_id}`} target={target} />}
      </SheetContent>
    </Sheet>
  );
}

function ViewerBody({ target }: { target: ViewerTarget }) {
  const [detail, setDetail] = useState<DocDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(target.page ?? 1);
  const [step, setStep] = useState<(typeof STEPS)[number]>("deskewed");
  const [loadedSrc, setLoadedSrc] = useState("");

  useEffect(() => {
    let alive = true;
    api<DocDetail>(`/api/documents/${encodeURIComponent(target.rev_key)}`)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(String(e.message ?? e)));
    return () => {
      alive = false;
    };
  }, [target.rev_key]);

  const doc = detail?.document;
  const fmt = doc?.format;
  const base = `${API_URL}/api/documents/${encodeURIComponent(target.rev_key)}`;
  const imgSrc =
    fmt === "pdf"
      ? `${base}/page/${page}?chunk=${encodeURIComponent(page === target.page ? target.chunk_id : "")}`
      : fmt === "png" || fmt === "jpg"
        ? `${base}/image?step=${step}&chunk=${encodeURIComponent(target.chunk_id)}`
        : null;
  const figures = detail?.figures.filter((f) => f.page === page) ?? [];

  return (
    <>
            <SheetHeader className="border-b p-4 pr-12">
              <div className="flex flex-wrap items-center gap-2">
                {target.n != null && <Badge>Source {target.n}</Badge>}
                <Badge variant="outline">{target.doc_id}</Badge>
                <Badge variant="outline">Rev {target.revision}</Badge>
                {target.is_latest ? (
                  <Badge className="bg-emerald-600/15 text-emerald-700 dark:text-emerald-400">Latest</Badge>
                ) : (
                  <Badge variant="destructive">Superseded{target.superseded_by ? ` by ${target.superseded_by}` : ""}</Badge>
                )}
                {doc && <Badge variant="secondary">{doc.classification}</Badge>}
              </div>
              <SheetTitle className="text-base leading-snug">{target.title}</SheetTitle>
              <SheetDescription>
                {doc?.doc_type_label ?? "Document"}
                {target.section ? ` · ${target.section}` : ""}
                {target.page ? ` · page ${target.page}` : ""}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 p-4">
              {error && <p className="text-sm text-destructive">Could not load the document: {error}</p>}
              {!detail && !error && <Skeleton className="h-96 w-full" />}
              {imgSrc && (
                <div className="space-y-2">
                  {fmt === "pdf" && doc?.n_pages && doc.n_pages > 1 && (
                    <div className="flex items-center justify-between text-sm">
                      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                        <ChevronLeftIcon /> Previous
                      </Button>
                      <span className="text-muted-foreground">
                        Page {page} of {doc.n_pages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page >= doc.n_pages}
                        onClick={() => setPage(page + 1)}
                      >
                        Next <ChevronRightIcon />
                      </Button>
                    </div>
                  )}
                  {(fmt === "png" || fmt === "jpg") && (
                    <div className="flex flex-wrap gap-1" role="tablist" aria-label="Image processing step">
                      {STEPS.map((s) => (
                        <Button
                          key={s}
                          size="xs"
                          variant={s === step ? "default" : "outline"}
                          onClick={() => setStep(s)}
                          role="tab"
                          aria-selected={s === step}
                        >
                          {s}
                        </Button>
                      ))}
                    </div>
                  )}
                  <div className="relative overflow-hidden rounded-md border bg-white">
                    {loadedSrc !== imgSrc && <Skeleton className="absolute inset-0" />}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={imgSrc}
                      alt={`${target.doc_id} page ${page}`}
                      className="w-full"
                      onLoad={() => setLoadedSrc(imgSrc)}
                    />
                  </div>
                </div>
              )}
              {figures.length > 0 && (
                <div className="space-y-2">
                  <h3 className="flex items-center gap-1.5 text-sm font-medium">
                    <ImageIcon className="size-4" /> Figures on this page
                  </h3>
                  {figures.map((f) => (
                    <figure key={f.id} className="rounded-md border p-2">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={`${API_URL}/api/figures/${encodeURIComponent(f.id)}`} alt={f.caption} className="w-full" />
                      <figcaption className="mt-1 text-xs text-muted-foreground">{f.caption}</figcaption>
                    </figure>
                  ))}
                </div>
              )}
              <div className="space-y-1.5">
                <h3 className="text-sm font-medium">Cited passage</h3>
                <div className="max-h-72 overflow-y-auto rounded-md border bg-muted/40 p-3 text-sm whitespace-pre-wrap">
                  {highlightPassage(target.text ?? target.snippet, target.snippet)}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link href={`/library/${encodeURIComponent(target.rev_key)}`}>
                    <ExternalLinkIcon /> Open in library
                  </Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <a href={`${base}/file`}>
                    <DownloadIcon /> Original file
                  </a>
                </Button>
              </div>
            </div>
    </>
  );
}
