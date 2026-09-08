# Anteprime social

Due script generano quello che serve a X, Facebook, LinkedIn, WhatsApp e Telegram
per mostrare l'anteprima di un link del sito.

| Script | Cosa fa |
| --- | --- |
| `og_card.py` | Crea le card 1200×630 in `assets/social/`, una per pagina |
| `social-meta.py` | Inserisce i tag `og:` e `twitter:` nel `<head>` di ogni pagina |

Entrambi leggono i dati dalla pagina stessa: `<title>`, `<meta name="description">`
e l'occhiello `<p class="meta">`. Per un nuovo articolo non c'è niente da
configurare: basta che quei tre elementi ci siano.

## In automatico

Il workflow [`anteprime-social.yml`](../.github/workflows/anteprime-social.yml) gira a
ogni push su `main` che tocca `index.html` o `articoli/*.html`, genera le card
mancanti, aggiorna i meta tag e committa il risultato. Non serve fare nulla a mano.

Perché possa committare, in *Settings → Actions → General → Workflow permissions*
deve essere selezionato **Read and write permissions**.

## A mano

```bash
python3 -m pip install Pillow
python3 tools/og_card.py        # genera solo le card mancanti
python3 tools/social-meta.py    # aggiorna i meta tag
```

Altre opzioni:

- `og_card.py --list` — elenca le card previste senza generarle
- `og_card.py --force` — rigenera anche quelle già esistenti (dopo un cambio di stile)
- `og_card.py --prune` — elimina le card di pagine rinominate o cancellate
- `social-meta.py --check` — verifica soltanto, esce con 1 se qualcosa è da aggiornare

## Note

Il blocco dei meta tag è delimitato da commenti `<!-- social: ... -->`, quindi
rilanciare lo script aggiorna i tag invece di duplicarli. Non modificarlo a mano:
cambia il `<title>` o la `description` della pagina e rilancia.

Il font è scelto tra quelli presenti sul sistema — Helvetica Neue su macOS,
Liberation Sans sul runner Linux. Sono metricamente compatibili, quindi le card
vengono uguali da entrambe le parti. Le card esistenti non vengono comunque
riscritte senza `--force`.
