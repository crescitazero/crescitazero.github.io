#!/usr/bin/env python3
"""Normalizza il <head> e gli script di tutte le pagine di CrescitaZero.

Uso:
    python3 tools/build.py            # genera le card mancanti e scrive i tag
    python3 tools/build.py --check    # verifica soltanto, exit 1 se c'è da aggiornare
    python3 tools/build.py --no-card  # salta la generazione delle card

La pagina HTML resta l'unica fonte di verità: titolo, occhiello, description,
data e autori vengono letti dalla pagina stessa (<title>, <meta name="description">,
<p class="meta">, <p class="byline">) e riversati in un unico blocco delimitato
da commenti nel <head>:

    <!-- build: generato da tools/build.py -->
    ... canonical, og:, twitter:, author, article:*, script di tracciamento ...
    <!-- /build -->

Il blocco è idempotente: rilanciare lo script lo riscrive invece di duplicarlo.
Non modificarlo a mano — cambia la pagina e rilancia.

Lo script fa anche un po' di pulizia, sempre idempotente:
  - migra il vecchio blocco <!-- social --> di tools/social-meta.py;
  - toglie gli script di analytics messi a mano fuori dal blocco (Umami, GA4);
  - toglie gli <script> inline di tracciamento, ora in assets/js/tracking.js
    (gli snippet Datawrapper e il rilascio programmato di 01/02 restano);
  - uniforma il data-article sul <body> allo slug della pagina.
"""

import argparse
import os
import re
import sys
from html import escape, unescape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from og_card import ROOT, page_meta  # noqa: E402

SITE = "https://crescitazero.it"
TITOLO_HOME = "CrescitaZero — Perché l’Italia non cresce più?"

INIZIO = "  <!-- build: generato da tools/build.py -->"
FINE = "  <!-- /build -->"
BLOCCO_RE = re.compile(re.escape(INIZIO) + r".*?" + re.escape(FINE) + r"\n", re.S)

# il blocco che generava il vecchio tools/social-meta.py: va migrato e rimosso
BLOCCO_SOCIAL_RE = re.compile(
    r"  <!-- social: generato da tools/social-meta\.py -->.*?  <!-- /social -->\n", re.S
)

UMAMI = (
    '<script defer src="https://analyticsprogetti.lorenzoruffino.com/script.js" '
    'data-website-id="6a9e05f1-4924-4074-8876-6dde465d52c8" '
    'data-domains="crescitazero.it"></script>'
)
TRACKING = '<script defer src="/assets/js/tracking.js"></script>'

AUTORI_FALLBACK = [
    ("Lorenzo Ruffino", "https://www.lorenzoruffino.it/"),
    ("Elia Bidut", "https://lavoroinfatti.substack.com/"),
]

# script da togliere dalle pagine perché ora stanno nel blocco o in tracking.js
SCRIPT_UMAMI_RE = re.compile(r"[ \t]*<script[^>]*analyticsprogetti[^>]*>\s*</script>\n")
SCRIPT_TRACKING_RE = re.compile(r"[ \t]*<script[^>]*assets/js/tracking\.js[^>]*>\s*</script>\n")
SCRIPT_GTAG_RE = re.compile(r"[ \t]*<script[^>]*googletagmanager\.com/gtag[^>]*>\s*</script>\n")
SCRIPT_INLINE_RE = re.compile(r"[ \t]*<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>\n", re.S)


def slug(path):
    """Nome file senza estensione; la home vale "home"."""
    nome = os.path.basename(path)
    return "home" if nome == "index.html" else nome[:-5]


def pagine():
    """(percorso, url, og:type, immagine social) per ogni pagina del sito."""
    out = [(
        os.path.join(ROOT, "index.html"),
        f"{SITE}/",
        "website",
        f"{SITE}/assets/social/default.png",
    )]
    art_dir = os.path.join(ROOT, "articoli")
    for nome in sorted(os.listdir(art_dir)):
        if nome.endswith(".html"):
            out.append((
                os.path.join(art_dir, nome),
                f"{SITE}/articoli/{nome}",
                "article",
                f"{SITE}/assets/social/{nome[:-5]}.png",
            ))
    return out


def byline(html):
    """(data ISO, [(nome, url), ...]) letti dalla byline della pagina."""
    m = re.search(r'<p class="byline">.*?</p>', html, re.S)
    if not m:
        return None, AUTORI_FALLBACK
    testo = m.group(0)
    data = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})"', testo)
    autori = [
        (unescape(nome).strip(), url)
        for url, nome in re.findall(r'<a href="([^"]+)" rel="author">(.*?)</a>', testo, re.S)
    ]
    return (data.group(1) if data else None), (autori or AUTORI_FALLBACK)


