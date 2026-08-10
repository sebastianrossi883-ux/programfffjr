# Kit motion canonico da inserire

Inserisci questo unico blocco script una sola volta, letteralmente invariato, subito prima di `</body>`. Non riassumere, non riscrivere e non sostituire il codice. La pipeline ne verifichera' lo SHA256 e ripristinera' l'originale se viene alterato.

SHA256: `ecd6fec3d48d6bf09112d11cf15a0a9954d6163edc5e99d3b28a05bb8f20d9b6`

<script id="stitch-motion-kit">
/*! stitch-motion-kit:inizio — SENTINELLA, NON RIMUOVERE.
   Il tag di apertura di questo blocco e' citato anche nella prosa qui sopra
   (dentro il divieto "questo blocco non si tocca"). Una regex che cerchi
   solo quel tag aggancia LA CITAZIONE e inietta prosa italiana dentro uno
   script: SyntaxError alla prima riga, kit mai eseguito. Successo il
   3 ago 2026. Questa riga e' l'ancora univoca che permette all'estrattore
   di riconoscere il blocco VERO — per questo non ripete il tag alla
   lettera: lo ricreerebbe il problema che serve a evitare. */
gsap.registerPlugin(ScrollTrigger);

/* 0. CURVE DI EASING CRAFTED (Emil Kowalski) — le built-in GSAP sono troppo
   deboli: mancano del carattere che rende un'animazione intenzionale. Qui
   registro tre curve col carattere giusto. Se il plugin CustomEase e'
   caricato uso le cubic-bezier esatte; se non c'e', ripiego su built-in forti
   con lo STESSO nome, cosi' il resto del kit funziona identico in entrambi i
   casi. `registerEase` e `parseEase` sono nel core GSAP, non serve plugin. */
if (typeof CustomEase !== 'undefined') {
  gsap.registerPlugin(CustomEase);
  CustomEase.create('kOut',    '0.23, 1, 0.32, 1');     /* ease-out forte, editoriale */
  CustomEase.create('kInOut',  '0.77, 0, 0.175, 1');    /* ease-in-out drammatico */
  CustomEase.create('kDrawer', '0.32, 0.72, 0, 1');     /* glide morbido, lussuoso */
} else {
  gsap.registerEase('kOut',    gsap.parseEase('power4.out'));
  gsap.registerEase('kInOut',  gsap.parseEase('power4.inOut'));
  gsap.registerEase('kDrawer', gsap.parseEase('power3.out'));
}

/* 1. SMOOTH SCROLL — dietro un controllo: se Lenis non carica, il resto del
   kit deve continuare a funzionare invece di morire su questa riga */
