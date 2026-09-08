#!/usr/bin/env python3
"""Genera tutto quello che le pagine di CrescitaZero non contengono a mano.

Uso:
    python3 tools/build.py            # card mancanti, <head>, navigazione, file generati
    python3 tools/build.py --check    # verifica soltanto, exit 1 se c'è da aggiornare
    python3 tools/build.py --no-card  # salta la generazione delle card

La pagina HTML resta l'unica fonte di verità: titolo, occhiello, description,
data, autori e tempo di lettura vengono letti dalla pagina stessa (<title>,
<meta name="description">, <p class="meta">, <p class="byline">). Da lì
discende tutto il resto.

Dentro le pagine lo script scrive tre blocchi delimitati, tutti idempotenti
(rilanciarlo li riscrive invece di duplicarli — non modificarli a mano):

    <!-- build: ... -->  … </>   nel <head>: canonical, robots, alternate,
                                 og:, twitter:, JSON-LD, script di tracciamento
    /* build:nav */      … </>   nel <style>: lo stile della navigazione di serie
    <!-- build:nav -->   … </>   in fondo all'articolo: precedente / successivo

Fuori dalle pagine genera:

    articoli/<slug>.md    il gemello Markdown di ogni articolo
    robots.txt            crawler dei motori e degli assistenti: tutti ammessi
    sitemap.xml           home e articoli, lastmod = data di pubblicazione
    feed.xml              RSS 2.0 con il testo completo in content:encoded
    articoli.json         indice leggibile da una macchina
    llms.txt              guida sintetica per i modelli linguistici
    llms-full.txt         tutti gli articoli in Markdown in un file solo

I dati dei grafici arrivano dalla cache di tools/datawrapper.py
(assets/data/grafici/*.json), scaricata una volta e committata: il build
normale non ha bisogno della rete.

Lo script fa anche un po' di pulizia, sempre idempotente:
  - migra il vecchio blocco <!-- social --> di tools/social-meta.py;
  - toglie gli script di analytics messi a mano fuori dal blocco (Umami, GA4);
  - toglie gli <script> inline di tracciamento, ora in assets/js/tracking.js
    (gli snippet Datawrapper e il rilascio programmato di 01/02 restano);
  - uniforma il data-article sul <body> allo slug della pagina;
  - mette agli iframe Datawrapper il titolo vero del grafico.
"""

import argparse
import calendar
import json
import os
import re
import sys
from datetime import date, timedelta
from html import escape, unescape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datawrapper  # noqa: E402
import md  # noqa: E402
from og_card import ROOT, page_meta  # noqa: E402

SITE = "https://crescitazero.it"
TITOLO_HOME = "CrescitaZero — Perché l’Italia non cresce più?"
SERIE = "CrescitaZero"

INIZIO = "  <!-- build: generato da tools/build.py -->"
FINE = "  <!-- /build -->"
BLOCCO_RE = re.compile(re.escape(INIZIO) + r".*?" + re.escape(FINE) + r"\n", re.S)

# il blocco che generava il vecchio tools/social-meta.py: va migrato e rimosso
BLOCCO_SOCIAL_RE = re.compile(
    r"  <!-- social: generato da tools/social-meta\.py -->.*?  <!-- /social -->\n", re.S
)

NAV_INIZIO = "    <!-- build:nav -->"
NAV_FINE = "    <!-- /build:nav -->"
NAV_RE = re.compile(r"[ \t]*<!-- build:nav -->.*?<!-- /build:nav -->\n", re.S)

CSS_INIZIO = "    /* build:nav */"
CSS_FINE = "    /* /build:nav */"
CSS_RE = re.compile(r"[ \t]*/\* build:nav \*/.*?/\* /build:nav \*/\n", re.S)

ELENCO_INIZIO = "    <!-- build:elenco -->"
ELENCO_FINE = "    <!-- /build:elenco -->"
ELENCO_RE = re.compile(r"[ \t]*<!-- build:elenco -->.*?<!-- /build:elenco -->\n", re.S)

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

LOGO = f"{SITE}/assets/social/default.png"

# llms.txt deve restare una guida, non un archivio: oltre questa soglia le
# description degli articoli si riducono alla prima frase
LIMITE_LLMS = 5120

# script da togliere dalle pagine perché ora stanno nel blocco o in tracking.js
SCRIPT_UMAMI_RE = re.compile(r"[ \t]*<script[^>]*analyticsprogetti[^>]*>\s*</script>\n")
SCRIPT_TRACKING_RE = re.compile(r"[ \t]*<script[^>]*assets/js/tracking\.js[^>]*>\s*</script>\n")
SCRIPT_GTAG_RE = re.compile(r"[ \t]*<script[^>]*googletagmanager\.com/gtag[^>]*>\s*</script>\n")
SCRIPT_INLINE_RE = re.compile(r"[ \t]*<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>\n", re.S)

