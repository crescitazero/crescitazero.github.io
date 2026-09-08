# Build del sito

Tre script preparano quello che le pagine non contengono a mano: le anteprime
social, i dati dei grafici e tutto quello che si può dedurre dalle pagine —
tag nel `<head>`, navigazione tra episodi, versioni Markdown, feed, sitemap.

| Script | Cosa fa |
| --- | --- |
| `og_card.py` | Crea le card 1200×630 in `assets/social/`, una per pagina |
| `datawrapper.py` | Scarica in `assets/data/grafici/` titolo, fonte e dati dei grafici incorporati |
| `md.py` | Converte l'HTML di un articolo in Markdown (e in HTML ripulito per il feed) |
| `build.py` | Usa gli altri tre e scrive tutto il resto |

Tutto parte dalla pagina stessa: `<title>`, `<meta name="description">`,
l'occhiello `<p class="meta">` e — per data, autori e minuti di lettura — la
byline `<p class="byline">`. **Per un nuovo articolo non c'è niente da
configurare e niente da aggiornare a mano**: basta che quegli elementi ci
siano, il build fa il resto (card, meta tag, JSON-LD, `.md`, feed, sitemap,
`llms.txt`, navigazione precedente/successivo, elenco nella 404, e in home gli
attributi `data-umami-event` numerati sui link della lista articoli). La guida
passo-passo per un nuovo articolo è in [`CLAUDE.md`](../CLAUDE.md).

## In automatico

Il workflow [`build.yml`](../.github/workflows/build.yml) gira a ogni push su `main`
che tocca `index.html`, `404.html`, `articoli/*.html`, `assets/js/`, `assets/data/`
o gli script, genera le card mancanti, riscrive le pagine e i file generati e
committa il risultato. Non serve fare nulla a mano.

Perché possa committare, in *Settings → Actions → General → Workflow permissions*
deve essere selezionato **Read and write permissions**.

## A mano

```bash
python3 -m pip install Pillow
python3 tools/og_card.py       # genera solo le card mancanti
python3 tools/datawrapper.py   # scarica solo i grafici mancanti
python3 tools/build.py         # aggiorna pagine e file generati
```

Altre opzioni:

- `og_card.py --list` — elenca le card previste senza generarle
- `og_card.py --force` — rigenera anche quelle già esistenti (dopo un cambio di stile)
- `og_card.py --prune` — elimina le card di pagine rinominate o cancellate
- `datawrapper.py --list` — elenca i grafici trovati nelle pagine, con il titolo
- `datawrapper.py --refresh` — riscarica tutti i grafici (dopo una nuova versione)
- `datawrapper.py --prune` — elimina le cache di grafici non più incorporati
- `build.py --check` — verifica soltanto, esce con 1 se qualcosa è da aggiornare
- `build.py --no-card` — salta la generazione delle card (utile in locale senza Pillow aggiornato)

## `.nojekyll`

Alla radice c'è un file vuoto `.nojekyll`. Senza, GitHub Pages passerebbe il
sito attraverso Jekyll, che tratta i `.md` come sorgenti da convertire: i
gemelli `articoli/<slug>.md` diventerebbero `articoli/<slug>.html` e
**sovrascriverebbero gli articoli veri**. Il file non va cancellato. `build.py`
lo ricrea se sparisce.

## Cosa scrive `build.py` dentro le pagine

Tre blocchi delimitati da commenti, tutti idempotenti: rilanciare lo script li
riscrive invece di duplicarli. Non modificarli a mano — cambia la pagina e
rilancia.

**`<!-- build: ... -->` … `<!-- /build -->`, nel `<head>`**

- `<link rel="canonical">` e `<meta name="robots">` (sulla 404 `noindex, follow`);
- `<meta name="author">` con gli autori letti dalla byline;
- gli alternati: il feed RSS, il gemello `.md` (solo articoli), `llms.txt` come
  `rel="describedby"`, più `apple-touch-icon`;
- tag `og:` e `twitter:` con la card della pagina (non sulla 404);
- `article:published_time` / `article:modified_time` e `article:author` (solo articoli);
- **un solo** `<script type="application/ld+json">` per pagina: sulla home un
  `@graph` con `WebSite`, `Organization` e i due `Person` (letti dalla sezione
  Autori della home), sugli articoli `Article` + `BreadcrumbList`, sulla 404 un
  `WebPage`. `dateModified` vale quanto `datePublished`: non abbiamo una data di
  revisione affidabile e non ne inventiamo una da git;
- lo script di Umami (`analyticsprogetti.lorenzoruffino.com`, con `data-domains`);
- `<script defer src="/assets/js/tracking.js">`, in percorso assoluto così vale
  sia dalla root sia da `/articoli/`.

**`/* build:nav */` … `/* /build:nav */`, in fondo al `<style>`**

Lo stile della navigazione di serie, negli stessi colori del resto della pagina
(`--line`, `--muted`, `--accent`).

**`<!-- build:nav -->` … `<!-- /build:nav -->`, dopo `</article>`**

