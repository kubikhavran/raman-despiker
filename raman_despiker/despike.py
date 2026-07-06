"""Despiking (odstranění kosmických spiků / gamma-ray anomálií) Ramanových spekter.

Princip
-------
Kosmické spiky jsou velmi úzké (typicky 1-3 body) a ostré, zatímco skutečné
Ramanovy pásy jsou široké (mnoho bodů). Toho využíváme:

1. Od spektra odečteme klouzavý medián (malé okno) -> reziduum.
   Široké reálné pásy medián zachová (reziduum malé), úzký spike ne
   (reziduum velké).
2. Odlehlé body detekujeme robustním modifikovaným Z-skóre (medián + MAD).
   MAD je odolné vůči odlehlým hodnotám, takže práh sedí i u zašuměných spekter.
   Volitelně lokálně adaptivní měřítko -> chytá malé spiky v klidných úsecích
   i velké v hlučných.
3. Ochrana reálných píků: označí se jen souvislé úseky do zadané maximální
   šířky (širší útvar = reálný pás, ne spike).
4. Nahrazení: označené body se nahradí lineární interpolací z okolních
   *čistých* bodů. Zbytek spektra zůstává beze změny (žádné zkreslení).

Metoda vychází z principu Whitaker & Hayes, "A simple algorithm for despiking
Raman spectra", Chemom. Intell. Lab. Syst. 179 (2018) 82-84.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter


def _as_odd(n: int) -> int:
    """Vrátí nejbližší liché kladné číslo (median_filter chce liché okno)."""
    n = int(round(n))
    if n < 1:
        n = 1
    if n % 2 == 0:
        n += 1
    return n


def _mad_sigma(a: np.ndarray) -> tuple[float, float]:
    """Robustní odhad rozptylu (sigma z MAD) a mediánu."""
    med = float(np.median(a))
    mad = float(np.median(np.abs(a - med)))
    return 1.4826 * mad, med


def _noise_sigma(y: np.ndarray, window: int, adaptive: bool) -> np.ndarray:
    """Robustní odhad šumu z rozdílů sousedních bodů.

    Pro bílý šum má diff rozptyl 2*sigma^2, proto dělíme sqrt(2). Odhad z diferencí
    je odolný vůči (řídkým) spikům a při lokální variantě respektuje shot-noise,
    který roste u silného signálu (píky, vysoké pozadí).
    """
    n = y.size
    d = np.diff(y)
    med_d = float(np.median(d))
    mad_g = float(np.median(np.abs(d - med_d)))
    sigma_g = 1.4826 * mad_g / np.sqrt(2.0)
    if not np.isfinite(sigma_g) or sigma_g <= 0:
        sigma_g = float(np.std(d)) / np.sqrt(2.0) or 1.0

    if adaptive and window and window > 3:
        w = _as_odd(window)
        if w >= d.size:
            w = _as_odd(max(3, d.size - 1))
        # median(|d|) ~ MAD(d) (median rozdílů je ~0) -> lokální úroveň šumu
        local = median_filter(np.abs(d - med_d), size=w, mode="nearest")
        sigma_l = 1.4826 * local / np.sqrt(2.0)
        sigma_pts = np.empty(n)
        sigma_pts[1:] = sigma_l
        sigma_pts[0] = sigma_l[0]
        sigma = np.maximum(sigma_pts, 0.3 * sigma_g)
    else:
        sigma = np.full(n, sigma_g)

    sigma[~np.isfinite(sigma) | (sigma <= 0)] = sigma_g if sigma_g > 0 else 1.0
    return sigma


def _width_guard(flags: np.ndarray, max_width: int) -> np.ndarray:
    """Ponechá označené jen souvislé úseky délky <= max_width.

    Chrání reálné (širší) píky před smazáním. max_width <= 0 = bez ochrany.
    """
    if max_width <= 0:
        return flags
    out = flags.copy()
    n = len(flags)
    i = 0
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            if (j - i) > max_width:
                out[i:j] = False
            i = j
        else:
            i += 1
    return out


def detect_spikes(
    y,
    threshold: float = 6.0,
    med_kernel: int = 5,
    max_width: int = 3,
    adaptive: bool = True,
    adapt_window: int = 51,
    min_scale_frac: float = 0.3,
):
    """Detekuje spiky. Vrací (flags: bool[N], zscore: float[N]).

    Parameters
    ----------
    threshold : práh modifikovaného Z-skóre. Nižší = citlivější (víc spiků).
    med_kernel : okno klouzavého mediánu pro odhad hladkého pozadí.
    max_width : max. šířka spiku v bodech (ochrana reálných píků).
    adaptive : lokálně adaptivní měřítko šumu.
    adapt_window : okno pro lokální odhad šumu (v bodech).
    min_scale_frac : dolní mez lokálního měřítka jako podíl globálního
                     (brání falešným detekcím v naprosto plochých úsecích).
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 5:
        return np.zeros(n, dtype=bool), np.zeros(n)

    k = _as_odd(med_kernel)
    if k >= n:
        k = _as_odd(n - 1)
    # hladké pozadí; u spiku vrátí medián okna (spike sám je z mediánu vyloučen)
    base = median_filter(y, size=k, mode="nearest")
    resid = y - base

    # úroveň šumu z rozdílů sousedních bodů (lokálně adaptivní = respektuje shot-noise)
    sigma = _noise_sigma(y, adapt_window, adaptive)

    z = resid / sigma
    flags = np.abs(z) > threshold
    flags = _width_guard(flags, max_width)
    return flags, z


def despike(
    y,
    threshold: float = 6.0,
    med_kernel: int = 5,
    max_width: int = 3,
    iterations: int = 3,
    adaptive: bool = True,
    adapt_window: int = 51,
):
    """Odstraní spiky ze spektra.

    Iterativně (výchozí 3x): po nahrazení největších spiků klesne MAD a odhalí
    se i menší spiky, které byly "schované" vedle větších. Konverguje rychle.

    Returns
    -------
    cleaned : np.ndarray  -- vyčištěné intenzity (stejná délka jako y).
    mask    : np.ndarray(bool) -- True tam, kde byl bod nahrazen.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    cleaned = y.copy()
    total = np.zeros(n, dtype=bool)
    if n < 5:
        return cleaned, total

    idx = np.arange(n)
    for _ in range(max(1, iterations)):
        flags, _z = detect_spikes(
            cleaned, threshold, med_kernel, max_width, adaptive, adapt_window
        )
        new = flags & ~total
        if not new.any():
            break
        total |= flags
        good = ~total
        if good.sum() < 2:
            break
        # interpolace pouze přes označené body z čistých sousedů
        cleaned[total] = np.interp(idx[total], idx[good], cleaned[good])

    return cleaned, total


def despike_spectrum(x, y, **kwargs):
    """Pohodlný wrapper: seřadí podle x (interpolace pracuje v pořadí bodů),
    despikuje a vrátí (x, cleaned, mask) v původním pořadí vstupu.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(x)
    inv = np.argsort(order)
    cleaned_sorted, mask_sorted = despike(y[order], **kwargs)
    return x, cleaned_sorted[inv], mask_sorted[inv]