# i titoli che gli iframe hanno di default: si sostituiscono con quello vero
TITOLI_GENERICI = {"", "Grafico", "Grafico CrescitaZero"}

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
GIORNI_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MESI_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# i crawler dichiarati uno per uno in robots.txt: quelli degli assistenti sono
# i benvenuti quanto quelli dei motori, è una scelta di chi pubblica il sito
CRAWLER = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "ClaudeBot", "Claude-SearchBot", "Claude-User", "anthropic-ai",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Googlebot", "Bingbot", "Applebot", "Applebot-Extended",
    "Meta-ExternalAgent", "Amazonbot", "CCBot", "DuckAssistBot",
    "MistralAI-User", "cohere-ai", "YouBot",
]


# --- lettura delle pagine ---------------------------------------------------


def slug(path):
    """Nome file senza estensione; la home vale "home"."""
    nome = os.path.basename(path)
    return "home" if nome == "index.html" else nome[:-5]


def elenco_pagine():
    """(percorso, url, tipo, immagine social) per ogni pagina del sito."""
    out = [(
        os.path.join(ROOT, "index.html"),
        f"{SITE}/",
        "home",
        LOGO,
    )]
    art_dir = os.path.join(ROOT, "articoli")
    for nome in sorted(os.listdir(art_dir)):
        if nome.endswith(".html"):
            out.append((
                os.path.join(art_dir, nome),
                f"{SITE}/articoli/{nome}",
                "articolo",
                f"{SITE}/assets/social/{nome[:-5]}.png",
            ))
    out.append((os.path.join(ROOT, "404.html"), f"{SITE}/404.html", "404", LOGO))
    return out


def byline(html):
    """(data ISO, data leggibile, minuti di lettura, [(nome, url), ...])."""
    m = re.search(r'<p class="byline">.*?</p>', html, re.S)
    if not m:
        return None, "", None, AUTORI_FALLBACK
    testo = m.group(0)
    iso = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})"[^>]*>(.*?)</time>', testo, re.S)
    lettura = re.search(r'<span class="byline-reading">\s*(\d+)', testo)
    autori = [
        (unescape(nome).strip(), url)
        for url, nome in re.findall(r'<a href="([^"]+)" rel="author">(.*?)</a>', testo, re.S)
    ]
    return (
        iso.group(1) if iso else None,
        unescape(iso.group(2)).strip() if iso else "",
        int(lettura.group(1)) if lettura else None,
        autori or AUTORI_FALLBACK,
    )


def contenuto_articolo(html):
    """L'HTML dentro <article> (o dentro <main> se l'articolo non ce l'ha)."""
    m = re.search(r"<article\b[^>]*>(.*)</article>", html, re.S)
    if m:
        return m.group(1)
    m = re.search(r"<main\b[^>]*>(.*)</main>", html, re.S)
    return m.group(1) if m else ""


def salta_testata(nodo):
    """Occhiello, titolo e byline stanno già nel front matter: nel corpo no."""
    classi = nodo.classe().split()
    if nodo.tag == "h1":
        return True
    if nodo.tag == "p" and ("meta" in classi or "byline" in classi):
        return True
    if nodo.tag == "nav" and "series-nav" in classi:
        return True
    return False


def titolo_grafico(grafico):
    """Il titolo del grafico. Il « (Copy) » che resta dai duplicati in Datawrapper
    è un residuo dell'editor, non un titolo: via."""
    titolo = md.senza_tag(grafico.get("title"))
    return re.sub(r"\s*\((?:Copy|copia)\)$", "", titolo).strip()


class Pagina:
    def __init__(self, path, url, tipo, immagine, html, grafici):
        self.path = path
        self.url = url
        self.tipo = tipo
        self.immagine = immagine
        self.html = html
        self.slug = slug(path)
        self.rel = os.path.relpath(path, ROOT)

        titolo, occhiello, descrizione = page_meta(path)
        if titolo == "" or descrizione is None:
            raise SystemExit(f"{path}: titolo o description mancanti")
        self.titolo = titolo
        self.occhiello = occhiello
        self.descrizione = descrizione
        self.titolo_pieno = TITOLO_HOME if self.slug == "home" else f"{titolo} — CrescitaZero"

        self.data, self.data_leggibile, self.lettura, self.autori = byline(html)
        self.grafici = [
            grafici[f"{cid}/{ver}"]
            for cid, ver in datawrapper.grafici_in(html)
            if f"{cid}/{ver}" in grafici
        ]

        self.corpo_md = ""
        self.testo = ""
        self.parole = 0
        self.corpo_html = ""
        if self.tipo == "articolo":
            mappa = {f"{g['id']}/{g['version']}": g for g in self.grafici}
            interno = contenuto_articolo(NAV_RE.sub("", html))
            self.corpo_md, self.testo = md.converti(interno, url, mappa, salta_testata)
            self.parole = len(self.testo.split())
            self.corpo_html = md.html_pulito(interno, url, mappa, salta_testata)
        if not self.lettura and self.parole:
            self.lettura = max(1, round(self.parole / 200))

    @property
    def slug_md(self):
        return f"{SITE}/articoli/{self.slug}.md"

    @property
    def path_md(self):
        return os.path.join(ROOT, "articoli", f"{self.slug}.md")

    def firma(self):
        nomi = [nome for nome, _ in self.autori]
        if len(nomi) > 1:
            return ", ".join(nomi[:-1]) + " e " + nomi[-1]
        return nomi[0] if nomi else ""


