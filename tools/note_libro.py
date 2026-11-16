#!/usr/bin/env python3
"""Le note del libro «Crescita Zero» per la pagina /note.

Uso:
    # estrae le 755 note dal .docx, ricava dal PDF di stampa la pagina del
    # richiamo, scrive assets/data/note-libro.json e rigenera l'elenco in note.html
    python3 tools/note_libro.py --docx libro.docx --pdf libro_stampa.pdf

    # solo dal .docx (senza numeri di pagina)
    python3 tools/note_libro.py --docx libro.docx

    # rigenera note.html dal JSON già committato (non servono docx né PDF)
    python3 tools/note_libro.py

    # confronta JSON e note.html con il .docx; esce con 1 se qualcosa non torna
    python3 tools/note_libro.py --docx libro.docx --verifica

Servono python-docx e pymupdf, ma solo per leggere docx e PDF: il normale build
del sito (tools/build.py) e la CI non ne hanno bisogno.

Cosa fa:
  - nel .docx, dopo il titolo «Note», ogni paragrafo senza «N.<tab>» è il titolo
    di un capitolo e quelli numerati sono le sue note (numerazione da 1 in ogni
    capitolo). Il testo si conserva identico, corsivi e grassetti compresi;
  - gli URL diventano link (target _blank, rel noopener) senza la punteggiatura
    finale `.,;:»”` né una `)` non bilanciata;
  - «nota N» diventa un link all'ancora solo quando rimanda a una nota dello
    stesso capitolo senza ambiguità: «della/nella/con la nota N», «(nota N)» e le
    liste «(note 10, 13 e 25)» della nota che le dichiara. «p. 45 e nota 36» dopo
    una «cit.» è la nota a piè di pagina dell'opera citata e non si tocca;
  - il numero di pagina del cartaceo è quello in cui compare il richiamo, cioè il
    numero in apice (corpo 6,7) nel PDF di stampa, letto dal numero stampato a
    piè di pagina. Per ogni capitolo i richiami devono essere 1..N in ordine e le
    pagine d'inizio capitolo devono coincidere con l'indice del libro: se no, per
    quel capitolo le pagine non si scrivono (meglio nessuna pagina che una sbagliata).
"""

import argparse
import json
import os
import re
import sys
from html import escape, unescape
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, "assets", "data", "note-libro.json")
HTML_PATH = os.path.join(ROOT, "note.html")

INIZIO = "<!-- note:inizio -->"
FINE = "<!-- note:fine -->"
INDICE_INIZIO = "<!-- note:indice-inizio -->"
INDICE_FINE = "<!-- note:indice-fine -->"

PREFISSO_RE = re.compile(r"^(\d+)\.\t")
URL_RE = re.compile(r"https?://[^\s]+")
CODA_URL = ".,;:»”"

RIF_SEMPLICE_RE = re.compile(r"\b(?:della|nella|con la|alla|dalla) nota (\d+)\b")
RIF_TONDA_RE = re.compile(r"\(nota (\d+)\)")
GRUPPO_RE = re.compile(r"\(([^()]*)\)")


# --- identificativi dei capitoli ---------------------------------------------


def id_capitolo(titolo):
    if titolo.startswith("Prologo"):
        return "prologo"
    if titolo.startswith("Conclusione"):
        return "conclusione"
    m = re.match(r"Capitolo (\d+)\b", titolo)
    if m:
        return f"cap{m.group(1)}"
    raise SystemExit(f"titolo di capitolo non riconosciuto: {titolo!r}")


# --- lettura del docx --------------------------------------------------------


def segmenti_paragrafo(p):
    """[[testo, flag], ...] con flag '' | 'i' | 'b' | 'ib', senza il prefisso «N.<tab>»."""
    pezzi = []
    for r in p.runs:
        if not r.text:
            continue
        flag = ("i" if r.italic else "") + ("b" if r.bold else "")
        if pezzi and pezzi[-1][1] == flag:
            pezzi[-1][0] += r.text
        else:
            pezzi.append([r.text, flag])
    testo = "".join(t for t, _ in pezzi)
    m = PREFISSO_RE.match(testo)
    if not m:
        return None, pezzi
    da_togliere = m.end()
    out = []
    for t, f in pezzi:
        if da_togliere >= len(t):
            da_togliere -= len(t)
            continue
        out.append([t[da_togliere:], f])
        da_togliere = 0
    return int(m.group(1)), out


