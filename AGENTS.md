# Istruzioni per gli agenti

La guida operativa completa di questo repository è **[CLAUDE.md](CLAUDE.md)**: leggila
prima di toccare qualsiasi file. Questo è solo il rimando, con le regole che non si
possono ignorare nemmeno per un intervento piccolo.

1. **La pagina HTML è l'unica fonte di verità.** Titolo, description, occhiello
   (`<p class="meta">`) e byline (`<p class="byline">`, con `<time datetime>` e autori)
   vivono nella pagina; tutto il resto lo genera `tools/build.py`.
2. **Non modificare a mano** i blocchi `<!-- build -->`, `<!-- build:nav -->`, il CSS
   `/* build:nav */` né i file generati (`articoli/*.md`, `robots.txt`, `sitemap.xml`,
   `feed.xml`, `llms.txt`, `llms-full.txt`, `articoli.json`, `assets/social/`,
   `assets/data/`). Il workflow `.github/workflows/build.yml` li riscrive a ogni push.
3. **`.nojekyll` deve restare** alla radice, altrimenti GitHub Pages sovrascrive gli
   articoli HTML con i `.md`.
4. Dopo una modifica, `python3 tools/build.py --check` deve stampare solo `ok`; se no,
   lancia `python3 tools/build.py` e committa anche i file che riscrive.
5. Tracciamento: solo Umami, niente GA4. I click sono dichiarativi (`data-umami-event`
   nell'HTML), il resto sta in `assets/js/tracking.js`; mai tracciare due volte lo stesso
   elemento. Lo schema degli eventi è in testa a quel file.

Per un nuovo articolo e per verificare che il tracciamento funzioni: le sezioni
omonime di [CLAUDE.md](CLAUDE.md). Dettagli sugli script: [tools/README.md](tools/README.md).