if (typeof Lenis !== 'undefined') {
  const lenis = new Lenis({ duration: 1.1, smoothWheel: true });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((t) => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
}

/* 1.5 AUTO-TARGETING — E' QUESTO CHE RENDE IL KIT AUTOSUFFICIENTE.
   Il kit anima le classi `mk-*`. Se tu le applichi al markup (come chiesto
   sopra) questo blocco non tocca NIENTE: salta ogni elemento che sta dentro
   un elemento gia' marcato. Ma se una sezione resta senza classi, il kit se
   le assegna da solo invece di restare inerte: cosi' il movimento non
   dipende piu' dal fatto che tu ti ricordi di marcare ogni elemento.
   Non cambia il layout: aggiunge classi, piu' le due proprieta' che il
   parallax richiede per non scoprire una fascia vuota. */
(() => {
  const sezioni = [...document.querySelectorAll('section[data-reference-slot]')];
  if (!sezioni.length) return;
  /* libero = nessun ANTENATO gia' marcato (l'elemento stesso puo' avere
     piu' classi: un titolo puo' essere insieme .mk-hero e .mk-letters) */
  const libero = (el) => el && !(el.parentElement && el.parentElement.closest('[class*="mk-"]'));
  const marca = (el, cls) => { if (libero(el)) el.classList.add(cls); };

  const hero = sezioni[0];
  hero.querySelectorAll('h1, h2, p, a').forEach((el) => marca(el, 'mk-hero'));
  marca(hero.querySelector('h1, h2'), 'mk-letters');

  /* LA SEZIONE INCHIODATA SI SCEGLIE PER PRIMA, non per ultima.
     Dentro una sezione in pin, le ScrollTrigger dei figli calcolerebbero
     posizioni sbagliate: GSAP le vuole dichiarate con `pinnedContainer`.
     Invece di complicare ogni famiglia, quella sezione tiene SOLO il suo
     movimento di regia (il contenuto che avanza mentre la sezione resta
     ferma, che e' gia' l'effetto piu' cinematografico del kit) e viene
     esclusa dalle altre classi. */
  let sezionePin = document.querySelector('.mk-pin');
  if (!sezionePin) {
    const adatte = sezioni.slice(1).filter(
      (s) => s.offsetHeight >= window.innerHeight * 0.8 && s.firstElementChild);
    sezionePin = adatte[Math.floor(adatte.length / 2)] || null;
    if (sezionePin) {
      sezionePin.classList.add('mk-pin');
      sezionePin.firstElementChild.classList.add('mk-pin-move');
    }
  }

  sezioni.slice(1).forEach((sec) => {
    if (sec.classList.contains('mk-pin')) return;
    sec.querySelectorAll('h1, h2').forEach((el) => marca(el, 'mk-letters'));
    sec.querySelectorAll('h3, h4').forEach((el) => marca(el, 'mk-line'));
    sec.querySelectorAll('p, li, blockquote, figcaption').forEach((el) => marca(el, 'mk-reveal'));
    sec.querySelectorAll('img, video, picture').forEach((media) => {
      const wrap = media.parentElement;
      if (!libero(wrap) || /\bmk-/.test(wrap.className || '')) return;
      if (wrap.classList.contains('absolute') && wrap.classList.contains('inset-0')) {
        wrap.classList.add('mk-parallax');
        Object.assign(media.style, { position: 'absolute', left: '0', width: '100%',
                                     height: '130%', top: '-15%', objectFit: 'cover' });
      } else {
        wrap.classList.add('mk-scrub');
      }
    });
  });
})();

/* 2. HERO — UNICA animazione che parte al caricamento (e' gia' a schermo) */
gsap.from('.mk-hero', {
  y: 38, opacity: 0, duration: 1.3, ease: 'kInOut',
  stagger: 0.1
});

/* 3. REVEAL A MASCHERA — non semplice opacity: clip guidato dallo scroll.
   Parte da scale 0.96, non da scale 0: "niente nel mondo reale appare dal
   nulla" (Emil Kowalski). Anche una scala appena percettibile rende l'entrata
   naturale invece che teleportata. */
gsap.utils.toArray('.mk-reveal').forEach((el) => {
  gsap.fromTo(el,
    { clipPath: 'inset(0% 0% 0% 100%)', y: 38, opacity: 0, scale: 0.96 },
    { clipPath: 'inset(0% 0% 0% 0%)', y: 0, opacity: 1, scale: 1,
      duration: 1.3, ease: 'kInOut',
      scrollTrigger: { trigger: el, start: 'top 82%' } });
});

/* 4. TITOLI RIGA PER RIGA */
gsap.utils.toArray('.mk-line').forEach((el) => {
  gsap.from(el, {
    yPercent: 110, opacity: 0, duration: 1.3, ease: 'kInOut',
    stagger: 0.1,
    scrollTrigger: { trigger: el, start: 'top 88%' }
  });
});

/* 5. PARALLAX — segue la posizione dello scroll (scrub).
   `fromTo` simmetrico, NON `to`: con `to` l'immagine parte gia' spostata
   (a pagina caricata il trigger e' gia' a meta' corsa) e scopre un bordo
   vuoto. Con -10 -> +10 il punto centrale e' zero. */
gsap.utils.toArray('.mk-parallax').forEach((el) => {
  const media = el.querySelector('img, video, picture') || el;
  gsap.fromTo(media,
    { yPercent: -10 },
    { yPercent: 10, ease: 'none',
      scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top',
                       scrub: true } });
});

/* 6. SCRUB CINEMATICO — il media si APRE col dito sullo scroll (momento wow).
   clip-path + scale legati alla POSIZIONE dello scroll, non al tempo: e' la
   regia Awwwards che chiedi, elegante perche' scrub e non fade. */
gsap.utils.toArray('.mk-scrub').forEach((el) => {
  const media = el.querySelector('img, video, picture, canvas') || el;
  gsap.fromTo(media,
    { clipPath: 'inset(0% 0% 0% 100%)', scale: 1.18 },
    { clipPath: 'inset(0% 0% 0% 0%)', scale: 1, ease: 'none',
      scrollTrigger: { trigger: el, start: 'top 90%', end: 'center center',
                       scrub: 1.0 } });
});