I link «← Articolo precedente» e «Articolo successivo →», ordinati per data di
pubblicazione: il primo episodio non ha il precedente, l'ultimo il successivo. I
link portano `data-umami-event="series_nav_click"` con la direzione, quindi li
conta Umami da solo (vedi lo schema in `assets/js/tracking.js`).

La 404 ha un quarto blocco, `<!-- build:elenco -->`, con tutti gli articoli in
ordine di pubblicazione decrescente.

Oltre a questo lo script fa un po' di pulizia, sempre idempotente: migra il
vecchio blocco `<!-- social -->` (generato dal defunto `social-meta.py`), toglie
gli script di analytics messi a mano fuori dal blocco e i vecchi `<script>`
inline di tracciamento, uniforma il `data-article` del `<body>` allo slug della
pagina e dà agli iframe Datawrapper il **titolo vero del grafico** al posto del
generico `title="Grafico CrescitaZero"`. Gli snippet Datawrapper di 01–05 e il
rilascio programmato di 01/02 restano dove sono.

I titoli degli iframe già scritti a mano (per esempio quelli di 01) non vengono
toccati: si sostituiscono solo quelli mancanti o generici.

## Cosa scrive `build.py` fuori dalle pagine

| File | Cosa contiene |
| --- | --- |
| `articoli/<slug>.md` | Il gemello Markdown dell'articolo: front matter, testo, tabelle dei grafici |
| `robots.txt` | Tutti i crawler ammessi, quelli degli assistenti dichiarati uno per uno |
| `sitemap.xml` | Home e articoli, `lastmod` = data di pubblicazione |
| `feed.xml` | RSS 2.0 con `content:encoded`, autori in `dc:creator`, date a mezzogiorno di Roma |
| `articoli.json` | L'indice del sito leggibile da una macchina, grafici compresi |
| `llms.txt` | La guida sintetica per i modelli linguistici, sotto i 5 KB |
| `llms-full.txt` | Tutti gli articoli in Markdown in un file solo |

Nei `.md` ogni iframe Datawrapper diventa titolo del grafico, introduzione,
tabella dei dati e riga con fonte, link al grafico interattivo e link al CSV. La
tabella compare solo se sta in 40 righe e 8 colonne, altrimenti restano i link.
Nel feed, lo stesso iframe diventa un paragrafo con titolo e link.

`llms.txt` deve restare una guida: se supera i 5 KB le description degli
articoli si riducono automaticamente alla prima frase.

## I dati dei grafici

`datawrapper.py` legge gli iframe delle pagine e, per ogni grafico, scarica due
endpoint pubblici di `datawrapper.dwcdn.net`:

- `<id>/<versione>/embed.json` — titolo, tipo, introduzione, note, fonte;
- `<id>/<versione>/dataset.csv` — i dati.

Il risultato finisce in `assets/data/grafici/<id>-<versione>.json`, che **va
committato**. Come per le card, si scarica solo quello che manca: `build.py` usa
la cache e, se un file manca, prova a scaricarlo una volta con 15 secondi di
timeout; se non ci riesce lo segnala e prosegue senza dati per quel grafico,
senza rompere il build. In CI la cache c'è già, quindi il workflow non ha
bisogno della rete.

Quando si aggiorna un grafico su Datawrapper cambia il numero di versione
nell'URL dell'iframe: incollato il nuovo embed, il build scarica da solo il file
nuovo. `datawrapper.py --prune` toglie le cache dei grafici non più usati,
`--refresh` riscarica tutto (serve solo se cambia un titolo o una fonte senza
che cambi la versione).

I titoli con il suffisso « (Copy) », che Datawrapper aggiunge ai grafici
duplicati, vengono ripuliti in fase di build: se il grafico esiste ancora solo
come copia, conviene rinominarlo anche su Datawrapper.

## Eventi

Il tracciamento sta tutto in [`assets/js/tracking.js`](../assets/js/tracking.js):
in testa al file c'è lo schema completo degli eventi — nome, quando scattano,
proprietà — ed è quella la documentazione da tenere aggiornata.

In breve: i click su link e bottoni sono **dichiarativi** (attributi
`data-umami-event` / `data-umami-event-<proprietà>` scritti nell'HTML, Umami li
manda da solo: `article_open`, `newsletter_cta_click`, `nav_click`,
`contact_click`, `series_nav_click`), mentre lettura e interazione sono mandati
da `tracking.js` (`read_depth`, `read_time`, `article_complete`, `chart_view`,
`outbound_click`, `copy_text`). Un elemento con `data-umami-event` non va mai
tracciato anche da `tracking.js`, altrimenti conta doppio.

## Note

Il font delle card è scelto tra quelli presenti sul sistema — Helvetica Neue su
macOS, Liberation Sans sul runner Linux. Sono metricamente compatibili, quindi le
card vengono uguali da entrambe le parti. Le card esistenti non vengono comunque
riscritte senza `--force`.

Nessuno script usa librerie esterne oltre a Pillow (solo per le card): la
conversione in Markdown e la pulizia dell'HTML sono scritte con `html.parser`
della libreria standard, così il workflow resta quello che è.
