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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="yokoten")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen-data", help="generate the synthetic corpus + golden set")
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_gen_data)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