def blocco(url, titolo, description, immagine, og_type, alt, data, autori):
    e = lambda s: escape(s, quote=True)
    firma = ", ".join(nome for nome, _ in autori)
    righe = [
        INIZIO,
        f'  <link rel="canonical" href="{e(url)}">',
        f'  <meta name="author" content="{e(firma)}">',
        f'  <meta property="og:type" content="{og_type}">',
        '  <meta property="og:site_name" content="CrescitaZero">',
        '  <meta property="og:locale" content="it_IT">',
        f'  <meta property="og:url" content="{e(url)}">',
        f'  <meta property="og:title" content="{e(titolo)}">',
        f'  <meta property="og:description" content="{e(description)}">',
        f'  <meta property="og:image" content="{e(immagine)}">',
        '  <meta property="og:image:type" content="image/png">',
        '  <meta property="og:image:width" content="1200">',
        '  <meta property="og:image:height" content="630">',
        f'  <meta property="og:image:alt" content="{e(alt)}">',
    ]
    if og_type == "article":
        if data:
            righe.append(f'  <meta property="article:published_time" content="{data}">')
        for _, indirizzo in autori:
            righe.append(f'  <meta property="article:author" content="{e(indirizzo)}">')
    righe += [
        '  <meta name="twitter:card" content="summary_large_image">',
        f'  <meta name="twitter:title" content="{e(titolo)}">',
        f'  <meta name="twitter:description" content="{e(description)}">',
        f'  <meta name="twitter:image" content="{e(immagine)}">',
        f'  <meta name="twitter:image:alt" content="{e(alt)}">',
        f'  {UMAMI}',
        f'  {TRACKING}',
        FINE,
    ]
    return "\n".join(righe) + "\n"


def pulisci(html):
    """Toglie script di analytics e di tracciamento sparsi per la pagina."""
    html = SCRIPT_UMAMI_RE.sub("", html)
    html = SCRIPT_TRACKING_RE.sub("", html)
    html = SCRIPT_GTAG_RE.sub("", html)

    def scarta_tracciamento(m):
        corpo = m.group(1)
        # lo snippet GA4 e i vecchi script inline con umami.track: ora inutili
        if "umami.track" in corpo:
            return ""
        if "dataLayer" in corpo and "gtag(" in corpo:
            return ""
        return m.group(0)

    html = SCRIPT_INLINE_RE.sub(scarta_tracciamento, html)

    # le rimozioni possono lasciare righe vuote di troppo
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = re.sub(r"\n[ \t]*\n(?=[ \t]*</head>)", "\n", html)
    html = re.sub(r"\n[ \t]*\n(?=[ \t]*</body>)", "\n", html)
    return html


def marca_body(html, nome):
    """Uniforma il data-article del <body> allo slug della pagina."""
    m = re.search(r"<body([^>]*)>", html)
    if not m:
        raise SystemExit("manca il <body>")
    attributi = re.sub(r'\s*data-article="[^"]*"', "", m.group(1))
    return html[:m.start()] + f'<body data-article="{nome}"{attributi}>' + html[m.end():]


def applica(path, url, og_type, immagine, check=False):
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    titolo, _, description = page_meta(path)
    if titolo == "" or description is None:
        raise SystemExit(f"{path}: titolo o description mancanti")
    if slug(path) == "home":
        titolo = TITOLO_HOME
    else:
        titolo = f"{titolo} — CrescitaZero"
    # la card mostra marchio, occhiello e titolo: il titolo stesso la descrive
    alt = titolo

    data, autori = byline(html)
    nuovo = blocco(url, titolo, description, immagine, og_type, alt, data, autori)

    aggiornato = BLOCCO_RE.sub("", BLOCCO_SOCIAL_RE.sub("", html))
    aggiornato = pulisci(aggiornato)
    aggiornato = marca_body(aggiornato, slug(path))

    ancora = re.search(r'^  <meta name="description".*?>\n', aggiornato, re.M | re.S)
    if not ancora:
        raise SystemExit(f'{path}: manca <meta name="description">, non so dove inserire')
    i = ancora.end()
    aggiornato = aggiornato[:i] + "\n" + nuovo + aggiornato[i:]

    rel = os.path.relpath(path, ROOT)
    if aggiornato == html:
        print(f"ok       {rel}")
        return False
    if check:
        print(f"DA AGGIORNARE {rel}")
        return True
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(aggiornato)
    print(f"scritto  {rel}")
    return True


def genera_card():
    """Le card mancanti, con lo stesso codice di og_card.py."""
    import og_card

    print(f"font: {og_card.font_name()}")
    for out_path, titolo, occhiello, sottotitolo in og_card.cards():
        rel = os.path.relpath(out_path, ROOT)
        if os.path.exists(out_path):
            print(f"esiste  {rel}")
            continue
        og_card.make_card(titolo, occhiello, out_path, sottotitolo)
        print(f"scritto {rel}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="non scrive, segnala solo le differenze")
    ap.add_argument("--no-card", action="store_true", help="non generare le card social")
    args = ap.parse_args()

    if not args.check and not args.no_card:
        genera_card()

    cambiate = [applica(p, u, t, i, check=args.check) for p, u, t, i in pagine()]
    if args.check and any(cambiate):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
