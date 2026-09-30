"use client";

import { useEffect, useState } from "react";
import { CheckCircle2Icon, CircleDashedIcon, Loader2Icon, SaveIcon } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

type Config = {
  llm_provider: string;
  llm_model: string;
  embedding_model: string;
  chunking: string;
  vector_store: string;
  faiss_index: string;
  retrieval_mode: string;
  reranker: boolean;
  top_k: number;
  candidates: number;
  query_rewrite: boolean;
  use_filters: boolean;
  prompt_version: string;
  abstain_threshold: number;
  abstain_threshold_dense: number;
  collections: string[];
};
type Options = {
  providers: Record<string, { available: boolean; default: string; models: string[] }>;
  embedding_models: string[];
  chunking: string[];
  vector_stores: string[];
  faiss_index: string[];
  retrieval_modes: string[];
  prompt_versions: string[];
};

const PROVIDER_HELP: Record<string, string> = {
  groq: "Set GROQ_API_KEY in .env (free key at console.groq.com).",
  gemini: "Set GOOGLE_API_KEY in .env (free key at aistudio.google.com).",
  ollama: "Install Ollama and run `ollama pull qwen3:8b` - data never leaves the machine.",
  local: "Hugging Face model in-process on CPU. Always available, slower.",
};

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[14rem_1fr] sm:items-center">
      <div>
        <Label>{label}</Label>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Pick({ value, options, onChange, label }: { value: string; options: string[]; onChange: (v: string) => void; label: string }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full sm:w-80" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export default function SettingsPage() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [opts, setOpts] = useState<Options | null>(null);
  const [device, setDevice] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ config: Config; options: Options }>("/api/config")
      .then((r) => {
        setCfg(r.config);
        setOpts(r.options);
      })
      .catch((e) => setError(e.message));
    api<{ device: string }>("/api/health").then((h) => setDevice(h.device)).catch(() => {});
  }, []);

  const set = <K extends keyof Config>(k: K, v: Config[K]) => setCfg((c) => (c ? { ...c, [k]: v } : c));

  async function save() {
    if (!cfg) return;
    setSaving(true);
    try {
      await api("/api/config", { method: "PUT", body: JSON.stringify(cfg) });
      toast.success("Settings saved - the next question uses them");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (error) return <p className="mx-auto max-w-4xl p-6 text-destructive">Could not load settings: {error}</p>;
  if (!cfg || !opts) return <Skeleton className="mx-auto m-6 h-[70vh] w-full max-w-4xl" />;
  const prov = opts.providers[cfg.llm_provider];
  const models = [...new Set([prov?.default, ...(prov?.models ?? [])].filter(Boolean))] as string[];

  return (
    <div className="mx-auto w-full max-w-4xl flex-1 space-y-6 px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground">
            Switch models, stores and retrieval strategies to demo the trade-offs measured on the Evaluation page.
            {device && <> Running on <Badge variant="outline">{device}</Badge>.</>}
          </p>
        </div>
        <Button onClick={save} disabled={saving}>
          {saving ? <Loader2Icon className="animate-spin" /> : <SaveIcon />} Save
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Language model</CardTitle>
          <CardDescription>Unavailable providers fall back to the next available one (Groq → Gemini → Ollama → local).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(opts.providers).map(([name, p]) => (
              <button
                key={name}
                type="button"
                onClick={() => {
                  set("llm_provider", name);
                  set("llm_model", "");
                }}
                className={`rounded-md border p-3 text-left text-sm transition-colors hover:bg-accent ${
                  cfg.llm_provider === name ? "border-primary ring-1 ring-primary" : ""
                }`}
              >
                <div className="flex items-center gap-2 font-medium capitalize">
                  {p.available ? (
                    <CheckCircle2Icon className="size-4 text-emerald-600" />
                  ) : (
                    <CircleDashedIcon className="size-4 text-muted-foreground" />
                  )}
                  {name}
                  <span className="text-xs font-normal text-muted-foreground">{p.available ? "available" : "not configured"}</span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{PROVIDER_HELP[name]}</p>
              </button>
            ))}
          </div>
          <Row label="Model" hint="Empty = provider default">
            {models.length > 1 ? (
              <Pick value={cfg.llm_model || prov.default} options={models} onChange={(v) => set("llm_model", v)} label="Model" />
            ) : (
              <Input value={cfg.llm_model} placeholder={prov?.default} onChange={(e) => set("llm_model", e.target.value)} className="sm:w-80" aria-label="Model" />
            )}
          </Row>
          <Row label="Prompt version" hint="See backend/prompts/CHANGELOG.md">
            <Pick value={cfg.prompt_version} options={opts.prompt_versions} onChange={(v) => set("prompt_version", v)} label="Prompt version" />
          </Row>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Retrieval</CardTitle>
          <CardDescription>Embedding model and chunking changes build a new index on first use (cached afterwards).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Row label="Retrieval mode">
            <Pick value={cfg.retrieval_mode} options={opts.retrieval_modes} onChange={(v) => set("retrieval_mode", v)} label="Retrieval mode" />
          </Row>
          <Row label="Vector store">
            <Pick value={cfg.vector_store} options={opts.vector_stores} onChange={(v) => set("vector_store", v)} label="Vector store" />
          </Row>
          {cfg.vector_store === "faiss" && (
            <Row label="FAISS index" hint="Flat = exact; HNSW = approximate graph">
              <Pick value={cfg.faiss_index} options={opts.faiss_index} onChange={(v) => set("faiss_index", v)} label="FAISS index" />
            </Row>
          )}
          <Row label="Embedding model">
            <Pick value={cfg.embedding_model} options={opts.embedding_models} onChange={(v) => set("embedding_model", v)} label="Embedding model" />
          </Row>
          <Row label="Chunking">
            <Pick value={cfg.chunking} options={opts.chunking} onChange={(v) => set("chunking", v)} label="Chunking" />
          </Row>
          <Row label="Cross-encoder reranker">
            <Switch checked={cfg.reranker} onCheckedChange={(v) => set("reranker", v)} aria-label="Reranker" />
          </Row>
          <Row label="Query rewriting" hint="Condense follow-ups + glossary expansion">
            <Switch checked={cfg.query_rewrite} onCheckedChange={(v) => set("query_rewrite", v)} aria-label="Query rewriting" />
          </Row>
          <Row label="Metadata filters" hint="Extract year / component / plant from the question">
            <Switch checked={cfg.use_filters} onCheckedChange={(v) => set("use_filters", v)} aria-label="Metadata filters" />
          </Row>
          <Row label={`Passages to the LLM (top-k): ${cfg.top_k}`}>
            <Slider value={[cfg.top_k]} min={1} max={12} step={1} onValueChange={([v]) => set("top_k", v)} className="sm:w-80" aria-label="Top k" />
          </Row>
          <Row label={`Candidates retrieved: ${cfg.candidates}`}>
            <Slider value={[cfg.candidates]} min={5} max={60} step={5} onValueChange={([v]) => set("candidates", v)} className="sm:w-80" aria-label="Candidates" />
          </Row>
          <Row label={`Abstain below relevance: ${cfg.abstain_threshold.toFixed(2)}`} hint="Calibrated on the dev split">
            <Slider
              value={[cfg.abstain_threshold]}
              min={0}
              max={0.9}
              step={0.01}
              onValueChange={([v]) => set("abstain_threshold", v)}
              className="sm:w-80"
              aria-label="Abstention threshold"
            />
          </Row>
        </CardContent>
      </Card>
    </div>
  );
}