def raccogli():
    """Tutte le pagine, con i dati dei grafici già risolti dalla cache."""
    grafici = {}
    for cid, ver in datawrapper.grafici_usati():
        grafico = datawrapper.carica(cid, ver)
        if grafico is None:
            print(f"ATTENZIONE grafico {cid}/{ver} senza dati: la pagina resta com'è", file=sys.stderr)
            continue
        grafico["title"] = titolo_grafico(grafico)
        grafici[f"{cid}/{ver}"] = grafico

    pagine = []
    for path, url, tipo, immagine in elenco_pagine():
        with open(path, encoding="utf-8") as fh:
            pagine.append(Pagina(path, url, tipo, immagine, fh.read(), grafici))
    return pagine


def articoli(pagine):
    """Gli articoli in ordine di episodio, cioè di data crescente."""
    return sorted(
        (p for p in pagine if p.tipo == "articolo"),
        key=lambda p: (p.data or "", p.slug),
    )


# --- JSON-LD ----------------------------------------------------------------


def persone_sito(html_home):
    """Nome e link degli autori, letti dalla sezione Autori della home."""
    out = []
    fallback = dict(AUTORI_FALLBACK)
    for m in re.finditer(r'<article class="author">(.*?)</article>', html_home, re.S):
        blocco = m.group(1)
        nome = re.search(r"<h3>(.*?)</h3>", blocco, re.S)
        if not nome:
            continue
        nome = unescape(nome.group(1)).strip()
        link, visti = [], set()
        for indirizzo in re.findall(r'<a href="([^"]+)"', blocco):
            pulito = unescape(indirizzo).split("?")[0]
            if pulito not in visti:
                visti.add(pulito)
                link.append(pulito)
        principale = fallback.get(nome) or (link[0] if link else "")
        out.append({
            "name": nome,
            "url": principale,
            "sameAs": [u for u in link if u.rstrip("/") != principale.rstrip("/")],
        })
    return out


def handle_x(persone, nome):
    """L'handle X (@nome) di un autore, dal link x.com nella sezione Autori."""
    for p in persone:
        if p["name"] != nome:
            continue
        for u in p.get("sameAs", []):
            m = re.match(r"https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/?$", u)
            if m:
                return "@" + m.group(1)
    return ""


def persona(nome, url, sameAs=None):
    p = {"@type": "Person", "name": nome}
    if url:
        p["url"] = url
    if sameAs:
        p["sameAs"] = sameAs
    return p


def organizzazione(con_id=False):
    org = {"@type": "Organization"}
    if con_id:
        org["@id"] = f"{SITE}/#organization"
    org.update({"name": SERIE, "url": f"{SITE}/", "logo": LOGO})
    org["sameAs"] = [url for _, url in AUTORI_FALLBACK]
    return org


def grafo(pagina, persone):
    """Il @graph JSON-LD della pagina."""
    if pagina.tipo == "home":
        sito = {
            "@type": "WebSite",
            "@id": f"{SITE}/#website",
            "name": SERIE,
            "url": f"{SITE}/",
            "description": pagina.descrizione,
            "inLanguage": "it",
            "publisher": {"@id": f"{SITE}/#organization"},
        }
        nodi = [sito, organizzazione(con_id=True)]
        nodi += [persona(p["name"], p["url"], p["sameAs"]) for p in persone]
        return nodi

    if pagina.tipo == "404":
        return [{
            "@type": "WebPage",
            "@id": f"{pagina.url}#webpage",
            "name": pagina.titolo,
            "url": pagina.url,
            "description": pagina.descrizione,
            "inLanguage": "it",
            "isPartOf": {"@type": "WebSite", "name": SERIE, "url": f"{SITE}/"},
        }]

    articolo = {
        "@type": "Article",
        "@id": f"{pagina.url}#article",
        "headline": pagina.titolo,
        "description": pagina.descrizione,
        "image": pagina.immagine,
        "datePublished": pagina.data,
        # non abbiamo una data di revisione affidabile: vale quella di pubblicazione
        "dateModified": pagina.data,
        "inLanguage": "it",
        "wordCount": pagina.parole,
        "articleSection": pagina.occhiello,
        "isPartOf": {"@type": "CreativeWorkSeries", "name": SERIE, "url": f"{SITE}/"},
        "author": [persona(nome, url) for nome, url in pagina.autori],
        "publisher": organizzazione(),
        "mainEntityOfPage": pagina.url,
    }
    briciole = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Articoli", "item": f"{SITE}/#articoli"},
            {"@type": "ListItem", "position": 3, "name": pagina.titolo, "item": pagina.url},
        ],
    }
    return [articolo, briciole]


