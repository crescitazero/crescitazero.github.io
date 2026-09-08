#!/usr/bin/env python3
"""Genera le immagini di anteprima social (Open Graph / X) di CrescitaZero.

Uso:
    python3 tools/og_card.py                      # genera solo le card mancanti
    python3 tools/og_card.py --force              # rigenera tutto
    python3 tools/og_card.py --list               # mostra le card previste

Le card sono 1200x630 e riprendono lo stile del sito: fondo crema, griglia
verticale, marchio CZ, occhiello in accento e titolo in nero.

Il font viene scelto tra i candidati disponibili sul sistema (Helvetica Neue su
macOS, Liberation Sans su Linux/CI): stessa impostazione grafica, metriche molto
simili. Le card esistenti non vengono toccate senza --force, così un font
diverso sulla macchina di turno non riscrive quelle già pubblicate.
"""

import argparse
import os
import re
import sys
from functools import lru_cache
from html import unescape
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "social")

W, H = 1200, 630
BG = (251, 250, 246)
TEXT = (17, 17, 17)
MUTED = (95, 95, 90)
LINE = (222, 219, 210)
ACCENT = (36, 87, 255)
GRID = (243, 242, 237)

PAD = 76

# Famiglie in ordine di preferenza: (regular, bold), ciascuno (percorso, indice).
FONT_FAMILIES = [
    (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ),
    (
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 1),
    ),
    (
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ),
    (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ),
]


def pick_family():
    for regular, bold in FONT_FAMILIES:
        if os.path.exists(regular[0]) and os.path.exists(bold[0]):
            return regular, bold
    raise SystemExit(
        "Nessun font disponibile. Su Linux: sudo apt-get install fonts-liberation"
    )


@lru_cache(maxsize=1)
def family():
    """Risolta alla prima card: social-meta.py importa questo modulo senza font."""
    return pick_family()


def font(size, face=0):
    path, index = family()[1 if face else 0]
    return ImageFont.truetype(path, size, index=index)


def font_name():
    return " ".join(font(20).getname())


def text_width(draw, s, f, tracking=0):
    w = draw.textlength(s, font=f)
    return w + tracking * max(len(s) - 1, 0)


def draw_tracked(draw, xy, s, f, fill, tracking=0):
    x, y = xy
    if not tracking:
        draw.text((x, y), s, font=f, fill=fill)
        return
    for ch in s:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + tracking


def wrap(draw, s, f, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if text_width(draw, trial, f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_title(draw, title, max_w, max_lines=4, sizes=(66, 60, 54, 48, 44, 40)):
    for size in sizes:
        f = font(size, 1)
        lines = wrap(draw, title, f, max_w)
        if len(lines) <= max_lines:
            return f, lines, size
    f = font(sizes[-1], 1)
    return f, wrap(draw, title, f, max_w)[:max_lines], sizes[-1]


def make_card(title, kicker, out_path, subtitle=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # griglia verticale come sullo sfondo del sito
    for x in range(0, W, 88):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)

    # barra di accento a sinistra
    d.rectangle([0, 0, 10, H], fill=ACCENT)

    inner = W - PAD - 60

    # marchio CZ + wordmark
    box = 54
    bx, by = PAD, PAD - 10
    d.rectangle([bx, by, bx + box, by + box], outline=TEXT, width=3)
    fm = font(21, 1)
    tw = text_width(d, "CZ", fm)
    d.text((bx + (box - tw) / 2, by + box / 2 - 14), "CZ", font=fm, fill=TEXT)
    fw = font(30, 1)
    d.text((bx + box + 18, by + box / 2 - 21), "CrescitaZero", font=fw, fill=TEXT)

    # occhiello
    fk = font(20, 1)
    ky = by + box + 66
    draw_tracked(d, (PAD, ky), kicker.upper(), fk, ACCENT, tracking=2.4)

    # titolo
    ft, lines, size = fit_title(d, title, inner - PAD, max_lines=4 if subtitle else 5)
    y = ky + 52
    leading = int(size * 1.18)
    for line in lines:
        d.text((PAD, y), line, font=ft, fill=TEXT)
        y += leading

    # sottotitolo opzionale
    if subtitle:
        fs = font(25, 0)
        y += 12
        for line in wrap(d, subtitle, fs, inner - PAD)[:2]:
            d.text((PAD, y), line, font=fs, fill=MUTED)
            y += 34

    # piede
    fy = H - PAD - 6
    d.line([(PAD, fy - 26), (W - PAD, fy - 26)], fill=LINE, width=1)
    ff = font(22, 0)
    d.text((PAD, fy), "crescitazero.it", font=ff, fill=MUTED)
    fa = font(22, 0)
    author = "Lorenzo Ruffino ed Elia Bidut"
    d.text((W - PAD - text_width(d, author, fa), fy), author, font=fa, fill=MUTED)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def page_meta(path):
    """Estrae titolo (senza suffisso), occhiello e description da una pagina."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = unescape(m.group(1)).strip() if m else ""
    title = re.sub(r"\s*[-–]\s*CrescitaZero$", "", title)
    m = re.search(r'<p class="meta">(.*?)</p>', html, re.S)
    kicker = unescape(m.group(1)).strip() if m else "CrescitaZero"
    m = re.search(r'<meta name="description" content="(.*?)"', html, re.S)
    desc = unescape(m.group(1)).strip() if m else None
    return title, kicker, desc


def cards():
    out = [(
        os.path.join(OUT_DIR, "default.png"),
        "Perché l’Italia non cresce più?",
        "Italia, crescita, dati",
        "Un progetto gratuito per capire la stagnazione italiana partendo dai dati.",
    )]
    art_dir = os.path.join(ROOT, "articoli")
    for name in sorted(os.listdir(art_dir)):
        if not name.endswith(".html"):
            continue
        path = os.path.join(art_dir, name)
        title, kicker, _ = page_meta(path)
        out.append((
            os.path.join(OUT_DIR, name.replace(".html", ".png")),
            title,
            kicker,
            None,
        ))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="elenca le card senza generarle")
    ap.add_argument("--force", action="store_true", help="rigenera anche le card già esistenti")
    ap.add_argument(
        "--prune",
        action="store_true",
        help="elimina le card rimaste orfane (pagina rinominata o cancellata)",
    )
    args = ap.parse_args()

    if not args.list:
        print(f"font: {font_name()}")

    wanted = {out_path for out_path, _, _, _ in cards()}
    if args.prune and os.path.isdir(OUT_DIR):
        for name in sorted(os.listdir(OUT_DIR)):
            path = os.path.join(OUT_DIR, name)
            if name.endswith(".png") and path not in wanted:
                os.remove(path)
                print(f"rimosso {os.path.relpath(path, ROOT)}")

    for out_path, title, kicker, subtitle in cards():
        rel = os.path.relpath(out_path, ROOT)
        if args.list:
            print(f"{rel}\n  [{kicker}] {title}")
            continue
        if os.path.exists(out_path) and not args.force:
            print(f"esiste  {rel}")
            continue
        make_card(title, kicker, out_path, subtitle)
        print(f"scritto {rel}")


if __name__ == "__main__":
    sys.exit(main())
