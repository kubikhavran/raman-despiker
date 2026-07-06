# Sestavení .exe a instalátoru pro kolegy

Dvě varianty distribuce. Obě spouštěj v aktivovaném virtuálním prostředí.

## A) Nejjednodušší — jeden .exe soubor

```bash
pip install pyinstaller
python build_exe.py --onefile
```

Vznikne `dist\RamanDespiker.exe`. Ten stačí poslat kolegům — spustí ho dvojklikem,
nepotřebují Python. (Start je o pár sekund pomalejší, protože se rozbaluje do dočasné složky.)

## B) Pořádný instalátor (setup.exe) — doporučeno pro více lidí

1. Sestav aplikaci jako složku (rychlejší start):
   ```bash
   pip install pyinstaller
   python build_exe.py
   ```
   Vznikne `dist\RamanDespiker\` (celá složka s `RamanDespiker.exe`).

2. Nainstaluj **Inno Setup**: https://jrsoftware.org/isdl.php

3. Sestav instalátor:
   ```bash
   iscc installer.iss
   ```
   (nebo otevři `installer.iss` v Inno Setup a klikni *Compile*).

4. Vznikne `Output\RamanDespiker_Setup.exe` — tohle pošli kolegům. Nainstaluje
   aplikaci, vytvoří zástupce v nabídce Start i na ploše, jde odinstalovat
   přes *Přidat/odebrat programy*. Nevyžaduje admin práva (instaluje se do profilu).

## Ikona (volitelné)

Pokud do `assets\icon.ico` dáš ikonu, build ji použije automaticky.

## Poznámky

- .exe je vázaný na Windows x64 (stejné jako cílové PC kolegů).
- Antivir občas u neznámého .exe hlásí „SmartScreen" — jde o nepodepsanou aplikaci;
  kolega dá *Více informací → Přesto spustit*. Podepsání certifikátem je nad rámec
  tohoto projektu.
