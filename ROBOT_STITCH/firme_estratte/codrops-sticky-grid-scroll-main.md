# Componente `codrops-sticky-grid-scroll-main`

- nome cartella: `codrops-sticky-grid-scroll-main`
- funzione mount: `mountCodropsStickyGridScrollMain`
- valore root: `CodropsStickyGridScrollMainOriginal`
- attributo sezione: `data-stitch-native-component="codrops-sticky-grid-scroll-main"`

## Token letterali obbligatori

Sono le stringhe che il gate cerca nell'export. Se Stitch riscrive il
componente invece di integrarlo, spariscono e l'export viene scartato.

- `class StickyGridScroll`
- `ScrollTrigger`
- `new Lenis(`

## Matematica dell'animazione

La parte trasferibile: questi numeri si portano sui media del sito,
il markup della demo no.

| parametro | valori |
|---|---|
| start | `top bottom`, `top 57%`, `top 25%` |
| end | `top top`, `bottom bottom` |
| scrub | `true` |
| toggleActions | `play none none reset` |
| ease | `none`, `power1.out`, `power1.inOut`, `power3.inOut`, `power2.inOut`, `power1.${isVisible ?` |
| duration | `0.7`, `1`, `0.5`, `0.4` |
| stagger | `0.06` |
| scale | `2.05` |
| xPercent | `-40`, `40` |
| yPercent | `-100` |
| agganci | `-=0.5`, `-=90%`, `-=0.6`, `-=0.32` |
| lenis | `0.08`, `1.4` |

## File sorgente

- `src/index.html`
- `src/styles/base.css`
- `src/styles/index.css`
- `src/scripts/index.js`
- `src/scripts/utils.js`
