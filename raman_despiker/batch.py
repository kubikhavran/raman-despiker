"""Dávkové zpracování celé složky spekter."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from .despike import despike_spectrum
from .io_loaders import Spectrum, list_spectra_files, load_any, write_txt


@dataclass
class DespikeParams:
    threshold: float = 6.0
    med_kernel: int = 5
    max_width: int = 3
    iterations: int = 3
    adaptive: bool = True
    adapt_window: int = 51

    def as_kwargs(self) -> dict:
        return dict(
            threshold=self.threshold,
            med_kernel=self.med_kernel,
            max_width=self.max_width,
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
