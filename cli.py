"""Dávkové odspikování z příkazové řádky (bez GUI).

Použití:
    python cli.py VSTUPNI_SLOZKA [-o VYSTUPNI_SLOZKA] [--threshold 6.0]
                  [--max-width 3] [--iterations 3] [--med-kernel 5]
                  [--no-adaptive] [--recursive]
"""
from __future__ import annotations

import argparse
import os
import sys

from raman_despiker.batch import DespikeParams, process_folder


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dávkové odstranění spiků z Ramanových spekter.")
    p.add_argument("input", help="Vstupní složka se spektry (.txt / .wdf)")
    p.add_argument("-o", "--output", default=None, help="Výstupní složka (výchozí: <vstup>/despiked)")
    p.add_argument("--threshold", type=float, default=6.0)
    p.add_argument("--max-width", type=int, default=3)
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--med-kernel", type=int, default=5)
    p.add_argument("--no-adaptive", action="store_true", help="Vypne lokálně adaptivní práh")
    p.add_argument("--recursive", action="store_true", help="Projít i podsložky")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    out = args.output or os.path.join(args.input, "despiked")
    params = DespikeParams(
        threshold=args.threshold,
        med_kernel=args.med_kernel,
        max_width=args.max_width,
        iterations=args.iterations,
        adaptive=not args.no_adaptive,
    )

    def progress(done, total, msg):
        print(f"[{done}/{total}] {msg}")

    summary = process_folder(args.input, out, params, recursive=args.recursive, progress=progress)
    print("-" * 60)
    print(f"Souborů: {summary.n_files} | OK: {summary.n_ok} | Chyb: {summary.n_failed} "
          f"| Spiků celkem: {summary.total_spikes}")
    print(f"Uloženo do: {out}")
    if summary.n_failed:
        print("Chybné soubory:")
        for r in summary.results:
            if not r.ok:
                print(f"  - {os.path.basename(r.source)}: {r.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