def jsonld(pagina, persone):
    dati = {"@context": "https://schema.org", "@graph": grafo(pagina, persone)}
    testo = json.dumps(dati, ensure_ascii=False, indent=2)
    # dentro uno <script> la sequenza </ chiuderebbe il tag in anticipo
    testo = testo.replace("</", "<\\/")
    righe = ["  " + r if r else r for r in testo.split("\n")]
    return ['  <script type="application/ld+json">'] + righe + ["  </script>"]


# --- blocco del <head> ------------------------------------------------------


def blocco(pagina, persone):
    e = lambda s: escape(s, quote=True)
    righe = [INIZIO, f'  <link rel="canonical" href="{e(pagina.url)}">']

    if pagina.tipo == "404":
        righe.append('  <meta name="robots" content="noindex, follow">')
    else:
        righe.append(
            '  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">'
        )
    righe.append(f'  <meta name="author" content="{e(", ".join(n for n, _ in pagina.autori))}">')
    righe.append(
        f'  <link rel="alternate" type="application/rss+xml" title="{SERIE}" href="{SITE}/feed.xml">'
    )
    if pagina.tipo == "articolo":
        righe.append(f'  <link rel="alternate" type="text/markdown" href="{pagina.slug_md}">')
    righe.append(f'  <link rel="describedby" type="text/markdown" href="{SITE}/llms.txt">')
    righe.append(f'  <link rel="apple-touch-icon" href="{SITE}/favicon.png">')

    if pagina.tipo != "404":
        og_type = "article" if pagina.tipo == "articolo" else "website"
        righe += [
            f'  <meta property="og:type" content="{og_type}">',
            f'  <meta property="og:site_name" content="{SERIE}">',
            '  <meta property="og:locale" content="it_IT">',
            f'  <meta property="og:url" content="{e(pagina.url)}">',
            f'  <meta property="og:title" content="{e(pagina.titolo_pieno)}">',
            f'  <meta property="og:description" content="{e(pagina.descrizione)}">',
            f'  <meta property="og:image" content="{e(pagina.immagine)}">',
            '  <meta property="og:image:type" content="image/png">',
            '  <meta property="og:image:width" content="1200">',
            '  <meta property="og:image:height" content="630">',
            f'  <meta property="og:image:alt" content="{e(pagina.titolo_pieno)}">',
        ]
        if pagina.tipo == "articolo":
            if pagina.data:
                righe.append(f'  <meta property="article:published_time" content="{pagina.data}">')
                righe.append(f'  <meta property="article:modified_time" content="{pagina.data}">')
            for _, indirizzo in pagina.autori:
                righe.append(f'  <meta property="article:author" content="{e(indirizzo)}">')
        righe += [
            '  <meta name="twitter:card" content="summary_large_image">',
            f'  <meta name="twitter:title" content="{e(pagina.titolo_pieno)}">',
            f'  <meta name="twitter:description" content="{e(pagina.descrizione)}">',
            f'  <meta name="twitter:image" content="{e(pagina.immagine)}">',
            f'  <meta name="twitter:image:alt" content="{e(pagina.titolo_pieno)}">',
        ]
        # X accetta un solo creator: il primo autore. Gli altri stanno nel JSON-LD.
        handle = handle_x(persone, pagina.autori[0][0] if pagina.autori else "")
        if handle:
            righe.append(f'  <meta name="twitter:creator" content="{e(handle)}">')

    righe += jsonld(pagina, persone)
    righe += [f"  {UMAMI}", f"  {TRACKING}", FINE]
    return "\n".join(righe) + "\n"


# --- navigazione tra episodi ------------------------------------------------


