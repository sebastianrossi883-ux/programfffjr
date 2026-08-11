#!/usr/bin/env python3
"""Download the current Stitch project through the browser UI."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from playwright.sync_api import Error, TimeoutError, sync_playwright


STITCH_URL = "https://stitch.withgoogle.com/"
PROFILE_DIR = Path("~/Downloads/reference_splitter/.stitch_browser_profile").expanduser()
DEBUG_DIR = Path("~/Downloads/reference_splitter/debug").expanduser()
DOWNLOAD_DIR = Path("~/Downloads/stitch_downloads").expanduser()
BROWSER_DOWNLOAD_DIR = Path("~/Downloads").expanduser()
LAST_PROJECT_URL_PATH = Path("/Users/utente/Downloads/reference_splitter/LAST_STITCH_PROJECT_URL.txt")
LAST_DOWNLOAD_PATH = Path("/Users/utente/Downloads/reference_splitter/LAST_STITCH_DOWNLOAD_PATH.txt")
# Manifest scritto dallo Stadio 1 (motion_component_selector): var CSS / marker
# <img> -> foto originale a piena risoluzione. Lo Stadio 2 (qui) lo usa per
# rimpiazzare le anteprime LQIP con le foto vere dopo il download.
GUEST_IMAGE_MANIFEST_PATH = Path("/Users/utente/Downloads/reference_splitter/generated_motion/GUEST_IMAGE_MANIFEST.json")
ENV_PATH = Path("/Users/utente/Downloads/reference_splitter/.env")
REJECTED_DIR = DOWNLOAD_DIR / "rejected_exports"
LOGIN_WAIT_MS = 600000
MCP_URL = "https://stitch.googleapis.com/mcp"
PROTOCOL_VERSION = "2025-06-18"


def surfaces(page):
    yield page
    for frame in page.frames:
        if frame is not page.main_frame:
            yield frame


def first_visible(page, selectors: list[str], timeout: int = 1200):
    for surface in surfaces(page):
        for selector in selectors:
            locator = surface.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout)
                return locator
            except (TimeoutError, Error):
                continue
    return None


def click_text(page, pattern: str, label: str, timeout: int = 1800) -> bool:
    regex = re.compile(pattern, re.I)
    for surface in surfaces(page):
        locator = surface.get_by_text(regex).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.click(timeout=2500)
            print(f"OK: {label}")
            return True
        except (TimeoutError, Error):
            continue
    print(f"Non trovo testo: {label}")
    return False


def visible_text_exists(page, pattern: str, timeout: int = 250) -> bool:
    regex = re.compile(pattern, re.I)
    for surface in surfaces(page):
        try:
            body_text = surface.locator("body").inner_text(timeout=timeout)
            if regex.search(body_text):
                return True
        except (TimeoutError, Error):
            continue

    for surface in surfaces(page):
        locator = surface.get_by_text(regex).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            return True
        except (TimeoutError, Error):
            continue
    return False


def locator_text(locator) -> str:
    try:
        return locator.inner_text(timeout=700).strip()
    except Error:
        try:
            return (locator.text_content(timeout=700) or "").strip()
        except Error:
            return ""


def save_debug(page, label: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
    screenshot = DEBUG_DIR / f"{stamp}_{slug}.png"
    html = DEBUG_DIR / f"{stamp}_{slug}.html"
    try:
        page.screenshot(path=str(screenshot), full_page=True)
        html.write_text(page.content())
        print(f"Debug screenshot: {screenshot}")
        print(f"Debug HTML: {html}")
    except Exception as exc:
        print(f"Non riesco a salvare debug: {exc}")


def click_top_left_menu(page) -> bool:
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Prefer the real hamburger by position. Broad aria/menu selectors can hit
    # the Google account menu on Stitch, which is not the project menu.
    candidate = page.locator("button, [role=button]").filter(visible=True)
    count = min(candidate.count(), 80)
    for index in range(count):
        item = candidate.nth(index)
        try:
            box = item.bounding_box(timeout=600)
        except Error:
            continue
        if not box:
            continue
        if 10 <= box["x"] <= 95 and 10 <= box["y"] <= 80 and 34 <= box["width"] <= 90 and 30 <= box["height"] <= 75:
            item.click(timeout=2500)
            print("OK: menu progetto (hamburger alto-sinistra)")
            return True

    selectors = [
        "button:has-text('☰')",
        "[role=button]:has-text('☰')",
    ]
    locator = first_visible(page, selectors, timeout=1200)
    if locator:
        locator.click(timeout=2500)
        print("OK: menu progetto")
        return True

    # Stitch's project menu is sometimes rendered as an icon-only canvas-ish
    # control that Playwright cannot name. The button is fixed in the top-left
    # of the app, so use the same coordinates the user would click manually.
    try:
        page.mouse.click(52, 35)
        page.wait_for_timeout(900)
        if visible_text_exists(
            page,
            r"Scarica\s+progetto|Download\s+project|Condividi|Share|Duplica\s+progetto|Duplicate\s+project",
            timeout=1400,
        ):
            print("OK: menu progetto (coordinate alto-sinistra)")
            return True
    except Error:
        pass

    print("Non trovo il menu a tre linee.")
    return False


# Frasi di stato che Stitch mostra MENTRE genera. Restano pero' scritte nella
# chat anche dopo, per sempre: sono un indizio, mai una prova. Chi le legge
# deve sempre chiedersi "questa e' nuova o e' la cronologia?".
ACTIVE_GENERATION_PATTERN = (
    # STATI IN INGLESE. L'interfaccia di Stitch puo' essere in inglese anche
    # con Chrome in italiano, e li' il messaggio di lavoro in corso e' un
    # semplice "Thinking...". Mancava, e senza di lui il robot non vedeva mai
    # partire la generazione: restava senza prova forte e finiva sulla via
    # lenta o sulla spinta. Restano parole strette: niente "Building" o
    # "Designing", che compaiono anche nei testi fissi dell'interfaccia.
    r"\bThinking\b|\bReasoning\b|\bAnalyz(?:e|ing)\b|\bAnalysing\b|"
    r"\bRendering\b|\bWorking\s+on\b|"
    r"\bSto\s+pensando\b|\bElaborazione\b|"
    r"Generazione\s+(?:immagine|schermata)\s+in\s+corso|"
    r"Generazione\s+schermata|"
    r"Generazione\s+immagine|"
    r"schermata\s+in\s+corso|"
    r"immagine\s+in\s+co|"
    r"in\s+corso\.{2,}|"
    r"(?:Generating|Creating)\s+(?:an?\s+)?(?:image|screen)|"
    r"Whipping\s+up\s+an?\s+image|"
    r"Mapping\s+out\s+the\s+components|"
    r"(?:Generazione|Generating|schermata|screen|immagine|image)"
    r"[^()\n]{0,40}\(\s*\d+\s*/\s*\d+\s*\)"
)
EXPORT_PATTERN = r"\bEsporta\b|\bExport\b"

# Stato dell'ultimo invio, fotografato da mark_generation_baseline().
_GENERATION_BASELINE: dict[str, Any] = {}


def _origine(url: str) -> str:
    trovato = re.match(r"^(https?://[^/]+)", url or "")
    return trovato.group(1) if trovato else ""


def frame_interfaccia(page):
    """I frame che appartengono all'APP Stitch, non all'anteprima del sito.

    Leggere il solo main_frame era troppo stretto: pezzi della UI di Stitch
    (composer, e con ogni probabilita' la chat) vivono in un iframe, quindi lo
    stato della generazione non compariva proprio. Era questo a far scattare la
    spinta su una generazione in corso.

    Il criterio e' l'origine: stessa origine della pagina = interfaccia; tutto
    il resto (blob:, about:srcdoc, altri host) e' anteprima del sito generato.
    """
    origine = _origine(page.url)
    yield page.main_frame
    for frame in page.frames:
        if frame is page.main_frame:
            continue
        if origine and _origine(frame.url) == origine:
            yield frame


def main_frame_text(page) -> str:
    """Testo dell'interfaccia di Stitch, SENZA l'anteprima del sito.

    L'anteprima resta fuori perche' contiene il copy del sito generato, e un
    testo italiano ("questo", "gusto", "posto") faceva scattare i vecchi
    controlli sullo stato. Lo stato di Stitch sta nella sua UI, non nel sito
    che ha disegnato.
    """
    parti: list[str] = []
    for frame in frame_interfaccia(page):
        try:
            parti.append(frame.locator("body").inner_text(timeout=1200))
        except (TimeoutError, Error):
            continue
    return "\n".join(parti)


def preview_signature(page) -> str:
    """Impronta delle anteprime sul canvas: cambia quando nasce una schermata.

    E' l'unica prova POSITIVA che una fase ha prodotto qualcosa. Le frasi in
    chat dicono solo che qualcosa e' stato annunciato, e restano li' per
    sempre; una schermata nuova invece si vede.
    """
    interfaccia = {id(frame) for frame in frame_interfaccia(page)}
    parti: list[str] = []
    for frame in page.frames:
        if id(frame) in interfaccia:
            continue
        try:
            testo = frame.locator("body").inner_text(timeout=800)
        except (TimeoutError, Error):
            continue
        # Lunghezza arrotondata: assorbe il testo che si assesta durante il
        # rendering senza perdere un cambio di schermata vero.
        parti.append(f"{frame.url}|{len(testo) // 200}")
    return hashlib.sha1("\n".join(sorted(parti)).encode("utf-8")).hexdigest()


def mark_generation_baseline(page) -> None:
    """Fotografa il canvas PRIMA di un invio.

    Va chiamata da `send()`: e' il solo istante in cui sappiamo con certezza
    che quello che si vede appartiene alla fase PRECEDENTE. Senza questa foto
    l'attesa non sa distinguere "il sito e' pronto" da "sto guardando il sito
    della fase prima e quello nuovo non e' nemmeno cominciato" - ed e' proprio
    li' che il robot rischia di mandare /animate su una schermata vecchia.
    """
    _GENERATION_BASELINE["preview"] = preview_signature(page)
    _GENERATION_BASELINE["busy_hits"] = len(
        re.findall(ACTIVE_GENERATION_PATTERN, main_frame_text(page), re.I)
    )
    _GENERATION_BASELINE["at"] = time.time()


def generation_started_since_baseline(page) -> bool:
    """True se e' comparso un segnale di generazione NUOVO dopo l'ultimo invio.

    Si conta quante volte la frase di stato appare, invece di chiedere se
    appare: la cronologia non si cancella, quindi l'unica cosa che distingue
    una generazione vera e' che le occorrenze AUMENTANO.
    """
    if not _GENERATION_BASELINE:
        return bool(re.search(ACTIVE_GENERATION_PATTERN, main_frame_text(page), re.I))
    adesso = len(re.findall(ACTIVE_GENERATION_PATTERN, main_frame_text(page), re.I))
    return adesso > int(_GENERATION_BASELINE.get("busy_hits", 0))


def canvas_mosso_dopo_invio(page) -> bool:
    """True se il canvas e' cambiato rispetto alla foto scattata da send()."""
    baseline = _GENERATION_BASELINE.get("preview")
    if baseline is None:
        return False
    return preview_signature(page) != baseline


def wait_for_generation_complete(
    page,
    timeout_ms: int,
    minimo_secondi: int = 45,
    quiete_secondi: int = 15,
    minimo_senza_stato: int = 150,
    sblocco_frasi_vecchie_secondi: int = 75,
    attesa_partenza_secondi: int = 180,
) -> bool:
    """True solo quando la fase corrente e' DAVVERO finita.

    Ci sono due errori possibili e non sono equivalenti:

    1. PARTIRE TROPPO PRESTO. Il prompt successivo finisce su una schermata
       incompleta o su quella della fase precedente. Costa una generazione e
       sporca il sito. Da evitare sempre.
    2. NON PARTIRE MAI. La fase 1 e' finita ma il robot non se ne accorge e
       muore in timeout senza mandare /animate. E' il difetto che ha bloccato
       tutti i giri del 2026-08-10 (19 run, tutte ferme alla FASE 1).

    Il vecchio codice sbagliava sul secondo: leggeva le frasi di stato su
    TUTTA la pagina, e siccome la chat di Stitch non si svuota, la frase
    "Generazione schermata in corso" della fase 1 continuava a risultare vera
    per sempre. Il ramo "sta ancora generando" si ripeteva fino al timeout e
    il controllo su Esporta - l'unico che puo' rispondere "finito" - non
    veniva mai raggiunto.

    La regola nuova non si fida di nessuna frase, e chiede tre cose insieme:

    - PROVA DI PARTENZA: o il canvas si e' mosso rispetto alla foto scattata
      da `mark_generation_baseline()` all'invio, o le frasi di stato sono
      AUMENTATE di numero. Finche' manca, non si conclude niente: e' il
      paletto contro l'errore 1.
    - QUIETE: chat E canvas devono restare identici per `quiete_secondi`, e
      comunque non si conclude prima di `minimo_secondi` dall'invio. Una
      pagina che sta generando cambia in continuazione, quindi la quiete non
      puo' essere simulata da una fase ancora in corso. Il minimo copre la
      pausa fra l'invio e il primo segnale, quando Stitch "pensa" a schermo
      immobile e il canvas si e' gia' mosso per gli allegati.
    - ESPORTA visibile: esiste una schermata esportabile.

    La frase di stato resta come freno, ma con una scadenza: se la pagina e'
    ferma identica da `sblocco_frasi_vecchie_secondi`, quella frase e'
    cronologia, non lavoro in corso, e viene ignorata. E' il paletto contro
    l'errore 2, e non puo' far partire nulla in anticipo: una generazione
    vera non tiene la pagina immobile per piu' di un minuto.
    """
    inizio = time.time()
    deadline = inizio + (timeout_ms / 1000)
    baseline_preview = _GENERATION_BASELINE.get("preview")
    baseline_stato = int(_GENERATION_BASELINE.get("busy_hits", 0))

    partenza_vista = False
    stato_confermato = False
    ultimo_hash = ""
    fermo_da = inizio
    frasi_vecchie_segnalate = False
    ultimo_debug_stallo = 0.0
    ultimo_messaggio = 0.0

    while time.time() < deadline:
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)

        adesso = time.time()
        testo = main_frame_text(page)
        canvas = preview_signature(page)
        # La quiete si misura su chat E canvas insieme. Il canvas da solo
        # basterebbe a smentire una pagina "ferma": una schermata che si sta
        # ancora disegnando cambia testo anche quando la chat tace.
        impronta = hashlib.sha1(f"{testo}\n#canvas#\n{canvas}".encode("utf-8")).hexdigest()
        if impronta != ultimo_hash:
            ultimo_hash = impronta
            fermo_da = adesso
        secondi_fermo = adesso - fermo_da

        occupato = bool(re.search(ACTIVE_GENERATION_PATTERN, testo, re.I))
        esporta = bool(re.search(EXPORT_PATTERN, testo, re.I))

        # Le due prove NON valgono uguale.
        #
        # Un messaggio di stato in piu' rispetto all'invio significa che una
        # generazione e' stata annunciata: prova forte.
        #
        # Il canvas che si muove significa solo che qualcosa e' comparso, e
        # non e' per forza un sito: Stitch rende i .md allegati come schede
        # documento e quelle appaiono subito dopo l'invio, senza che sia
        # stato generato niente (vedi attachment_name_counts_on_page). Prova
        # debole, quindi tenuta a una soglia di tempo molto piu' alta prima
        # di poter dire "finito".
        if len(re.findall(ACTIVE_GENERATION_PATTERN, testo, re.I)) > baseline_stato:
            if not stato_confermato:
                stato_confermato = True
                print("Generazione confermata: e' comparso un nuovo messaggio di stato.")
            partenza_vista = True
        elif not partenza_vista and baseline_preview is not None and canvas != baseline_preview:
            partenza_vista = True
            print(
                "Movimento sul canvas senza messaggio di stato: potrebbe essere solo "
                "un allegato: valuto la fine, ma con l'attesa minima lunga."
            )

        if not partenza_vista:
            if adesso - inizio > attesa_partenza_secondi:
                # Non e' un timeout di generazione: e' Stitch che non ha mai
                # cominciato (tipicamente ha risposto solo a parole). Dirlo
                # subito vale piu' che aspettare altri 12 minuti per poi
                # stampare la frase sbagliata.
                print(
                    f"Nessuna generazione partita entro {attesa_partenza_secondi}s: "
                    "Stitch non ha prodotto nessuna schermata nuova."
                )
                try:
                    from send_to_stitch import save_debug
                    save_debug(page, "generation_never_started")
                except Exception:
                    pass
                return False
            if adesso - ultimo_messaggio > 30:
                ultimo_messaggio = adesso
                print(f"Aspetto che la generazione parta ({int(adesso - inizio)}s)...")
            page.wait_for_timeout(3000)
            continue

        # QUANDO SI PUO' IGNORARE LA FRASE DI STATO.
        # Non basta che la pagina sia ferma: con la UI inglese Stitch scrive
        # "Thinking..." e puo' restare immobile per minuti mentre lavora
        # davvero. La differenza la fa il canvas: se non si e' mosso non c'e'
        # ancora nessun risultato, quindi quella frase e' lavoro in corso e si
        # aspetta. Se invece una schermata nuova e' comparsa, il lavoro e'
        # finito e la frase rimasta a schermo e' cronologia.
        risultato_presente = baseline_preview is not None and canvas != baseline_preview
        sblocco_possibile = risultato_presente and secondi_fermo >= sblocco_frasi_vecchie_secondi

        if occupato and not sblocco_possibile:
            if adesso - ultimo_messaggio > 30:
                ultimo_messaggio = adesso
                print(f"Stitch sta ancora generando ({int(adesso - inizio)}s): aspetto...")
            if adesso - ultimo_debug_stallo > 120:
                ultimo_debug_stallo = adesso
                try:
                    from send_to_stitch import save_debug
                    save_debug(page, "generation_wait_stuck")
                except Exception:
                    pass
            page.wait_for_timeout(5000)
            continue

        if occupato and not frasi_vecchie_segnalate:
            frasi_vecchie_segnalate = True
            print(
                f"La frase 'generazione in corso' e' ancora scritta, ma la pagina e' "
                f"identica da {int(secondi_fermo)}s: e' cronologia della chat, la ignoro."
            )

        if not esporta:
            if adesso - ultimo_messaggio > 30:
                ultimo_messaggio = adesso
                print("Nessun bottone Esporta: la schermata non e' ancora esportabile, aspetto...")
            page.wait_for_timeout(3000)
            continue

        # Prova debole (solo canvas): non basta a concludere presto. Diventa
        # accettabile solo in fondo al budget, come ultima risorsa, perche' il
        # caso che copre e' "Stitch ha lavorato ma la frase di stato non la
        # riconosciamo piu'" - e li' fermarsi vorrebbe dire buttare una
        # generazione gia' pagata. Se invece non ha lavorato davvero, questa
        # attesa lunghissima e' proprio quello che impedisce l'invio anticipato.
        soglia = (
            minimo_secondi
            if stato_confermato
            else max(minimo_senza_stato, (timeout_ms / 1000) * 0.6)
        )
        if secondi_fermo < quiete_secondi or adesso - inizio < soglia:
            page.wait_for_timeout(3000)
            continue

        prova = "messaggio di stato" if stato_confermato else "solo movimento canvas"
        print(
            f"OK: generazione completata (pagina e canvas fermi da {int(secondi_fermo)}s, "
            f"Esporta presente, prova: {prova})."
        )
        return True

    if not partenza_vista:
        print("Tempo scaduto senza che nessuna generazione sia mai partita.")
    else:
        print("Tempo scaduto: Stitch sembra ancora in generazione.")
    try:
        from send_to_stitch import save_debug
        save_debug(page, "generation_timeout")
    except Exception:
        pass
    return False


