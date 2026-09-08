# CrescitaZero — guida operativa

Sito statico su GitHub Pages (dominio `crescitazero.it`, dal file `CNAME`) della serie
CrescitaZero di Lorenzo Ruffino ed Elia Bidut. Niente framework, niente build tool
esterni: `index.html`, `404.html` e `articoli/*.html` sono scritti a mano con CSS
inline. Tutto il resto lo generano gli script in `tools/`, che girano da soli in CI.

## La regola che tiene insieme tutto

**La pagina HTML è l'unica fonte di verità.** `tools/build.py` legge da ogni pagina
`<title>`, `<meta name="description">`, l'occhiello `<p class="meta">` e la byline
`<p class="byline">` (autori con `rel="author"`, `<time datetime>`), e da lì scrive:

- nel `<head>`, un blocco `<!-- build: … --> … <!-- /build -->`: canonical, Open Graph,
  Twitter card, author, robots, JSON-LD, link a feed/Markdown/llms.txt, script Umami e
  `tracking.js`;
- sul `<body>`, `data-article="<slug>"` (slug = nome file senza estensione, `home` per la home);
- negli articoli, la navigazione precedente/successivo (`<!-- build:nav -->`);
- in home, gli attributi `data-umami-event` sui link della lista articoli, numerati;
- fuori dalle pagine: `assets/social/*.png`, `articoli/*.md`, `robots.txt`, `sitemap.xml`,
  `feed.xml`, `llms.txt`, `llms-full.txt`, `articoli.json`, `assets/data/grafici/*.json`.

Conseguenze pratiche:

- **Non modificare mai a mano** ciò che sta dentro i blocchi `<!-- build -->`,
  `<!-- build:nav -->`, il CSS `/* build:nav */`, né i file generati: il prossimo build li
  riscrive. Per cambiare un tag, cambia la sorgente (title, description, byline…) o
  `tools/build.py`.
- Il workflow `.github/workflows/build.yml` gira a ogni push su `main` e committa i file
  generati. Si può anche lanciare in locale: `python3 tools/build.py` (idempotente;
  `--check` esce con 1 se qualcosa è da aggiornare).
- `.nojekyll` alla radice **deve restare**: senza, GitHub Pages passerebbe i `.md` per
  Jekyll e sovrascriverebbe gli articoli HTML.

## Nuovo articolo: cosa fare

1. Crea `articoli/<slug>.html` copiando l'articolo più recente dello stesso tipo
   (08 per gli approfondimenti, h1-2026 per le note brevi). Nello slug non usare spazi
   né caratteri speciali: diventa nome della card, del `.md` e valore di `data-article`.
2. Nell'HTML devono esserci, e devono essere corretti, perché tutto ne deriva:
   - `<title>Titolo dell'articolo - CrescitaZero</title>`
   - `<meta name="description" content="…">` (finisce su Google, nelle card e in llms.txt)
   - `<p class="meta">Approfondimento</p>` (l'occhiello: Approfondimento, Aggiornamento, Letture…)
   - la byline sotto l'`<h1>`, con `<time datetime="AAAA-MM-GG">` e i due autori con `rel="author"`
   - per i grafici Datawrapper, l'`<iframe src="https://datawrapper.dwcdn.net/<id>/<v>/">`
     (il `title` lo mette il build dal titolo del grafico; il grafico deve essere pubblicato
     con «Get the data» attivo perché il build ne scarichi i dati)
   - l'`<article>` che racchiude il testo (è quello che diventa Markdown e feed)
3. Aggiungi la voce in cima alla lista in `index.html` (sezione `#articoli`), copiando la
   precedente. **Non serve** scrivere `data-umami-event`: li numera il build.
4. Committa e pusha su `main`. Il workflow genera card, `.md`, dati dei grafici, aggiorna
   sitemap/feed/llms e committa. Fine.

Lo stesso vale per una correzione: cambia il testo, pusha, il resto si riallinea.

## Come essere sicuri che il tracciamento funzioni

Dopo il push, quando il workflow è verde (Actions → «Build sito»):

1. Apri l'articolo pubblicato e verifica nel sorgente che nel blocco build ci siano
   `analyticsprogetti.lorenzoruffino.com/script.js` con `data-domains="crescitazero.it"` e
   `/assets/js/tracking.js`, e che il `<body>` abbia `data-article="<slug>"`. In locale, la
   stessa verifica è `python3 tools/build.py --check` (deve esser tutto `ok`) più:
   ```bash
   grep -c 'analyticsprogetti' index.html articoli/*.html   # 1 per pagina
   grep -o 'data-umami-event-position="[0-9]*"' index.html  # 1…N senza buchi
   ```
2. Apri l'articolo **da fuori la rete di casa** (telefono con rete dati, o un altro
   posto), scorri fino in fondo, resta più di 30 secondi. In Umami → sito CrescitaZero →
   *Events* devono comparire `read_depth` (25/50/75/100) e `read_time` (30), con la
   proprietà `article` uguale allo slug. Se clicchi il link dalla home compare anche
   `article_open` con la `position` giusta.
3. Perché «da fuori»: `analyticsprogetti.lorenzoruffino.com` ha DNS split-horizon e dalla
   LAN risolve a un IP privato; Chrome blocca (Private Network Access) gli script che una
   pagina pubblica carica da un IP privato, quindi da casa `window.umami` non esiste e non
   parte nulla. Non è un problema del sito. Per risolverlo alla radice: far rispondere il
   preflight `OPTIONS` di Pangolin con `Access-Control-Allow-Private-Network: true`, oppure
   togliere la risoluzione locale di quel dominio.
4. Se un evento non arriva, la console del browser non aiuta: `tracking.js` degrada in
   silenzio quando Umami manca (per scelta, così un adblocker non genera errori). Per
   debug in locale, stubba `window.umami = { track: console.log }` prima di scrollare.

Schema completo degli eventi, con nomi e proprietà: in testa a `assets/js/tracking.js`.
I click su link/bottoni sono dichiarativi (`data-umami-event` nell'HTML, li manda Umami
da solo); mai tracciarli anche da `tracking.js`, conterebbero doppio.

## Cose da sapere

- I grafici Datawrapper vengono messi in cache in `assets/data/grafici/<id>-<v>.json`
  (titolo, fonte, note, righe del CSV). Se cambi versione del grafico cambia l'URL e il
  build scarica la nuova; se modifichi un grafico senza cambiare versione, lancia
  `python3 tools/datawrapper.py --refresh` e committa.
- Le card social non vengono rigenerate se esistono: dopo un cambio di titolo, cancella
  `assets/social/<slug>.png` (o `og_card.py --force` per tutte).
- Date e autori stanno solo nella byline. La data dell'articolo 08 è un segnaposto
  (`<!-- data da confermare -->`) finché non viene confermata.
- Non c'è GA4 e non deve tornare: Umami è cookieless e non richiede banner di consenso.
- Dettagli sugli script, i file generati e le opzioni: `tools/README.md`.