CSS_NAV = """\
    .series-nav { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 44px 0 8px; }
    .series-nav-item { display: block; padding: 16px 18px; border: 1px solid var(--line); }
    .series-nav-item:hover { border-color: var(--accent); }
    .series-nav-next { grid-column: 2; text-align: right; }
    .series-nav-verso { display: block; color: var(--muted); font-size: 0.78rem; font-weight: 850; letter-spacing: 0.08em; text-transform: uppercase; }
    .series-nav-titolo { display: block; margin-top: 6px; font-weight: 700; line-height: 1.35; letter-spacing: -0.02em; }
    @media (max-width: 560px) { .series-nav { grid-template-columns: 1fr; } .series-nav-next { grid-column: 1; text-align: left; } }
"""


def css_nav():
    return CSS_INIZIO + "\n" + CSS_NAV + CSS_FINE + "\n"


def blocco_nav(precedente, successivo):
    """La navigazione «articolo precedente / successivo» in fondo all'articolo."""
    if precedente is None and successivo is None:
        return ""
    righe = [
        NAV_INIZIO,
        '    <nav class="series-nav" aria-label="Altri articoli della serie">',
    ]
    for verso, etichetta, pagina in (
        ("prev", "← Articolo precedente", precedente),
        ("next", "Articolo successivo →", successivo),
    ):
        if pagina is None:
            continue
        righe += [
            f'      <a class="series-nav-item series-nav-{verso}" href="{pagina.slug}.html"'
            f' data-umami-event="series_nav_click" data-umami-event-direction="{verso}">',
            f'        <span class="series-nav-verso">{etichetta}</span>',
            f'        <span class="series-nav-titolo">{escape(pagina.titolo)}</span>',
            "      </a>",
        ]
    righe += ["    </nav>", NAV_FINE]
    return "\n".join(righe) + "\n"


# --- elenco degli articoli nella 404 ----------------------------------------


def blocco_elenco(recenti):
    righe = [ELENCO_INIZIO, '    <nav class="elenco" aria-label="Tutti gli articoli">']
    for pagina in recenti:
        occhiello = escape(pagina.occhiello)
        if pagina.data_leggibile:
            occhiello += f" · {escape(pagina.data_leggibile)}"
        righe += [
            f'      <a href="/articoli/{pagina.slug}.html">',
            f'        <span class="elenco-kicker">{occhiello}</span>',
            f'        <span class="elenco-titolo">{escape(pagina.titolo)}</span>',
            "      </a>",
        ]
    righe += ["    </nav>", ELENCO_FINE]
    return "\n".join(righe) + "\n"


# --- pulizia e scrittura delle pagine ---------------------------------------


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


def titola_iframe(html, grafici):
    """Dà agli iframe Datawrapper il titolo vero del grafico.

    Tocca solo i titoli mancanti o generici: quelli già scritti a mano nella
    pagina restano, e un titolo già uguale non viene riscritto."""
    mappa = {f"{g['id']}/{g['version']}": g for g in grafici}

    def sostituisci(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]*)"', tag)
        chiave = md.DATAWRAPPER_RE.search(src.group(1)) if src else None
        if not chiave:
            return tag
        grafico = mappa.get(f"{chiave.group(1)}/{chiave.group(2)}")
        if not grafico or not grafico["title"]:
            return tag
        nuovo = escape(grafico["title"], quote=True)
        attuale = re.search(r'\btitle="([^"]*)"', tag)
        if attuale is None:
            return tag[:len("<iframe")] + f' title="{nuovo}"' + tag[len("<iframe"):]
        if unescape(attuale.group(1)).strip() not in TITOLI_GENERICI:
            return tag
        return tag[:attuale.start(1)] + nuovo + tag[attuale.end(1):]

    return re.sub(r"<iframe\b[^>]*>", sostituisci, html)


def marca_elenco_home(html):
    """Numera i link agli articoli nella lista della home per il tracciamento.

    Ogni <a href="articoli/<slug>.html"> dentro la sezione #articoli riceve
    data-umami-event="article_open", lo slug e la posizione nella lista
    (1 = il più in alto). Così un nuovo articolo in cima rinumera gli altri da
    solo, senza che nessuno debba ritoccare gli attributi a mano."""
    m = re.search(r'<section[^>]*\bid="articoli"[^>]*>.*?</section>', html, re.S)
    if not m:
        return html
    sezione = m.group(0)
    contatore = [0]

    def sostituisci(tag):
        link = tag.group(0)
        href = re.search(r'href="articoli/([^"/]+)\.html"', link)
        if not href:
            return link
        contatore[0] += 1
        link = re.sub(r'\s+data-umami-event(?:-[a-z]+)?="[^"]*"', "", link)
        attributi = (
            f' data-umami-event="article_open"'
            f' data-umami-event-article="{href.group(1)}"'
            f' data-umami-event-position="{contatore[0]}"'
        )
        # gli attributi vanno subito dopo l'href, prima di eventuali altri
        return link[:href.end()] + attributi + link[href.end():]

    nuova = re.sub(r"<a\b[^>]*>", sostituisci, sezione)
    return html[:m.start()] + nuova + html[m.end():]


