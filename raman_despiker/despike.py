"""Despiking (odstranění kosmických spiků / gamma-ray anomálií) Ramanových spekter.

Princip (single-spectrum režim)
-------------------------------
Kosmické spiky jsou úzké (na tomto přístroji měřeno FWHM ≤ ~5 bodů), zatímco
skutečné Ramanovy pásy jsou širší (FWHM ≥ ~7 bodů). Mezi tím je bezpečná mezera.

1. Od spektra odečteme klouzavý medián (okno širší než spike, užší než reálný
   pás) -> reziduum. Reálné pásy medián zachová (malé reziduum), spike ne.
2. Šum odhadneme z **druhých diferencí** — ten je necitlivý na lineární sklon,
   takže se spike pozná i na hraně/vrcholu reálného píku. Lokálně adaptivní.
3. Modifikované Z-skóre rezidua se prahuje s **hysterezí**: jádro spiku |z|>práh
   se rozšíří na okolní body |z|>práh/2 (zachytí i širší spike a jeho boky).
4. Ochrana reálných pásů: souvislý označený úsek delší než width_cap se odznačí
   (širší útvar = reálný pás, ne spike).
5. Nahrazení lineární interpolací z čistých sousedů; zbytek spektra beze změny.
6. Iterace: po odstranění velkých spiků klesne šum a odhalí se menší.

Vychází z principu Whitaker & Hayes (2018) rozšířeného o měřením podložené
šířkové kritérium a odhad šumu z druhých diferencí.

Pozn.: Pro opakovaná měření téhož vzorku existuje spolehlivější konsenzuální
režim napříč spektry — viz modul `consensus`.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter

# ---- výchozí parametry (podložené měřením na trénovacích datech) ----
DEFAULT_THRESHOLD = 6.0
DEFAULT_MED_KERNEL = 5      # okno mediánu pro odhad hladkého pozadí
DEFAULT_WIDTH_CAP = 5       # delší souvislý úsek = reálný pás -> neodstraní se
DEFAULT_ITERATIONS = 5
DEFAULT_ADAPT_WINDOW = 151  # okno (v pořadí dle úrovně signálu) pro model šumu
HYSTERESIS_FRAC = 0.5       # spodní práh pro rozšíření spiku (× threshold)


def _as_odd(n: int) -> int:
    n = int(round(n))
    if n < 1:
        n = 1
    return n + 1 if n % 2 == 0 else n


def _noise_sigma(y: np.ndarray, window: int, adaptive: bool) -> np.ndarray:
    """Odhad šumu závislý na úrovni signálu (model shot-noise).

    Šum v Ramanově spektru roste s intenzitou (shot-noise ~ sqrt(signál)), takže
    vrchol silného píku má velký šum. Kdybychom používali jednu globální úroveň
    šumu, ostrá špička reálného píku by vypadala jako spike. Proto:

    1. Šumový proxy = absolutní 2. diference (necitlivá na lineární sklon).
    2. Hladké pozadí (medián) udává úroveň signálu v každém bodě.
    3. Body seřadíme podle úrovně signálu a spočteme klouzavý medián proxy v
       tomto pořadí -> sigma jako rostoucí funkce signálu. Vrchol píku (vysoký
       signál) tak dostane velký šum (nízké z), spike na pozadí malý (vysoké z).

    Pro bílý šum má 2. diference rozptyl 6*sigma^2 -> dělíme sqrt(6).
    """
    n = y.size
    d2 = np.diff(y, 2)  # délka n-2
    med = float(np.median(d2))
    ad2 = np.abs(d2 - med)
    sigma_g = 1.4826 * float(np.median(ad2)) / np.sqrt(6.0)
    if not np.isfinite(sigma_g) or sigma_g <= 0:
        sigma_g = float(np.std(d2)) / np.sqrt(6.0) or 1.0

    # proxy do bodové domény (délka n)
    ap = np.empty(n)
    ap[1:-1] = ad2
    ap[0] = ad2[0] if ad2.size else 0.0
    ap[-1] = ad2[-1] if ad2.size else 0.0

    if adaptive and window and window > 3 and n > 5:
        w = _as_odd(window)
        if w >= n:
            w = _as_odd(n - 1)
        base = median_filter(y, size=_as_odd(11) if n > 11 else _as_odd(n - 1),
                             mode="nearest")
        order = np.argsort(base, kind="mergesort")
        s_sorted = median_filter(ap[order], size=w, mode="nearest")
        sigma = np.empty(n)
        sigma[order] = 1.4826 * s_sorted / np.sqrt(6.0)
        sigma = np.maximum(sigma, 0.3 * sigma_g)
    else:
        sigma = np.full(n, sigma_g)

    sigma[~np.isfinite(sigma) | (sigma <= 0)] = sigma_g if sigma_g > 0 else 1.0
    return sigma


def _hysteresis(strong: np.ndarray, weak: np.ndarray) -> np.ndarray:
    """Rozšíří jádra (strong) na souvislé úseky splňující weak."""
    out = np.zeros_like(strong)
    n = len(strong)
    i = 0
    while i < n:
        if weak[i]:
            j = i
            while j < n and weak[j]:
                j += 1
            if strong[i:j].any():
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def _width_guard(flags: np.ndarray, max_run: int) -> np.ndarray:
    """Odznačí souvislé úseky delší než max_run (chrání reálné pásy)."""
    if max_run <= 0:
        return flags
    out = flags.copy()
    n = len(flags)
    i = 0
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            if (j - i) > max_run:
                out[i:j] = False
            i = j
        else:
            i += 1
    return out


def detect_spikes(
    y,
    threshold: float = DEFAULT_THRESHOLD,
    med_kernel: int = DEFAULT_MED_KERNEL,
    width_cap: int = DEFAULT_WIDTH_CAP,
    adaptive: bool = True,
    adapt_window: int = DEFAULT_ADAPT_WINDOW,
):
    """Detekuje spiky. Vrací (flags: bool[N], zscore: float[N])."""
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 7:
        return np.zeros(n, dtype=bool), np.zeros(n)

    k = _as_odd(med_kernel)
    if k >= n:
        k = _as_odd(n - 1)
    base = median_filter(y, size=k, mode="nearest")
    resid = y - base
    sigma = _noise_sigma(y, adapt_window, adaptive)
    z = resid / sigma

    az = np.abs(z)
    strong = az > threshold
    weak = az > threshold * HYSTERESIS_FRAC
    flags = _hysteresis(strong, weak)
    flags = _width_guard(flags, width_cap)
    return flags, z


def despike(
    y,
    threshold: float = DEFAULT_THRESHOLD,
    med_kernel: int = DEFAULT_MED_KERNEL,
    width_cap: int = DEFAULT_WIDTH_CAP,
    iterations: int = DEFAULT_ITERATIONS,
    adaptive: bool = True,
    adapt_window: int = DEFAULT_ADAPT_WINDOW,
):
    """Odstraní spiky ze spektra.

    Returns
    -------
    cleaned : np.ndarray  -- vyčištěné intenzity.
    mask    : np.ndarray(bool) -- True tam, kde byl bod nahrazen.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    cleaned = y.copy()
    total = np.zeros(n, dtype=bool)
    if n < 7:
        return cleaned, total

    idx = np.arange(n)
    for _ in range(max(1, iterations)):
        flags, _z = detect_spikes(
            cleaned, threshold, med_kernel, width_cap, adaptive, adapt_window
        )
        new = flags & ~total
        if not new.any():
            break
        total |= flags
        good = ~total
        if good.sum() < 2:
            break
        cleaned[total] = np.interp(idx[total], idx[good], cleaned[good])

    return cleaned, total


def despike_spectrum(x, y, **kwargs):
    """Seřadí podle x (interpolace pracuje v pořadí bodů), despikuje a vrátí
    (x, cleaned, mask) v původním pořadí vstupu."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(x)
    inv = np.argsort(order)
    cleaned_sorted, mask_sorted = despike(y[order], **kwargs)
    return x, cleaned_sorted[inv], mask_sorted[inv]
