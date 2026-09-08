#!/usr/bin/env python3
"""Cache locale dei grafici Datawrapper incorporati nelle pagine.

Uso:
    python3 tools/datawrapper.py            # scarica solo i grafici mancanti
    python3 tools/datawrapper.py --refresh  # riscarica tutto
    python3 tools/datawrapper.py --list     # elenca i grafici trovati nelle pagine

Ogni iframe `https://datawrapper.dwcdn.net/<id>/<versione>/` presente in una
pagina diventa un file `assets/data/grafici/<id>-<versione>.json` con titolo,
introduzione, note, fonte e i dati del grafico (il CSV pubblico, righe come
liste). I file sono committati nel repository: `build.py` legge solo la cache,
così il build normale — anche quello in CI — non ha bisogno della rete.

Endpoint pubblici usati (uno per grafico, solo se il file manca):
    .../<id>/<versione>/embed.json    metadati (titolo, fonte, intro, note)
    .../<id>/<versione>/dataset.csv   i dati

Se il download fallisce lo script lo segnala e va avanti: un grafico senza
cache resta semplicemente senza dati, non blocca il build.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "assets", "data", "grafici")

TIMEOUT = 15
BASE = "https://datawrapper.dwcdn.net"

# gli iframe scrivono sempre l'indirizzo per esteso: id e versione stanno lì
IFRAME_RE = re.compile(r"datawrapper\.dwcdn\.net/([A-Za-z0-9_-]+)/(\d+)/")


def pagine_html():
    """Tutte le pagine del sito, la home per prima."""
    out = [os.path.join(ROOT, "index.html")]
    art_dir = os.path.join(ROOT, "articoli")
    for nome in sorted(os.listdir(art_dir)):
        if nome.endswith(".html"):
            out.append(os.path.join(art_dir, nome))
    return out


def grafici_in(html):
    """[(id, versione), ...] nell'ordine in cui compaiono nella pagina, senza doppioni."""
    visti, out = set(), []
    for cid, ver in IFRAME_RE.findall(html):
        if (cid, ver) not in visti:
            visti.add((cid, ver))
            out.append((cid, ver))
    return out


def grafici_usati():
    """[(id, versione), ...] su tutto il sito, nell'ordine delle pagine."""
    visti, out = set(), []
    for path in pagine_html():
        with open(path, encoding="utf-8") as fh:
            for coppia in grafici_in(fh.read()):
                if coppia not in visti:
                    visti.add(coppia)
                    out.append(coppia)
    return out


def percorso(cid, ver):
    return os.path.join(CACHE, f"{cid}-{ver}.json")


def _leggi(url, timeout):
    richiesta = urllib.request.Request(url, headers={"User-Agent": "CrescitaZero build"})
    with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
        return risposta.read()


def _righe_csv(testo):
    """Il CSV di Datawrapper: quasi sempre virgole, ogni tanto punto e virgola."""
    prima = testo.split("\n", 1)[0]
    delimitatore = ","
    for candidato in (";", "\t"):
        if prima.count(candidato) > prima.count(","):
            delimitatore = candidato
    righe = [r for r in csv.reader(io.StringIO(testo), delimiter=delimitatore) if any(r)]
    return righe


def scarica(cid, ver, timeout=TIMEOUT):
    """Metadati e dati di un grafico. None se la rete o l'endpoint non rispondono."""
    try:
        meta = json.loads(_leggi(f"{BASE}/{cid}/{ver}/embed.json", timeout))
    except (urllib.error.URLError, OSError, ValueError) as errore:
        print(f"ATTENZIONE {cid}-{ver}: embed.json non scaricato ({errore})", file=sys.stderr)
        return None

    chart = meta.get("chart") or {}
    descrivi = (chart.get("metadata") or {}).get("describe") or {}
    annota = (chart.get("metadata") or {}).get("annotate") or {}

    try:
        righe = _righe_csv(_leggi(f"{BASE}/{cid}/{ver}/dataset.csv", timeout).decode("utf-8-sig"))
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as errore:
        print(f"ATTENZIONE {cid}-{ver}: dataset.csv non scaricato ({errore})", file=sys.stderr)
        righe = []

    return {
        "id": cid,
        "version": ver,
        "url": chart.get("publicUrl") or f"{BASE}/{cid}/{ver}/",
        "title": (chart.get("title") or "").strip(),
        "intro": (descrivi.get("intro") or "").strip(),
        "notes": (annota.get("notes") or "").strip(),
        "source_name": (descrivi.get("source-name") or "").strip(),
        "source_url": (descrivi.get("source-url") or "").strip(),
        "byline": (descrivi.get("byline") or "").strip(),
        "type": chart.get("type") or "",
        "data": righe,
    }


def salva(grafico):
    os.makedirs(CACHE, exist_ok=True)
    path = percorso(grafico["id"], grafico["version"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(grafico, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def carica(cid, ver, scarica_se_manca=True, timeout=TIMEOUT):
    """Il grafico dalla cache; se manca lo scarica una volta sola. None se non c'è."""
    path = percorso(cid, ver)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError as errore:
            print(f"ATTENZIONE {cid}-{ver}: cache illeggibile ({errore})", file=sys.stderr)
            return None
    if not scarica_se_manca:
        return None
    grafico = scarica(cid, ver, timeout)
    if grafico is None:
        return None
    salva(grafico)
    print(f"scaricato {os.path.relpath(percorso(cid, ver), ROOT)}")
    return grafico


def aggiorna(refresh=False):
    """Scarica i grafici mancanti (tutti con refresh). Torna quanti ne ha scritti."""
    scritti = 0
    for cid, ver in grafici_usati():
        rel = os.path.relpath(percorso(cid, ver), ROOT)
        if os.path.exists(percorso(cid, ver)) and not refresh:
            print(f"esiste    {rel}")
            continue
        grafico = scarica(cid, ver)
        if grafico is None:
            continue
        salva(grafico)
        scritti += 1
        print(f"scritto   {rel}")
    return scritti


def orfani():
    """Le cache di grafici non più presenti in nessuna pagina."""
    if not os.path.isdir(CACHE):
        return []
    attesi = {f"{cid}-{ver}.json" for cid, ver in grafici_usati()}
    return [n for n in sorted(os.listdir(CACHE)) if n.endswith(".json") and n not in attesi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="riscarica anche i grafici già in cache")
    ap.add_argument("--list", action="store_true", help="elenca i grafici delle pagine senza scaricare")
    ap.add_argument("--prune", action="store_true", help="elimina le cache rimaste orfane")
    args = ap.parse_args()

    if args.list:
        for cid, ver in grafici_usati():
            grafico = carica(cid, ver, scarica_se_manca=False)
            titolo = grafico["title"] if grafico else "(non in cache)"
            print(f"{cid}/{ver}  {titolo}")
        return 0

    if args.prune:
        for nome in orfani():
            os.remove(os.path.join(CACHE, nome))
            print(f"rimosso   assets/data/grafici/{nome}")

    aggiorna(refresh=args.refresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