/* 7. SEZIONE INCHIODATA — la sezione resta ferma mentre il suo contenuto
   avanza. E' il momento di regia piu' cinematografico: garantito UNA volta,
   sulla prima sezione marcata `.mk-pin`; pin multipli sono ignorati. */
gsap.utils.toArray('.mk-pin').slice(0, 1).forEach((el) => {
  const dentro = el.querySelector('.mk-pin-move') || el.firstElementChild;
  if (!dentro) return;
  gsap.to(dentro, {
    yPercent: -18, ease: 'none',
    scrollTrigger: { trigger: el, start: 'top top', end: '+=90%',
                     pin: true, scrub: 1.0, anticipatePin: 1 }
  });
});

/* 8. TITOLI LETTERA PER LETTERA — su OGNI titolo marcato `.mk-letters`, non
   solo sul primo: e' la differenza tra "un sito con un bel titolo" e "un sito
   con SplitText sui titoli" (Kettmeir). Dietro un controllo: se SplitText non
   c'e', ogni titolo resta semplicemente visibile, non sparisce. */
if (typeof SplitText !== 'undefined') {
  gsap.utils.toArray('.mk-letters').forEach((el) => {
    const split = new SplitText(el, { type: 'chars' });
    gsap.from(split.chars, {
      yPercent: 100, opacity: 0, duration: 1.3, ease: 'kInOut',
      stagger: 0.05,
      scrollTrigger: { trigger: el, start: 'top 85%' }
    });
  });
}

/* 9. COREOGRAFIE COMPOSTE — LA DIFFERENZA FRA "SI MUOVE" E "E' DIRETTO".
   Misurato il 2 ago 2026 confrontando kettmeir.com col nostro sito generato:
   loro 27 `.timeline(`, noi 1 — pur avendo PIU' scrub di loro (24 contro 9).
   Un `to()` isolato e' una manopola: una proprieta' legata allo scroll. Una
   timeline e' una REGIA: piu' cose in sequenza, con sfasamenti. E' li' che
   stava tutto il divario di "wow", non nella tecnologia (Lenis, parallax e
   zoom c'erano gia'). Questi due set-piece si auto-assegnano: non dipendono
   dalla buona volonta' di Stitch. */

/* 9A. SET-PIECE PINNATO — zoom, apertura, titolo e didascalia in UNA timeline:
   quattro movimenti sfasati sullo stesso scroll, non quattro effetti scollegati. */
(() => {
  let cine = document.querySelector('.mk-cinema');
  if (!cine) {
    const cand = gsap.utils.toArray('section[data-reference-slot]').filter((s) =>
      !s.classList.contains('mk-pin') && s.querySelector('img'));
    cine = cand[Math.min(2, cand.length - 1)] || null;
    if (cine) cine.classList.add('mk-cinema');
  }
  if (!cine) return;
  const media = cine.querySelector('img, video, picture');
  if (!media) return;
  const titolo = cine.querySelector('h1, h2, h3');
  const testo = cine.querySelector('p');
  const tl = gsap.timeline({
    scrollTrigger: { trigger: cine, start: 'top top', end: '+=120%',
                     pin: true, scrub: 1.0, anticipatePin: 1 }
  });
  tl.fromTo(media, { scale: 1.25, clipPath: 'inset(0% 0% 0% 100%)' },
                   { scale: 1, clipPath: 'inset(0% 0% 0% 0%)', ease: 'none' }, 0);
  if (titolo) tl.fromTo(titolo, { yPercent: 45, opacity: 0 },
                                { yPercent: 0, opacity: 1, ease: 'none' }, 0.15);
  if (testo) tl.fromTo(testo, { yPercent: 30, opacity: 0 },
                              { yPercent: 0, opacity: 1, ease: 'none' }, 0.35);
  tl.to(media, { scale: 1.06, ease: 'none' }, 0.6);
})();

/* 9B. PARALLAX A TRE STRATI — profondita' vera: i media di una stessa sezione
   scorrono a velocita' diverse DENTRO UNA SOLA timeline. L'assegnazione va
   fatta PRIMA di animare, altrimenti il forEach non trova ancora le classi. */
