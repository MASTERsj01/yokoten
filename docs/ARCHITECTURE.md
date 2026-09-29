# Yokoten — Architecture

Yokoten is a retrieval-augmented copilot over a (synthetic) Tier-1 automotive supplier's engineering record:
lessons-learned reports, 8Ds, DFMEA/PFMEA sheets, DVP&R / test reports, design-review minutes, ECNs,
supplier-quality reports, work instructions, field-failure analyses and scanned drawings.

## System overview

```mermaid
flowchart LR
  subgraph Ingestion
    F[PDF / DOCX / XLSX / CSV / MD / PNG / JPG] --> L[LangChain BaseLoader subclasses<br/>PyMuPDF · pdfplumber · python-docx · openpyxl]
    F -->|scans, drawings| CV[OpenCV preprocess<br/>gray · denoise · deskew · adaptive threshold] --> OCR[Tesseract / EasyOCR]
    OCR --> TB[Title-block parser<br/>part no · rev · material]
    L --> FIG[PDF figure extraction + captions]
    L & OCR & FIG --> CH[Chunkers<br/>fixed · recursive · structure · parent-child]
    CH --> ENT[Entity extraction<br/>regex + HF NER]
    ENT --> EMB[Sentence Transformers]
    EMB --> FA[(FAISS Flat / HNSW)]
    EMB --> CR[(ChromaDB)]
    CH --> BM[(BM25)]
    CH --> DB[(SQLite: documents · chunks · figures · structured tables)]
  end

  subgraph Query["RAG pipeline (every step recorded in the trace)"]
    Q[Question + history] --> C1[Condense follow-up]
    C1 --> C2[Glossary acronym expansion]
    C2 --> C3[Filter extraction<br/>year · product line · component · doc type · plant]
    C3 --> C4{Intent router<br/>HF zero-shot NLI}
    C4 -->|analytical| SQL[Text-to-SQL over structured tables]
    C4 -->|knowledge| R1[Hybrid retrieval<br/>dense + BM25 → RRF, role-aware filters]
    R1 --> R2[Cross-encoder rerank]
    R2 --> G{Relevance gate}
    G -->|below threshold| AB[Abstain + closest documents]
    G --> SB[Small-to-big parents · dedup · revision awareness]
    SB --> P[Versioned prompt → LLM stream<br/>Groq · Gemini · Ollama]
    P --> V[NLI check per sentence → confidence]
    V --> T[(Trace)]
  end

  UI[Next.js UI] <-->|REST + SSE| API[FastAPI]
  API --> Query
  API --> Ingestion
  EV[Eval harness + ablations] --> Query
  EV --> REP[docs/EVALUATION_REPORT.md + /eval dashboard]
```

## Folder structure

```
backend/                 FastAPI + pipeline (uv project, package `yokoten`)
  yokoten/
    config.py            .env settings, RuntimeConfig (switchable in UI / eval), device detection
    db.py                SQLModel tables (documents, chunks, traces, feedback, eval runs, structured tables)
    api.py               REST + SSE endpoints
    cli.py               `yokoten gen-data | ingest | ask | eval`
    datagen/             seeded synthetic corpus + golden set generator
    ingest/              loaders, OCR/image processing, chunking, entities, ingestion pipeline
    retrieval/           embeddings, FAISS/Chroma stores, BM25, RRF, reranker
    rag/                 LLM providers + cache, query understanding, NLI, pipeline, text-to-SQL
    evaluation/          metrics, harness, ablations, report generator
  prompts/               versioned prompt files + CHANGELOG.md
  tests/
frontend/                Next.js 16 + TypeScript + Tailwind v4 + shadcn/ui
data/                    glossary + generated corpus (data/corpus, gitignored, reproducible)
eval/                    golden.jsonl (dev/test split) + results/
docs/                    architecture, decisions, evaluation report, demo & interview assets
tasks.ps1                task runner (setup, data, ingest, dev, test, lint, eval)
```

## Tech choices (one line each)

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI + native `EventSourceResponse` | typed REST + SSE streaming with OpenAPI docs for free |
| Orchestration | LangChain (loaders, splitters, retriever, prompts, LCEL chains, chat models) | provider abstraction and standard interfaces; no LangGraph: the pipeline is linear |
| Embeddings | Sentence Transformers `BAAI/bge-small-en-v1.5` (+ MiniLM-L6, bge-base in ablation) | strong quality for 33M params, CPU-friendly |
| Vector DB | FAISS (Flat / HNSW) and ChromaDB behind one interface | compare exact vs ANN vs a persisted DB with native metadata filters |
| Lexical | rank-bm25 + Reciprocal Rank Fusion | part numbers and codes need exact-match recall |
| Reranker | `cross-encoder/ms-marco-MiniLM-L6-v2` | big precision gain for ~20 ms per pair on CPU |
| NLI / intent | HF Transformers `cross-encoder/nli-deberta-v3-xsmall` | one small model does both sentence faithfulness and zero-shot intent |
| NER | HF `dslim/distilbert-NER` + regex | supplier/org names from free text; regex for part numbers and project codes |
| LLM | Groq (default), Gemini (fallback + judge), Ollama (local) | free tiers + an on-prem story; the judge is from a different family than the generator |
| Parsing | PyMuPDF, pdfplumber, python-docx, openpyxl/pandas | page-level bounding boxes for citation highlights |
| Image processing | OpenCV + Tesseract (EasyOCR fallback) | classic, explainable preprocessing |
| Storage | SQLite via SQLModel | zero-ops, Postgres-ready |
| Frontend | Next.js + shadcn/ui + Recharts | fast to build a polished, accessible UI |
| Source viewer | backend renders the PDF page to PNG with highlight boxes (PyMuPDF) | no pdf.js worker plumbing; works for every format |

## Phase plan

| Phase | Output |
|---|---|
| P0 Setup | scaffold, tooling, CI, Docker skeleton, health endpoint + UI shell |
| P1 Data | seeded corpus generator (~200 docs, 5 formats), manifest, golden set (~120 Q, dev/test) |
| P2 Ingestion | loaders, OCR pipeline, 4 chunkers, entities, embeddings, FAISS/Chroma/BM25, incremental re-index |
| P3 RAG core | full pipeline, providers + cache, citations, abstention, NLI, traces, SSE API, CLI |
| P4 Website | landing, chat, search, library, onboarding, eval, settings |
| P5 Evaluation | harness, ablations, dashboard, auto-generated report |
| P5b Public data | NHTSA recalls subset as a separate collection + small eval |
| P6 Next-level | K text-to-SQL → N access control → M SME verification loop |
| P7 Ship | docs/assets, one-command Docker run, deployment (after approval) |
