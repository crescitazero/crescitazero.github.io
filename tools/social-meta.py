#!/usr/bin/env python3
"""Inserisce (o aggiorna) i meta tag Open Graph e X/Twitter in tutte le pagine.

Uso:
    python3 tools/social-meta.py            # scrive i tag
    python3 tools/social-meta.py --check    # verifica soltanto, exit 1 se manca qualcosa

Il blocco è delimitato da commenti, quindi rilanciare lo script aggiorna i tag
esistenti invece di duplicarli. Titolo, occhiello e description vengono letti
dalla pagina stessa: per una nuova pagina basta rilanciare lo script.
"""

import argparse
import os
import re
import sys
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from og_card import ROOT, page_meta  # noqa: E402

SITE = "https://crescitazero.it"
START = "  <!-- social: generato da tools/social-meta.py -->"
END = "  <!-- /social -->"
BLOCK_RE = re.compile(
    re.escape(START) + r".*?" + re.escape(END) + r"\n", re.S
)


def block(url, title, description, image, og_type, alt):
    e = lambda s: escape(s, quote=True)
    rows = [
        START,
        f'  <link rel="canonical" href="{e(url)}">',
        f'  <meta property="og:type" content="{og_type}">',
        '  <meta property="og:site_name" content="CrescitaZero">',
        '  <meta property="og:locale" content="it_IT">',
        f'  <meta property="og:url" content="{e(url)}">',
        f'  <meta property="og:title" content="{e(title)}">',
        f'  <meta property="og:description" content="{e(description)}">',
        f'  <meta property="og:image" content="{e(image)}">',
        '  <meta property="og:image:type" content="image/png">',
        '  <meta property="og:image:width" content="1200">',
        '  <meta property="og:image:height" content="630">',
        f'  <meta property="og:image:alt" content="{e(alt)}">',
        '  <meta name="twitter:card" content="summary_large_image">',
        f'  <meta name="twitter:title" content="{e(title)}">',
        f'  <meta name="twitter:description" content="{e(description)}">',
        f'  <meta name="twitter:image" content="{e(image)}">',
        f'  <meta name="twitter:image:alt" content="{e(alt)}">',
        END,
    ]
    return "\n".join(rows) + "\n"


def pages():
    """(percorso, url, og:type, immagine social) per ogni pagina del sito."""
    out = [(
        os.path.join(ROOT, "index.html"),
        f"{SITE}/",
        "website",
        f"{SITE}/assets/social/default.png",
    )]
    art_dir = os.path.join(ROOT, "articoli")
    for name in sorted(os.listdir(art_dir)):
        if name.endswith(".html"):
            out.append((
                os.path.join(art_dir, name),
                f"{SITE}/articoli/{name}",
                "article",
                f"{SITE}/assets/social/{name[:-5]}.png",
            ))
    return out


def apply(path, url, og_type, image, check=False):
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    title, _, description = page_meta(path)
    if path.endswith("index.html") and os.path.dirname(path) == ROOT:
        title = "CrescitaZero — Perché l’Italia non cresce più?"
    else:
        title = f"{title} — CrescitaZero"
    alt = f"CrescitaZero — {page_meta(path)[0]}"

    new = block(url, title, description or "", image, og_type, alt)
    cleaned = BLOCK_RE.sub("", html)

    if BLOCK_RE.search(html):
        updated = BLOCK_RE.sub(lambda _: new, html, count=1)
    else:
        anchor = re.search(r'^  <meta name="description".*?>\n', cleaned, re.M | re.S)
        if not anchor:
            raise SystemExit(f"{path}: manca <meta name=\"description\">, non so dove inserire")
        i = anchor.end()
        updated = cleaned[:i] + "\n" + new + cleaned[i:]

    rel = os.path.relpath(path, ROOT)
    if updated == html:
        print(f"ok       {rel}")
        return False
    if check:
        print(f"DA AGGIORNARE {rel}")
        return True
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"scritto  {rel}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="non scrive, segnala solo le differenze")
    args = ap.parse_args()
    changed = [apply(p, u, t, i, check=args.check) for p, u, t, i in pages()]
    if args.check and any(changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
