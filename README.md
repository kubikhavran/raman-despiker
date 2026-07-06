# Raman Despiker

Desktopová aplikace pro **dávkové odstranění kosmických spiků a gamma-ray anomálií**
z Ramanových spekter (Renishaw inVia). Vyber složku se spektry, aplikace všechna
projde, odstraní spiky a uloží vyčištěná spektra do `.txt`. Obsahuje **náhled
před/po** s vyznačenými spiky a živě nastavitelnou citlivostí.

- Vstup: `.txt` (dvousloupcový export `x  y`, i s indexovým sloupcem) a `.wdf`
  (nativní formát Renishaw inVia; podporuje i soubory s více spektry / mapy).
- Výstup: `.txt` (dvousloupcový `x  y`, tabulátorem oddělený).

## Jak to funguje (bez zkreslení spektra)

Kosmické spiky jsou velmi úzké (1–3 body) a ostré, reálné Ramanovy pásy jsou
široké. Algoritmus toho využívá:

1. **Reziduum od klouzavého mediánu** – odečte hladké pozadí; široké reálné pásy
   zůstanou (malé reziduum), úzký spike vyčnívá (velké reziduum).
2. **Robustní detekce (modifikované Z-skóre, medián + MAD)** – odolná vůči
   odlehlým hodnotám; volitelně **lokálně adaptivní**, takže chytá malé spiky
   v klidných úsecích i velké v hlučných.
3. **Ochrana reálných píků (max. šířka spiku)** – smažou se jen úzké útvary.
4. **Nahrazení interpolací** – označené body se dopočítají z okolních *čistých*
   bodů; **zbytek spektra zůstává beze změny**.
5. **Iterace** – opakováním se odhalí i menší spiky schované vedle velkých.

Vychází z: Whitaker & Hayes, *A simple algorithm for despiking Raman spectra*,
Chemom. Intell. Lab. Syst. 179 (2018) 82–84.

## Instalace a spuštění (Python)

```bash
# 1) vytvoř virtuální prostředí
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Linux/macOS

# 2) nainstaluj závislosti
pip install -r requirements.txt

# 3) spusť aplikaci
python app.py
```

### Dávka z příkazové řádky (bez GUI)

```bash
python cli.py "C:\cesta\ke\spektrum" -o "C:\cesta\vystup" --threshold 6
```

## Parametry

| Parametr | Význam | Výchozí |
|---|---|---|
| Práh (citlivost) | Nižší = citlivější (víc spiků), vyšší = konzervativnější | 6.0 |
| Max. šířka spiku | Širší útvar = reálný pás (nemaže se) | 3 body |
| Iterace | Opakování detekce | 3 |
| Okno mediánu | Okno pro odhad pozadí | 5 bodů |
| Lokálně adaptivní práh | Přizpůsobení lokálnímu šumu | zapnuto |

## Sestavení .exe pro kolegy

```bash
pip install pyinstaller
python build_exe.py
```

Výsledek je v `dist/`. Viz `build_exe.py` a `INSTALLER.md`.

## Struktura

```
raman_despiker/
  despike.py      # jádro algoritmu
  io_loaders.py   # čtení .txt a .wdf, zápis .txt
  batch.py        # dávkové zpracování složky
  gui.py          # desktopové GUI (PySide6)
app.py            # spuštění GUI
cli.py            # dávka z příkazové řádky
```

## Licence

MIT — viz [LICENSE](LICENSE).
