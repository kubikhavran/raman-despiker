"""Základní testy despike jádra."""
import numpy as np

from raman_despiker.despike import despike, despike_spectrum, detect_spikes


def _synthetic():
    x = np.linspace(100, 3200, 3000)
    # hladké pozadí + široký reálný pík + šum
    rng = np.random.default_rng(0)
    peak = 5000 * np.exp(-((x - 1600) ** 2) / (2 * 15.0 ** 2))
    y = 3000 + peak + rng.normal(0, 40, x.size)
    return x, y


def test_removes_single_spike():
    x, y = _synthetic()
    y_spiked = y.copy()
    y_spiked[1000] += 8000  # ostrý jednobodový spike
    cleaned, mask = despike(y_spiked, threshold=6.0)
    assert mask[1000]
    assert abs(cleaned[1000] - y[1000]) < 400  # vráceno blízko originálu


def test_preserves_real_peak():
    x, y = _synthetic()
    mask, _z = detect_spikes(y, threshold=6.0)
    # reálný široký pík (kolem indexu odpovídajícího 1600) se nesmí označit
    peak_idx = np.argmin(np.abs(x - 1600))
    assert not mask[peak_idx]


def test_low_noise_no_false_positives():
    x, y = _synthetic()
    _, mask = despike(y, threshold=6.0)
    # bez vložených spiků má být označeno minimum bodů (< 0.5 %)
    assert mask.sum() < 0.005 * y.size


def test_order_independence():
    x, y = _synthetic()
    y[500] += 9000
    # sestupné x (jako Renishaw) musí dát stejný počet spiků jako vzestupné
    _, _, mask_desc = despike_spectrum(x[::-1], y[::-1], threshold=6.0)
    _, _, mask_asc = despike_spectrum(x, y, threshold=6.0)
    assert mask_desc.sum() == mask_asc.sum()


def test_multiple_spikes():
    x, y = _synthetic()
    for i in (200, 800, 1500, 2500):
        y[i] += 7000
    _, mask = despike(y, threshold=6.0)
    for i in (200, 800, 1500, 2500):
        assert mask[i], f"spike at {i} nebyl detekován"