gsap.utils.toArray('section[data-reference-slot]').forEach((s) => {
  if (s.classList.contains('mk-cinema') || s.classList.contains('mk-pin')) return;
  if (s.querySelectorAll('img, picture, video').length >= 2) s.classList.add('mk-depth');
});
gsap.utils.toArray('.mk-depth').forEach((el) => {
  const strati = el.querySelectorAll('img, picture, video');
  if (strati.length < 2) return;
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true }
  });
  strati.forEach((img, i) => {
    const rate = Math.max(4, 10 + 6 - i * 7);
    tl.fromTo(img, { yPercent: -rate }, { yPercent: rate, ease: 'none' }, 0);
  });
});


/* MESSA A FUOCO — il media entra leggermente sfocato e si mette a fuoco
   sullo scroll. Elegante perche' non muove niente: cambia solo la nitidezza. */
gsap.utils.toArray('.mk-blur').forEach((el) => {
  const media = el.querySelector('img, video, picture') || el;
  const didascalia = el.querySelector('figcaption, p');
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'top 92%', end: 'center 60%',
                     scrub: 1.0 }
  });
  tl.fromTo(media, { filter: 'blur(14px)', scale: 1.06 },
                   { filter: 'blur(0px)', scale: 1, ease: 'none' }, 0);
  /* la didascalia sale DOPO che il media e' a fuoco: prima si vede, poi si legge */
  if (didascalia) tl.fromTo(didascalia, { yPercent: 24, opacity: 0 },
                                        { yPercent: 0, opacity: 1, ease: 'none' }, 0.3);
});

/* MONOCROMIA RISOLTA — il media torna al colore seguendo lo scroll. */
gsap.utils.toArray('.mk-monochrome').forEach((el) => {
  const media = el.querySelector('img, video, picture') || el;
  gsap.fromTo(media,
    { filter: 'grayscale(1) contrast(0.9)', scale: 1.04 },
    { filter: 'grayscale(0) contrast(1)', scale: 1, ease: 'none',
      scrollTrigger: { trigger: el, start: 'top 92%', end: 'center 55%',
                       scrub: 1.0 } });
});

/* RAIL ORIZZONTALE — la distanza reale dipende dallo scrollWidth della rail. */
gsap.utils.toArray('.mk-horizontal-rail').forEach((el) => {
  const candidati = [...el.children].filter((child) => child.scrollWidth > el.clientWidth + 40);
  const rail = el.querySelector('[data-motion-rail], .rail, .track') || candidati[0];
  if (!rail) return;
  const distanza = () => Math.max(0, rail.scrollWidth - el.clientWidth);
  if (distanza() < 40) return;
  gsap.to(rail, {
    x: () => -distanza(), ease: 'none',
    scrollTrigger: { trigger: el, start: 'top top',
      end: () => '+=' + distanza(), pin: true, scrub: 1.0,
      anticipatePin: 1, invalidateOnRefresh: true }
  });
});

/* SIPARIO SENZA MARKUP INVENTATO — clip del media esistente con scrub. */
gsap.utils.toArray('.mk-curtain-auto').forEach((el) => {
  const media = el.querySelector('img, video, picture') || el;
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'top 90%', end: 'center 55%',
                     scrub: 1.0 }
  });
  tl.fromTo(el, { clipPath: 'inset(0% 100% 0% 0%)' },
                    { clipPath: 'inset(0% 0% 0% 0%)', ease: 'none' }, 0);
  if (media !== el) tl.fromTo(media, { scale: 1.14 },
                                      { scale: 1, ease: 'none' }, 0);
});

/* DERIVA LATERALE — due colonne che scorrono a velocita' diverse. Da' la
   sensazione di profondita' senza muovere niente in verticale. */
gsap.utils.toArray('.mk-drift').forEach((el, i) => {
  const verso = i % 2 ? 1 : -1;
  const testo = el.querySelector('h1, h2, h3, p');
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'top bottom', end: 'center center',
                     scrub: 1.0 }
  });
  tl.fromTo(el, { xPercent: verso * 7, opacity: 0.55 },
                { xPercent: 0, opacity: 1, ease: 'none' }, 0);
  /* il testo deriva in CONTROSENSO e in ritardo: e' lo sfasamento a dare
     profondita', non lo spostamento in se'. */
  if (testo) tl.fromTo(testo, { xPercent: verso * -6 },
                              { xPercent: 0, ease: 'none' }, 0.2);
});

