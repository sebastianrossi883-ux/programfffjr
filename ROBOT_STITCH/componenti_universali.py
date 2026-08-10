#!/usr/bin/env python3
"""Catalogo AUTOMATICO dei componenti: una cartella, ci butti dentro la roba.

Perche' esiste
--------------
Il CATALOGO in motion_component_selector.py e' scritto a mano: per ogni
componente qualcuno ha deciso id, nome della funzione mount, valore root,
elenco dei file sorgente e i tre token letterali che il gate poi pretende
nell'export. Trenta voci compilate una per una. Aggiungere un componente
nuovo voleva dire aprire il sorgente Python e scrivere un'altra voce.

Qui invece si guarda una cartella e si ricava tutto da soli:

    componenti/
      codrops-sticky-grid-scroll-main/
      un-altro-effetto/
      terzo.zip            <- gli zip vengono aperti da soli

Ogni sottocartella diventa una voce di catalogo con la stessa forma di quelle
scritte a mano, quindi il resto della pipeline non cambia di una riga.

Cosa ricava, e come
-------------------
- id           dal nome della cartella, ripulito
- function     mount + NomeInCamelCase
- dom_value    NomeInCamelCase + "Original"
- source_files i file portabili veri (html/css/js), esclusi node_modules,
               dist, build, .git, __MACOSX
- required_tokens  NON inventati: stringhe letterali PRESE dal sorgente e
               ricontrollate dentro il sorgente prima di essere scritte. Sono
               quelle che il gate usa per capire se Stitch ha davvero
               integrato il codice o se se l'e' riscritto a modo suo.
- profilo motion  i numeri dell'animazione (scrub, start/end, ease, stagger,
               scale, xPercent/yPercent, durate, agganci negativi): la
               "matematica" da portare nel design del sito invece del markup.

Uso
---
    python3 componenti_universali.py                    # cartella di default
    python3 componenti_universali.py --cartella /percorso/componenti
    python3 componenti_universali.py --scheda           # scrive le schede .md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
CARTELLA_COMPONENTI = PROJECT_DIR / "componenti"
CATALOGO_JSON = PROJECT_DIR / "CATALOGO_COMPONENTI.json"
CARTELLA_SCHEDE = PROJECT_DIR / "firme_estratte"

SUFFISSI_PORTABILI = {".html", ".htm", ".css", ".scss", ".js", ".mjs", ".jsx", ".ts", ".tsx"}
PARTI_DA_IGNORARE = {
    ".git", ".cache", "node_modules", "dist", "build", "coverage", "__MACOSX",
    ".vite", ".next", "vendor",
}
# File che non descrivono il componente: pesano e basta.
NOMI_DA_IGNORARE = re.compile(r"^(?:package(?:-lock)?\.json|tsconfig.*|vite\.config\..*)$", re.I)

# Marcatori di libreria: valgono come token solo se compaiono davvero.
MARCATORI_LIBRERIA = (
    "Flip.getState", "Flip.from", "Flip.fit", "ScrollSmoother.create",
    "ScrollTrigger", "gsap.registerPlugin", "gsap.timeline", "new Lenis",
    "Draggable", "Splitting", "animation-timeline", "scroll-timeline",
    "view-timeline", "requestAnimationFrame", "IntersectionObserver",
)


# Rumore che i download si portano dietro: "-main" e "-master" da GitHub,
# "codrops-" dal nome dell'autore, " 2" dalle copie del Finder. Toglierlo fa
# uscire l'id che una persona avrebbe scritto a mano.
_RUMORE_NOME = (
    r"^codrops[-_]", r"[-_](?:main|master|gh-pages)$", r"[-_]?\s*\d+$",
    r"^tmp[-_]", r"[-_]copy$",
)


def _slug(testo: str) -> str:
    testo = re.sub(r"[^a-zA-Z0-9]+", "-", testo).strip("-").lower()
    for schema in _RUMORE_NOME:
        precedente = None
        while precedente != testo:
            precedente = testo
            testo = re.sub(schema, "", testo).strip("-")
    return re.sub(r"-{2,}", "-", testo) or "componente"


def _camel(slug: str) -> str:
    return "".join(parte.capitalize() for parte in slug.split("-") if parte)


def apri_zip_nella_cartella(cartella: Path) -> list[Path]:
    """Scompatta gli .zip trovati, cosi' si puo' anche solo trascinarli dentro."""
    aperti: list[Path] = []
    for archivio in sorted(cartella.glob("*.zip")):
        destinazione = cartella / archivio.stem
        if destinazione.is_dir():
            continue
        try:
            with zipfile.ZipFile(archivio) as zf:
                zf.extractall(destinazione)
        except (zipfile.BadZipFile, OSError) as exc:
            print(f"  zip non apribile, lo salto: {archivio.name} ({exc})")
            continue
        # Uno zip che contiene una sola cartella: si toglie il guscio.
        figli = [p for p in destinazione.iterdir() if p.name != "__MACOSX"]
        if len(figli) == 1 and figli[0].is_dir():
            interno = figli[0]
            for elemento in list(interno.iterdir()):
                elemento.rename(destinazione / elemento.name)
            interno.rmdir()
        aperti.append(destinazione)
        print(f"  aperto: {archivio.name} -> {destinazione.name}/")
    return aperti


def file_sorgente(radice: Path, massimo: int = 12) -> list[Path]:
    """I file che descrivono davvero il componente, in ordine utile."""
    trovati: list[Path] = []
    for percorso in sorted(radice.rglob("*")):
        if not percorso.is_file():
            continue
        if PARTI_DA_IGNORARE & set(percorso.parts):
            continue
        if percorso.suffix.lower() not in SUFFISSI_PORTABILI:
            continue
        if NOMI_DA_IGNORARE.match(percorso.name):
            continue
        trovati.append(percorso)

    def peso(percorso: Path) -> tuple[int, str]:
        suffisso = percorso.suffix.lower()
        ordine = {".html": 0, ".htm": 0, ".css": 1, ".scss": 1}.get(suffisso, 2)
        return ordine, str(percorso).lower()

    return sorted(trovati, key=peso)[:massimo]


def token_obbligatori(sorgente: str, massimo: int = 3) -> list[str]:
    """Tre stringhe letterali che devono sopravvivere nell'export.

    Non si inventa niente: si pescano dal sorgente e si ricontrollano dentro
    il sorgente. Se Stitch riscrive il componente a modo suo, queste spariscono
    e il gate se ne accorge.
    """
    classi = re.findall(r"\bclass\s+([A-Z][A-Za-z0-9_]{2,})", sorgente)
    costruttori = re.findall(r"\bnew\s+([A-Z][A-Za-z0-9_]{2,})\s*\(", sorgente)
    librerie = [m for m in MARCATORI_LIBRERIA if m in sorgente]

    # Tre token dello STESSO tipo non dicono tre cose: "class Tizio" e
    # "new Tizio(" cadono insieme alla prima riscrittura. Si prende quindi una
    # prova per famiglia - la classe, la libreria, un costruttore diverso -
    # cosi' perche' spariscano tutte Stitch deve aver rifatto davvero tutto.
    scelti: list[str] = []
    nomi_usati: set[str] = set()

    if classi:
        scelti.append(f"class {classi[0]}")
        nomi_usati.add(classi[0])
    if librerie:
        scelti.append(librerie[0])
    for nome in costruttori:
        if nome in nomi_usati:
            continue
        scelti.append(f"new {nome}(")
        nomi_usati.add(nome)
        break

    # Se una famiglia manca (per esempio niente classi), si completa con
    # quello che c'e', senza mai scendere sotto la soglia.
    riserva = [f"class {n}" for n in classi[1:]] + librerie[1:] + [
        f"new {n}(" for n in costruttori if n not in nomi_usati
    ]
    for voce in riserva:
        if len(scelti) >= massimo:
            break
        if voce not in scelti:
            scelti.append(voce)

    return [voce for voce in scelti[:massimo] if voce in sorgente]


def profilo_motion(sorgente: str) -> dict:
    """I numeri dell'animazione: la parte trasferibile al design del sito."""

    def unici(valori) -> list[str]:
        visti: list[str] = []
        for valore in valori:
            testo = str(valore).strip()
            if testo and testo not in visti:
                visti.append(testo)
        return visti

    blocchi_st = re.findall(r"scrollTrigger\s*:\s*\{(.*?)\}", sorgente, re.S)
    testo_st = "\n".join(blocchi_st)
    stagger_oggetto = re.findall(r"stagger\s*:\s*\{([^}]*)\}", sorgente)

    return {
        "start": unici(re.findall(r"start\s*:\s*[\"']([^\"']+)[\"']", testo_st)),
        "end": unici(re.findall(r"end\s*:\s*[\"']([^\"']+)[\"']", testo_st)),
        "scrub": unici(re.findall(r"scrub\s*:\s*([^,\n}]+)", testo_st)),
        "pin": unici(re.findall(r"pin\s*:\s*([^,\n}]+)", testo_st)),
        "toggleActions": unici(re.findall(r"toggleActions\s*:\s*[\"']([^\"']+)[\"']", testo_st)),
        "ease": unici(re.findall(r"ease\s*:\s*[\"'`]([^\"'`]+)[\"'`]", sorgente)),
        "duration": unici(re.findall(r"duration\s*:\s*([\d.]+)", sorgente)),
        "stagger": unici(
            re.findall(r"stagger\s*:\s*([\d.]+)", sorgente)
            + re.findall(r"each\s*:\s*([\d.]+)", "\n".join(stagger_oggetto))
        ),
        "scale": unici(re.findall(r"scale\s*:\s*([\d.]+)", sorgente)),
        "xPercent": unici(re.findall(r"xPercent\s*:\s*(-?[\d.]+)", sorgente)),
        "yPercent": unici(re.findall(r"yPercent\s*:\s*(-?[\d.]+)", sorgente)),
        "agganci": unici(re.findall(r"[\"'](-=[\d.]+%?)[\"']", sorgente)),
        "lenis": unici(
            re.findall(r"lerp\s*:\s*([\d.]+)", sorgente)
            + re.findall(r"wheelMultiplier\s*:\s*([\d.]+)", sorgente)
        ),
    }


