#!/usr/bin/env python3
"""Gate della FASE 1 (design): verifica prima di spendere le altre 5 generazioni.

Perche' esiste: il gate motion gira solo alla FINE, dopo sei generazioni. Se la
fase 1 consegna un sito sbagliato (due marchi diversi, sette sezioni, icone
material), quel difetto si porta dietro tutto il giro e lo si scopre a crediti
gia' bruciati.

Qui i controlli sono locali e costano zero: si legge l'HTML della schermata
appena generata e si confronta con i dati che Python ha gia' deciso
(nome inventato della cantina, marchi reali da escludere).

Principio del progetto: il gate VERIFICA e RIPORTA, non rimanda a Stitch.
Ogni retry e' credito bruciato, quindi un fallimento ferma il giro.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

# Sezioni che non contano nel totale: sono aggiunte dalle fasi successive.
_GUEST_MARKERS = ("data-stitch-native-component", "data-stitch-added-guest")
_FRAMER_MARKERS = ("data-stitch-framer-interaction", "data-stitch-framer-added")

# Copy da template IA: se compaiono, non e' stato trascritto dalle reference.
_TEMPLATE_COPY = re.compile(
    r"(?i)\b(discover our|welcome to our|our story begins|explore our|"
    r"lorem ipsum|get started|sign up today|your journey begins)\b"
)

# Icone: la regola anti-icone e' nel prompt da sempre ma non veniva applicata.
_ICON_FONTS = re.compile(
    r"(?i)material-symbols|material-icons|font-awesome|\bfa-[a-z]|"
    r"lucide-|feather-icons|bi-[a-z]+\s|remixicon"
)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _normalize(text: str) -> str:
    """Confronto tollerante: accenti, apostrofi tipografici e spazi multipli."""
    text = _strip_accents(text.lower())
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"[^a-z0-9']+", " ", text).strip()


def _visible_text(html: str) -> str:
    """Testo visibile: via script, style e commenti, che portano falsi positivi.

    Senza questo il blocco del Guest Component (che contiene i commenti del
    sorgente Codrops e i nomi delle sue classi) farebbe scattare i controlli.
    """
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


def top_level_sections(html: str) -> list[str]:
    """Le <section> di primo livello, escluse quelle interne a Guest/Framer.

    Serve un conteggio onesto: il gate motion contava anche le
    `<section class="content--*">` INTERNE al Guest Component, e generava 13
    errori fantasma per giro.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # senza bs4 si ripiega su un conteggio grezzo
        return re.findall(r"<section\b[^>]*>", html, re.I)

    soup = BeautifulSoup(html, "html.parser")
    radice = soup.body or soup
    sezioni = []
    for sezione in radice.find_all("section"):
        # dentro un'altra section (es. i pannelli interni del Guest): non conta
        if sezione.find_parent("section") is not None:
            continue
        attributi = " ".join(f'{k}="{v}"' for k, v in sezione.attrs.items())
        if any(marker in attributi for marker in _GUEST_MARKERS + _FRAMER_MARKERS):
            continue
        sezioni.append(str(sezione)[:200])
    return sezioni