/* SIPARIO — un pannello del colore d'accento scorre via e scopre il media.
   Serve un figlio `.mk-curtain-panel` posizionato sopra il media. */
gsap.utils.toArray('.mk-curtain').forEach((el) => {
  const panel = el.querySelector('.mk-curtain-panel');
  if (!panel) return;
  const media = el.querySelector('img, video, picture');
  const titolo = el.querySelector('h1, h2, h3');
  const tl = gsap.timeline({ scrollTrigger: { trigger: el, start: 'top 78%' } });
  tl.to(panel, { scaleY: 0, transformOrigin: 'top center',
                 duration: 1.3, ease: 'kInOut' }, 0);
  /* il media si assesta MENTRE il sipario scorre: sono simultanei ma di durata
     diversa, ed e' questo che fa sembrare il movimento "girato" e non "acceso". */
  if (media) tl.fromTo(media, { scale: 1.12 },
                              { scale: 1, duration: 1.3 * 1.25, ease: 'kInOut' }, 0);
  if (titolo) tl.fromTo(titolo, { yPercent: 40, opacity: 0 },
                                { yPercent: 0, opacity: 1, duration: 1.3, ease: 'kInOut' },
                                1.3 * 0.45);
});

/* CONTROTEMPO — il testo sale mentre il media scende: le due meta' della
   sezione si muovono in direzioni opposte, agganciate allo scroll. */
gsap.utils.toArray('.mk-counter').forEach((el) => {
  const testo = el.querySelector('.mk-counter-text');
  const media = el.querySelector('.mk-counter-media');
  if (!testo || !media) return;
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top',
                     scrub: 1.0 }
  });
  tl.fromTo(testo, { yPercent: 10 }, { yPercent: -10, ease: 'none' }, 0);
  tl.fromTo(media, { yPercent: -5 }, { yPercent: 5, ease: 'none' }, 0);
  /* terzo strato a velocita' intermedia: con due soli elementi il controtempo
     si legge come "una cosa sale, una scende"; col terzo diventa profondita'. */
  const kicker = el.querySelector('.mk-kicker, span, figcaption');
  if (kicker) tl.fromTo(kicker, { yPercent: 10 * 0.6 },
                                { yPercent: -10 * 0.6, ease: 'none' }, 0);
});

/* ARRIVO LUCE-BUIO — il media perde luce lentamente mentre titolo e CTA
   emergono; non crea overlay o contenuto, usa solo la scena gia' esistente. */
gsap.utils.toArray('.mk-light-dark').forEach((el) => {
  const media = el.querySelector('img, video, picture');
  const testo = el.querySelector('h1, h2, h3, p');
  const cta = el.querySelector('a, button');
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'top 82%', end: 'center center',
                     scrub: 1.0 }
  });
  if (media) tl.fromTo(media, { filter: 'brightness(1.08)', scale: 1.03 },
                             { filter: 'brightness(0.52)', scale: 1, ease: 'none' }, 0);
  if (testo) tl.fromTo(testo, { yPercent: 18, opacity: 0.35 },
                             { yPercent: 0, opacity: 1, ease: 'none' }, 0.28);
  if (cta) tl.fromTo(cta, { yPercent: 12, opacity: 0 },
                         { yPercent: 0, opacity: 1, ease: 'none' }, 0.56);
});

/* CONGEDO — la sezione si allontana mentre esce dallo schermo, invece di
   sparire di colpo. E' la meta' mancante di ogni "entrata": da' continuita'. */
gsap.utils.toArray('.mk-exit').forEach((el) => {
  const media = el.querySelector('img, video, picture');
  const tl = gsap.timeline({
    scrollTrigger: { trigger: el, start: 'bottom 70%', end: 'bottom top',
                     scrub: 1.0 }
  });
  tl.to(el, { yPercent: -6, opacity: 0.35, scale: 0.97, ease: 'none' }, 0);
  /* il media resta indietro mentre la sezione se ne va: due velocita' diverse
     nello stesso congedo, invece di un blocco unico che svanisce. */
  if (media) tl.to(media, { yPercent: 8, ease: 'none' }, 0);
});

/* CTA MAGNETICA — il bottone segue il cursore di pochi pixel e torna a posto.
   Unico effetto non guidato dallo scroll ammesso: e' una micro-risposta.
   In piu' (Emil Kowalski) scala a 0.97 alla pressione: da' feedback istantaneo,
   il bottone "sente" il click invece di restare inerte. */
