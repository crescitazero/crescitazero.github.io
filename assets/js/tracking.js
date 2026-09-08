/*
 * CrescitaZero — tracciamento condiviso (Umami)
 * ---------------------------------------------------------------------------
 * Unico file per tutte le pagine. Vanilla JS, nessuna dipendenza. Se Umami non
 * c'è (adblocker, offline, sviluppo in locale) tutto degrada in silenzio: gli
 * eventi vengono semplicemente scartati e in console non compare nulla.
 *
 * Ogni evento porta con sé due proprietà comuni:
 *   article — lo slug della pagina, dall'attributo data-article del <body>
 *             (per la home vale "home"); lo inietta tools/build.py
 *   page    — "home" oppure "article"
 *
 * SCHEMA DEGLI EVENTI
 * ===========================================================================
 *
 * Dichiarativi — li manda Umami da solo sui click, leggendo gli attributi
 * data-umami-event / data-umami-event-<proprietà> presenti nell'HTML.
 * Questo file NON li tocca mai (altrimenti conterebbero doppio).
 *
 *   article_open         click su un articolo dalla lista in home
 *                        · article  slug dell'articolo aperto
 *                        · position posizione nella lista, 1 = il più recente
 *   newsletter_cta_click click su un link/bottone di iscrizione a una newsletter
 *                        · author   ruffino | bidut
 *                        · location hero | autori | contatti | article
 *   nav_click            click sulla navigazione in alto della home
 *                        · target   articoli | progetto | metodo | autori
 *   contact_click        click su un contatto (email, LinkedIn, X)
 *                        · target   email | linkedin | x
 *                        · author   ruffino | bidut (per LinkedIn e X)
 *                        · location id della sezione (autori, contatti)
 *   series_nav_click     click sui link «articolo precedente / successivo».
 *                        · direction prev | next
 *                        NON ancora presente nelle pagine: i link prev/next
 *                        arrivano in una fase successiva e useranno
 *                        data-umami-event="series_nav_click"
 *                        data-umami-event-direction="prev|next".
 *
 * Via JavaScript — li manda questo file.
 *
 *   read_depth       la pagina è stata scrollata fino a una soglia
 *                    · depth 25 | 50 | 75 | 100 (una volta per soglia)
 *   read_time        tempo passato sulla pagina con la scheda in primo piano
 *                    · seconds 30 | 60 | 120 | 300 (una volta per soglia)
 *   article_complete l'articolo è stato letto per intero: depth 100 e almeno
 *                    60 secondi di lettura visibile. Una volta, solo articoli.
 *   chart_view       un grafico Datawrapper è entrato in vista per metà
 *                    · chart id del grafico (es. ySqez), una volta per grafico
 *   outbound_click   click su un link esterno privo di data-umami-event
 *                    · destination hostname di destinazione
 *                    · label       testo del link, max 80 caratteri
 *   copy_text        copia di una selezione più lunga di 40 caratteri
 *                    · length numero di caratteri copiati (max 1 ogni 5 s)
 *
 * Il file gestisce anche il ridimensionamento degli iframe Datawrapper
 * (messaggio "datawrapper-height"), che prima stava nello script inline delle
 * pagine: vale sia per gli iframe con classe .datawrapper-chart sia per quelli
 * senza.
 */