def inserisci(html, testo, dopo_re, errore):
    """Infila un blocco subito dopo la prima riga che combacia."""
    m = re.search(dopo_re, html, re.M | re.S)
    if not m:
        raise SystemExit(errore)
    return html[:m.end()] + testo + html[m.end():]


def applica(pagina, precedente, successivo, persone, recenti, check=False):
    html = pagina.html

    aggiornato = BLOCCO_RE.sub("", BLOCCO_SOCIAL_RE.sub("", html))
    aggiornato = NAV_RE.sub("", CSS_RE.sub("", ELENCO_RE.sub("", aggiornato)))
    aggiornato = pulisci(aggiornato)
    aggiornato = marca_body(aggiornato, pagina.slug)
    aggiornato = titola_iframe(aggiornato, pagina.grafici)
    if pagina.slug == "home":
        aggiornato = marca_elenco_home(aggiornato)

    aggiornato = inserisci(
        aggiornato,
        "\n" + blocco(pagina, persone),
        r'^  <meta name="description".*?>\n',
        f'{pagina.path}: manca <meta name="description">, non so dove inserire',
    )

    if pagina.tipo == "articolo":
        nav = blocco_nav(precedente, successivo)
        if nav:
            # lo stile va in fondo al <style>, la navigazione dopo l'articolo
            m = re.search(r"^[ \t]*</style>", aggiornato, re.M)
            if not m:
                raise SystemExit(f"{pagina.path}: manca il <style>, non so dove mettere il CSS")
            aggiornato = aggiornato[:m.start()] + css_nav() + aggiornato[m.start():]
            i = aggiornato.rfind("</article>")
            if i == -1:
                m = re.search(r"^[ \t]*</main>", aggiornato, re.M)
                if not m:
                    raise SystemExit(f"{pagina.path}: non so dove mettere la navigazione")
                inizio = m.start()
            else:
                inizio = aggiornato.index("\n", i) + 1
            aggiornato = aggiornato[:inizio] + nav + aggiornato[inizio:]

    if pagina.tipo == "404":
        aggiornato = inserisci(
            aggiornato,
            blocco_elenco(recenti),
            r"^[ \t]*<h2>Tutti gli articoli</h2>\n",
            f"{pagina.path}: manca il titolo «Tutti gli articoli»",
        )

    return scrivi(pagina.path, aggiornato, check)


# --- file generati ----------------------------------------------------------


def scrivi(path, contenuto, check):
    """Scrive solo se cambia qualcosa. True se il file è (o sarebbe) da aggiornare."""
    rel = os.path.relpath(path, ROOT)
    esistente = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            esistente = fh.read()
    if esistente == contenuto:
        print(f"ok       {rel}")
        return False
    if check:
        print(f"DA AGGIORNARE {rel}")
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(contenuto)
    print(f"scritto  {rel}")
    return True


def virgolette(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def markdown_articolo(pagina):
    """Il gemello Markdown di un articolo, front matter compreso."""
    testa = [
        "---",
        f"title: {virgolette(pagina.titolo)}",
        f"description: {virgolette(pagina.descrizione)}",
        "authors: [" + ", ".join(virgolette(n) for n, _ in pagina.autori) + "]",
        f"date: {pagina.data}",
        f"canonical: {pagina.url}",
        f"series: {SERIE}",
        "---",
        "",
        f"# {pagina.titolo}",
        "",
    ]
    pezzi = []
    if pagina.occhiello:
        pezzi.append(f"*{pagina.occhiello}*")
    if pagina.autori:
        pezzi.append(f"di {pagina.firma()}")
    if pagina.data_leggibile:
        pezzi.append(pagina.data_leggibile)
    if pagina.lettura:
        pezzi.append(f"{pagina.lettura} min di lettura")
    testa.append(" · ".join(pezzi))

    coda = (
        "---\n"
        f"Questo testo è la versione Markdown di {pagina.url}. "
        f"Serie {SERIE} di Lorenzo Ruffino ed Elia Bidut. "
        "Puoi citarlo liberamente indicando la fonte."
    )
    return "\n".join(testa) + "\n\n" + pagina.corpo_md + "\n\n" + coda + "\n"


def robots():
    righe = [
        f"# {SERIE} — {SITE}",
        "# Tutti i crawler sono ammessi, quelli degli assistenti come quelli dei motori.",
        f"# Una guida ai contenuti pensata per i modelli linguistici: {SITE}/llms.txt",
        "",
        "User-agent: *",
        "Allow: /",
    ]
    for nome in CRAWLER:
        righe += ["", f"User-agent: {nome}", "Allow: /"]
    righe += ["", f"Sitemap: {SITE}/sitemap.xml", ""]
    return "\n".join(righe)


def sitemap(elenco, ultima):
    righe = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{SITE}/</loc>",
        f"    <lastmod>{ultima}</lastmod>",
        "  </url>",
    ]
    for pagina in elenco:
        righe += [
            "  <url>",
            f"    <loc>{pagina.url}</loc>",
            f"    <lastmod>{pagina.data}</lastmod>",
            "  </url>",
        ]
    righe += ["</urlset>", ""]
    return "\n".join(righe)


