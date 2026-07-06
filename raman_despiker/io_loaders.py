"""Načítání a ukládání spekter: podpora .txt (Renishaw export) a .wdf (nativní).

Jeden soubor .wdf může obsahovat více spekter (mapa / více akumulací) — vrací se
proto vždy seznam objektů Spectrum.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import numpy as np

TXT_EXT = {".txt", ".csv", ".dat", ".asc", ".spc_txt"}
WDF_EXT = {".wdf"}


@dataclass
class Spectrum:
    x: np.ndarray          # Ramanův posun (cm^-1) nebo jiná osa X
    y: np.ndarray          # intenzita
    name: str              # zobrazované jméno (např. jméno souboru, u map s indexem)
    source: str            # cesta ke zdrojovému souboru
    index: int = 0         # pořadí spektra ve zdrojovém souboru (mapy)

    def copy_with(self, y):
        return Spectrum(self.x.copy(), np.asarray(y, float), self.name, self.source, self.index)


def _parse_number_line(line: str):
    """Z řádku vytáhne čísla. Zvládá tab/mezera/čárka/středník jako oddělovač
    a čárku i jako desetinnou (Czech export)."""
    s = line.strip()
    if not s or s[0] in "#;%\"'":
        # může to být hlavička; zkusíme přesto, ale řádky začínající # ignorujeme
        if not s or s[0] in "#%":
            return None
    # nejprve dělení podle bílých znaků
    toks = s.split()
    if len(toks) >= 2:
        # čárky jsou pravděpodobně desetinné
        toks = [t.replace(",", ".") for t in toks]
    else:
        # jednosloupcový po whitespace -> zkusíme čárku/středník jako oddělovač
        toks = [t for t in re.split(r"[;,]", s) if t != ""]
    try:
        return [float(t) for t in toks]
    except ValueError:
        return None


def load_txt(path: str) -> list[Spectrum]:
    rows = []
    ncols = None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            vals = _parse_number_line(line)
            if vals is None or len(vals) < 2:
                continue
            if ncols is None:
                ncols = len(vals)
            if len(vals) == ncols:
                rows.append(vals)
    if not rows:
        raise ValueError(f"V souboru nebyla nalezena číselná data: {path}")

    arr = np.asarray(rows, dtype=float)
    if arr.shape[1] == 2:
        xi, yi = 0, 1
    else:
        # 3+ sloupců: bývá index | x | y. Poznáme index (celá čísla 1..N).
        col0 = arr[:, 0]
        looks_like_index = np.allclose(col0, np.round(col0)) and (
            np.array_equal(col0, np.arange(col0[0], col0[0] + len(col0)))
        )
        if looks_like_index:
            xi, yi = 1, 2
        else:
            xi, yi = 0, 1

    name = os.path.splitext(os.path.basename(path))[0]
    return [Spectrum(arr[:, xi], arr[:, yi], name, path, 0)]


def load_wdf(path: str) -> list[Spectrum]:
    try:
        from renishawWiRE import WDFReader
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Pro čtení .wdf je potřeba balík 'renishawWiRE' (pip install renishawWiRE)."
        ) from e

    reader = WDFReader(path)
    x = np.asarray(reader.xdata, dtype=float).ravel()
    spectra = np.asarray(reader.spectra, dtype=float)
    name = os.path.splitext(os.path.basename(path))[0]

    out: list[Spectrum] = []
    if spectra.ndim == 1:
        out.append(Spectrum(x, spectra.astype(float), name, path, 0))
    else:
        flat = spectra.reshape(-1, spectra.shape[-1])
        multi = flat.shape[0] > 1
        for i in range(flat.shape[0]):
            nm = f"{name}#{i + 1}" if multi else name
            out.append(Spectrum(x, flat[i].astype(float), nm, path, i))
    try:
        reader.close()
    except Exception:
        pass
    return out


def load_any(path: str) -> list[Spectrum]:
    ext = os.path.splitext(path)[1].lower()
    if ext in WDF_EXT:
        return load_wdf(path)
    return load_txt(path)


def is_supported(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in TXT_EXT or ext in WDF_EXT


def list_spectra_files(folder: str, recursive: bool = False) -> list[str]:
    result = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                p = os.path.join(root, fn)
                if is_supported(p):
                    result.append(p)
    else:
        for fn in sorted(os.listdir(folder)):
            p = os.path.join(folder, fn)
            if os.path.isfile(p) and is_supported(p):
                result.append(p)
    return sorted(result)


def write_txt(path: str, x: np.ndarray, y: np.ndarray, delimiter: str = "\t",
              fmt: str = "%.6f") -> None:
    """Uloží spektrum jako dvousloupcový textový soubor (x <sep> y)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for xv, yv in zip(x, y):
            f.write(f"{fmt % xv}{delimiter}{fmt % yv}\n")