gsap.utils.toArray('.mk-magnetic').forEach((btn) => {
  btn.addEventListener('mousemove', (e) => {
    const r = btn.getBoundingClientRect();
    gsap.to(btn, { x: (e.clientX - r.left - r.width / 2) * 0.22,
                   y: (e.clientY - r.top - r.height / 2) * 0.22,
                   duration: 0.4, ease: 'kOut' });
  });
  btn.addEventListener('mouseleave', () => {
    gsap.to(btn, { x: 0, y: 0, scale: 1, duration: 0.6, ease: 'kDrawer' });
  });
  btn.addEventListener('mousedown', () => {
    gsap.to(btn, { scale: 0.97, duration: 0.14, ease: 'kOut' });
  });
  btn.addEventListener('mouseup', () => {
    gsap.to(btn, { scale: 1, duration: 0.2, ease: 'kOut' });
  });
});

/* AUDIT RUNTIME — distingue una classe presente da una timeline realmente
   registrata. Non modifica il layout e resta disponibile agli strumenti di
   verifica come window.__STITCH_MOTION_AUDIT__. */
const runMotionAudit = () => {
  const selectorPerFirma = {
    'slow-crop-push': '.mk-scrub',
    'three-depth-parallax': '.mk-depth',
    'directional-clip': '.mk-reveal',
    'pinned-editorial': '.mk-pin',
    'split-frame': '.mk-counter',
    'focus-resolve': '.mk-blur',
    'counter-scroll': '.mk-counter',
    'curtain-handoff': '.mk-curtain-auto',
    'triptych-focus': '.mk-depth',
    'image-window': '.mk-scrub',
    'horizontal-rail': '.mk-horizontal-rail',
    'mask-to-landscape': '.mk-reveal',
    'layered-collage': '.mk-depth',
    'scale-through': '.mk-cinema',
    'light-to-dark': '.mk-light-dark',
    'monochrome-resolve': '.mk-monochrome'
  };
  const triggers = ScrollTrigger.getAll();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const slots = gsap.utils.toArray('section[data-reference-slot]').map((section) => {
    const signature = section.dataset.motionSignature || '';
    const selector = selectorPerFirma[signature] || '';
    const targets = selector ? gsap.utils.toArray(section.querySelectorAll(selector)) : [];
    if (selector && section.matches(selector)) targets.unshift(section);
    const triggerCount = targets.reduce((total, target) => total + triggers.filter((st) => {
      const trigger = st.trigger;
      return trigger === target || (trigger && target.contains(trigger));
    }).length, 0);
    return {
      slot: section.dataset.referenceSlot || '', signature,
      targets: targets.length, triggers: triggerCount,
      active: reduced ? true : Boolean(signature && targets.length && triggerCount)
    };
  });
  window.__STITCH_MOTION_AUDIT__ = { reducedMotion: reduced, slots };
  document.documentElement.dataset.motionAudit =
    slots.length === 6 && slots.every((slot) => slot.active) ? 'pass' : 'fail';
};

/* RISPETTO DELLE PREFERENZE UTENTE.
   ATTENZIONE `.mk-letters`: SplitText non anima il contenitore, anima i
   `<div>` per-carattere che crea DENTRO. Un clearProps sul solo `.mk-letters`
   resetta il guscio ma lascia i caratteri fermi a yPercent:100/opacity:0 =
   titolo invisibile per sempre sotto reduced-motion. Serve `.mk-letters *`. */
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  ScrollTrigger.getAll().forEach((t) => t.kill());
  gsap.set('.mk-reveal, .mk-line, .mk-hero, .mk-scrub, .mk-scrub img, .mk-scrub video, '
         + '.mk-drift, .mk-blur, .mk-blur img, .mk-monochrome, .mk-monochrome img, '
         + '.mk-horizontal-rail, .mk-horizontal-rail *, .mk-curtain-auto, .mk-curtain-auto *, '
         + '.mk-light-dark, .mk-exit, .mk-counter-text, '
         + '.mk-counter-media, .mk-letters, .mk-letters *, .mk-curtain-panel, .mk-pin-move',
           { clearProps: 'all', opacity: 1 });
}

requestAnimationFrame(() => requestAnimationFrame(runMotionAudit));
window.addEventListener('load', () => {
  ScrollTrigger.refresh();
  window.setTimeout(runMotionAudit, 120);
});
</script>
