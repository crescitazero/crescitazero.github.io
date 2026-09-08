# Build del sito

Due script preparano quello che le pagine non contengono a mano: le anteprime
social e il blocco di tag e script nel `<head>`.

| Script | Cosa fa |
| --- | --- |
| `og_card.py` | Crea le card 1200×630 in `assets/social/`, una per pagina |
| `build.py` | Scrive nel `<head>` il blocco con canonical, `og:`, `twitter:`, autori, data e script di tracciamento |

Entrambi leggono i dati dalla pagina stessa: `<title>`, `<meta name="description">`,
l'occhiello `<p class="meta">` e — per data e autori — la byline `<p class="byline">`.
Per un nuovo articolo non c'è niente da configurare: basta che quegli elementi ci siano.

## In automatico

Il workflow [`build.yml`](../.github/workflows/build.yml) gira a ogni push su `main`
che tocca `index.html`, `articoli/*.html`, `assets/js/` o gli script, genera le card
mancanti, aggiorna il `<head>` e committa il risultato. Non serve fare nulla a mano.

Perché possa committare, in *Settings → Actions → General → Workflow permissions*
deve essere selezionato **Read and write permissions**.

## A mano

```bash
python3 -m pip install Pillow
python3 tools/og_card.py   # genera solo le card mancanti
python3 tools/build.py     # aggiorna il <head> di tutte le pagine
```

Altre opzioni:

- `og_card.py --list` — elenca le card previste senza generarle
- `og_card.py --force` — rigenera anche quelle già esistenti (dopo un cambio di stile)
- `og_card.py --prune` — elimina le card di pagine rinominate o cancellate
- `build.py --check` — verifica soltanto, esce con 1 se qualcosa è da aggiornare
- `build.py --no-card` — salta la generazione delle card (utile in locale senza Pillow aggiornato)

## Cosa scrive `build.py`

Il blocco è delimitato da commenti `<!-- build: ... -->` … `<!-- /build -->`, quindi
rilanciare lo script lo riscrive invece di duplicarlo. Non modificarlo a mano: cambia
la pagina e rilancia. Dentro ci finiscono:

- `<link rel="canonical">`, tag `og:` e `twitter:` con la card della pagina;
- `<meta name="author">` con gli autori letti dalla byline;
- `article:published_time` e `article:author` (solo sugli articoli);
- lo script di Umami (`analyticsprogetti.lorenzoruffino.com`, con `data-domains`);
- `<script defer src="/assets/js/tracking.js">`, in percorso assoluto così vale
  sia dalla root sia da `/articoli/`.

Oltre a questo lo script fa un po' di pulizia, sempre idempotente: migra il vecchio
blocco `<!-- social -->` (generato dal defunto `social-meta.py`), toglie gli script
di analytics messi a mano fuori dal blocco e i vecchi `<script>` inline di
tracciamento, e uniforma il `data-article` del `<body>` allo slug della pagina
(nome file senza estensione, `home` per la homepage). Gli snippet Datawrapper di
01–05 e il rilascio programmato di 01/02 restano dove sono.

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
