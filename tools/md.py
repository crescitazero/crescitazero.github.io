#!/usr/bin/env python3
"""Conversione dell'HTML degli articoli in Markdown (e in HTML ripulito).

Serve a `build.py` per due cose:

  - il gemello Markdown di ogni articolo (`articoli/<slug>.md`), la versione
    che leggono i modelli linguistici e chiunque preferisca il testo semplice;
  - il `content:encoded` del feed RSS, cioè lo stesso articolo in HTML ma
    senza script, iframe, stili inline e attributi di tracciamento.

Niente dipendenze esterne: `html.parser` della libreria standard costruisce un
alberello di nodi e da lì si rende quello che serve. Gli articoli usano un
insieme ristretto di tag (h1-h3, p, em, strong, a, ul/ol/li, blockquote, br,
img, figure/figcaption, div/span, hr) più gli iframe di Datawrapper con il
loro `<script>` di ridimensionamento, che qui viene sempre ignorato.

Ogni iframe Datawrapper diventa, in Markdown, il titolo del grafico, la sua
introduzione, la tabella dei dati (solo se sta in TABELLA_RIGHE_MAX righe e
TABELLA_COLONNE_MAX colonne) e la riga con fonte e link; nel feed, un
paragrafo con titolo e link al grafico interattivo.
"""

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin

# oltre queste soglie la tabella diventa illeggibile: restano solo i link
TABELLA_RIGHE_MAX = 40
TABELLA_COLONNE_MAX = 8

VUOTI = {"br", "img", "hr", "meta", "link", "input", "source", "col"}
IGNORATI = {"script", "style", "noscript", "template"}

BLOCCHI = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote",
    "div", "figure", "figcaption", "hr", "article", "main", "section", "header",
    "footer", "aside", "iframe", "table", "nav",
}

# tag e attributi ammessi nel content:encoded del feed
HTML_TAG_OK = {
    "p", "h2", "h3", "h4", "em", "i", "strong", "b", "a", "ul", "ol", "li",
    "blockquote", "br", "img", "figure", "figcaption", "hr", "code", "sub", "sup",
}
HTML_ATTR_OK = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
}

DATAWRAPPER_RE = re.compile(r"datawrapper\.dwcdn\.net/([A-Za-z0-9_-]+)/(\d+)/")


