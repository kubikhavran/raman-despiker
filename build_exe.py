"""Sestavení samostatné .exe aplikace přes PyInstaller.

Použití:
    pip install pyinstaller
    python build_exe.py            # onedir (rychlý start, složka v dist/RamanDespiker)
    python build_exe.py --onefile  # jeden .exe soubor (pomalejší start)

Výstup je v adresáři dist/. Pro tvorbu instalátoru (setup.exe) viz INSTALLER.md.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets" / "icon.ico"


def main():
    try:
        import PyInstaller.__main__  # noqa
    except ImportError:
        print("Chybí PyInstaller. Nainstaluj: pip install pyinstaller")
        sys.exit(1)

    onefile = "--onefile" in sys.argv

    args = [
        str(ROOT / "app.py"),
        "--name", "RamanDespiker",
        "--windowed",           # bez konzolového okna
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
        # matplotlib a PySide6 mají vlastní hooky; jistota pro backend:
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "--collect-submodules", "renishawWiRE",
    ]
    if ICON.exists():
        args += ["--icon", str(ICON)]

    # vyčistit staré buildy
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    import PyInstaller.__main__ as pim
    pim.run(args)

    print("\nHotovo. Výstup:")
    if onefile:
        print(f"  {ROOT / 'dist' / 'RamanDespiker.exe'}")
    else:
        print(f"  {ROOT / 'dist' / 'RamanDespiker'}  (celá složka)")


if __name__ == "__main__":
    main()
