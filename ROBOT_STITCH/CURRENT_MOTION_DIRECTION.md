# Piano motion selezionato automaticamente — vincolante

Questo file e' la memoria esterna della pipeline. Non scegliere nuovi effetti e non sostituire una riga con fade-up/parallax generico. Assegna a ogni slot le classi mk-* coerenti con la regia indicata; il movimento reale e' implementato dal kit canonico allegato, che va inserito invariato nella schermata corrente.

## Sei firme scroll, in quest'ordine

⚠️ **Non inventare classi o effetti.** La riga di ogni slot indica la classe e soprattutto il bersaglio: se dice media, la classe va sul media o sul suo wrapper gia' esistente, non sul `<section>` intero. Quando dice sezione, va invece sul `<section>`. Non creare wrapper, pannelli, CTA o testo per soddisfare la mappa.

1. `[data-reference-slot="1"]` — **Mask to Landscape** → classe/regia: **`mk-reveal`**
   _una maschera geometrica cresce fino a rivelare paesaggio o media full-bleed_
   **Bersagli nel markup esistente:** media dominante: `mk-reveal`; titolo: `mk-letters`; pannello/caption esistente: `mk-reveal`
2. `[data-reference-slot="2"]` — **Three-Depth Parallax** → classe/regia: **`mk-depth`**
   _sfondo, soggetto e pannello a tre velocita' leggere e distinte_
   **Bersagli nel markup esistente:** sezione con almeno due media: `mk-depth`; pannello o caption esistente: `mk-reveal`
3. `[data-reference-slot="3"]` — **Scale-through Handoff** → classe/regia: **`mk-cinema`**
   _un media aumenta di scala fino a diventare il fondale della sezione successiva_
   **Bersagli nel markup esistente:** sezione: `mk-cinema`; media dominante, titolo e testo restano figli distinti della stessa scena
4. `[data-reference-slot="4"]` — **Slow Crop Push** → classe/regia: **`mk-scrub`**
   _zoom/crop cinematografico in scrub sul media dominante; nessun pannello che sale_
   **Bersagli nel markup esistente:** wrapper del media dominante: `mk-scrub`; titolo/pannello esistente: `mk-reveal`
5. `[data-reference-slot="5"]` — **Pinned Editorial Story** → classe/regia: **`mk-pin` + `mk-pin-move`**
   _una sola sezione fissata: media stabile, copy/caption avanzano in capitoli senza vuoti_
   **Bersagli nel markup esistente:** sezione: `mk-pin`; primo blocco interno gia' presente: `mk-pin-move`; titolo e media restano separati
6. `[data-reference-slot="6"]` — **Triptych Focus** → classe/regia: **`mk-depth`**
   _trittico: i tre media acquistano profondita' e il focus passa con lo scroll_
   **Bersagli nel markup esistente:** sezione con almeno due media: `mk-depth`; pannello/caption esistente: `mk-reveal`

## Fallback strutturale vincolato

La firma indicata resta obbligatoria quando il suo prerequisito esiste. Se e solo se manca, non applicare una classe vuota e non ripiegare su un reveal generico: usa la prima firma compatibile non ancora usata nell'ordine dello slot. Compatibilita': `horizontal-rail` richiede un contenitore `data-motion-rail` reale; le regie depth richiedono almeno due media; `pinned-editorial` richiede media, testo e un blocco interno; counter e light-to-dark richiedono media e testo; le altre firme richiedono almeno un media reale.

- slot 1: `curtain-handoff` -> `counter-scroll` -> `focus-resolve` -> `scale-through` -> `light-to-dark` -> `monochrome-resolve`
- slot 2: `pinned-editorial` -> `counter-scroll` -> `slow-crop-push` -> `curtain-handoff` -> `monochrome-resolve` -> `scale-through`
- slot 3: `layered-collage` -> `three-depth-parallax` -> `counter-scroll` -> `curtain-handoff` -> `focus-resolve` -> `light-to-dark`
- slot 4: `horizontal-rail` -> `counter-scroll` -> `curtain-handoff` -> `slow-crop-push` -> `scale-through` -> `monochrome-resolve`
- slot 5: `curtain-handoff` -> `focus-resolve` -> `counter-scroll` -> `light-to-dark` -> `slow-crop-push` -> `monochrome-resolve`
- slot 6: `light-to-dark` -> `monochrome-resolve` -> `counter-scroll` -> `curtain-handoff` -> `scale-through` -> `focus-resolve`

## Micro-interazioni globali, massimo due

- `soft-tilt`: tilt massimo 2 gradi su singolo prodotto/menu, disattivato su touch
- `caption-relay`: caption e numero aggiornano lo stato nel media sticky senza autoplay

## Regole di assegnazione

- Inserisci esclusivamente il kit canonico allegato. Non scrivere un secondo GSAP, ScrollTrigger, Lenis, timeline, listener o motore.
- Il compito di questa fase e' associare la classe dominante e i bersagli mk-* reali alla regia di ogni slot, registrando sullo stesso section `data-motion-signature="id-effettivo"` per l'audit runtime.
- Non aggiungere, eliminare, fondere o ridisegnare sezioni.
- Tutto il contenuto deve restare visibile senza JavaScript e con `prefers-reduced-motion`.