def ultima_domenica(anno, mese):
    giorno = date(anno, mese, calendar.monthrange(anno, mese)[1])
    return giorno - timedelta(days=(giorno.weekday() + 1) % 7)


def fuso(giorno):
    """L'ora legale italiana: dall'ultima domenica di marzo a quella di ottobre."""
    if ultima_domenica(giorno.year, 3) <= giorno < ultima_domenica(giorno.year, 10):
        return "+0200"
    return "+0100"


def rfc822(iso):
    """La data di pubblicazione, a mezzogiorno di Roma, come la vuole RSS."""
    giorno = date(*(int(p) for p in iso.split("-")))
    return (
        f"{GIORNI_EN[giorno.weekday()]}, {giorno.day:02d} {MESI_EN[giorno.month - 1]} "
        f"{giorno.year} 12:00:00 {fuso(giorno)}"
    )


def feed(elenco, descrizione):
    e = lambda s: escape(s, quote=False)
    ultima = rfc822(elenco[0].data) if elenco else rfc822(date.today().isoformat())
    righe = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        "  <channel>",
        f"    <title>{SERIE}</title>",
        f"    <link>{SITE}/</link>",
        f'    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>',
        f"    <description>{e(descrizione)}</description>",
        "    <language>it</language>",
        f"    <lastBuildDate>{ultima}</lastBuildDate>",
    ]
    for pagina in elenco:
        contenuto = pagina.corpo_html.replace("]]>", "]]&gt;")
        righe += [
            "    <item>",
            f"      <title>{e(pagina.titolo)}</title>",
            f"      <link>{pagina.url}</link>",
            f'      <guid isPermaLink="true">{pagina.url}</guid>',
            f"      <pubDate>{rfc822(pagina.data)}</pubDate>",
        ]
        for nome, _ in pagina.autori:
            righe.append(f"      <dc:creator>{e(nome)}</dc:creator>")
        righe += [
            f"      <category>{e(pagina.occhiello)}</category>",
            f"      <description>{e(pagina.descrizione)}</description>",
            f"      <content:encoded><![CDATA[{contenuto}]]></content:encoded>",
            "    </item>",
        ]
    righe += ["  </channel>", "</rss>", ""]
    return "\n".join(righe)


def indice(elenco, descrizione):
    dati = {
        "site": {
            "name": SERIE,
            "url": f"{SITE}/",
            "description": descrizione,
            "feed": f"{SITE}/feed.xml",
            "sitemap": f"{SITE}/sitemap.xml",
            "llms": f"{SITE}/llms.txt",
        },
        "articles": [],
    }
    for pagina in elenco:
        dati["articles"].append({
            "slug": pagina.slug,
            "title": pagina.titolo,
            "description": pagina.descrizione,
            "kicker": pagina.occhiello,
            "date": pagina.data,
            "authors": [{"name": n, "url": u} for n, u in pagina.autori],
            "url": pagina.url,
            "url_md": pagina.slug_md,
            "image": pagina.immagine,
            "reading_minutes": pagina.lettura,
            "word_count": pagina.parole,
            "charts": [
                {
                    "id": g["id"],
                    "version": g["version"],
                    "title": g["title"],
                    "source": g["source_name"],
                    "url": g["url"],
                    "csv_url": g["url"].rstrip("/") + "/dataset.csv",
                }
                for g in pagina.grafici
            ],
        })
    return json.dumps(dati, ensure_ascii=False, indent=2) + "\n"


def intestazione_llms():
    return f"""# {SERIE}

> {SERIE} è un progetto divulgativo gratuito di Lorenzo Ruffino ed Elia Bidut che
> prova a rispondere con i dati a una domanda sola: perché l'Italia non cresce più.
> Ogni episodio prende un pezzo del problema — produttività, salari, dimensione
> delle imprese, competenze, management, ruolo dello Stato — e lo ricostruisce a
> partire da fonti pubbliche (Istat, Eurostat, OCSE) e da grafici con i dati
> scaricabili. I contenuti sono liberamente citabili indicando la fonte con un
> link alla pagina originale.

Il metodo è dichiarato: si parte dai dati delle istituzioni ufficiali, si
limitano le opinioni e si rendono trasparenti fonti e metodologie. Lorenzo
Ruffino si occupa di analisi dati e data journalism; Elia Bidut, dalla
newsletter Lavoro Infatti, di lavoro, salari e produttività. Di ogni articolo
esiste la versione Markdown allo stesso indirizzo con estensione .md, pensata
per la lettura automatica.
"""


