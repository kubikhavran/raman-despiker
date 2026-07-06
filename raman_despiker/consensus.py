"""Konsenzuální (napříč-spektrální) odstranění spiků pro OPAKOVANÁ měření.

Když složka obsahuje více měření téhož vzorku na stejné ose X, je nejspolehlivější
metodou porovnání se skupinovým konsenzem: kosmické spiky dopadají náhodně, takže
se v robustním mediánu přes spektra neobjeví. Bod, který v konkrétním spektru
výrazně (a úzce) převyšuje konsenzus, je spike -> nahradí se interpolací.

Reálné pásy jsou v konsenzu obsaženy, takže se nikdy neodstraní. Široké odlišnosti
mezi spektry (jiné pozadí, jiná intenzita, jiný spot) se neoznačí díky omezení
šířky — mění se jen úzké odchylky.

Tento režim je vhodný POUZE pro spektra téhož vzorku na shodné ose X. Pro směs
různých vzorků použij single-spectrum režim (`despike`).
"""
from __future__ import annotations

import numpy as np

from .despike import despike, _hysteresis, _width_guard, HYSTERESIS_FRAC

DEFAULT_CONSENSUS_THRESHOLD = 6.0
DEFAULT_CONSENSUS_WIDTH_CAP = 8   # konsenzus je spolehlivý -> povolíme širší spike


def group_signature(x: np.ndarray, decimals: int = 2) -> tuple:
    """Podpis osy X pro seskupení spekter (délka + zaokrouhlené krajní body a krok)."""
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return (x.size,)
    return (
        x.size,
        round(float(x[0]), decimals),
        round(float(x[-1]), decimals),
        round(float(x[1] - x[0]), decimals),
    )


def build_consensus(Y: np.ndarray):
    """Z matice spekter (n_spekter × n_bodů) vrátí (median, mad_scale).

    mad je zdola omezené (podlaha), aby v místech, kde se spektra náhodně
    přesně shodnou, neexplodovalo z-skóre a nevznikaly falešné detekce.
    """
    Y = np.asarray(Y, dtype=float)
    med = np.median(Y, axis=0)
    mad = 1.4826 * np.median(np.abs(Y - med), axis=0)
    floor = 0.25 * np.median(mad[mad > 0]) if np.any(mad > 0) else 1.0
    mad = np.maximum(mad, floor) + 1e-9
    return med, mad


def consensus_flags(
    y: np.ndarray,
    med: np.ndarray,
    mad: np.ndarray,
    threshold: float = DEFAULT_CONSENSUS_THRESHOLD,
    width_cap: int = DEFAULT_CONSENSUS_WIDTH_CAP,
) -> np.ndarray:
    """Označí úzké body, kde y převyšuje konsenzus (kladná odchylka v jednotkách MAD).

    Použije hysterezi (jádro > práh rozšíří na okolí > práh/2) a šířkovou pojistku.
    """
    dev = (y - med) / mad
    strong = dev > threshold
    weak = dev > threshold * HYSTERESIS_FRAC
    flags = _hysteresis(strong, weak)
    return _width_guard(flags, width_cap)


def consensus_despike_group(
    Y: np.ndarray,
    threshold: float = DEFAULT_CONSENSUS_THRESHOLD,
    width_cap: int = DEFAULT_CONSENSUS_WIDTH_CAP,
    combine_single: bool = True,
    single_kwargs: dict | None = None,
):
    """Despikuje skupinu spekter (stejná osa X) konsenzem.

    combine_single=True sjednotí konsenzuální nálezy se single-spectrum despike
    (pojistka pro spiky v místech, kde je i reálný pás).

    Returns: (cleaned_matrix, masks_matrix)
    """
    Y = np.asarray(Y, dtype=float)
    if Y.ndim == 1:
        Y = Y[None, :]
    n_spec, n = Y.shape
    med, mad = build_consensus(Y)
    idx = np.arange(n)
    cleaned = np.empty_like(Y)
    masks = np.zeros_like(Y, dtype=bool)
    sk = single_kwargs or {}

    for i in range(n_spec):
        y = Y[i]
        flags = consensus_flags(y, med, mad, threshold, width_cap)
        if combine_single:
            _, m_single = despike(y, **sk)
            flags = flags | m_single
        good = ~flags
        c = y.copy()
        if flags.any() and good.sum() >= 2:
            c[flags] = np.interp(idx[flags], idx[good], y[good])
        cleaned[i] = c
        masks[i] = flags

    return cleaned, masks
