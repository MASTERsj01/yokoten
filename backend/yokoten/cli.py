"""Command line: yokoten gen-data | ingest | ask | eval"""

import argparse
import json
import time

from yokoten.config import ROOT, settings


def cmd_gen_data(args):
    from yokoten.datagen import generate

    t = time.perf_counter()
    stats = generate(settings.corpus_dir, ROOT / "eval" / "golden.jsonl", seed=args.seed)
    print(json.dumps(stats, indent=2))
    print(f"generated in {time.perf_counter() - t:.1f}s -> {settings.corpus_dir}")


def cmd_ingest(args):
    from yokoten.ingest.pipeline import ingest_corpus

    report = ingest_corpus(ocr_engine=args.ocr, ner=not args.no_ner, force=args.force)
    print(json.dumps(report, indent=2))


def cmd_search(args):
    from yokoten.config import load_runtime
    from yokoten.retrieval.index import get_index

    cfg = load_runtime()
    index = get_index(args.chunking or cfg.chunking, cfg.embedding_model)
    for h in index.search(args.query, mode=args.mode, k=args.k, store=args.store):
        c = index.chunks[h.idx]
        print(f"{h.fused:.4f} dense={h.dense_rank} bm25={h.bm25_rank} {c.doc_id:18s} | {c.text[:110]!r}")


def cmd_ask(args):
    import sys

    from yokoten.config import load_runtime
    from yokoten.rag.pipeline import answer

    cfg = load_runtime()
    if args.provider:
        cfg.llm_provider, cfg.llm_model = args.provider, args.model or ""
    for ev in answer(args.question, cfg=cfg, role=args.role):
        name, data = ev["event"], ev["data"]
        if name == "meta":
            print(
                f"[{data['provider']}/{data['model']}] intent={data['intent']} filters={data['filters']} "
                f"gate={data['gate']}\nstandalone: {data['standalone']}\n"
            )
        elif name == "token":
            sys.stdout.write(data["text"])
            sys.stdout.flush()
        elif name == "verification":
            verif = data
        elif name == "done":
            print("\n")
            for c in data["citations"]:
                loc = f"p.{c['page']}" if c["page"] else c["section"]
                print(f"  [{c['n']}] {c['doc_id']} Rev {c['revision']} - {c['title']} ({loc})")
            if data["abstained"] and data["related"]:
                print("  closest documents: " + ", ".join(r["doc_id"] for r in data["related"]))
            print(
                f"\nconfidence={data['confidence']} ({data['confidence_label']}) "
                f"faithfulness={verif.get('faithfulness')} latency={data['latency_ms']:.0f} ms "
                f"trace={data['trace_id']}"
            )
            if data["suggestions"]:
                print("follow-ups: " + " | ".join(data["suggestions"]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="yokoten")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen-data", help="generate the synthetic corpus + golden set")
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_gen_data)
    i = sub.add_parser("ingest", help="ingest data/corpus into SQLite + indexes (incremental)")
    i.add_argument("--ocr", default="auto", choices=["auto", "tesseract", "easyocr"])
    i.add_argument("--no-ner", action="store_true")
    i.add_argument("--force", action="store_true", help="re-process unchanged files")
    i.set_defaults(func=cmd_ingest)
    s = sub.add_parser("search", help="retrieval only (no LLM)")
    s.add_argument("query")
    s.add_argument("--mode", default="hybrid", choices=["dense", "bm25", "hybrid"])
    s.add_argument("--store", default="faiss", choices=["faiss", "chroma"])
    s.add_argument("--chunking", default=None)
    s.add_argument("-k", type=int, default=8)
    s.set_defaults(func=cmd_search)
    a = sub.add_parser("ask", help="ask a question (full RAG pipeline, streamed)")
    a.add_argument("question")
    a.add_argument("--provider", choices=["groq", "gemini", "ollama", "local"])
    a.add_argument("--model")
    a.add_argument("--role", default="admin")
    a.set_defaults(func=cmd_ask)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