def leggi_docx(percorso):
    import docx

    d = docx.Document(percorso)
    ps = d.paragraphs
    titoli = [i for i, p in enumerate(ps) if p.style.name == "Heading 1"]
    inizio = next(i for i in titoli if ps[i].text.strip() == "Note")
    fine = next(i for i in titoli if i > inizio)

    capitoli = []
    for p in ps[inizio + 1:fine]:
        n, seg = segmenti_paragrafo(p)
        testo = p.text
        if n is None:
            if testo.strip():
                capitoli.append({"id": id_capitolo(testo.strip()), "titolo": testo.strip(), "note": []})
            continue
        corrente = capitoli[-1]
        if n != len(corrente["note"]) + 1:
            raise SystemExit(f"{corrente['titolo']}: la nota {n} non segue la {len(corrente['note'])}")
        corrente["note"].append({"n": n, "testo": "".join(t for t, _ in seg), "segmenti": seg})

    indice = {}
    for p in ps[:inizio]:
        m = re.match(r"^((?:Prologo|Capitolo \d+|Conclusione) – .+?)\t(\d+)$", p.text)
        if m:
            indice[id_capitolo(m.group(1))] = int(m.group(2))
    return capitoli, indice


# --- pagine dal PDF ----------------------------------------------------------


def pagine_dal_pdf(percorso, capitoli, indice):
    """Per ogni capitolo, se la sequenza torna, {n: pagina stampata}; se no None."""
    import pymupdf

    doc = pymupdf.open(percorso)
    stampate = {}
    apici = []  # (indice pdf, numero)
    titoli = {}  # indice pdf -> testi in corpo 20
    for i, pagina in enumerate(doc):
        for b in pagina.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for riga in b["lines"]:
                for s in riga["spans"]:
                    t = s["text"].strip()
                    if not t:
                        continue
                    if s["bbox"][1] > 600 and s["size"] > 11 and re.fullmatch(r"\d+", t):
                        stampate[i] = int(t)
                    elif round(s["size"], 1) == 6.7 and s["flags"] & 1 and re.fullmatch(r"\d+", t):
                        apici.append((i, int(t)))
                    elif s["size"] >= 19.5:
                        titoli.setdefault(i, []).append(t)

    def stampata(i):
        if i in stampate:
            return stampate[i]
        # pagine senza numero (frontespizi di parte): continuano dalla precedente
        return stampate[i - 1] + 1 if i - 1 in stampate else None

    # inizio di ogni capitolo: la pagina del PDF il cui numero stampato è quello
    # dell'indice e che porta in grande l'inizio del titolo
    inizi = {}
    for c in capitoli:
        pag = indice.get(c["id"])
        cand = [i for i in range(len(doc)) if stampata(i) == pag
                and any(c["titolo"].startswith(t) or t.startswith(c["titolo"][:15]) for t in titoli.get(i, []))]
        if len(cand) == 1:
            inizi[c["id"]] = cand[0]

    risultato = {}
    ordine = [c["id"] for c in capitoli]
    for k, c in enumerate(capitoli):
        cid = c["id"]
        if cid not in inizi:
            print(f"ATTENZIONE {cid}: inizio capitolo non coincide con l'indice, niente pagine", file=sys.stderr)
            risultato[cid] = None
            continue
        a = inizi[cid]
        b = inizi.get(ordine[k + 1], len(doc)) if k + 1 < len(ordine) else None
        if b is None:
            # l'ultimo capitolo (Conclusione) finisce dove comincia «Note»
            b = next((i for i, ts in titoli.items() if "Note" in ts and i > a), len(doc))
        seq = [(i, n) for i, n in apici if a <= i < b]
        numeri = [n for _, n in seq]
        atteso = list(range(1, len(c["note"]) + 1))
        if numeri != atteso:
            print(f"ATTENZIONE {cid}: richiami {len(numeri)} contro {len(atteso)} note o ordine diverso, niente pagine", file=sys.stderr)
            risultato[cid] = None
            continue
        pagine = {n: stampata(i) for i, n in seq}
        if any(v is None for v in pagine.values()) or list(pagine.values()) != sorted(pagine.values()):
            print(f"ATTENZIONE {cid}: pagine non monotone, niente pagine", file=sys.stderr)
            risultato[cid] = None
            continue
        risultato[cid] = pagine
    return risultato


# --- link nel testo ----------------------------------------------------------