(() => {
  "use strict";

  const body = document.body;
  if (!body) return;

  const article = body.dataset.article || "";
  const page = article === "home" ? "home" : "article";
  const isArticle = page === "article";

  /** Manda l'evento solo se Umami è stato caricato davvero. */
  const track = (name, data) => {
    try {
      if (window.umami && typeof window.umami.track === "function") {
        window.umami.track(name, Object.assign({ article, page }, data || {}));
      }
    } catch (e) {
      /* mai rumore in console per colpa delle statistiche */
    }
  };

  // --- profondità di scroll -------------------------------------------------

  const SOGLIE_DEPTH = [25, 50, 75, 100];
  const depthFatte = new Set();
  let fondoRaggiunto = false;

  const misuraDepth = () => {
    const disponibile = document.documentElement.scrollHeight - window.innerHeight;
    const progresso = disponibile <= 0
      ? 100
      : Math.min(100, Math.round(window.scrollY / disponibile * 100));
    SOGLIE_DEPTH.forEach((soglia) => {
      if (progresso >= soglia && !depthFatte.has(soglia)) {
        depthFatte.add(soglia);
        track("read_depth", { depth: soglia });
      }
    });
    if (progresso >= 100) fondoRaggiunto = true;
    verificaCompletamento();
  };

  window.addEventListener("scroll", misuraDepth, { passive: true });
  window.addEventListener("resize", misuraDepth, { passive: true });
  window.addEventListener("load", misuraDepth, { once: true });

  // --- tempo di lettura (solo con la scheda visibile) -----------------------

  const SOGLIE_TEMPO = [30, 60, 120, 300];
  const tempoFatte = new Set();
  let secondiVisibili = 0;
  let completoMandato = false;
  let orologio = null;

  const verificaCompletamento = () => {
    if (completoMandato || !isArticle) return;
    if (fondoRaggiunto && secondiVisibili >= 60) {
      completoMandato = true;
      track("article_complete");
      fermaOrologioSeFinito();
    }
  };

  const fermaOrologioSeFinito = () => {
    const tempiFiniti = tempoFatte.size === SOGLIE_TEMPO.length;
    const completoFinito = !isArticle || completoMandato;
    if (orologio && tempiFiniti && completoFinito) {
      window.clearInterval(orologio);
      orologio = null;
    }
  };

  const battito = () => {
    if (document.visibilityState !== "visible") return;
    secondiVisibili += 1;
    SOGLIE_TEMPO.forEach((soglia) => {
      if (secondiVisibili >= soglia && !tempoFatte.has(soglia)) {
        tempoFatte.add(soglia);
        track("read_time", { seconds: soglia });
      }
    });
    verificaCompletamento();
    fermaOrologioSeFinito();
  };

  orologio = window.setInterval(battito, 1000);

  // prima misura appena il file è eseguito: le pagine cortissime sono già al 100%
  misuraDepth();

  // --- grafici Datawrapper entrati in vista ---------------------------------

  /** Da https://datawrapper.dwcdn.net/ySqez/2/ ricava "ySqez". */
  const idGrafico = (frame) => {
    const src = frame.getAttribute("src") || "";
    const m = src.match(/datawrapper\.dwcdn\.net\/([^/?#]+)/);
    if (m) return m[1];
    const id = frame.id || "";
    return id.replace(/^datawrapper-chart-/, "") || "sconosciuto";
  };

  const grafici = () => Array.prototype.slice
    .call(document.querySelectorAll("iframe"))
    .filter((frame) => (frame.getAttribute("src") || "").indexOf("datawrapper") !== -1);

  if (typeof window.IntersectionObserver === "function") {
    const visti = new Set();
    const osservatore = new window.IntersectionObserver((voci) => {
      voci.forEach((voce) => {
        if (!voce.isIntersecting) return;
        const chart = idGrafico(voce.target);
        osservatore.unobserve(voce.target);
        if (visti.has(chart)) return;
        visti.add(chart);
        track("chart_view", { chart });
      });
    }, { threshold: 0.5 });
    grafici().forEach((frame) => osservatore.observe(frame));
  }

  // --- click sui link esterni ----------------------------------------------

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!target || typeof target.closest !== "function") return;
    // i link già marcati li conta Umami da solo: qui li ignoriamo sempre
    if (target.closest("[data-umami-event]")) return;
    const link = target.closest("a[href]");
    if (!link) return;
    if (link.protocol !== "http:" && link.protocol !== "https:") return;
    if (link.hostname === window.location.hostname) return;
    track("outbound_click", {
      destination: link.hostname,
      label: (link.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80),
    });
  });

  // --- testo copiato --------------------------------------------------------

  let ultimaCopia = 0;
  document.addEventListener("copy", () => {
    const selezione = window.getSelection ? String(window.getSelection()) : "";
    if (selezione.length <= 40) return;
    const ora = Date.now();
    if (ora - ultimaCopia < 5000) return;
    ultimaCopia = ora;
    track("copy_text", { length: selezione.length });
  });

  // --- altezza degli iframe Datawrapper ------------------------------------

  window.addEventListener("message", (event) => {
    const altezze = event.data && event.data["datawrapper-height"];
    if (!altezze) return;
    // vale sia per gli iframe con classe .datawrapper-chart sia per quelli senza
    const frames = document.querySelectorAll("iframe");
    Array.prototype.forEach.call(frames, (frame) => {
      if (frame.contentWindow !== event.source) return;
      Object.keys(altezze).forEach((chiave) => {
        frame.style.height = String(altezze[chiave]) + "px";
      });
    });
  });
})();
