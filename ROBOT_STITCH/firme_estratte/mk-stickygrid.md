# Firma estratta: `mk-stickygrid` — Sticky Grid Scroll

Matematica presa da `codrops-sticky-grid-scroll-main/src/scripts/index.js` e
riscritta per il **markup del sito**, non per il markup della demo.

La differenza e' tutta qui. Il Guest Component (fase 3) inserisce il sorgente
com'e': una sezione estranea, con il suo HTML, il suo CSS e il suo aspetto da
demo Codrops, appiccicata dentro una cantina. Riconoscibile, e non tua. Questa
firma invece prende solo i **numeri** e li fa muovere sulle tue foto, con la
tua tipografia: stesso effetto, sito unico.

## I numeri, presi uno per uno dal sorgente

| Cosa | Valore originale | Dove sta nel sorgente |
|---|---|---|
| colonne | 3, distribuite con `index % 3` | `groupItemsByColumn()` |
| direzione colonne | pari dall'alto, dispari dal basso | `fromTop = colIndex % 2 === 0` |
| distanza di partenza | `wh - (wh - grid.offsetHeight) / 2` | `gridRevealTimeline()` |
| stagger dentro la colonna | `0.06`, `from: 'end'` se scende, `'start'` se sale | idem |
| ease della comparsa | `power1.inOut` | idem |
| zoom della griglia | `scale: 2.05`, `duration: 1`, `power3.inOut` | `gridZoomTimeline()` |
| colonne laterali | `xPercent: -40` e `+40`, in parallelo (`"<"`) | idem |
| colonna centrale | `yPercent: ±40`, `duration: 0.5`, `power1.inOut`, `"-=0.5"` | idem |
| aggancio zoom dopo reveal | `"-=0.6"` | `animateGridOnScroll()` |
| aggancio del testo | `"-=0.32"`, legato a `direction === 1` | idem |
| finestra di scroll | `start: 'top 25%'`, `end: 'bottom bottom'`, `scrub: true` | idem |
| parallax del blocco | `yPercent: -100`, `ease: 'none'`, da `top bottom` a `top top` | `addParallaxOnScroll()` |
| titolo | `opacity 0 -> 1`, `0.7s`, `power1.out`, da `top 57%` | `animateTitleOnScroll()` |
| smooth scroll | `lerp: 0.08`, `wheelMultiplier: 1.4`, `lagSmoothing(0)` | `initSmoothScrolling()` |

## Prerequisito

Serve una sezione che abbia **almeno 6 media reali gia' presenti**. Se non
c'e', la firma non si applica e si usa il fallback dello slot: non si creano
griglie finte per far posto all'effetto.

## Codice da inserire invariato nel kit

```js
/* mk-stickygrid — SCROLL GRID SOSPESA.
   Matematica di Codrops Sticky Grid Scroll applicata ai media del sito.
   Le foto restano le tue: qui si muovono soltanto. */
(function () {
  const sezioni = gsap.utils.toArray('section[data-reference-slot]').filter((s) =>
    !s.classList.contains('mk-pin') &&
    !s.classList.contains('mk-cinema') &&
    s.querySelectorAll('img, picture, video').length >= 6);
  const sez = document.querySelector('.mk-stickygrid') || sezioni[0];
  if (!sez) return;
  sez.classList.add('mk-stickygrid');

  const media = gsap.utils.toArray(sez.querySelectorAll('img, picture, video'));
  const griglia = media[0].parentElement.parentElement || sez;
  const titolo = sez.querySelector('h1, h2, h3');
  const testo = sez.querySelector('p');

  /* 3 colonne, come l'originale: index % 3 */
  const colonne = [[], [], []];
  media.forEach((el, i) => colonne[i % 3].push(el));

  /* distanza di partenza: la griglia parte tutta fuori dalla viewport */
  const wh = window.innerHeight;
  const dy = wh - (wh - griglia.offsetHeight) / 2;

  const tl = gsap.timeline({
    scrollTrigger: { trigger: sez, start: 'top 25%', end: 'bottom bottom', scrub: true }
  });

  /* 1. comparsa: colonne pari dall'alto, dispari dal basso, stagger 0.06 */
  colonne.forEach((col, i) => {
    const dallAlto = i % 2 === 0;
    tl.from(col, {
      y: dy * (dallAlto ? -1 : 1),
      stagger: { each: 0.06, from: dallAlto ? 'end' : 'start' },
      ease: 'power1.inOut'
    }, 'reveal');
  });

  /* 2. zoom: la griglia cresce, le laterali si aprono, la centrale si divide */
  const zoom = gsap.timeline({ defaults: { duration: 1, ease: 'power3.inOut' } });
  zoom.to(griglia, { scale: 2.05 });
  zoom.to(colonne[0], { xPercent: -40 }, '<');
  zoom.to(colonne[2], { xPercent: 40 }, '<');
  zoom.to(colonne[1], {
    yPercent: (i) => (i < Math.floor(colonne[1].length / 2) ? -1 : 1) * 40,
    duration: 0.5, ease: 'power1.inOut'
  }, '-=0.5');
  tl.add(zoom, '-=0.6');

  /* 3. il testo entra mentre lo zoom finisce, e torna indietro se risali */
  if (titolo || testo) {
    tl.add(() => {
      const avanti = tl.scrollTrigger.direction === 1;
      gsap.timeline({ defaults: { overwrite: true } })
        .to(titolo || {}, { yPercent: avanti ? 0 : 12, opacity: avanti ? 1 : 0,
                            duration: 0.7, ease: 'power2.inOut' })
        .to(testo || {}, { opacity: avanti ? 1 : 0, duration: 0.4,
                           ease: 'power1.' + (avanti ? 'inOut' : 'out') }, '-=90%');
    }, '-=0.32');
  }

  /* 4. parallax d'ingresso del blocco intero */
  gsap.from(sez, {
    yPercent: -12, ease: 'none',
    scrollTrigger: { trigger: sez, start: 'top bottom', end: 'top top', scrub: true }
  });
})();
```

## Cosa e' stato adattato, e perche'

- `yPercent: -100` sul wrapper e' diventato `-12` sulla sezione. L'originale
  ha un wrapper interno alto due schermate fatto apposta; una sezione del sito
  non ce l'ha, e -100 la sparerebbe fuori pagina.
- `preloadImages()` e `document.body.classList.remove('loading')` non servono:
  il sito non ha stato di caricamento e le foto sono gia' nel DOM.
- Gli `import` ES (`lenis`, `gsap`, `gsap/ScrollTrigger`) non ci sono: nel kit
  GSAP e ScrollTrigger arrivano dal CDN come globali.
- `opacity` e `pointerEvents` su descrizione e bottone valgono solo se quegli
  elementi esistono davvero; qui la firma li cerca e li salta se mancano.
- Lenis resta come sta gia' nel kit (`lerp 0.08`, `wheelMultiplier 1.4`,
  `lagSmoothing(0)`): sono gli stessi valori dell'originale.