def taglia_url(url):
    while url:
        if url[-1] in CODA_URL:
            url = url[:-1]
        elif url[-1] == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def collegamenti(testo, cid, n, quante):
    """Intervalli (inizio, fine, tipo, valore) da trasformare in link."""
    out = []
    for m in URL_RE.finditer(testo):
        url = taglia_url(m.group(0))
        if len(url) > len("https://"):
            out.append((m.start(), m.start() + len(url), "url", url))

    def valida(num):
        return 1 <= num <= quante and num != n

    for rx in (RIF_SEMPLICE_RE, RIF_TONDA_RE):
        for m in rx.finditer(testo):
            num = int(m.group(1))
            if valida(num):
                out.append((m.start(1), m.end(1), "nota", num))
    if "nelle note di questo capitolo" in testo:
        for g in GRUPPO_RE.finditer(testo):
            for m in re.finditer(r"\d+", g.group(1)):
                num = int(m.group(0))
                if valida(num):
                    out.append((g.start(1) + m.start(), g.start(1) + m.end(), "nota", num))
    out.sort()
    # niente sovrapposizioni
    pulito, fino = [], -1
    for iv in out:
        if iv[0] >= fino:
            pulito.append(iv)
            fino = iv[1]
    return pulito


def html_nota(nota, cid, quante):
    """L'HTML del testo di una nota: corsivi, grassetti, URL e rimandi."""
    testo = nota["testo"]
    ivs = collegamenti(testo, cid, nota["n"], quante)

    # spezzo i segmenti ai confini dei link
    tagli = sorted({0, len(testo)} | {x for iv in ivs for x in iv[:2]})
    segs = []  # (inizio, fine, flag)
    pos = 0
    for t, f in nota["segmenti"]:
        segs.append((pos, pos + len(t), f))
        pos += len(t)

    def avvolgi(s, f):
        s = escape(s, quote=False)
        if "b" in f:
            s = f"<strong>{s}</strong>"
        if "i" in f:
            s = f"<em>{s}</em>"
        return s

    def render(a, b):
        out = []
        for sa, sb, f in segs:
            x, y = max(a, sa), min(b, sb)
            if x < y:
                out.append(avvolgi(testo[x:y], f))
        return "".join(out)

    out = []
    for a, b in zip(tagli, tagli[1:]):
        iv = next((v for v in ivs if v[0] <= a and b <= v[1]), None)
        if iv is None:
            out.append(render(a, b))
        elif iv[2] == "url":
            if a == iv[0]:
                href = escape(iv[3], quote=True)
                out.append(f'<a href="{href}" target="_blank" rel="noopener">')
            out.append(render(a, b))
            if b == iv[1]:
                out.append("</a>")
        else:
            out.append(f'<a class="nota-rif" href="#{cid}-{iv[3]}">{render(a, b)}</a>')
    return "".join(out)


# --- JSON e HTML -------------------------------------------------------------