def leggi_componente(radice: Path) -> dict | None:
    sorgenti = file_sorgente(radice)
    if not sorgenti:
        print(f"  {radice.name}: nessun file portabile, lo salto.")
        return None

    testo = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in sorgenti)
    token = token_obbligatori(testo)
    if not token:
        print(f"  {radice.name}: nessun token riconoscibile, lo salto.")
        return None

    identificativo = _slug(radice.name)
    camel = _camel(identificativo)
    return {
        "id": identificativo,
        "name": radice.name,
        "function": f"mount{camel}",
        "dom_value": f"{camel}Original",
        "source_root": str(radice),
        "source_files": [str(p.relative_to(radice)) for p in sorgenti],
        "required_tokens": token,
        "source_hashes": {
            str(p.relative_to(radice)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorgenti
        },
        "profilo_motion": profilo_motion(testo),
    }


def scopri(cartella: Path) -> list[dict]:
    if not cartella.is_dir():
        raise SystemExit(f"Cartella componenti non trovata: {cartella}")
    print(f"Leggo i componenti da: {cartella}")
    apri_zip_nella_cartella(cartella)

    voci: list[dict] = []
    for percorso in sorted(cartella.iterdir()):
        if not percorso.is_dir() or percorso.name in PARTI_DA_IGNORARE:
            continue
        voce = leggi_componente(percorso)
        if voce:
            voci.append(voce)
            print(
                f"  {voce['id']}: {len(voce['source_files'])} file, "
                f"token {voce['required_tokens']}"
            )
    return voci


def scrivi_scheda(voce: dict) -> Path:
    CARTELLA_SCHEDE.mkdir(parents=True, exist_ok=True)
    profilo = voce["profilo_motion"]
    righe = [
        f"# Componente `{voce['id']}`",
        "",
        f"- nome cartella: `{voce['name']}`",
        f"- funzione mount: `{voce['function']}`",
        f"- valore root: `{voce['dom_value']}`",
        f"- attributo sezione: `data-stitch-native-component=\"{voce['id']}\"`",
        "",
        "## Token letterali obbligatori",
        "",
        "Sono le stringhe che il gate cerca nell'export. Se Stitch riscrive il",
        "componente invece di integrarlo, spariscono e l'export viene scartato.",
        "",
    ]
    righe += [f"- `{token}`" for token in voce["required_tokens"]]
    righe += ["", "## Matematica dell'animazione", "",
              "La parte trasferibile: questi numeri si portano sui media del sito,",
              "il markup della demo no.", "", "| parametro | valori |", "|---|---|"]
    for chiave, valori in profilo.items():
        if valori:
            righe.append(f"| {chiave} | " + ", ".join(f"`{v}`" for v in valori[:8]) + " |")
    righe += ["", "## File sorgente", ""]
    righe += [f"- `{nome}`" for nome in voce["source_files"]]
    percorso = CARTELLA_SCHEDE / f"{voce['id']}.md"
    percorso.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return percorso


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cartella", type=Path, default=CARTELLA_COMPONENTI)
    parser.add_argument("--uscita", type=Path, default=CATALOGO_JSON)
    parser.add_argument("--scheda", action="store_true", help="Scrive anche le schede .md")
    args = parser.parse_args()

    voci = scopri(args.cartella.expanduser())
    if not voci:
        print("Nessun componente utilizzabile trovato.")
        return 1

    args.uscita.write_text(
        json.dumps({"cartella": str(args.cartella), "componenti": voci}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nCatalogo scritto: {args.uscita} ({len(voci)} componenti)")

    if args.scheda:
        for voce in voci:
            print(f"  scheda: {scrivi_scheda(voce)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
