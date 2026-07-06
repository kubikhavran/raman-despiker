# Raman Despiker

Desktopová aplikace pro **dávkové odstranění kosmických spiků a gamma-ray anomálií**
z Ramanových spekter (Renishaw inVia). Vyber složku se spektry, aplikace všechna
projde, odstraní spiky a uloží vyčištěná spektra do `.txt`. Obsahuje **náhled
před/po** s vyznačenými spiky a živě nastavitelnou citlivostí.

- Vstup: `.txt` (dvousloupcový export `x  y`, i s indexovým sloupcem) a `.wdf`
  (nativní formát Renishaw inVia; podporuje i soubory s více spektry / mapy).
- Výstup: `.txt` (dvousloupcový `x  y`, tabulátorem oddělený).

## Jak to funguje (bez zkreslení spektra)

Kosmické spiky jsou úzké (na testovaném přístroji FWHM ≤ ~5 bodů), reálné
Ramanovy pásy širší (FWHM ≥ ~7 bodů) — mezi tím je bezpečná mezera.

### Single-spectrum režim (výchozí, univerzální)

1. **Reziduum od klouzavého mediánu** – odečte hladké pozadí; široké reálné pásy
   zůstanou (malé reziduum), úzký spike vyčnívá (velké reziduum).
2. **Odhad šumu závislý na signálu (model shot-noise)** – šum roste s intenzitou,
   takže ostrá špička silného píku má velký šum (nízké skóre → neoznačí se),
   kdežto spike na pozadí malý šum (vysoké skóre → označí se). Šum se počítá
   z 2. diferencí (necitlivé na sklon → spike se pozná i na hraně píku).
3. **Prahování s hysterezí** – jádro spiku (|z| > práh) se rozšíří na okolí
   (|z| > práh/2), takže se zachytí i širší spike a jeho boky.
4. **Ochrana reálných pásů (max. šířka)** – delší souvislý útvar = reálný pás.
5. **Nahrazení interpolací** – označené body se dopočítají z okolních *čistých*
   bodů; **zbytek spektra zůstává beze změny**.
6. **Iterace** – opakováním se odhalí i menší spiky schované vedle velkých.

### Konsenzuální režim (opt-in, pro OPAKOVANÁ měření téhož vzorku)

Když složka obsahuje více měření téhož vzorku (stejná osa X), spiky se poznají
porovnáním se skupinovým **mediánem** – dopadají náhodně, takže v mediánu nejsou.
Reálné pásy jsou v mediánu obsaženy, proto se nikdy neodstraní. Zapíná se
zaškrtávátkem v GUI (nebo `--consensus` v CLI). **Nepoužívat pro směs různých
vzorků.**

### Ruční doladění

V náhledu lze **levým klikem** odstranit případný zbylý spike a **pravým klikem**
úpravu vrátit; tlačítko *Uložit zobrazené* uloží aktuální (auto + ruční) spektrum.

Metoda vychází z principu Whitaker & Hayes, *A simple algorithm for despiking
Raman spectra*, Chemom. Intell. Lab. Syst. 179 (2018) 82–84, rozšířeného o
měřením podložené šířkové kritérium, signálově závislý model šumu a konsenzus.

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
| Max. šířka spiku | Delší souvislý útvar = reálný pás (nemaže se) | 5 px |
| Iterace | Opakování detekce | 5 |
| Okno mediánu | Okno pro odhad pozadí | 5 px |
| Lokálně adaptivní práh | Signálově závislý model šumu | zapnuto |

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
