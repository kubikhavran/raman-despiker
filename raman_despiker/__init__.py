"""Raman Despiker — dávkové odstranění kosmických spiků z Ramanových spekter."""

from .despike import despike, despike_spectrum, detect_spikes
from .io_loaders import Spectrum, load_any, load_txt, load_wdf, write_txt
from .batch import DespikeParams, process_folder

__version__ = "1.0.0"

__all__ = [
    "despike",
    "despike_spectrum",
    "detect_spikes",
    "Spectrum",
    "load_any",
    "load_txt",
    "load_wdf",
    "write_txt",
    "DespikeParams",
    "process_folder",
]