def click_export_button(page) -> bool:
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return click_text(page, r"\bEsporta\b|\bExport\b", "menu esporta", timeout=3000)


def click_download_menu_item(page) -> bool:
    return click_text(
        page,
        r"Scarica\s+progetto|Download\s+project|Download\s+code|Scarica\s+codice|Download|Scarica",
        "scarica progetto",
        timeout=6000,
    )


def export_panel_is_open(page) -> bool:
    return visible_text_exists(
        page,
        r"\bFormat\b|\bFormato\b|AI\s+Studio|Figma|MCP|Netlify|Lovable|Bolt|\.zip|Codice\s+negli\s+Appunti",
        timeout=900,
    )


def close_export_panel_if_open(page) -> None:
    if not export_panel_is_open(page):
        return

    viewport = page.viewport_size or {"width": 1440, "height": 950}
    page.mouse.click(viewport["width"] - 93, 108)
    page.wait_for_timeout(700)


def select_visible_screen_on_canvas(page) -> bool:
    close_export_panel_if_open(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    viewport = page.viewport_size or {"width": 1440, "height": 950}
    # Normalize the canvas a little before clicking. Stitch often restores the
    # last pan/zoom from a previous project; after interruptions the generated
    # screen may be visible but not under the old click coordinates.
    for shortcut in ("Meta+0", "Control+0", "Escape"):
        try:
            page.keyboard.press(shortcut)
            page.wait_for_timeout(250)
        except Error:
            pass

    # Stitch can place both reasoning/inventory cards and the actual generated
    # website on the canvas. The website is usually a tall vertical screen, so
    # prefer clicks lower inside the object before trying the top row. This
    # avoids attaching follow-up prompts to the inventory card.
    x_positions = [0.84, 0.78, 0.70, 0.62, 0.54, 0.46, 0.38, 0.30, 0.24, 0.18]
    y_positions = [0.50, 0.60, 0.42, 0.34, 0.26, 0.20, 0.70]
    candidate_points = [(viewport["width"] * x, viewport["height"] * y) for y in y_positions for x in x_positions]

    for x, y in candidate_points:
        try:
            page.mouse.click(x, y)
            page.wait_for_timeout(700)
            if visible_text_exists(
                page,
                r"\bMore\b|\bAltro\b|\bOpzioni\b|Cosa\s+vorresti\s+cambiare|What\s+would\s+you\s+like\s+to\s+change",
                timeout=500,
            ):
                print(f"OK: selezione schermata canvas ({int(x)}, {int(y)})")
                return True
        except Error:
            continue

    # Last-resort fallback for Stitch UI changes. Never continue unless the
    # click is confirmed: otherwise a follow-up can be attached to a reasoning
    # card or to the wrong generated screen.
    fallback_x = viewport["width"] * 0.50
    fallback_y = viewport["height"] * 0.50
    try:
        page.mouse.click(fallback_x, fallback_y)
        page.wait_for_timeout(900)
        if visible_text_exists(
            page,
            r"\bMore\b|\bAltro\b|\bOpzioni\b|Cosa\s+vorresti\s+cambiare|What\s+would\s+you\s+like\s+to\s+change",
            timeout=800,
        ):
            print(f"OK: selezione schermata canvas fallback ({int(fallback_x)}, {int(fallback_y)})")
            return True
        print(
            "Selezione schermata fallback non confermata: "
            "interrompo per non applicare il prompt alla scheda sbagliata."
        )
        return False
    except Error:
        print("Non riesco a selezionare una schermata nel canvas.")
        return False


def ensure_screen_selected_for_export(page) -> bool:
    no_selection_pattern = r"Nessuna\s+schermata\s+selezionata|No\s+screen\s+selected"

    if not visible_text_exists(page, no_selection_pattern, timeout=500):
        return True

    close_export_panel_if_open(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    viewport = page.viewport_size or {"width": 1440, "height": 950}
    candidate_points = [
        (viewport["width"] * 0.82, viewport["height"] * 0.24),
        (viewport["width"] * 0.70, viewport["height"] * 0.24),
        (viewport["width"] * 0.60, viewport["height"] * 0.24),
        (viewport["width"] * 0.52, viewport["height"] * 0.24),
        (viewport["width"] * 0.45, viewport["height"] * 0.24),
        (viewport["width"] * 0.39, viewport["height"] * 0.24),
        (viewport["width"] * 0.33, viewport["height"] * 0.24),
        (viewport["width"] * 0.28, viewport["height"] * 0.24),
        (viewport["width"] * 0.23, viewport["height"] * 0.24),
    ]

    for x, y in candidate_points:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
            page.mouse.click(x, y)
            page.wait_for_timeout(700)
            print(f"Provo schermata canvas ({int(x)}, {int(y)})...")
            if not click_export_button(page):
                continue
            page.wait_for_timeout(900)
            if not visible_text_exists(page, no_selection_pattern, timeout=700):
                print(f"OK: schermata selezionata per export ({int(x)}, {int(y)})")
                return True
            close_export_panel_if_open(page)
        except Error:
            continue

    print("Non riesco a selezionare una schermata esportabile.")
    return False


def select_all_screens_for_export(page) -> bool:
    no_selection_pattern = r"Nessuna\s+schermata\s+selezionata|No\s+screen\s+selected"
    quick_select_pattern = r"Seleziona\s+tutto|Select\s+all"

    if not visible_text_exists(page, no_selection_pattern + "|" + quick_select_pattern, timeout=900):
        return True

    if click_text(page, quick_select_pattern, "seleziona tutte le schermate", timeout=2500):
        page.wait_for_timeout(1500)
    else:
        page.keyboard.press("Meta+A")
        page.wait_for_timeout(1500)
        print("OK: seleziona tutte le schermate con Cmd+A")

    if visible_text_exists(page, no_selection_pattern, timeout=900):
        page.keyboard.press("Meta+A")
        page.wait_for_timeout(1500)
        if visible_text_exists(page, no_selection_pattern, timeout=900):
            print("Non riesco a selezionare le schermate per esportare.")
            return False

    print("OK: schermate selezionate per esportazione")
    return True


def choose_zip_format(page) -> bool:
    zip_pattern = re.compile(r"^\s*\.zip\s*$", re.I)
    viewport = page.viewport_size or {"width": 1440, "height": 950}

    for surface in surfaces(page):
        candidates = surface.locator("button, [role=button], label, div").filter(visible=True)
        try:
            count = min(candidates.count(), 240)
        except Error:
            continue

        for index in range(count):
            item = candidates.nth(index)
            text = locator_text(item)
            if not zip_pattern.search(text):
                continue
            try:
                box = item.bounding_box(timeout=600)
            except Error:
                continue
            if not box:
                continue

            if box["x"] >= viewport["width"] - 450:
                try:
                    item.click(timeout=2500)
                    page.wait_for_timeout(700)
                    print("OK: formato .zip")
                    return True
                except Error:
                    continue

    if click_text(page, r"^\s*\.zip\s*$", "formato .zip", timeout=2500):
        page.wait_for_timeout(700)
        return True

    print("Non trovo il formato .zip nel pannello Esporta.")
    return False


def fill_export_description_if_present(page) -> None:
    viewport = page.viewport_size or {"width": 1440, "height": 950}
    text = "Esporta il progetto Stitch completo in formato zip."

    for surface in surfaces(page):
        candidates = surface.locator("textarea, input").filter(visible=True)
        try:
            count = min(candidates.count(), 40)
        except Error:
            continue

        for index in range(count):
            item = candidates.nth(index)
            try:
                box = item.bounding_box(timeout=500)
            except Error:
                continue
            if not box or box["x"] < viewport["width"] - 460:
                continue
            try:
                item.fill(text, timeout=1500)
                print("OK: descrizione export compilata")
                return
            except Error:
                continue


def click_right_export_panel_button(page) -> bool:
    pattern = re.compile(r"^\s*(Esporta|Export)\s*$", re.I)
    viewport = page.viewport_size or {"width": 1440, "height": 950}

    for attempt in range(5):
        for surface in surfaces(page):
            candidates = surface.locator("button, [role=button]").filter(visible=True)
            try:
                count = min(candidates.count(), 160)
            except Error:
                continue

            for index in range(count):
                item = candidates.nth(index)
                text = locator_text(item)
                if not pattern.search(text):
                    continue
                try:
                    box = item.bounding_box(timeout=600)
                except Error:
                    continue
                if not box:
                    continue

                is_right_panel = box["x"] >= viewport["width"] - 430
                is_lower_half = box["y"] >= viewport["height"] * 0.45
                if is_right_panel and is_lower_half:
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    try:
                        page.mouse.move(x, y)
                        page.mouse.down()
                        page.wait_for_timeout(120)
                        page.mouse.up()
                        page.wait_for_timeout(700)
                        print(f"OK: click fisico pulsante esporta nel pannello ({int(x)}, {int(y)})")
                        return True
                    except Error:
                        try:
                            item.click(timeout=2500, force=True)
                            page.wait_for_timeout(700)
                            print("OK: pulsante esporta nel pannello")
                            return True
                        except Error:
                            continue

        if attempt < 4:
            page.mouse.move(viewport["width"] - 200, viewport["height"] - 140)
            page.mouse.wheel(0, 850)
            page.wait_for_timeout(700)

    print("Non trovo il pulsante Esporta nel pannello.")
    return False


def click_export_panel_button_by_coordinates(page) -> bool:
    viewport = page.viewport_size or {"width": 1440, "height": 950}
    x = viewport["width"] - 205
    y = viewport["height"] - 48
    try:
        page.mouse.move(x, y)
        page.wait_for_timeout(100)
        page.mouse.down()
        page.wait_for_timeout(180)
        page.mouse.up()
        page.wait_for_timeout(1000)
        print(f"OK: click coordinate bottone Esporta ({int(x)}, {int(y)})")
        return True
    except Error:
        print("Non riesco a cliccare il bottone Esporta a coordinate.")
        return False


def unique_destination(path: Path) -> Path:
    if not path.suffix:
        path = path.with_suffix(".zip")
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    return path.with_name(f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}{suffix}")


def last_project_id() -> str:
    try:
        value = LAST_PROJECT_URL_PATH.read_text().strip()
    except OSError:
        return ""
    match = re.search(r"/projects/(\d+)", value)
    return match.group(1) if match else ""


def zip_destination_for(source_name: str) -> Path:
    project_id = last_project_id()
    if project_id:
        return unique_destination(DOWNLOAD_DIR / f"stitch-project-{project_id}.zip")
    return unique_destination(DOWNLOAD_DIR / source_name)


def save_playwright_download(download) -> Path:
    suggested = download.suggested_filename or f"stitch-project-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    destination = zip_destination_for(suggested)
    download.save_as(str(destination))
    print(f"Download salvato: {destination}")
    return destination


def is_complete_zip(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.endswith(".crdownload"):
        return False
    # Chrome/Stitch can save the project as a UUID-like file with no suffix.
    # It is still a valid ZIP, but Finder cannot open it until we add .zip.
    if path.suffix and path.suffix.lower() != ".zip":
        return False

    try:
        size_before = path.stat().st_size
        if size_before <= 0:
            return False
        time.sleep(1)
        size_after = path.stat().st_size
        if size_before != size_after:
            return False
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def zip_has_site_code(path: Path) -> bool:
    """Lo ZIP contiene un SITO, non un allegato reso a schermo.

    Prima bastava che esistesse un `code.html`: ma Stitch crea una schermata
    anche per ogni .md allegato, quindi passava anche un export contenente
    solo il manifest (visto il 2026-07-25). Ora il contenuto deve avere una
    struttura da sito.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            nomi = [
                name for name in archive.namelist()
                if name.endswith("/code.html") or name == "code.html"
            ]
            if not nomi:
                return False
            for name in nomi:
                testo = archive.read(name).decode("utf-8", errors="ignore")
                if looks_like_generated_website(testo):
                    return True
            print("ZIP scartato: il code.html non e' un sito (allegato reso a schermo).")
            return False
    except (OSError, zipfile.BadZipFile, KeyError):
        return False


def _load_guest_image_manifest() -> dict[str, dict]:
    """Appiattisce il manifest Stadio 1 in {var: {file, name, kind}}.

    I nomi variabile portano gia' il prefisso di slot (`g1img-*`, `g2img-*`),
    quindi sono univoci fra i due Guest: si possono unire senza collisioni.
    """
    if not GUEST_IMAGE_MANIFEST_PATH.is_file():
        return {}
    try:
        raw = json.loads(GUEST_IMAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    flat: dict[str, dict] = {}
    for entries in raw.values():
        if isinstance(entries, dict):
            flat.update(entries)
    return flat


def _rewrite_html_to_real_images(html: str, manifest: dict[str, dict]) -> tuple[str, dict[str, str], int]:
    """Riscrive i riferimenti LQIP sulle foto originali (percorsi relativi).

    Ritorna (html_riscritto, {arcname_relativo: file_origine}, sostituzioni).
    Non riserializza il documento: tocca solo le dichiarazioni `--gNimg-K:` e
    gli `src` degli <img data-guest-img>, lasciando intatto il resto
    dell'output di Stitch.
    """
    used: dict[str, str] = {}
    replacements = 0

    for var, entry in manifest.items():
        source = Path(entry.get("file", ""))
        if not source.is_file():
            continue
        rel = f"assets/guest/{entry['name']}"
        kind = entry.get("kind", "var")
        if kind == "var":
            # `--g1img-1: url(<lqip>)`  ->  `--g1img-1: url(assets/guest/..)`
            pattern = re.compile(
                r"(--" + re.escape(var) + r"\s*:\s*)url\(\s*['\"]?[^)]*?['\"]?\s*\)"
            )
            html, n = pattern.subn(lambda m: f"{m.group(1)}url({rel})", html)
        else:
            # <img ... data-guest-img="g1img-1" ... src="<lqip>">: riscrivi il src
            # dell'esatto tag marcato, in qualunque ordine siano gli attributi.
            n = 0

            def rewrite_img(match: "re.Match[str]") -> str:
                nonlocal n
                tag = match.group(0)
                if f'data-guest-img="{var}"' not in tag and f"data-guest-img='{var}'" not in tag:
                    return tag
                new_tag, count = re.subn(
                    r"""\bsrc\s*=\s*(['"]).*?\1""", f'src="{rel}"', tag, count=1
                )
                if count == 0:  # <img> senza src esplicito: aggiungilo
                    new_tag = tag[:-1].rstrip() + f' src="{rel}">' if tag.endswith(">") else tag
                n += 1
                return new_tag

            html = re.sub(r"<img\b[^>]*>", rewrite_img, html)
        if n:
            used[rel] = str(source)
            replacements += n
    return html, used, replacements


def inject_original_guest_images(zip_path: Path) -> None:
    """Stadio 2: sostituisce le anteprime LQIP con le foto originali full-res.

    Il bundle Guest consegna a Stitch solo un'anteprima leggera di ogni foto
    (variabile CSS o data URI su <img>), cosi' Stitch non inventa immagini IA.
    Qui, a valle del download, copiamo le foto ORIGINALI a piena risoluzione
    nell'export e puntiamo i riferimenti su quei file: il sito consegnato ha la
    stessa qualita' del componente originale. Le foto sono le demo del
    componente, il punto di partenza da cui l'utente sostituisce a mano.

    Non solleva mai: un fallimento qui non deve buttare via un download valido.
    """
    try:
        manifest = _load_guest_image_manifest()
        if not manifest:
            return
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            code_name = next(
                (n for n in names if n.endswith("/code.html") or n == "code.html"), None
            )
            if code_name is None:
                return
            html = archive.read(code_name).decode("utf-8", errors="ignore")
            others = {n: archive.read(n) for n in names if n != code_name}

        root = code_name.rsplit("/", 1)[0] + "/" if "/" in code_name else ""
        new_html, used, replacements = _rewrite_html_to_real_images(html, manifest)
        if not used:
            print("Stadio 2 foto: nessun marker trovato nell'export (Stitch li ha rimossi?).")
            return

        tmp = zip_path.with_suffix(".stage2.zip")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name, data in others.items():
                out.writestr(name, data)
            out.writestr(code_name, new_html)
            for rel, source in used.items():
                out.write(source, f"{root}{rel}")
        tmp.replace(zip_path)
        print(
            f"Stadio 2 foto: {replacements} riferimenti su {len(used)} foto originali "
            f"({len(manifest)} nel manifest) iniettati a piena risoluzione in {zip_path.name}."
        )
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"Stadio 2 foto: salto l'iniezione ({exc}). Il download resta valido.")


SELECTION_PATH = Path("/Users/utente/Downloads/reference_splitter/CURRENT_MOTION_SELECTION.json")

# Markup delle icone Material: `<span class="material-symbols-outlined">arrow_forward</span>`.
# Vanno tolte insieme al loro contenuto, altrimenti resta la parola "arrow_forward"
# come testo visibile nel sito.
_ICON_SPAN = re.compile(
    r"<(span|i)\b[^>]*(?:material-symbols|material-icons)[^>]*>.*?</\1>",
    re.I | re.S,
)
_ICON_STYLESHEET = re.compile(
    r"<link\b[^>]*Material\+Symbols[^>]*>", re.I
)


def _brand_variants(nome: str) -> list[str]:
    """Varianti con cui un marchio puo' comparire nell'HTML."""
    base = " ".join(nome.split())
    varianti = {base, base.upper(), base.lower(), base.title()}
    # `Ca' San Sebastiano` compare anche come `Ca&#39;` o con apostrofo curvo.
    for apostrofo in ("&#39;", "&apos;", "’", "'"):
        varianti.add(base.replace("'", apostrofo))
        varianti.add(base.upper().replace("'", apostrofo))
    # Senza apostrofo: `CA SAN SEBASTIANO`
    varianti.add(base.replace("'", ""))
    varianti.add(base.upper().replace("'", ""))
    return sorted((v for v in varianti if v), key=len, reverse=True)


def enforce_site_identity(zip_path: Path) -> None:
    """PALETTO: impone l'identita' decisa da Python, invece di verificarla.

    Le 2 reference sono 2 aziende diverse: Stitch tende a lasciare i marchi
    veri nel sito (visto: hero "Mauro Sebaste", sezione "Cantine Pierino
    Vellano", footer "CA' SAN SEBASTIANO", tre identita' in una pagina).

    Chiederglielo nel prompt e poi controllarlo con un gate non serve: il gate
    scopre il problema a generazione gia' spesa. Qui il problema viene
    RIMOSSO a valle, deterministicamente, senza chiedere niente a nessuno:
    - ogni marchio reale viene sostituito col nome inventato;
    - le icone Material vengono tolte (col loro testo, es. `arrow_forward`).

    Non solleva mai: un fallimento non deve invalidare un download buono.
    """
    try:
        selezione = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    brand = selezione.get("brand") or {}
    nome_nuovo = brand.get("name")
    vietati = selezione.get("forbidden_brands") or []
    if not nome_nuovo:
        return

    try:
        with zipfile.ZipFile(zip_path) as archive:
            nomi = archive.namelist()
            code_name = next(
                (n for n in nomi if n.endswith("/code.html") or n == "code.html"), None
            )
            if code_name is None:
                return
            html = archive.read(code_name).decode("utf-8", errors="ignore")
            altri = {n: archive.read(n) for n in nomi if n != code_name}

        originale = html
        sostituzioni: dict[str, int] = {}

        for marchio in vietati:
            for variante in _brand_variants(marchio):
                if variante in html:
                    # Il nome nuovo segue il "caso" della variante trovata.
                    if variante.isupper():
                        rimpiazzo = nome_nuovo.upper()
                    elif variante.islower():
                        rimpiazzo = nome_nuovo.lower()
                    else:
                        rimpiazzo = nome_nuovo
                    quante = html.count(variante)
                    html = html.replace(variante, rimpiazzo)
                    sostituzioni[marchio] = sostituzioni.get(marchio, 0) + quante

        icone = len(_ICON_SPAN.findall(html))
        html = _ICON_SPAN.sub("", html)
        html = _ICON_STYLESHEET.sub("", html)

        if html == originale:
            return

        tmp = zip_path.with_suffix(".identity.zip")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for nome, dati in altri.items():
                out.writestr(nome, dati)
            out.writestr(code_name, html)
        tmp.replace(zip_path)

        dettaglio = ", ".join(f"{k} x{v}" for k, v in sostituzioni.items()) or "nessun marchio"
        print(
            f"Identita' imposta: {dettaglio} -> '{nome_nuovo}'; "
            f"icone Material rimosse: {icone}."
        )
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"Identita': salto l'imposizione ({exc}). Il download resta valido.")


# Plugin GSAP arrivati sul CDN pubblico solo con la 3.13: su 3.12.x l'URL
# risponde 404 (verificato con curl il 2026-07-27).
BONUS_GSAP_PLUGINS = (
    "SplitText", "MorphSVGPlugin", "DrawSVGPlugin", "ScrollSmoother",
    "InertiaPlugin", "CustomBounce", "CustomWiggle", "GSDevTools",
)


def repair_mechanical_defects(zip_path: Path) -> None:
    """Ripara i difetti MECCANICI dell'export: quelli con una sola risposta possibile.

    Terzo stadio, accanto a inject_original_guest_images() e
    enforce_site_identity(). Qui non si decide niente di creativo: si correggono
    due errori che hanno una risposta unica e verificabile, e che il prompt
    chiede ma Stitch puo' sempre sbagliare.

    1. VERSIONE GSAP. Il prompt scrive 3.13.0 in tutte e cinque le righe; il
       2026-07-27 Stitch ha riscritto 3.12.5 di sua iniziativa. Su 3.12.5
       `SplitText.min.js` risponde 404: il simbolo resta undefined, la prima
       `registerPlugin(... SplitText)` lancia ReferenceError e TUTTO il codice
       sotto quella riga non viene mai eseguito. Risultato consegnato: Lenis
       morto, menu che non si nasconde, hero e titoli invisibili.

    2. CONTENUTO NASCOSTO DAL CSS. Stitch aggiunge di sua iniziativa un
       "anti-FOUC" tipo `.mk-line, .mk-hero { opacity: 0; }` e lascia al JS il
       compito di riaccendere il testo. E' un interruttore generale: un solo
       script mancante svuota la pagina. Il kit usa gsap.from(), che degrada
       bene da solo, quindi quella riga va semplicemente cancellata.

    Non solleva mai: un fallimento qui non deve buttare via un download valido.
    """
    try:
        with zipfile.ZipFile(zip_path) as archive:
            nomi = archive.namelist()
            code_name = next(
                (n for n in nomi if n.endswith("/code.html") or n == "code.html"), None
            )
            if code_name is None:
                return
            html = archive.read(code_name).decode("utf-8", errors="ignore")
            altri = {n: archive.read(n) for n in nomi if n != code_name}

        originale = html
        versioni = 0
        nascosti: list[str] = []
        conservati: list[str] = []

        # CLASSI CHE IL JS ANIMA DAVVERO — leggere prima di toccare le regole
        # che nascondono. Il 2026-07-28 abbiamo scoperto che questa riparazione
        # cancellava `.js .mk-reveal { opacity: 0 }`, cioe' lo STATO INIZIALE
        # dell'animazione: l'elemento restava visibile dall'inizio e il reveal
        # allo scroll non si vedeva piu'. Le animazioni sparivano DOPO il
        # download, per mano nostra, e sembrava che Stitch non le avesse fatte.
        # Se il nome della classe compare dentro un <script>, quella regola non
        # e' un difetto: e' il "prima" di un'animazione, e va TENUTA.
        script_js = "\n".join(
            re.findall(r"<script[^>]*>(.*?)</script>", html, re.S | re.I)
        )

        # 1. Riscrive la versione SOLO sugli URL dei plugin bonus, che sono i
        #    soli a non esistere prima della 3.13. gsap.min.js e ScrollTrigger
        #    funzionano anche su 3.12.x e non li tocchiamo: allineiamo la
        #    versione di tutto il gruppo solo se un plugin bonus e' coinvolto.
        plugin_alternative = "|".join(BONUS_GSAP_PLUGINS)
        if re.search(
            rf"gsap/3\.(?:0|1|2|3|4|5|6|7|8|9|10|11|12)(?:\.\d+)?/(?:{plugin_alternative})\.min\.js",
            html,
        ):
            html, versioni = re.subn(
                r"(gsap/)3\.(?:0|1|2|3|4|5|6|7|8|9|10|11|12)(?:\.\d+)?(/)",
                r"\g<1>3.13.0\g<2>",
                html,
            )

        # 2. Cancella le regole che nascondono contenuto in attesa del JS.
        # Tre modi di nascondere lo stesso testo. Vanno trattati insieme:
        # togliere solo `opacity` lascia in piedi il clip-path, che nasconde
        # esattamente come prima. `inset(... 90%+ ...)` copre praticamente tutto
        # l'elemento, quindi conta come nascondere.
        nasconde = (
            r"opacity\s*:\s*0(?:\.0*)?\s*(?:;|$)"
            r"|visibility\s*:\s*hidden"
            r"|clip-path\s*:\s*inset\([^)]*(?:9\d|100)%[^)]*\)"
        )

        def _spegni_regola(match: re.Match) -> str:
            selettore, corpo = match.group(1), match.group(2)
            if not re.search(nasconde, corpo):
                return match.group(0)
            # Il filtro guardava SOLO i selettori di classe (.mk-, .reveal...).
            # Il 2026-07-27 Stitch ha scritto invece
            #   [data-motion-role] { opacity: 0 }
            # cioe' un selettore di ATTRIBUTO, applicato a 54 elementi fra cui
            # il logo e tutte le voci di menu: 30 restavano invisibili anche
            # dopo aver scorso tutta la pagina. La riparazione non lo vedeva.
            if not re.search(
                r"\.(?:mk-|reveal|split|line|fade|anim)"
                r"|\[data-(?:motion|anim|reveal|scroll|stitch-fill)",
                selettore,
                re.I,
            ):
                return match.group(0)
            # Su pseudo-classi e pseudo-elementi `opacity: 0` e' uno stato
            # legittimo (underline che compare all'hover, overlay chiuso): non
            # e' contenuto nascosto in attesa del JS. Non toccarli.
            if re.search(r"::?(?:hover|focus|active|before|after|not|checked)", selettore, re.I):
                return match.group(0)
            # STATO INIZIALE DI UN'ANIMAZIONE: se il JS nomina questa classe o
            # questo attributo, GSAP la rivelera' allo scroll. Cancellarla
            # significa cancellare l'animazione. La teniamo, e ci pensa la rete
            # di sicurezza iniettata piu' sotto a evitare che resti invisibile
            # per sempre se il JS non parte o il trigger non scatta.
            token = [t for t in re.findall(r"[.\[]([A-Za-z0-9_-]+)", selettore) if len(t) > 2]
            if token and any(t in script_js for t in token):
                conservati.append(re.sub(r"/\*.*?\*/", "", selettore, flags=re.S).strip())
                return match.group(0)
            # Etichetta per il log: via i commenti CSS che precedono il selettore.
            nascosti.append(
                re.sub(r"/\*.*?\*/", "", selettore, flags=re.S).strip()[:60]
            )
            ripulito = re.sub(
                r"opacity\s*:\s*0(?:\.0*)?\s*;?"
                r"|visibility\s*:\s*hidden\s*;?"
                r"|clip-path\s*:\s*inset\([^)]*(?:9\d|100)%[^)]*\)\s*;?",
                "",
                corpo,
            )
            if not ripulito.strip():
                return ""
            return f"{selettore}{{{ripulito}}}"

        def _ripulisci_style(match: re.Match) -> str:
            apertura, contenuto, chiusura = match.group(1), match.group(2), match.group(3)
            nuovo = re.sub(r"([^{}]+)\{([^{}]*)\}", _spegni_regola, contenuto)
            return f"{apertura}{nuovo}{chiusura}"

        html = re.sub(
            r"(<style\b[^>]*>)(.*?)(</style>)",
            _ripulisci_style,
            html,
            flags=re.I | re.S,
        )

        # 3. Rimette la GABBIA DI CONTENIMENTO sulla root del Guest.
        #    Gliela consegniamo gia' scritta e marcata "NON RIMUOVERE", ma il
        #    2026-07-27 Stitch ha riscritto quel blocco tenendo solo
        #    `position: relative` e buttando via `min-height`, `overflow` e
        #    `contain`. Senza `min-height` la section collassa a 0px se i suoi
        #    figli sono absolute; senza `overflow: hidden` le scene si
        #    disegnano sopra le sezioni successive (titoli del componente
        #    stampati sopra contatti e footer). E' un blocco CSS nostro, con un
        #    id noto: rimetterlo non richiede nessun giudizio.
        gabbia = 0
        for root_id in re.findall(r'id="(guest-\d+-[a-z0-9-]+)"', html):
            regola = re.search(
                rf"#{re.escape(root_id)}\s*\{{([^}}]*)\}}", html
            )
            if regola and "min-height" in regola.group(1) and "overflow" in regola.group(1):
                continue
            html = html.replace(
                "</head>",
                f"<style id=\"stitch-guest-cage-{root_id}\">\n"
                f"  /* GABBIA DI CONTENIMENTO reinserita a valle del download:\n"
                f"     senza min-height la section collassa a 0px, senza\n"
                f"     overflow le scene coprono le sezioni successive. */\n"
                f"  #{root_id} {{\n"
                f"    position: relative;\n"
                f"    overflow: hidden;\n"
                f"    isolation: isolate;\n"
                f"    transform: translateZ(0);\n"
                f"    contain: layout paint;\n"
                f"    min-height: 100vh;\n"
                f"  }}\n"
                f"  #{root_id} > * {{ max-width: 100%; }}\n"
                f"</style>\n</head>",
                1,
            )
            gabbia += 1

        # RETE DI SICUREZZA per le regole appena CONSERVATE.
        # Tenere lo stato iniziale dell'animazione riporta gli effetti, ma
        # riapre il rischio del 2026-07-27: se il JS non parte o lo
        # ScrollTrigger non scatta, quegli elementi restano invisibili per
        # sempre (30 elementi, logo e menu compresi). Qui il compromesso:
        # l'elemento resta nascosto - e quindi animabile - ma se dopo 3,5s e'
        # ancora invisibile MENTRE E' SOTTO GLI OCCHI, lo riveliamo noi.
        # Chi e' piu' in basso resta nascosto e conserva il suo reveal.
        if conservati:
            selettori_js = json.dumps(sorted(set(conservati)))
            html = html.replace(
                "</body>",
                "<script id=\"stitch-reveal-watchdog\">\n"
                "(function () {\n"
                f"  var SEL = {selettori_js};\n"
                "  function salva() {\n"
                "    SEL.forEach(function (sel) {\n"
                "      var nodi;\n"
                "      try { nodi = document.querySelectorAll(sel); } catch (e) { return; }\n"
                "      Array.prototype.forEach.call(nodi, function (el) {\n"
                "        var r = el.getBoundingClientRect();\n"
                "        if (r.bottom < 0 || r.top > window.innerHeight) return;\n"
                "        var s = getComputedStyle(el);\n"
                "        if (parseFloat(s.opacity) > 0.01 && s.visibility !== 'hidden') return;\n"
                "        el.style.setProperty('opacity', '1', 'important');\n"
                "        el.style.setProperty('visibility', 'visible', 'important');\n"
                "        el.style.setProperty('clip-path', 'none', 'important');\n"
                "      });\n"
                "    });\n"
                "  }\n"
                "  var atteso = false;\n"
                "  function programma() {\n"
                "    if (atteso) return;\n"
                "    atteso = true;\n"
                "    setTimeout(function () { atteso = false; salva(); }, 3500);\n"
                "  }\n"
                "  window.addEventListener('load', programma);\n"
                "  window.addEventListener('scroll', programma, { passive: true });\n"
                "})();\n"
                "</script>\n</body>",
                1,
            )

        # MOTION KIT DICHIARATO MA MAI SCRITTO — 2026-07-28.
        # Stitch marca gli elementi con .mk-hero/.mk-reveal/.mk-parallax/
        # .mk-scrub e poi consegna
        #     <script id="stitch-motion-components">/* Motion Kit */</script>
        # cioe' un commento vuoto: le classi non animano NIENTE e la pagina
        # sembra semplicemente ferma. E' il "ne esegue uno e finge gli altri"
        # nella forma piu' pura, e non serve chiedergli di rifarlo: le
        # animazioni di base sono meccaniche e le scriviamo noi, sempre uguali
        # e sempre funzionanti. Se invece Stitch le ha scritte davvero, non
        # tocchiamo niente.
        # FAMIGLIA PER FAMIGLIA, non tutto-o-niente. Stitch ne implementa
        # alcune e ne salta altre: il 2026-07-28 aveva scritto mk-line,
        # mk-reveal e mk-parallax ma NON mk-scrub, che era sullo sfondo della
        # hero e su tre card. Un controllo unico avrebbe o lasciato mk-scrub
        # morto, o riscritto sopra le tre gia' funzionanti raddoppiandole.
        # Una classe conta come implementata se il suo nome compare in un
        # qualunque script della pagina (querySelectorAll, selettore, stringa).
        FAMIGLIE = ("hero", "reveal", "line", "fade", "parallax", "scrub")
        presenti = {
            f for f in FAMIGLIE
            if re.search(rf'class="[^"]*\bmk-{f}\b', html)
        }
        orfane = sorted(f for f in presenti if f"mk-{f}" not in script_js)
        classi_mk = orfane
        motion_kit = 0
        if orfane and "gsap.min.js" in html:
            motion_kit = len(orfane)
            blocchi = {
                "hero": "  tutti('.mk-hero').forEach(function (el, i) {\n"
                        "    gsap.from(el, { opacity: 0, y: 30, scale: 0.98, duration: 1.1,\n"
                        "      ease: EASE, delay: 0.15 + i * 0.08 });\n  });\n",
                "reveal": "  tutti('.mk-reveal').forEach(function (el) {\n"
                          "    gsap.from(el, { opacity: 0, y: 36, scale: 0.985, duration: 0.9,\n"
                          "      ease: EASE, scrollTrigger: { trigger: el, start: 'top 85%', once: true } });\n  });\n",
                "line": "  tutti('.mk-line').forEach(function (el) {\n"
                        "    gsap.from(el, { opacity: 0, y: 30, duration: 1, ease: EASE,\n"
                        "      scrollTrigger: { trigger: el, start: 'top 85%', once: true } });\n  });\n",
                "fade": "  tutti('.mk-fade').forEach(function (el) {\n"
                        "    gsap.from(el, { opacity: 0, duration: 0.8, ease: EASE,\n"
                        "      scrollTrigger: { trigger: el, start: 'top 90%', once: true } });\n  });\n",
                "parallax": "  tutti('.mk-parallax').forEach(function (el) {\n"
                            "    gsap.fromTo(el, { yPercent: -8 }, { yPercent: 8, ease: 'none',\n"
                            "      scrollTrigger: { trigger: el.parentElement || el, start: 'top bottom',\n"
                            "        end: 'bottom top', scrub: true } });\n  });\n",
                "scrub": "  tutti('.mk-scrub').forEach(function (el) {\n"
                         "    gsap.fromTo(el, { scale: 1.12 }, { scale: 1, ease: 'none',\n"
                         "      scrollTrigger: { trigger: el, start: 'top bottom', end: 'top 30%',\n"
                         "        scrub: true } });\n  });\n",
            }
            corpo = "".join(blocchi[f] for f in orfane)
            html = html.replace(
                "</body>",
                "<script id=\"stitch-motion-kit-fallback\">\n"
                "/* Implementazione del motion kit: Stitch aveva dichiarato le classi\n"
                "   mk-* lasciando vuoto #stitch-motion-components. Curve morbide,\n"
                "   nessun rimbalzo, nessuna partenza da scale(0). */\n"
                "(function () {\n"
                "  if (!window.gsap || document.getElementById('mk-kit-done')) return;\n"
                "  var m = document.createElement('meta'); m.id = 'mk-kit-done';\n"
                "  document.head.appendChild(m);\n"
                "  if (window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);\n"
                "  var EASE = 'power3.out';\n"
                "  function tutti(sel) { return gsap.utils.toArray(sel); }\n"
                + corpo +
                "})();\n"
                "</script>\n</body>",
                1,
            )

        if html == originale:
            print("Riparazione meccanica: niente da correggere.")
            return

        tmp = zip_path.with_suffix(".repair.zip")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name, data in altri.items():
                out.writestr(name, data)
            out.writestr(code_name, html)
        tmp.replace(zip_path)

        parti = []
        if versioni:
            parti.append(f"{versioni} URL GSAP portati a 3.13.0 (i 3.12.x davano 404)")
        if nascosti:
            parti.append(
                f"{len(nascosti)} regole che nascondevano contenuto rimosse "
                f"({', '.join(dict.fromkeys(nascosti))})"
            )
        if motion_kit:
            parti.append(
                f"MOTION KIT SCRITTO DA NOI: Stitch aveva dichiarato {motion_kit} "
                f"famiglie mk-* ({', '.join(classi_mk)}) lasciando vuoto lo script; "
                f"senza questo la pagina restava ferma"
            )
        if conservati:
            unici = list(dict.fromkeys(conservati))
            parti.append(
                f"{len(unici)} stati iniziali di animazione CONSERVATI "
                f"({', '.join(s[:40] for s in unici[:4])}"
                f"{'...' if len(unici) > 4 else ''}) + rete di sicurezza a 3,5s"
            )
        if gabbia:
            parti.append(
                f"{gabbia} gabbia/e di contenimento Guest reinserite "
                f"(Stitch le aveva cancellate: senza, la section collassa a 0px)"
            )
        print("Riparazione meccanica: " + "; ".join(parti) + ".")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"Riparazione meccanica: salto ({exc}). Il download resta valido.")


def reject_incomplete_export(path: Path) -> None:
    try:
        REJECTED_DIR.mkdir(parents=True, exist_ok=True)
        destination = unique_destination(REJECTED_DIR / path.name)
        shutil.move(str(path), str(destination))
        print(f"Export incompleto spostato negli scarti: {destination}")
    except OSError as exc:
        print(f"Non riesco a spostare export incompleto: {exc}")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_mcp_response(raw: bytes, content_type: str | None) -> dict[str, Any]:
    text = raw.decode("utf-8", "replace")
    if content_type and "text/event-stream" in content_type:
        payloads = []
        for line in text.splitlines():
            if line.startswith("data:"):
                payloads.append(line[5:].strip())
        text = "\n".join(payloads)
    return json.loads(text)


def mcp_rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    load_dotenv(ENV_PATH)
    api_key = os.environ.get("STITCH_API_KEY")
    if not api_key:
        raise RuntimeError(f"STITCH_API_KEY mancante in {ENV_PATH}")

    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params

    request = urllib.request.Request(
        MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "X-Goog-Api-Key": api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        return parse_mcp_response(response.read(), response.headers.get("content-type"))


def mcp_call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return mcp_rpc("tools/call", {"name": name, "arguments": arguments})


def walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def screen_id_from_name(name: str) -> str:
    match = re.search(r"/screens/([^/]+)", name)
    return match.group(1) if match else name


def collect_screen_refs(response: dict[str, Any], project_id: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    screens: list[dict[str, str]] = []

    for node in walk_json(response):
        raw_name = node.get("name")
        if not isinstance(raw_name, str):
            continue
        if f"projects/{project_id}/screens/" not in raw_name:
            continue

        screen_id = screen_id_from_name(raw_name)
        if screen_id in seen:
            continue
        seen.add(screen_id)
        screens.append(
            {
                "name": raw_name,
                "screenId": screen_id,
                "title": str(node.get("title") or ""),
            }
        )

    return screens


def file_bytes_from_mcp_file(file_info: Any) -> tuple[bytes | None, str]:
    if not isinstance(file_info, dict):
        return None, ""

    mime_type = str(file_info.get("mimeType") or "")
    encoded = file_info.get("fileContentBase64")
    if isinstance(encoded, str) and encoded:
        try:
            return base64.b64decode(encoded), mime_type
        except (ValueError, TypeError):
            return None, mime_type

    url = file_info.get("downloadUrl")
    if not isinstance(url, str) or not url:
        return None, mime_type

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
            return data, mime_type or str(response.headers.get("content-type") or "")
    except (urllib.error.URLError, OSError) as exc:
        print(f"Non riesco a scaricare file MCP {url[:80]}...: {exc}")
        return None, mime_type


def looks_like_html(data: bytes) -> bool:
    sample = data[:5000].decode("utf-8", "ignore").lower()
    return ("<html" in sample or "<body" in sample or "<!doctype" in sample) and len(data) > 300


def mcp_screen_payload(project_id: str, screen_ref: dict[str, str]) -> dict[str, Any] | None:
    screen_id = screen_ref["screenId"]
    name = screen_ref["name"] or f"projects/{project_id}/screens/{screen_id}"
    try:
        return mcp_call_tool(
            "get_screen",
            {
                "name": name,
                "projectId": project_id,
                "screenId": screen_id,
            },
        )
    except Exception as exc:
        print(f"MCP get_screen fallito per {screen_id}: {exc}")
        return None


def looks_like_generated_website(text: str) -> bool:
    """True solo se la schermata e' un SITO, non un documento.

    Stitch trasforma in schermate anche gli allegati .md che carichiamo
    (manifest, bundle componente...). Quelle schermate contengono le PAROLE
    "gsap.", "ScrollTrigger", "data-motion-component=" perche' le nominano nel
    testo, quindi col punteggio a parole vincevano sempre: il 2026-07-25 e'
    stato scaricato STITCH_MOTION_EXECUTION_MANIFEST.md al posto del sito, con
    200008 punti (il massimo) e zero <section>.

    Un sito generato ha sempre almeno una <section>, oppure un <header>/<nav>
    piu' un <footer>. Un documento markdown reso a schermo non ha nessuno di
    questi tag strutturali.
    """
    lowered = text.lower()
    sections = lowered.count("<section")
    if sections >= 1:
        return True
    has_shell = ("<header" in lowered or "<nav" in lowered) and "<footer" in lowered
    return has_shell


def score_screen_html(content: bytes) -> int:
    """Punteggio della schermata. Ritorna -1 per le schermate NON-sito.

    I marker vanno cercati come attributi HTML reali, non come parole nel
    testo: un allegato che li cita non li possiede.
    """
    text = content.decode("utf-8", errors="ignore")
    if not looks_like_generated_website(text):
        return -1

    score = len(content) // 1000  # base score dalla dimensione in KB
    # Marker cercati dentro un tag aperto (`<... data-motion-...`), cosi' una
    # citazione dentro <pre>/<code> non conta come possesso reale.
    def has_attribute(name: str) -> bool:
        return bool(re.search(rf"<[a-zA-Z][^>]*\b{re.escape(name)}", text))

    if has_attribute("data-motion-manifest"):
        score += 100000
    if has_attribute("data-motion-component="):
        score += 50000
    if re.search(r"gsap\s*\.\s*(?:timeline|to|from|fromTo|set|registerPlugin)\s*\(", text):
        score += 30000
    if "new Lenis" in text:
        score += 20000
    if has_attribute("data-stitch-native-component"):
        score += 20000
    return score


def find_best_screen_html(project_id: str) -> tuple[bytes | None, dict[str, Any] | None]:
    try:
        screens_response = mcp_call_tool("list_screens", {"projectId": project_id})
    except Exception as exc:
        print(f"MCP list_screens fallito: {exc}")
        return None, None

    screens = collect_screen_refs(screens_response, project_id)
    if not screens:
        print("MCP non ha restituito schermate esportabili.")
        return None, None

    best_html: bytes | None = None
    best_meta: dict[str, Any] | None = None
    best_score: int = -1

    for screen_ref in screens:
        payload = mcp_screen_payload(project_id, screen_ref)
        if not payload:
            continue

        for node in walk_json(payload):
            html_file = node.get("htmlCode") if isinstance(node, dict) else None
            data, _mime = file_bytes_from_mcp_file(html_file)
            if data and looks_like_html(data):
                sc = score_screen_html(data)
                # Punteggio negativo = non e' un sito (allegato .md reso a
                # schermo). Va scartato sempre, anche se e' la prima schermata
                # trovata: `best_html is None` da solo la farebbe passare.
                if sc < 0:
                    titolo = node.get("title") if isinstance(node, dict) else ""
                    print(f"  scarto schermata non-sito: {titolo or 'senza titolo'}")
                    continue
                if best_html is None or sc > best_score:
                    best_html = data
                    best_score = sc
                    best_meta = {
                        "projectId": project_id,
                        "screen": screen_ref,
                        "title": node.get("title") if isinstance(node, dict) else "",
                        "deviceType": node.get("deviceType") if isinstance(node, dict) else "",
                        "width": node.get("width") if isinstance(node, dict) else "",
                        "height": node.get("height") if isinstance(node, dict) else "",
                    }

    if not best_html:
        print(
            "MCP ha trovato schermate, ma nessuna e' un sito generato "
            "(solo allegati/documenti). Non scarico nulla."
        )
    return best_html, best_meta


def create_mcp_recovery_zip(project_id: str) -> Path | None:
    if not project_id:
        return None

    print("Provo recupero via Stitch MCP: cerco htmlCode del progetto...")
    html_data, metadata = find_best_screen_html(project_id)
    if not html_data:
        return None

    destination = unique_destination(DOWNLOAD_DIR / f"stitch-project-{project_id}-mcp-code.zip")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        root = f"stitch-project-{project_id}-mcp-code"
        archive.writestr(f"{root}/code.html", html_data)
        archive.writestr(
            f"{root}/metadata.json",
            json.dumps(metadata or {"projectId": project_id}, indent=2, ensure_ascii=False),
        )

    if not zip_has_site_code(destination):
        print(f"Recupero MCP creato ma non valido: {destination}")
        reject_incomplete_export(destination)
        return None

    inject_original_guest_images(destination)
    enforce_site_identity(destination)
    repair_mechanical_defects(destination)
    LAST_DOWNLOAD_PATH.write_text(str(destination))
    print(f"OK: recupero MCP completato con code.html: {destination}")
    return destination


def wait_for_external_zip(started_at: float, timeout_seconds: int = 180) -> Path | None:
    deadline = time.time() + timeout_seconds
    search_dirs = [DOWNLOAD_DIR, BROWSER_DOWNLOAD_DIR]
    print("Controllo se Chrome ha salvato lo zip direttamente in Downloads...")

    while time.time() < deadline:
        candidates: list[Path] = []
        for folder in search_dirs:
            if not folder.exists():
                continue
            try:
                candidates.extend(
                    path
                    for path in folder.iterdir()
                    if path.is_file()
                    and (path.suffix.lower() == ".zip" or not path.suffix)
                    and path.stat().st_mtime >= started_at - 10
                )
            except OSError:
                continue

        for candidate in sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True):
            if not is_complete_zip(candidate):
                continue

            destination = zip_destination_for(candidate.name)
            try:
                if candidate.resolve() != destination.resolve():
                    shutil.copy2(candidate, destination)
                    print(f"Zip trovato e copiato: {destination}")
                    return destination
                print(f"Zip trovato: {candidate}")
                return candidate
            except OSError as exc:
                print(f"Zip trovato ma non copiabile: {exc}")
                return candidate

        time.sleep(2)

    print("Non trovo zip recenti salvati da Chrome.")
    return None


def try_download_via_menu(page, opener) -> Path | None:
    if not opener(page):
        return None
    page.wait_for_timeout(900)

    if not export_panel_is_open(page):
        started_at = time.time()
        click_download_menu_item(page)
        page.wait_for_timeout(1200)
        if not export_panel_is_open(page):
            direct_download = wait_for_external_zip(started_at, timeout_seconds=45)
            if direct_download:
                return direct_download

    if visible_text_exists(
        page,
        r"Nessuna\s+schermata\s+selezionata|No\s+screen\s+selected|Seleziona\s+tutto|Select\s+all",
        timeout=900,
    ):
        if not ensure_screen_selected_for_export(page):
            return None

    if not choose_zip_format(page):
        return None

    fill_export_description_if_present(page)

    started_at = time.time()
    try:
        with page.expect_download(timeout=25000) as download_info:
            if not click_export_panel_button_by_coordinates(page) and not click_right_export_panel_button(page):
                raise RuntimeError("download action not found")
        download = download_info.value
    except RuntimeError as exc:
        print(f"Download non avviato: {exc}")
        return None
    except TimeoutError:
        print("Stitch non ha mandato l'evento download a Playwright.")
        return wait_for_external_zip(started_at)

    return save_playwright_download(download)


def download_project(page) -> Path | None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    project_id = last_project_id()

    try:
        for attempt in range(1, 4):
            if not wait_for_generation_complete(page, timeout_ms=30 * 60 * 1000):
                return None

            incomplete_export = False

            result = try_download_via_menu(page, click_top_left_menu)
            if result and zip_has_site_code(result):
                inject_original_guest_images(result)
                enforce_site_identity(result)
                repair_mechanical_defects(result)
                LAST_DOWNLOAD_PATH.write_text(str(result))
                return result
            if result:
                print(f"Export incompleto: {result} non contiene code.html.")
                reject_incomplete_export(result)
                incomplete_export = True

            result = try_download_via_menu(page, click_export_button)
            if result and zip_has_site_code(result):
                inject_original_guest_images(result)
                enforce_site_identity(result)
                repair_mechanical_defects(result)
                LAST_DOWNLOAD_PATH.write_text(str(result))
                return result
            if result:
                print(f"Export incompleto: {result} non contiene code.html.")
                reject_incomplete_export(result)
                incomplete_export = True

            if incomplete_export:
                if attempt < 3:
                    print("Aspetto ancora: Stitch potrebbe non aver finito il sito.")
                    page.wait_for_timeout(60000)
                    continue
                fallback = create_mcp_recovery_zip(project_id)
                if fallback:
                    return fallback
                return None
            break

        print("Non sono riuscito a trovare un menu con Scarica progetto.")
    except (NameError, AttributeError, TypeError, ImportError) as exc:
        # Vedi la nota gemella in send_to_stitch.py: un errore di codice non
        # deve MAI essere stampato come "browser disconnesso", altrimenti si
        # cerca la causa nella rete mentre il difetto e' in queste righe.
        print("")
        print("!!! BUG NEL NOSTRO CODICE, non un problema di rete o di Stitch !!!")
        print(f"    {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        print("")
    except Exception as exc:
        print(f"Browser chiuso o disconnesso durante l'attesa/download ({exc}). Passo direttamente al recupero via Stitch MCP...")

    fallback = create_mcp_recovery_zip(project_id)
    if fallback:
        return fallback
    return None


def read_last_project_url() -> str:
    if not LAST_PROJECT_URL_PATH.exists():
        return ""
    value = LAST_PROJECT_URL_PATH.read_text().strip()
    if re.match(r"^https://stitch\.withgoogle\.com/projects/\d+", value):
        return value
    return ""


def choose_project_page(browser, requested_url: str):
    pages = list(browser.pages)

    if requested_url:
        page = pages[0] if pages else browser.new_page()
        page.bring_to_front()
        page.goto(requested_url, wait_until="domcontentloaded", timeout=60000)
        return page

    for candidate in pages:
        if "/projects/" in candidate.url:
            candidate.bring_to_front()
            print(f"Uso progetto gia' aperto: {candidate.url}")
            return candidate

    saved_url = read_last_project_url()
    if saved_url:
        page = pages[0] if pages else browser.new_page()
        page.bring_to_front()
        print(f"Apro ultimo progetto salvato: {saved_url}")
        page.goto(saved_url, wait_until="domcontentloaded", timeout=60000)
        return page

    for candidate in pages:
        if "stitch.withgoogle.com" in candidate.url and candidate.url != "about:blank":
            candidate.bring_to_front()
            print(f"Uso pagina Stitch ripristinata: {candidate.url}")
            return candidate

    page = pages[0] if pages else browser.new_page()
    page.bring_to_front()
    print("Nessun progetto trovato: apro Stitch.")
    page.goto(STITCH_URL, wait_until="domcontentloaded", timeout=60000)
    return page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scarica il progetto Stitch aperto.")
    parser.add_argument(
        "--url",
        default="",
        help="URL progetto Stitch da aprire prima del download. Se vuoto, prova a usare l'ultima pagina ripristinata.",
    )
    parser.add_argument("--wait-login", action="store_true", help="Aspetta il login se richiesto.")
    parser.add_argument("--debug", action="store_true", help="Salva screenshot/HTML debug.")
    parser.add_argument("--slow", action="store_true", help="Rallenta le azioni per debug visivo.")
    parser.add_argument(
        "--browser",
        choices=("chrome", "chromium"),
        default="chrome",
        help="Browser da usare. Default: chrome reale installato sul Mac.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with sync_playwright() as p:
        launch_options = {
            "headless": False,
            "slow_mo": 350 if args.slow else 0,
            "viewport": {"width": 1440, "height": 950},
            "accept_downloads": True,
            "downloads_path": str(DOWNLOAD_DIR),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-crash-reporter",
                "--disable-crashpad",
                "--restore-last-session",
            ],
        }
        if args.browser == "chrome":
            launch_options["channel"] = "chrome"

        try:
            browser = p.chromium.launch_persistent_context(str(PROFILE_DIR), **launch_options)
        except Error as exc:
            print("Non riesco ad aprire Chrome con il profilo Stitch.")
            print("Se hai ancora aperto una finestra automatica di Stitch, chiudila e rilancia questo comando.")
            print(exc)
            return 2

        page = choose_project_page(browser, args.url)
        page.wait_for_timeout(3000)

        if "accounts.google.com" in page.url or "signin" in page.url.lower():
            if args.wait_login:
                print("Stitch chiede login. Fai login nella finestra aperta: continuo appena rientra su Stitch.")
                deadline = time.time() + (LOGIN_WAIT_MS / 1000)
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    if "accounts.google.com" not in page.url and "signin" not in page.url.lower():
                        break
                page.wait_for_timeout(2500)
            else:
                print("Stitch chiede login. Fai login e rilancia il comando.")
                save_debug(page, "download_login_required") if args.debug else None
                browser.close()
                return 2

        result = download_project(page)
        if not result:
            save_debug(page, "download_failed") if args.debug else None
            print("Download non completato. Apri il progetto giusto in Stitch e rilancia.")
            browser.close()
            return 1

        save_debug(page, "download_done") if args.debug else None
        page.wait_for_timeout(2000)
        browser.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