class Nodo:
    __slots__ = ("tag", "attrs", "figli", "testo")

    def __init__(self, tag, attrs=None, testo=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.figli = []
        self.testo = testo

    def classe(self):
        return self.attrs.get("class", "")


class Albero(HTMLParser):
    """Da HTML a un albero di Nodo. I tag non chiusi si chiudono da soli."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.radice = Nodo("#radice")
        self.pila = [self.radice]

    def handle_starttag(self, tag, attrs):
        nodo = Nodo(tag, {k: (v or "") for k, v in attrs})
        self.pila[-1].figli.append(nodo)
        if tag not in VUOTI:
            self.pila.append(nodo)

    def handle_startendtag(self, tag, attrs):
        self.pila[-1].figli.append(Nodo(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.pila) - 1, 0, -1):
            if self.pila[i].tag == tag:
                del self.pila[i:]
                return

    def handle_data(self, data):
        if self.pila[-1].tag in IGNORATI:
            return
        self.pila[-1].figli.append(Nodo("#testo", testo=data))


def analizza(html):
    a = Albero()
    a.feed(html)
    a.close()
    return a.radice


def spazi(s):
    return re.sub(r"\s+", " ", s)


# --- Markdown ---------------------------------------------------------------


def _enfasi(inner, marcatore):
    """`**testo **` non è valido: gli spazi vanno tenuti fuori dai marcatori."""
    if not inner.strip():
        return inner
    prima = inner[: len(inner) - len(inner.lstrip())]
    dopo = inner[len(inner.rstrip()):]
    return f"{prima}{marcatore}{inner.strip()}{marcatore}{dopo}"


class Rendi:
    """Rende un albero in Markdown. Un'istanza per articolo."""

    def __init__(self, base_url, grafici=None):
        self.base = base_url
        self.grafici = grafici or {}
        self.testo_semplice = []

    def url(self, href):
        return urljoin(self.base, (href or "").strip())

    # inline -----------------------------------------------------------------

    def inline(self, nodo, semplice=False):
        """Il contenuto inline di un nodo. Con semplice=True niente marcatori."""
        out = []
        for f in nodo.figli:
            if f.tag == "#testo":
                out.append(spazi(f.testo))
            elif f.tag in IGNORATI:
                continue
            elif f.tag == "br":
                out.append("\n")
            elif f.tag == "img":
                alt = spazi(f.attrs.get("alt", "")).strip()
                out.append(f"![{alt}]({self.url(f.attrs.get('src'))})")
            elif f.tag == "a":
                dentro = self.inline(f, semplice)
                if not dentro.strip():
                    continue
                if semplice:
                    out.append(dentro)
                    continue
                # gli spazi finiti dentro il link vanno tenuti fuori dalle parentesi,
                # altrimenti due link consecutivi si attaccano
                prima = dentro[: len(dentro) - len(dentro.lstrip())]
                dopo = dentro[len(dentro.rstrip()):]
                out.append(f"{prima}[{dentro.strip()}]({self.url(f.attrs.get('href'))}){dopo}")
            elif f.tag in ("em", "i"):
                dentro = self.inline(f, semplice)
                out.append(dentro if semplice else _enfasi(dentro, "*"))
            elif f.tag in ("strong", "b"):
                dentro = self.inline(f, semplice)
                out.append(dentro if semplice else _enfasi(dentro, "**"))
            elif f.tag == "code":
                dentro = self.inline(f, semplice)
                out.append(dentro if semplice else _enfasi(dentro, "`"))
            else:
                out.append(self.inline(f, semplice))
        return "".join(out)

    # blocchi ----------------------------------------------------------------

    def blocchi(self, nodo, salta=None):
        """La lista dei blocchi Markdown dei figli di un nodo."""
        out = []
        for f in nodo.figli:
            out.extend(self.blocco(f, salta))
        return [b for b in out if b.strip()]

    def blocco(self, nodo, salta=None):
        tag = nodo.tag
        if tag in IGNORATI:
            return []
        if salta and salta(nodo):
            return []

        if tag == "#testo":
            testo = spazi(nodo.testo).strip()
            return [testo] if testo else []

        if tag == "iframe":
            return self.grafico(nodo)

        if tag == "hr":
            return ["---"]

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            titolo = spazi(self.inline(nodo, semplice=True)).strip()
            if not titolo:
                return []
            self.testo_semplice.append(titolo)
            return ["#" * int(tag[1]) + " " + titolo]

        if tag == "p" or tag == "figcaption":
            testo = self.inline(nodo).strip()
            if not testo:
                return []
            self.testo_semplice.append(self.inline(nodo, semplice=True).strip())
            if tag == "figcaption":
                testo = _enfasi(testo, "*")
            return [testo]

        if tag in ("ul", "ol"):
            righe, n = [], 0
            for voce in nodo.figli:
                if voce.tag != "li":
                    continue
                n += 1
                marcatore = f"{n}. " if tag == "ol" else "- "
                interni = self.blocchi(voce, salta)
                if not interni:
                    continue
                corpo = "\n\n".join(interni)
                rientro = " " * len(marcatore)
                prima, *resto = corpo.split("\n")
                righe.append(marcatore + prima + "".join("\n" + (rientro + r if r else "") for r in resto))
            return ["\n".join(righe)] if righe else []

        if tag == "li":
            testo = self.inline(nodo).strip()
            if testo:
                self.testo_semplice.append(self.inline(nodo, semplice=True).strip())
                return [testo]
            return self.blocchi(nodo, salta)

        if tag == "blockquote":
            interni = self.blocchi(nodo, salta)
            if not interni:
                return []
            corpo = "\n\n".join(interni)
            return ["\n".join(("> " + r).rstrip() for r in corpo.split("\n"))]

        if tag == "img":
            alt = spazi(nodo.attrs.get("alt", "")).strip()
            return [f"![{alt}]({self.url(nodo.attrs.get('src'))})"]

        if tag in BLOCCHI or tag == "#radice":
            return self.blocchi(nodo, salta)

        # un tag inline capitato fuori da un paragrafo
        testo = self.inline(nodo).strip()
        return [testo] if testo else []

    # grafici ----------------------------------------------------------------

    def grafico(self, nodo):
        m = DATAWRAPPER_RE.search(nodo.attrs.get("src", ""))
        if not m:
            return []
        grafico = self.grafici.get(f"{m.group(1)}/{m.group(2)}")
        if not grafico:
            return []
        return blocco_grafico(grafico)


def tabella(righe):
    """La tabella Markdown dei dati, oppure None se è troppo grande."""
    if not righe or len(righe) - 1 > TABELLA_RIGHE_MAX:
        return None
    colonne = max(len(r) for r in righe)
    if colonne > TABELLA_COLONNE_MAX:
        return None

    def cella(v):
        return spazi(str(v)).strip().replace("|", "\\|") or " "

    out = ["| " + " | ".join(cella(v) for v in _pareggia(righe[0], colonne)) + " |"]
    out.append("| " + " | ".join("---" for _ in range(colonne)) + " |")
    for riga in righe[1:]:
        out.append("| " + " | ".join(cella(v) for v in _pareggia(riga, colonne)) + " |")
    return "\n".join(out)


def _pareggia(riga, colonne):
    return list(riga) + [""] * (colonne - len(riga))


def senza_tag(s):
    return spazi(re.sub(r"<[^>]+>", "", s or "")).strip()


def blocco_grafico(grafico):
    """I blocchi Markdown di un grafico Datawrapper."""
    titolo = senza_tag(grafico.get("title")) or "Grafico"
    intro = senza_tag(grafico.get("intro"))
    note = senza_tag(grafico.get("notes"))
    url = grafico.get("url") or ""
    csv_url = url.rstrip("/") + "/dataset.csv"

    testa = f"**{titolo}**"
    if intro:
        testa += f"\n_{intro}_"
    out = [testa]

    corpo = tabella(grafico.get("data") or [])
    if corpo:
        out.append(corpo)
    if note:
        out.append(f"_{note}_")

    pezzi = []
    fonte = senza_tag(grafico.get("source_name"))
    if fonte:
        indirizzo = (grafico.get("source_url") or "").strip()
        pezzi.append(f"Fonte: [{fonte}]({indirizzo})" if indirizzo else f"Fonte: {fonte}")
    pezzi.append(f"[Grafico interattivo]({url})")
    pezzi.append(f"[Dati CSV]({csv_url})")
    out.append(" · ".join(pezzi))
    return out


def converti(html, base_url, grafici=None, salta=None):
    """(markdown, testo semplice) del frammento HTML passato."""
    rendi = Rendi(base_url, grafici)
    blocchi = rendi.blocchi(analizza(html), salta)
    markdown = "\n\n".join(blocchi).strip()
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown, " ".join(t for t in rendi.testo_semplice if t)


# --- HTML ripulito per il feed ----------------------------------------------


def html_pulito(html, base_url, grafici=None, salta=None):
    """L'articolo in HTML senza script, iframe, stili e attributi di tracciamento."""
    grafici = grafici or {}
    out = []

    def indirizzo(href):
        return urljoin(base_url, (href or "").strip())

    def scrivi(nodo):
        for f in nodo.figli:
            if f.tag in IGNORATI:
                continue
            if salta and salta(f):
                continue
            if f.tag == "#testo":
                out.append(escape(f.testo, quote=False))
                continue
            if f.tag == "iframe":
                m = DATAWRAPPER_RE.search(f.attrs.get("src", ""))
                grafico = grafici.get(f"{m.group(1)}/{m.group(2)}") if m else None
                if grafico:
                    titolo = escape(senza_tag(grafico.get("title")) or "Grafico")
                    url = escape(grafico.get("url") or "", quote=True)
                    out.append(f'<p><strong>{titolo}</strong> — <a href="{url}">Grafico interattivo</a></p>')
                continue
            if f.tag not in HTML_TAG_OK:
                # div, span, section e simili: si tiene il contenuto, non il contenitore
                scrivi(f)
                continue
            attributi = ""
            for chiave in sorted(HTML_ATTR_OK.get(f.tag, set())):
                if chiave not in f.attrs:
                    continue
                valore = f.attrs[chiave]
                if chiave in ("href", "src"):
                    valore = indirizzo(valore)
                attributi += f' {chiave}="{escape(valore, quote=True)}"'
            if f.tag in VUOTI:
                out.append(f"<{f.tag}{attributi}>")
                continue
            out.append(f"<{f.tag}{attributi}>")
            scrivi(f)
            out.append(f"</{f.tag}>")

    scrivi(analizza(html))
    pulito = "".join(out)
    pulito = re.sub(r"\s*\n\s*", "\n", pulito)
    pulito = re.sub(r"\n{2,}", "\n", pulito)
    return pulito.strip()