def prima_frase(testo):
    m = re.match(r"(.+?[.!?])(?:\s|$)", testo)
    return m.group(1) if m else testo


def llms(elenco):
    """La guida per i modelli. Se supera i 5 KB le description si accorciano."""
    testo = _llms(elenco, corte=False)
    if len(testo.encode("utf-8")) > LIMITE_LLMS:
        testo = _llms(elenco, corte=True)
    return testo


def _llms(elenco, corte):
    righe = [intestazione_llms(), "## Articoli", ""]
    for pagina in elenco:
        descrizione = prima_frase(pagina.descrizione) if corte else pagina.descrizione
        righe.append(f"- [{pagina.titolo}]({pagina.slug_md}): {descrizione}")
    righe += [
        "",
        "## Dati e formati",
        "",
        f"- [feed.xml]({SITE}/feed.xml): RSS con il testo completo di ogni articolo.",
        f"- [sitemap.xml]({SITE}/sitemap.xml): tutte le pagine con la data di pubblicazione.",
        f"- [articoli.json]({SITE}/articoli.json): indice degli articoli con autori, "
        "conteggio parole e grafici usati.",
        f"- [llms-full.txt]({SITE}/llms-full.txt): tutti gli articoli in Markdown in un file solo.",
        f"- [Dati dei grafici]({SITE}/assets/data/grafici/): un JSON per grafico con titolo, "
        "fonte, note e righe del CSV; i CSV originali stanno su datawrapper.dwcdn.net.",
        "",
        "## Autori",
        "",
        "- [Lorenzo Ruffino](https://www.lorenzoruffino.it/): newsletter di analisi dati "
        "su demografia, economia e politica italiana.",
        "- [Elia Bidut](https://lavoroinfatti.substack.com/): newsletter Lavoro Infatti, "
        "su lavoro, salari e produttività.",
        "",
    ]
    return "\n".join(righe)


def llms_full(elenco):
    pezzi = [intestazione_llms().rstrip("\n")]
    pezzi += [markdown_articolo(p).strip() for p in elenco]
    return "\n\n---\n\n".join(pezzi) + "\n"


# --- orchestrazione ---------------------------------------------------------


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

    pagine = raccogli()
    home = next(p for p in pagine if p.tipo == "home")
    persone = persone_sito(home.html)
    episodi = articoli(pagine)
    recenti = list(reversed(episodi))

    cambiate = []
    for pagina in pagine:
        precedente = successivo = None
        if pagina.tipo == "articolo":
            i = episodi.index(pagina)
            precedente = episodi[i - 1] if i > 0 else None
            successivo = episodi[i + 1] if i < len(episodi) - 1 else None
        cambiate.append(applica(pagina, precedente, successivo, persone, recenti, args.check))

    for pagina in episodi:
        cambiate.append(scrivi(pagina.path_md, markdown_articolo(pagina), args.check))

    ultima = recenti[0].data if recenti else date.today().isoformat()
    cambiate.append(scrivi(os.path.join(ROOT, "robots.txt"), robots(), args.check))
    cambiate.append(scrivi(os.path.join(ROOT, "sitemap.xml"), sitemap(recenti, ultima), args.check))
    cambiate.append(
        scrivi(os.path.join(ROOT, "feed.xml"), feed(recenti, home.descrizione), args.check)
    )
    cambiate.append(
        scrivi(os.path.join(ROOT, "articoli.json"), indice(recenti, home.descrizione), args.check)
    )
    testo_llms = llms(episodi)
    cambiate.append(scrivi(os.path.join(ROOT, "llms.txt"), testo_llms, args.check))
    cambiate.append(scrivi(os.path.join(ROOT, "llms-full.txt"), llms_full(episodi), args.check))

    peso = len(testo_llms.encode("utf-8"))
    if peso > LIMITE_LLMS:
        print(f"ATTENZIONE llms.txt pesa {peso} byte, oltre i 5 KB consigliati", file=sys.stderr)

    nojekyll = os.path.join(ROOT, ".nojekyll")
    if not os.path.exists(nojekyll):
        if args.check:
            print("DA AGGIORNARE .nojekyll")
            cambiate.append(True)
        else:
            open(nojekyll, "w").close()
            print("scritto  .nojekyll")

    if args.check and any(cambiate):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
