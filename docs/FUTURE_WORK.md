# Future work — taking Yokoten from prototype to a plant-wide service

The prototype runs on one laptop against a synthetic corpus. This is how it would scale inside a real
Tier-1 supplier, roughly in the order I would do it.

## 1. Connectors instead of a manifest
- **Document / PLM systems:** incremental connectors for the DMS (SharePoint, OpenText, Documentum) and PLM
  (Teamcenter, Windchill, 3DEXPERIENCE). Each connector yields the same `Document` metadata the manifest provides
  today (doc type, part numbers, project, plant, revision, classification), so the ingestion pipeline is unchanged.
- **Quality systems:** 8D / CAPA / FMEA tools (e.g. APIS IQ-FMEA, Plato, QAD, SAP QM) exported as structured rows —
  these go straight into the SQL tables used by the text-to-SQL route, not just into the vector index.
- **Change detection:** the pipeline already skips unchanged files by SHA-256 and re-embeds only changed chunks;
  connectors would feed it change events (webhooks / delta queries) instead of a nightly full scan.

## 2. Identity and per-document access control
- **SSO:** OIDC / SAML (Azure AD / Entra ID) instead of the demo role switcher; the user's groups map to the
  classification levels already enforced in retrieval, search, the library, onboarding digests and the SQL views.
- **Document-level ACLs:** replace the four classification levels with the source system's ACLs, stored per chunk
  and applied as a pre-filter (Chroma `where`, FAISS ID selector) — the mechanism is already in place.
- **Audit log:** persist who asked what and which documents were shown (the trace table is most of this already).

## 3. Serving on-prem
- **LLM:** a 7–8B instruction model (Llama 3.x 8B, Qwen 3 8B) on one plant GPU server via vLLM or Ollama is enough
  for cited, extractive answers; a 70B model on a shared cluster for harder synthesis. No document leaves the plant.
- **Retrieval:** at 10–100× this corpus (millions of chunks) move from FAISS Flat to HNSW / IVF-PQ or to a
  managed vector DB with native metadata filtering (Chroma/Qdrant/pgvector); keep BM25 (OpenSearch) for part
  numbers. The eval harness already compares Flat vs HNSW vs Chroma, so the switch is measurable.
- **Storage:** SQLite -> Postgres (SQLModel models are portable); object storage for originals and page renders.
- **Throughput:** batch embeddings on GPU at ingestion; cache reranker scores for popular queries; stream answers.

## 4. Feedback-driven improvement
- The SME verification loop already stores verified / corrected answers and reuses them for similar questions.
  Next: route every thumbs-down with a comment to the responsible SME queue, and add corrected answers to the
  golden set so the evaluation grows with real questions.
- Fine-tune the embedding model / reranker on (question, clicked source) pairs once enough usage exists.
- Weekly regression eval in CI against the golden set; block releases that drop Recall@5 or faithfulness.

## 5. Better understanding of engineering content
- **Tables and drawings:** layout-aware parsing (e.g. table structure models) for complex test-report tables;
  GD&T and dimension extraction from drawings; Tesseract/PaddleOCR ensemble with confidence voting.
- **Multilingual:** Japanese and German originals via a multilingual embedding model (e.g. BGE-M3) and answers in
  the user's language.
- **Visual similarity:** CLIP embeddings of defect photos to find similar past failures (the "J" option).
- **Knowledge graph:** link part -> supplier -> 8D -> ECN -> DFMEA row explicitly, so multi-hop questions are
  answered by graph traversal instead of hoping both hops land in the top-k passages.

## 6. Yokoten as a process, not just a chatbot
- Push, not pull: when a new 8D is closed, suggest the lessons learned to every project using the same part family,
  supplier or process (the "horizontal deployment" section of each lessons-learned report is already structured).
- Design-review assistant: before a gate review, list past issues and open DFMEA high-priority items for the
  component under review.