def cloned_sections(html: str) -> list[str]:
    """Sezioni con la STESSA identica anatomia: sintomo di template ripetuto.

    Difetto visto il 2026-07-26: Stitch aveva fatto un solo blocco (foto a
    pieno campo + riquadro con kicker, titolo, due righe, un bottone) e lo
    aveva ripetuto SEI volte alternando il lato. Sei sezioni con lo stesso
    conteggio di p/a/img/h/div sono quasi sempre un template IA, non le
    griglie diverse delle reference.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    radice = soup.body or soup
    impronte: dict[tuple, int] = {}
    for sezione in radice.find_all("section"):
        if sezione.find_parent("section") is not None:
            continue
        attributi = " ".join(f'{k}="{v}"' for k, v in sezione.attrs.items())
        if any(m in attributi for m in _GUEST_MARKERS + _FRAMER_MARKERS):
            continue
        impronta = (
            len(sezione.find_all("p")),
            len(sezione.find_all("a")),
            len(sezione.find_all("img")),
            len(sezione.find_all(["h1", "h2", "h3"])),
            len(sezione.find_all("div")),
        )
        impronte[impronta] = impronte.get(impronta, 0) + 1
    return [
        f"{quante} sezioni identiche (p={i[0]} a={i[1]} img={i[2]} titoli={i[3]} div={i[4]})"
        for i, quante in impronte.items()
        if quante >= 3
    ]


def check_design_html(html: str, selection: dict, sezioni_attese: int = 6) -> list[str]:
    """Elenco degli errori bloccanti della fase 1. Lista vuota = PASS."""
    errori: list[str] = []
    testo = _visible_text(html)
    testo_normalizzato = _normalize(testo)
    brand = (selection or {}).get("brand") or {}
    vietati = (selection or {}).get("forbidden_brands") or []

    # 1. Numero di sezioni: almeno quelle attese. Le reference possono avere
    # piu' blocchi editoriali reali: vietarli falserebbe il progetto e
    # costringerebbe Stitch a comprimere o cancellare sezioni corrette.
    sezioni = top_level_sections(html)
    if len(sezioni) < sezioni_attese:
        errori.append(
            f"sezioni di primo livello: {len(sezioni)} sotto il minimo di {sezioni_attese} "
            f"(le sezioni interne a Guest/Framer non sono contate)"
        )

    # 2. Il marchio inventato deve esserci: e' l'identita' del sito.
    nome = brand.get("name")
    if nome and _normalize(nome) not in testo_normalizzato:
        errori.append(
            f"manca il nome della cantina '{nome}': il sito deve intestarsi a lui"
        )

    # 3. I marchi VERI delle reference non devono comparire. E' il controllo
    #    che intercetta il Frankenstein a due (o tre) aziende in una pagina.
    for marchio in vietati:
        if not marchio:
            continue
        if _normalize(marchio) in testo_normalizzato:
            errori.append(
                f"marchio reale della reference presente nel sito: '{marchio}' "
                f"(il sito deve essere solo di '{nome or 'la cantina inventata'}')"
            )

    # 4. Un solo header e un solo footer.
    for tag, atteso in (("header", 1), ("footer", 1)):
        quanti = len(re.findall(rf"<{tag}\b", html, re.I))
        if quanti != atteso:
            errori.append(f"<{tag}> presenti: {quanti} invece di {atteso}")

    # 5. Icone ed emoji: il tell "da IA" piu' visibile (es. il calice).
    icone = _ICON_FONTS.findall(html)
    if icone:
        errori.append(
            f"icone vietate presenti ({len(icone)} occorrenze, es. "
            f"{sorted(set(icone))[:3]}): i contatti si scrivono a parole"
        )
    emoji = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", testo)
    if emoji:
        errori.append(f"emoji presenti nel testo: {sorted(set(emoji))[:5]}")

    # 6. Copy da template invece che trascritto dalle reference.
    template = _TEMPLATE_COPY.findall(testo)
    if template:
        errori.append(f"copy da template IA: {sorted(set(template))[:3]}")

    # 7. Sezioni clonate: un solo blocco ripetuto N volte invece delle griglie
    #    diverse delle reference.
    for clone in cloned_sections(html):
        errori.append(
            f"template ripetuto: {clone} - le reference hanno griglie diverse, "
            f"riproduci quelle"
        )

    # 8. Il sito ha delle fotografie? Una cantina senza immagini e' un guscio.
    immagini = len(re.findall(r"<img\b", html, re.I)) + len(
        re.findall(r"background-image", html, re.I)
    )
    if immagini < sezioni_attese:
        errori.append(
            f"solo {immagini} immagini in tutta la pagina (minimo {sezioni_attese}): "
            f"le sezioni delle reference sono costruite sulle fotografie"
        )

    return errori


def report(errori: list[str], contesto: str = "") -> bool:
    """Stampa l'esito. Ritorna True se si puo' proseguire."""
    intestazione = f"GATE FASE 1 (design){' - ' + contesto if contesto else ''}"
    if not errori:
        print(f"{intestazione}: PASS")
        return True
    print(f"{intestazione}: FAIL - {len(errori)} problemi")
    for errore in errori:
        print(f"  - {errore}")
    return False


def main() -> int:
    """Uso manuale: verify_design_phase.py <file.html|file.zip> [selection.json]"""
    import json
    import zipfile

    if len(sys.argv) < 2:
        print(__doc__)
        print("uso: verify_design_phase.py <code.html|export.zip> [CURRENT_MOTION_SELECTION.json]")
        return 2

    sorgente = Path(sys.argv[1])
    if sorgente.suffix.lower() == ".zip":
        with zipfile.ZipFile(sorgente) as archivio:
            nome = next(
                n for n in archivio.namelist()
                if n.endswith("/code.html") or n == "code.html"
            )
            html = archivio.read(nome).decode("utf-8", errors="ignore")
    else:
        html = sorgente.read_text(encoding="utf-8", errors="ignore")

    percorso_selezione = Path(
        sys.argv[2] if len(sys.argv) > 2
        else "/Users/utente/Downloads/reference_splitter/CURRENT_MOTION_SELECTION.json"
    )
    selezione = json.loads(percorso_selezione.read_text(encoding="utf-8"))

    # Su un export completo le sezioni attese sono 6 + quelle aggiunte dopo:
    # qui si controlla solo il design, quindi si contano le 6 originali.
    return 0 if report(check_design_html(html, selezione), sorgente.name) else 1


if __name__ == "__main__":
    raise SystemExit(main())
