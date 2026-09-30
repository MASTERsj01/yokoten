# Resume bullets

All numbers come from evaluation run `20260930-050009` (`eval/results/latest.json`, reproduce with `.\tasks.ps1 eval`),
measured on the held-out test split of a 129-question golden set. Generation numbers use a 1.5B-parameter local model
on CPU - re-run with a hosted model before quoting different ones.

**Yokoten — RAG copilot for engineering lessons learned** (Python, FastAPI, LangChain, FAISS, ChromaDB, Sentence
Transformers, Hugging Face Transformers, OpenCV, Next.js)

- Built an end-to-end retrieval-augmented chatbot over 231 multi-format engineering documents (8D reports, FMEAs, test
  reports, scanned drawings) with hybrid dense + BM25 retrieval, cross-encoder reranking and page-level citations,
  reaching **98.4% Recall@5 and 0.93 MRR** on the held-out test set.
- Designed a reproducible evaluation harness (dev/test split, 20+ one-variable ablations); query rewriting added
  **+8.2 pts Recall@5** and metadata filtering **+4.8 pts MRR**, and the tuned pipeline raised answer correctness from
  **59.5% (naive RAG) to 74.3%** with the same LLM.
- Reduced unsupported answers with a citation-enforcing prompt (cited answers **5% → 74%**, hallucination rate
  **35.1% → 28.9%**), a dev-calibrated abstention gate and a sentence-level faithfulness checker validated on 107
  labelled claims (**88% true-positive, 97% true-negative rate**).
- Added an OpenCV preprocessing + OCR pipeline for scanned drawings (field accuracy **78.4% → 86.4%**) and a read-only,
  role-scoped text-to-SQL route for counting questions (accuracy **12.5% → 62.5%**).

Shorter variant (one line): *RAG copilot over 231 engineering documents: 98.4% Recall@5, 59.5% → 74.3% answer
correctness vs naive RAG, validated hallucination checks, OCR for scanned drawings (Python, LangChain, FAISS, Next.js).*
