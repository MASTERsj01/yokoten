export type Source = {
  n: number;
  chunk_id: string;
  doc_id: string;
  rev_key: string;
  title: string;
  doc_type: string;
  revision: string;
  is_latest: boolean;
  superseded_by: string | null;
  format: string;
  page: number | null;
  section: string;
  bboxes: number[][];
  snippet: string;
  text: string;
  scores: Record<string, number | string | null>;
};

export type SentenceCheck = {
  text: string;
  cited: number[];
  entailment: number;
  contradiction: number;
  supported: boolean;
};

export type Verification = {
  sentences: SentenceCheck[];
  faithfulness: number | null;
  citation_precision: number | null;
  confidence: number;
  confidence_label: string;
};

export type Related = { doc_id: string; rev_key: string; title: string; doc_type: string; score: number };

export type SqlResult = { query: string; columns: string[]; rows: (string | number | null)[][]; n_rows: number };
export type VerifiedMatch = { id: number; question: string; status: string; similarity: number };

export type Done = {
  trace_id: string;
  answer: string;
  abstained: boolean;
  citations: Source[];
  suggestions: string[];
  related: Related[];
  confidence: number;
  confidence_label: string;
  latency_ms: number;
  sql?: SqlResult | null;
  verified?: VerifiedMatch | null;
};

export type Meta = {
  trace_id: string;
  standalone: string;
  expanded: string;
  filters: Record<string, unknown>;
  filters_relaxed: boolean;
  intent: string;
  provider: string;
  model: string;
  gate: number;
};

export type Step = { name: string; ms: number } & Record<string, unknown>;

export type RetrievedRow = {
  chunk_id: string;
  doc_id: string;
  title: string;
  revision: string;
  section: string;
  page: number | null;
  kind: string;
  dense: number | null;
  dense_rank: number | null;
  bm25: number | null;
  bm25_rank: number | null;
  fused: number;
  rerank: number | null;
  snippet: string;
};

export type Trace = {
  id: string;
  question: string;
  standalone: string;
  answer: string;
  abstained: boolean;
  confidence: number | null;
  confidence_label: string;
  intent: string;
  role: string;
  provider: string;
  model: string;
  prompt_version: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  created_at: string;
  data: {
    steps: Step[];
    expanded: string;
    expansions: string[];
    filters: Record<string, unknown>;
    filters_relaxed: boolean;
    intent_detail: Record<string, unknown>;
    retrieved: RetrievedRow[];
    sources: Source[];
    verification: Verification;
    config: Record<string, unknown>;
    llm_cached: boolean;
    gate: number;
    sql?: { query: string; rows: Record<string, unknown>[]; columns: string[] };
  };
};

export type DocSummary = {
  rev_key: string;
  doc_id: string;
  title: string;
  doc_type: string;
  doc_type_label: string;
  format: string;
  collection: string;
  source: string;
  year: number | null;
  date: string | null;
  product_line: string | null;
  component: string | null;
  project: string | null;
  plant: string | null;
  suppliers: string[];
  part_numbers: string[];
  revision: string;
  is_latest: boolean;
  superseded_by: string | null;
  supersedes: string | null;
  classification: string;
  status: string;
  error: string | null;
  n_pages: number | null;
  n_chunks: number;
  ocr_engine: string | null;
  ocr_confidence: number | null;
  ocr_fields?: Record<string, string> | null;
};

export type ChunkRow = {
  id: string;
  idx: number;
  kind: string;
  section: string;
  text: string;
  page: number | null;
  parent_id: string | null;
  entities: Record<string, string[]>;
};

export type FigureRow = { id: string; page: number; caption: string };

export type DocDetail = {
  document: DocSummary & { extra: Record<string, unknown>; author: string | null };
  chunks: ChunkRow[];
  figures: FigureRow[];
  revisions: { rev_key: string; revision: string; is_latest: boolean }[];
  fmea_rows: Record<string, unknown>[];
  strategy: string;
};

export type SearchResult = {
  doc_id: string;
  rev_key: string;
  title: string;
  doc_type: string;
  doc_type_label: string;
  product_line: string | null;
  component: string | null;
  project: string | null;
  plant: string | null;
  year: number | null;
  revision: string;
  is_latest: boolean;
  chunk_id: string;
  section: string;
  page: number | null;
  text: string;
  scores: {
    dense: number | null;
    dense_rank: number | null;
    bm25: number | null;
    bm25_rank: number | null;
    fused: number;
    rerank: number | null;
    relevance: number | null;
  };
};

export type Facet = { value: string | number; count: number };

export type Catalog = {
  components: Record<string, { name: string; line: string }>;
  product_lines: Record<string, string>;
  plants: Record<string, string>;
  doc_types: Record<string, string>;
  roles: string[];
};
