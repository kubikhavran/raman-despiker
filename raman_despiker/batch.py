"""Dávkové zpracování celé složky spekter."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .despike import despike_spectrum
from .consensus import consensus_despike_group, group_signature
from .io_loaders import Spectrum, list_spectra_files, load_any, write_txt


@dataclass
class DespikeParams:
    threshold: float = 6.0
    med_kernel: int = 5
    width_cap: int = 5
    iterations: int = 5
    adaptive: bool = True
    adapt_window: int = 151

    def as_kwargs(self) -> dict:
        return dict(
            threshold=self.threshold,
            med_kernel=self.med_kernel,
            width_cap=self.width_cap,
            iterations=self.iterations,
            adaptive=self.adaptive,
            adapt_window=self.adapt_window,
        )


@dataclass
class FileResult:
    source: str
    output: str
    n_spectra: int
    n_spikes: int
    ok: bool
    error: str = ""


@dataclass
class BatchSummary:
    results: list[FileResult] = field(default_factory=list)

    @property
    def n_files(self) -> int:
        return len(self.results)

    @property
    def n_ok(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def n_failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def total_spikes(self) -> int:
        return sum(r.n_spikes for r in self.results if r.ok)


def _safe_name(name: str) -> str:
    return "".join(c if c not in '<>:"/\\|?*' else "_" for c in name)


def despike_spectrum_obj(spec: Spectrum, params: DespikeParams):
    """Vrátí (cleaned_spectrum, n_spikes)."""
    x, cleaned, mask = despike_spectrum(spec.x, spec.y, **params.as_kwargs())
    return spec.copy_with(cleaned), int(mask.sum())


def process_folder(
    input_dir: str,
    output_dir: str,
    params: DespikeParams,
    recursive: bool = False,
    suffix: str = "_despiked",
    progress: Callable[[int, int, str], None] | None = None,
) -> BatchSummary:
    """Zpracuje všechny podporované soubory ve složce a uloží vyčištěná .txt.

    progress(done, total, message) je volitelný callback pro GUI.
    """
    os.makedirs(output_dir, exist_ok=True)
    files = list_spectra_files(input_dir, recursive=recursive)
    summary = BatchSummary()
    total = len(files)

    for i, path in enumerate(files):
        base = os.path.splitext(os.path.basename(path))[0]
        try:
            specs = load_any(path)
            n_spikes = 0
            out_path = ""
            multi = len(specs) > 1
            for spec in specs:
                cleaned, ns = despike_spectrum_obj(spec, params)
                n_spikes += ns
                if multi:
                    out_name = f"{_safe_name(base)}_{spec.index + 1:04d}{suffix}.txt"
                else:
                    out_name = f"{_safe_name(base)}{suffix}.txt"
                out_path = os.path.join(output_dir, out_name)
                write_txt(out_path, cleaned.x, cleaned.y)
            summary.results.append(
                FileResult(path, out_path, len(specs), n_spikes, True)
            )
        except Exception as e:  # pragma: no cover - robustnost dávky
            summary.results.append(
                FileResult(path, "", 0, 0, False, str(e))
            )
        if progress:
            progress(i + 1, total, os.path.basename(path))

    return summary


def process_folder_consensus(
    input_dir: str,
    output_dir: str,
    params: DespikeParams,
    recursive: bool = False,
    suffix: str = "_despiked",
    consensus_threshold: float = 6.0,
    consensus_width_cap: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
) -> BatchSummary:
    """Konsenzuální dávka pro OPAKOVANÁ měření téhož vzorku.

    Spektra se seskupí podle shodné osy X; v každé skupině (>=2 spektra) se
    despikuje porovnáním se skupinovým mediánem. Skupiny s jediným spektrem
    spadnou zpět na single-spectrum režim.
    """
    os.makedirs(output_dir, exist_ok=True)
    files = list_spectra_files(input_dir, recursive=recursive)
    summary = BatchSummary()
    total = len(files)

    # 1) načti vše, seskup podle osy X
    records = []  # (path, base, spec, multi_placeholder)
    file_specs: dict[str, list[Spectrum]] = {}
    for i, path in enumerate(files):
        base = os.path.splitext(os.path.basename(path))[0]
        try:
            specs = load_any(path)
            file_specs[path] = specs
            for spec in specs:
                records.append((path, base, spec))
        except Exception as e:
            summary.results.append(FileResult(path, "", 0, 0, False, str(e)))
        if progress:
            progress(i, total, f"načítám {os.path.basename(path)}")

    groups: dict[tuple, list[int]] = {}
    for k, (_p, _b, spec) in enumerate(records):
        groups.setdefault(group_signature(spec.x), []).append(k)

    # 2) despikuj po skupinách, výsledky ulož podle zdrojového souboru
    cleaned_by_record: dict[int, tuple] = {}  # k -> (x, y_clean, n_spikes)
    for sig, ks in groups.items():
        Y = np.array([records[k][2].y for k in ks])
        if len(ks) >= 2:
            cleaned, masks = consensus_despike_group(
                Y, threshold=consensus_threshold, width_cap=consensus_width_cap,
                combine_single=True, single_kwargs=params.as_kwargs(),
            )
            for row, k in enumerate(ks):
                spec = records[k][2]
                cleaned_by_record[k] = (spec.x, cleaned[row], int(masks[row].sum()))
        else:
            spec = records[ks[0]][2]
            x, yc, mask = despike_spectrum(spec.x, spec.y, **params.as_kwargs())
            cleaned_by_record[ks[0]] = (x, yc, int(mask.sum()))

    # 3) zápis po souborech (zachová pojmenování jako single režim)
    done = 0
    for path, specs in file_specs.items():
        base = os.path.splitext(os.path.basename(path))[0]
        multi = len(specs) > 1
        n_spikes = 0
        out_path = ""
        ok = True
        err = ""
        try:
            for si, spec in enumerate(specs):
                # najdi odpovídající záznam
                k = next(kk for kk, (pp, _bb, sp) in enumerate(records)
                         if pp == path and sp is spec)
                x, yc, ns = cleaned_by_record[k]
                n_spikes += ns
                if multi:
                    out_name = f"{_safe_name(base)}_{spec.index + 1:04d}{suffix}.txt"
                else:
                    out_name = f"{_safe_name(base)}{suffix}.txt"
                out_path = os.path.join(output_dir, out_name)
                write_txt(out_path, x, yc)
        except Exception as e:
            ok = False
            err = str(e)
        summary.results.append(FileResult(path, out_path, len(specs), n_spikes, ok, err))
        done += 1
        if progress:
            progress(done, total, os.path.basename(path))

    return summary