def scrivi_json(capitoli, pagine):
    dati = {
        "titolo": "Crescita Zero. Perché l’Italia non cresce da trent’anni e come può ripartire",
        "autori": ["Lorenzo Ruffino", "Elia Bidut"],
        "note_totali": sum(len(c["note"]) for c in capitoli),
        "pagine": "numero di pagina dell'edizione cartacea (6×9 pollici) in cui compare il richiamo; assente se non verificabile",
        "capitoli": [],
    }
    for c in capitoli:
        pg = pagine.get(c["id"]) if pagine else None
        voce = {"id": c["id"], "titolo": c["titolo"], "note": []}
        for nota in c["note"]:
            v = {"n": nota["n"], "testo": nota["testo"], "segmenti": nota["segmenti"]}
            if pg:
                v["pagina"] = pg[nota["n"]]
            voce["note"].append(v)
        dati["capitoli"].append(voce)
    with open(JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return dati


def leggi_json():
    with open(JSON_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def indice_html(dati):
    righe = ["        " + INDICE_INIZIO, '        <ol class="note-indice">']
    for c in dati["capitoli"]:
        righe.append(
            f'          <li><a href="#{c["id"]}" data-umami-event="note_chapter_click"'
            f' data-umami-event-chapter="{c["id"]}">{escape(c["titolo"], quote=False)}</a>'
            f' <span class="note-conta" data-conta="{c["id"]}">{len(c["note"])}</span></li>'
        )
    righe += ["        </ol>", "        " + INDICE_FINE]
    return "\n".join(righe)


def elenco_html(dati):
    righe = ["      " + INIZIO]
    for c in dati["capitoli"]:
        cid = c["id"]
        quante = len(c["note"])
        righe.append(f'      <section class="note-capitolo" id="{cid}" data-capitolo="{cid}">')
        righe.append(f'        <h2>{escape(c["titolo"], quote=False)}</h2>')
        righe.append('        <ol class="note-elenco">')
        for nota in c["note"]:
            nid = f'{cid}-{nota["n"]}'
            pagina = (
                f'<span class="nota-pagina">p.&nbsp;{nota["pagina"]}</span>' if "pagina" in nota else ""
            )
            righe.append(
                f'          <li class="nota" id="{nid}">'
                f'<a class="nota-num" href="#{nid}" aria-label="Nota {nota["n"]}">{nota["n"]}</a>'
                f'<div class="nota-corpo"><p class="nota-testo">{html_nota(nota, cid, quante)}</p>{pagina}</div></li>'
            )
        righe.append("        </ol>")
        righe.append("      </section>")
    righe.append("      " + FINE)
    return "\n".join(righe)


def aggiorna_html(dati):
    with open(HTML_PATH, encoding="utf-8") as fh:
        html = fh.read()
    for ini, fin, nuovo in (
        (INDICE_INIZIO, INDICE_FINE, indice_html(dati)),
        (INIZIO, FINE, elenco_html(dati)),
    ):
        rx = re.compile(r"[ \t]*" + re.escape(ini) + r".*?" + re.escape(fin), re.S)
        if not rx.search(html):
            raise SystemExit(f"note.html: mancano i marcatori {ini} … {fin}")
        html = rx.sub(lambda m: nuovo, html, count=1)
    with open(HTML_PATH, "w", encoding="utf-8") as fh:
        fh.write(html)


# --- verifica ----------------------------------------------------------------


class Lettore(HTMLParser):
    """Raccoglie id e testo di ogni nota in note.html."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.note = {}
        self.cur = None
        self.nel_testo = False
        self.link = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li" and "nota" in (a.get("class") or "").split():
            self.cur = a["id"]
            self.note[self.cur] = ""
        elif tag == "p" and "nota-testo" in (a.get("class") or "").split():
            self.nel_testo = True
        elif tag == "a" and self.nel_testo:
            self.link.append(a)

    def handle_endtag(self, tag):
        if tag == "p" and self.nel_testo:
            self.nel_testo = False

    def handle_data(self, data):
        if self.nel_testo and self.cur:
            self.note[self.cur] += data


def verifica(capitoli_docx):
    dati = leggi_json()
    errori = []
    if len(dati["capitoli"]) != len(capitoli_docx):
        errori.append("numero di capitoli diverso")
    totale = 0
    for cj, cd in zip(dati["capitoli"], capitoli_docx):
        if cj["id"] != cd["id"] or cj["titolo"] != cd["titolo"]:
            errori.append(f"titolo diverso: {cj['titolo']!r} / {cd['titolo']!r}")
        if len(cj["note"]) != len(cd["note"]):
            errori.append(f"{cj['id']}: {len(cj['note'])} note nel JSON, {len(cd['note'])} nel docx")
        for nj, nd in zip(cj["note"], cd["note"]):
            totale += 1
            if nj["n"] != nd["n"] or nj["testo"] != nd["testo"] or nj["segmenti"] != nd["segmenti"]:
                errori.append(f"{cj['id']}-{nj['n']}: testo diverso dal docx")
    with open(HTML_PATH, encoding="utf-8") as fh:
        lettore = Lettore()
        lettore.feed(fh.read())
    attese = {f"{c['id']}-{n['n']}": n["testo"] for c in capitoli_docx for n in c["note"]}
    if set(lettore.note) != set(attese):
        errori.append("le ancore di note.html non sono quelle del docx")
    for nid, testo in attese.items():
        if lettore.note.get(nid) != testo:
            errori.append(f"{nid}: il testo in note.html differisce dal docx")
    for c in capitoli_docx:
        print(f"{c['id']:12s} {len(c['note']):4d} note")
    print(f"totale {totale} note, in note.html {len(lettore.note)}")
    for e in errori[:30]:
        print("ERRORE", e)
    return 0 if not errori and totale == len(lettore.note) else 1


# --- main --------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", help="il libro in .docx")
    ap.add_argument("--pdf", help="il PDF di stampa (per i numeri di pagina)")
    ap.add_argument("--verifica", action="store_true", help="confronta JSON e note.html con il docx")
    args = ap.parse_args()

    if args.docx:
        capitoli, indice = leggi_docx(args.docx)
        if args.verifica:
            return verifica(capitoli)
        pagine = pagine_dal_pdf(args.pdf, capitoli, indice) if args.pdf else None
        dati = scrivi_json(capitoli, pagine)
        print(f"scritto assets/data/note-libro.json: {dati['note_totali']} note")
    else:
        dati = leggi_json()
    aggiorna_html(dati)
    print("scritto note.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
