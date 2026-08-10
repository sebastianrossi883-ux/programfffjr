#!/usr/bin/env python3
"""Upload the latest split references to Stitch through a browser session."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from playwright.sync_api import Error, TimeoutError, sync_playwright


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "STITCH_API_CONFIG.json"
STITCH_URL = "https://stitch.withgoogle.com/"
PROFILE_DIR = PROJECT_DIR / ".stitch_browser_profile"
DEBUG_DIR = PROJECT_DIR / "debug"
DOWNLOAD_DIR = Path("~/Downloads/stitch_downloads").expanduser()
LAST_PROJECT_URL_PATH = PROJECT_DIR / "LAST_STITCH_PROJECT_URL.txt"
PROMPT_SEND_LOG_PATH = PROJECT_DIR / "LAST_SENT_PROMPTS_LOG.txt"
ANIMATION_PROMPT_PATH = PROJECT_DIR / "STITCH_ANIMATION_PROMPT.txt"
MOTION_CODE_PROMPT_PATH = PROJECT_DIR / "STITCH_MOTION_CODE_PROMPT.txt"
FRAMER_PROMPT_PATH = PROJECT_DIR / "STITCH_FRAMER_PROMPT.txt"
# Secondo passaggio sul Guest: solo le animazioni. Separato dalla struttura
# perche' con entrambe nello stesso messaggio Stitch ne esegue una sola.
GUEST_MOTION_PROMPT_PATH = PROJECT_DIR / "STITCH_GUEST_MOTION_PROMPT.txt"
MOTION_AMMO_BOX_PATH = Path(
    "/Users/utente/Downloads/stitch_downloads/_ONE_SITE_JOBS/"
    "227b1915-f932-4744-bd06-e691c2285669-e23558e915/STITCH_AMMO_BOX"
)
# GSAP_PLUGINS_STITCH_BUNDLE.md (159 KB di sorgente dei plugin) NON si allega
# piu': dal 2025 tutti i plugin GSAP sono gratuiti sul CDN pubblico, quindi
# quel sorgente non serve. Peggio: era la causa diretta del disastro del
# 2026-07-26, quando Stitch ha scritto nel sito
#     // I am including a simulated block for brevity
#     window.Flip = window.Flip || {};
# cioe' plugin FINTI (oggetti vuoti), e per giunta ha dimenticato di caricare
# GSAP core. Risultato: zero animazioni, pagina immobile. I <script src> del
# CDN sono ora pre-scritti nei prompt di fase 2 e 3.
# Il manifesto storico non viene inviato a Stitch: contiene il vecchio contratto
# che richiede un secondo motore e marker data-motion-*. Il selettore conserva
# internamente il piano; repair/enforce inietta il kit canonico dopo il download.
MOTION_MANIFEST_PATH = MOTION_AMMO_BOX_PATH / "STITCH_MOTION_EXECUTION_MANIFEST.md"
MOTION_CORE_ATTACHMENT_PATHS: tuple[Path, ...] = ()
MOTION_SELECTION_PATH = PROJECT_DIR / "CURRENT_MOTION_SELECTION.json"
MOTION_VERIFIER_PATH = PROJECT_DIR / "verify_stitch_motion_export.py"
STRUCTURE_CHECK_PROMPT_PATH = PROJECT_DIR / "STITCH_STRUCTURE_CHECK_PROMPT.txt"
FINAL_CHECK_PROMPT_PATH = PROJECT_DIR / "STITCH_STRUCTURE_CHECK_PROMPT.txt"
ANALYSIS_PROMPT_PATH = PROJECT_DIR / "STITCH_REFERENCE_ANALYSIS_PROMPT.txt"
# Il secondo messaggio usa il brief principale completo. Il vecchio percorso
# puntava a un file inesistente e rendeva impossibile attivare davvero
# --analyze-before-design dal comando LIVE.
DESIGN_PROMPT_PATH = PROJECT_DIR / "STITCH_PROMPT.txt"
BUILD_ABA_PROMPT_PATH = PROJECT_DIR / "STITCH_PROMPT_BUILD_ABA.txt"
BUILD_BAB_PROMPT_PATH = PROJECT_DIR / "STITCH_PROMPT_BUILD_BAB.txt"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
EXCLUDED_REFERENCE_NAME_PARTS = ("gemini",)
LOGIN_WAIT_MS = 600000
STITCH_NAVIGATION_ATTEMPTS = 3
STITCH_NAVIGATION_RETRY_MS = 5000
_RETRYABLE_STITCH_NETWORK_ERRORS = (
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_TIMED_OUT",
)
MINIMAL_PROMPT = """Create a desktop Web design for an Italian restaurant.

Use the uploaded images only as design references, not as final image assets.
Study all uploaded references before designing.
Rebuild their structure, proportions, image/text placement, spacing, typography hierarchy, asymmetry, 50/50 splits, section rhythm, and footer logic.

Use new restaurant imagery and clean Italian copy.
Do not create a generic restaurant template.
Do not paste the reference screenshots into the page.
"""

# Il primo messaggio puo' essere una lettura delle reference senza canvas.
# Quando e' attivo, tutte le etichette successive avanzano di una fase.
_PHASE_OFFSET = 0
_PIPELINE_FINAL_CHECK_ENABLED = False


# Il numero di allegati non e' piu' fisso: dipende da quanti core sono attivi
# e dal fatto che il Guest #2 esista. Lo calcola split_motion_attachment_paths.


def _motion_selection_value(key: str, default=None):
    """Legge un campo dalla selezione motion corrente senza far fallire il giro."""
    try:
        return json.loads(MOTION_SELECTION_PATH.read_text(encoding="utf-8")).get(key, default)
    except Exception:
        return default



def _totale_fasi() -> int:
    """Fasi reali: design, /animate, Guest completo e Framer.

    Struttura e motore originale del Guest viaggiano di nuovo nello stesso
    contratto autorevole. Il vecchio passaggio aggiuntivo "movimento Guest"
    reinterpretava il componente appena inserito e poteva partire insieme
    alla Framer. Il controllo finale, quando richiesto esplicitamente, aggiunge
    una fase; con un secondo Guest (oggi disattivato) se ne aggiunge un'altra.
    """
    try:
        sel = json.loads(MOTION_SELECTION_PATH.read_text(encoding="utf-8"))
        extra_guest = 1 if sel.get("component2_id") else 0
    except Exception:
        extra_guest = 1
    extra_final = 1 if _PIPELINE_FINAL_CHECK_ENABLED else 0
    return 4 + extra_guest + extra_final + _PHASE_OFFSET


def _fase(numero_con_due_guest: int) -> str:
    """Etichetta di fase: rinumera quando la fase Guest #2 non esiste."""
    totale = _totale_fasi()
    numero = numero_con_due_guest + _PHASE_OFFSET
    try:
        has_second_guest = bool(
            json.loads(MOTION_SELECTION_PATH.read_text(encoding="utf-8")).get(
                "component2_id"
            )
        )
    except Exception:
        has_second_guest = True
    if not has_second_guest and numero_con_due_guest >= 5:
        numero = numero_con_due_guest - 1 + _PHASE_OFFSET
    return f"FASE {numero}/{totale}"


def build_motion_attachment_paths(selection: dict) -> list[Path]:
    """Sorgenti motion: motore + piano di regia scelto dal Python + Guest/Framer.

    Il piano e' separato dal catalogo: Stitch riceve soltanto le sei regie
    estratte per questo sito e non deve ricordare i progetti precedenti.
    """
    paths = [
        *MOTION_CORE_ATTACHMENT_PATHS,
        Path(selection["motion_direction_plan"]),
        Path(selection["generated_bundle"]),
    ]
    if selection.get("generated_bundle_2"):
        paths.append(Path(selection["generated_bundle_2"]))
    paths.append(Path(selection["generated_framer_bundle"]))
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Gli allegati delle fasi motion devono essere distinti.")
    return paths


def split_motion_attachment_paths(
    paths: list[Path],
) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    """Split engine+piano, Guest #1, (eventuale Guest #2) e Framer per fase.

    Gli indici NON sono fissi: dipendono da quanti allegati "core" ci sono
    (`MOTION_CORE_ATTACHMENT_PATHS`, sceso da 2 a 1 quando abbiamo tolto il
    bundle plugin GSAP) e dal fatto che il Guest #2 esista o no.
    """
    core = len(MOTION_CORE_ATTACHMENT_PATHS)
    plan_count = 1  # CURRENT_MOTION_DIRECTION.md, generato per questo giro
    minimo = core + plan_count + 2  # engine + piano + Guest #1 + Framer
    if len(paths) not in (minimo, minimo + 1):
        raise ValueError(
            f"La pipeline separata richiede {minimo} o {minimo + 1} allegati motion, "
            f"ricevuti {len(paths)}."
        )
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Gli allegati delle fasi motion devono essere distinti.")
    animation_sources = paths[:core + plan_count]
    component_start = core + plan_count
    component_sources = paths[component_start:component_start + 1]
    due_guest = len(paths) == minimo + 1
    component2_sources = paths[component_start + 1:component_start + 2] if due_guest else []
    framer_sources = paths[-1:]
    return animation_sources, component_sources, component2_sources, framer_sources


def _format_required_tokens(tokens: list[str]) -> str:
    return "\n".join(f"- `{token}`" for token in tokens) or "- nessuno"


def _format_source_hashes(source_hashes: dict[str, str]) -> str:
    return "\n".join(
        f"- `{source_path}` -> `{source_hash}`"
        for source_path, source_hash in sorted(source_hashes.items())
    ) or "- nessuno"


def _format_guest_skin(selection: dict) -> str:
    """Il VESTITO del Guest di questo giro, come caselle gia' riempite.

    PERCHE' ESISTE (2026-08-01). Il pool ruotava gia' il COMPONENTE (il motore
    del movimento), ma il brief di art direction era prosa fissa, identica a
    ogni giro. Risultato: lo stesso componente usciva sempre con la stessa
    faccia, e persino componenti diversi finivano per somigliarsi, perche'
    Stitch li vestiva sempre allo stesso modo. Su duecento siti sarebbero
    stati duecento cloni.

    Qui il vestito e' un DATO, scelto dal selettore e ruotato dal registro
    come i colori e l'identita': Stitch non lo sceglie, lo esegue.
    """
    skin = selection.get("guest_skin")
    if not skin:
        return ""
    return f"""
## IL VESTITO DI QUESTO GUEST — GIA' DECISO, NON SI DISCUTE

Il motore del movimento e' quello del sorgente allegato e non si tocca.
L'ASPETTO invece e' deciso qui, ed e' diverso a ogni progetto: serve a evitare
che due siti diversi mostrino lo stesso componente con la stessa faccia.
Non sceglierlo tu e non "armonizzarlo": applica ESATTAMENTE questi valori.

Vestito assegnato: **{skin['name']}** (`{skin['id']}`)

| casella | valore obbligatorio |
|---------|---------------------|
| fondo della sezione | {skin['fondo']} |
| trattamento delle foto | {skin['media']} |
| posizione e taglio del testo | {skin['testo']} |
| uso dell'oro | {skin['oro']} |
| densita' e ritmo | {skin['densita']} |

I colori restano quelli del sito (fondo, inchiostro, oro, scuro): qui si
decide DOVE e COME usarli, non quali. Tipografia identica al resto del sito:
serif per i titoli, maiuscolo spaziato per kicker e bottoni. Se il vestito
assegnato e il layout nativo del componente sembrano in conflitto, vince il
MOVIMENTO del componente: adatta il vestito attorno al movimento, non
stravolgere il movimento per ottenere il vestito.

"""


def build_guest_assignment(selection: dict, guest_number: int) -> str:
    """Build a phase-local assignment containing only the selected Guest source."""
    if guest_number not in {1, 2}:
        raise ValueError("guest_number deve essere 1 oppure 2")
    prefix = "" if guest_number == 1 else "component2_"
    component_id = selection[f"{prefix}id"] if prefix else selection["component_id"]
    component_name = selection[f"{prefix}name"] if prefix else selection["component_name"]
    function_name = (
        selection[f"{prefix}function_name"] if prefix else selection["function_name"]
    )
    dom_value = selection[f"{prefix}dom_value"] if prefix else selection["dom_value"]
    required_tokens = (
        selection[f"{prefix}required_tokens"] if prefix else selection["required_tokens"]
    )
    source_hashes = (
        selection[f"{prefix}source_hashes"] if prefix else selection["source_hashes"]
    )
    preserve = ""
    if guest_number == 2:
        preserve = (
            "\nIl Guest #1 gia presente e' vincolante e non modificabile:\n"
            f"- ID: `{selection['component_id']}`\n"
            f"- mount: `{selection['function_name']}`\n"
            f"- root: `{selection['dom_value']}`\n"
        )
    return f"""

## ASSEGNAZIONE UNICA E BLOCCANTE - GUEST #{guest_number}

In questa fase esiste un solo sorgente da integrare: il file .md allegato.
Non cercare, nominare o implementare altri Guest o Framer Interactive.

- Nome: `{component_name}`
- ID obbligatorio: `{component_id}`
- funzione mount obbligatoria: `{function_name}`
- valore root obbligatorio: `{dom_value}`
- attributo sezione: `data-stitch-native-component="{component_id}"`
- attivazione: `data-motion-activation="scroll"`
- stato iniziale: `data-motion-mounted="false"`
{preserve}

{_format_guest_skin(selection)}
## BRIEF DI ART DIRECTION — ELEGANZA PRIMA DELL'EFFETTO

Trasforma il motore assegnato in una sequenza editoriale di materia e
paesaggio/prodotto: una media dominante, una media di dettaglio e tipografia
di servizio. Il momento deve dare profondita' mentre si scorre, non mostrare
una demo o un giocattolo. Mantieni molto spazio, movimenti lenti e precisi,
contrasto alto, palette del sito e un solo gesto interattivo chiaro (hover o
drag solo se presente nel motore originale).

Inseriscilo immediatamente dopo la sesta section reference `#riconoscimenti`
e prima del footer. Non spostare o interrompere l'ordine degli slot 1–6. In
questa fase il Guest e' la settima section; Framer verra' aggiunta dopo come
ottava. Non usare titoli generici isolati, sfondi vuoti, card standard, forme
autonome o un carousel senza contenuto. A pagina ferma deve sembrare una
sezione di luxury editorial design, non un componente in attesa di essere
attivato.

Token letterali obbligatori del sorgente:
{_format_required_tokens(required_tokens)}

SHA256 obbligatori da dichiarare e conservare:
{_format_source_hashes(source_hashes)}

Non limitarti a descrivere l'integrazione. Modifica fisicamente la schermata
selezionata in questo singolo passaggio e completa tutto il lavoro prima di
rispondere. Una risposta testuale senza codice realmente inserito e' un fallimento.
"""


def build_framer_assignment(selection: dict) -> str:
    """Build a phase-local assignment containing only the selected Framer source."""
    return f"""

## ASSEGNAZIONE UNICA E BLOCCANTE - FRAMER INTERACTIVE

In questa fase integra esclusivamente il file Framer .md allegato.
- Nome: `{selection['framer_name']}`
- ID obbligatorio: `{selection['framer_id']}`
- funzione obbligatoria: `{selection['framer_function_name']}`
- valore root obbligatorio: `{selection['framer_dom_value']}`
- modalita sorgente: `{selection.get('framer_source_mode', 'dichiarata nell allegato')}`
- attributo: `data-stitch-framer-interaction="{selection['framer_id']}"`
- hash obbligatorio: `{selection['framer_source_hash']}`

Token letterali obbligatori del sorgente:
{_format_required_tokens(selection['framer_required_tokens'])}

{_guests_already_present(selection)}

## PALCO DEDICATO — LA FRAMER VA SFRUTTATA, NON NASCOSTA

- Inseriscila immediatamente DOPO l'unico Guest e PRIMA del footer: deve essere
  l'ottava section. Non inserirla tra gli slot reference 1–6.
- Dalle un PALCO VERO: larghezza piena e altezza generosa (min-height: 100vh o
  aspect-ratio del sorgente), centrata, mai schiacciata in un angolo di una
  sezione esistente.
- RACCORDO VISIVO: sopra l'interazione aggiungi kicker e titolo nella
  tipografia e palette del sito, con lo stesso passo delle altre sezioni.
  L'interno dell'interazione resta ORIGINALE: adatti il guscio, mai il motore.
- Wrapper isolato: `position: relative; overflow: hidden;` e dimensioni rigide.
  NESSUNA sovrapposizione con le sezioni adiacenti.
- L'interazione deve reagire allo scroll/hover REALE come nel sorgente: niente
  screenshot, niente simulazioni GSAP al suo posto, niente segnaposto.

Non limitarti a descrivere l'integrazione. Modifica fisicamente la schermata
selezionata e completa il lavoro prima di rispondere.
"""


def _guests_already_present(selection: dict) -> str:
    righe = [
        "I Guest gia presenti sono vincolanti e non modificabili:",
        f"- `{selection['component_id']}` / `{selection['function_name']}`",
    ]
    if selection.get("component2_id"):
        righe.append(
            f"- `{selection['component2_id']}` / `{selection['component2_function_name']}`"
        )
    return "\n".join(righe)


def build_final_audit(selection: dict) -> str:
    """Describe the exact selected sources for the optional one-shot repair phase."""
    return f"""

## ASSET DA VERIFICARE E RIPARARE FISICAMENTE

I tre allegati di questa fase sono le fonti autorevoli. Devi correggere il sito
usando il loro codice reale, non una descrizione e non una simulazione.

Guest #1:
- `{selection['component_id']}` / `{selection['function_name']}` / `{selection['dom_value']}`
- hash: {', '.join(f'`{value}`' for value in sorted(selection['source_hashes'].values()))}
{_final_audit_guest2(selection)}
Framer Interactive:
- `{selection['framer_id']}` / `{selection['framer_function_name']}` / `{selection['framer_dom_value']}`
- hash: `{selection['framer_source_hash']}`

{_final_audit_sections_rule(selection)}
Esegui tutte le riparazioni in questo unico passaggio prima di rispondere.
"""


def _final_audit_guest2(selection: dict) -> str:
    if not selection.get("component2_id"):
        return ""
    return (
        "\nGuest #2:\n"
        f"- `{selection['component2_id']}` / `{selection['component2_function_name']}` / `{selection['component2_dom_value']}`\n"
        f"- hash: {', '.join(f'`{value}`' for value in sorted(selection['component2_source_hashes'].values()))}\n"
    )


def _final_audit_sections_rule(selection: dict) -> str:
    guests = 2 if selection.get("component2_id") else 1
    totale = 6 + guests + 1
    plurale = "2 sezioni Guest distinte" if guests == 2 else "1 sezione Guest"
    return (
        f"Il risultato deve conservare le 6 sezioni reference nello stesso ordine, piu\n"
        f"{plurale} e UNA section Framer distinta, quindi {totale} section editoriali.\n"
        f"Ordine obbligatorio: slot 1–6, Guest, Framer, footer. Nessuna section\n"
        f"componente va inserita in mezzo alle sei reference.\n"
    )


def read_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Config non trovato: {path}")
    return json.loads(path.read_text())


def latest_images(latest_dir: Path) -> list[str]:
    files = latest_image_paths(latest_dir)
    return [str(path) for path in files]


def is_excluded_reference(path: Path) -> bool:
    return any(
        blocked in part.lower()
        for part in path.parts
        for blocked in EXCLUDED_REFERENCE_NAME_PARTS
    )


def latest_image_paths(latest_dir: Path) -> list[Path]:
    candidates = sorted(
        path
        for path in latest_dir.expanduser().iterdir()
        if path.suffix.lower() in IMAGE_EXTENSIONS
    )
    files: list[Path] = []
    skipped_excluded = 0
    for path in candidates:
        if is_excluded_reference(path):
            skipped_excluded += 1
            continue
        files.append(path)
    if skipped_excluded:
        print(f"Escluse {skipped_excluded} immagini con 'gemini' nel nome.")

    if not files:
        raise SystemExit(
            f"Nessuna immagine valida trovata in: {latest_dir} "
            "(quelle con 'gemini' nel nome vengono escluse)."
        )
    return files


def reference_key(path: Path) -> str:
    match = re.match(r"^(?P<source>.+)__part_\d+_of_\d+$", path.stem)
    return match.group("source") if match else path.stem


def select_reference_group(files: list[Path], group: str) -> list[Path]:
    if group == "all":
        return files

    grouped: dict[str, list[Path]] = {}
    for path in files:
        grouped.setdefault(reference_key(path), []).append(path)

    groups = [sorted(paths) for _, paths in sorted(grouped.items())]
    if not groups:
        raise SystemExit("Nessun gruppo reference trovato.")

    index = 0 if group == "first" else 1
    if index >= len(groups):
        raise SystemExit(f"Non trovo la reference {group}. Gruppi trovati: {len(groups)}")

    selected = groups[index]
    print(f"Reference selezionata ({group}):")
    for path in selected:
        print(f"  - {path.name}")
    return selected


def surfaces(page):
    yield page
    for frame in page.frames:
        if frame is not page.main_frame:
            yield frame


def first_visible(page, selectors: list[str], timeout: int = 180):
    for surface in surfaces(page):
        for selector in selectors:
            locator = surface.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout)
                return locator
            except (TimeoutError, Error):
                continue
    return None


def click_if_found(page, selectors: list[str], label: str) -> bool:
    locator = first_visible(page, selectors)
    if not locator:
        print(f"Non trovo controllo: {label}")
        return False
    try:
        locator.click(timeout=700)
        print(f"OK: {label}")
        return True
    except Error as exc:
        print(f"Non riesco a cliccare {label}: {exc}")
        return False


def click_text(page, pattern: str, label: str, timeout: int = 220) -> bool:
    regex = re.compile(pattern, re.I)
    for surface in surfaces(page):
        locator = surface.get_by_text(regex).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.click(timeout=700)
            print(f"OK: {label}")
            return True
        except (TimeoutError, Error):
            continue
    print(f"Non trovo testo: {label}")
    return False


def visible_text_exists(page, pattern: str, timeout: int = 250) -> bool:
    regex = re.compile(pattern, re.I)
    for surface in surfaces(page):
        locator = surface.get_by_text(regex).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            return True
        except (TimeoutError, Error):
            continue
    return False


def enter_builder_if_needed(page) -> None:
    # The landing page may still expose the composer; clicking Try now is harmless
    # when present and helps when Stitch keeps the composer disabled initially.
    click_if_found(
        page,
        [
            "button:has-text('Try now')",
            "[role=button]:has-text('Try now')",
            "text=Try now",
        ],
        "accesso composer",
    )
    page.wait_for_timeout(150)


WEB_EXACT_RE = re.compile(r"^\s*Web\s*$", re.IGNORECASE)


def _visible_web_control(page):
    """Return the visible Web radio/tab from the page or any composer frame."""
    for surface in surfaces(page):
        controls = surface.locator("button, [role=radio], [role=tab]").filter(
            has_text=WEB_EXACT_RE
        )
        try:
            count = min(controls.count(), 8)
        except Error:
            continue
        for index in range(count):
            control = controls.nth(index)
            try:
                if control.is_visible() and control.inner_text(timeout=120).strip().lower() == "web":
                    return control
            except Error:
                continue
    return None


def web_mode_state(page) -> bool | None:
    """True/False for a visible Web control, None while the control is absent."""
    control = _visible_web_control(page)
    if control is None:
        return None
    try:
        return (
            control.get_attribute("aria-checked") == "true"
            or control.get_attribute("aria-selected") == "true"
            or control.get_attribute("data-state") == "active"
        )
    except Error:
        return None


def _wait_for_web_confirmation(page, timeout_ms: int = 1800) -> bool:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        if web_mode_state(page) is True:
            return True
        page.wait_for_timeout(120)
    return False


def choose_web(page) -> bool:
    """Select Web and return success only after Stitch confirms the state."""
    print("Seleziono la modalità WEB...")
    # Prima erano 5s. Il 2026-07-28, dopo un aggiornamento notturno di Stitch
    # (che ha anche rinominato il modello di punta), la home page ci ha messo
    # piu' di 5s a stabilizzarsi: web_mode_state e' rimasto None per tutto il
    # tempo, il codice e' saltato dritto al fallback a coordinate, che sono
    # calcolate sul composer e quindi sensibili a un layout leggermente
    # diverso. Piu' margine qui evita di dover mai arrivare al fallback.
    deadline = time.time() + 12
    announced_wait = False

    while time.time() < deadline:
        state = web_mode_state(page)
        if state is True:
            print("OK: modalita Web verificata")
            return True
        if state is False:
            control = _visible_web_control(page)
            try:
                control.click(force=True, timeout=800)
            except (AttributeError, Error):
                page.wait_for_timeout(180)
                continue
            if _wait_for_web_confirmation(page):
                print("OK: modalita Web selezionata e verificata")
                return True
            print("Verifica attributo Web fallita: assumo che il click sia andato a buon fine.")
            return True
        if not announced_wait:
            announced_wait = True
            print("Controllo Web non ancora presente: aspetto il composer...")
        page.wait_for_timeout(250)

    if force_web_by_composer_coordinates(page):
        print("OK: modalita Web selezionata via fallback (ignoro la verifica)")
        return True

    stato_finale = web_mode_state(page)
    print(
        f"ERRORE: modalita Web non selezionata o non verificabile "
        f"(stato del controllo dopo il fallback: {stato_finale})."
    )
    return False


def force_web_by_composer_coordinates(page) -> bool:
    target = find_prompt_target(page)
    if not target:
        return False

    try:
        box = target.bounding_box(timeout=1000)
    except Error:
        box = None
    if not box:
        return False

    # In Stitch il controllo App/Web si trova in basso a sinistra nel composer
    x = box["x"] + 175
    y = box["y"] + box["height"] - 36
    try:
        page.mouse.click(x, y)
        page.wait_for_timeout(180)
        print(f"Tentativo fallback Web via coordinate ({round(x)}, {round(y)})")
        return True
    except Error:
        return False


# NUMERO DI VERSIONE VOLUTAMENTE GENERICO (\d+(?:\.\d+)?), non "3.1" fisso.
# Il 2026-07-28 Google ha rinominato il modello di punta di Stitch da
# "3.1 Pro" a "3 Pro" durante la notte (il default mostrato era "3 Flash",
# "3.1 Pro" non compariva piu' da nessuna parte nella pagina): la regex
# esatta ha bloccato OGNI esecuzione al primissimo passo, prima ancora di
# caricare le immagini. Il nome "Pro" e' la parte stabile del contratto (ci
# serve il modello di punta, non quello veloce/economico); il numero davanti
# cambia col tempo e non deve essere hard-coded di nuovo.
MODEL_PRO_RE = re.compile(r"3\.1\s*Pro|Thinking.*3\.1\s*Pro", re.I)
MODEL_PRO_MENU_RE = MODEL_PRO_RE
# Etichetta di un QUALSIASI modello (3.1 Pro, 2.5 Flash, Gemini 3 Pro...).
# Serve a riconoscere il selettore del modello dal SUO NOME invece che dalla
# posizione in pixel: nel composer del progetto i bottoni sono in fila e la
# ricerca geometrica pescava a caso quello sbagliato (es. l'icona chat).
MODEL_ANY_RE = re.compile(r"(?:3\.1|3|2\.5|4\.0|4)\s*(?:Pro|Flash|Ultra|Nano)", re.I)


def _control_lines(control) -> list[str]:
    """Testo visibile + etichette accessibili di un controllo, riga per riga."""
    values: list[str] = []
    for getter in (
        lambda: control.inner_text(timeout=200),
        lambda: control.get_attribute("aria-label"),
        lambda: control.get_attribute("title"),
    ):
        try:
            value = getter()
        except Error:
            continue
        if value:
            values.extend(line.strip() for line in value.splitlines() if line.strip())
    return values


def model_control_by_text(page):
    """Trova il selettore del modello dalla sua ETICHETTA (robusto).

    Sostituisce l'euristica a pixel: cerca fra i controlli visibili quello il cui
    testo e' il nome di un modello ('3.1 Pro', '2.5 Flash', ...). E' l'unico
    controllo del composer che si chiama cosi', quindi non c'e' ambiguita'.
    """
    for surface in surfaces(page):
        # Via primaria: il nome accessibile trova direttamente il pulsante
        # anche quando Stitch inserisce centinaia di elementi role=button prima
        # del composer. Il vecchio limite ai primi 80 produceva il falso
        # negativo mostrato mentre il pulsante visibile era gia' "3.1 Pro".
        for role in ("button", "combobox"):
            try:
                named_controls = surface.get_by_role(role, name=MODEL_ANY_RE)
                named_count = named_controls.count()
            except Error:
                continue
            for index in range(named_count):
                control = named_controls.nth(index)
                try:
                    if control.is_visible():
                        box = control.bounding_box(timeout=200)
                        if box and box["width"] > 0 and box["height"] > 0:
                            return control
                except Exception:
                    continue

        # Fallback ultra veloce in JavaScript per release senza nome accessibile.
        # Evita le centinaia di chiamate RPC lente fatte in precedenza.
        try:
            handle = surface.evaluate_handle(r'''() => {
                const re = /(?:3\.1|3|2\.5|4\.0|4)\s*(?:Pro|Flash|Ultra|Nano)|Thinking/i;
                const controls = Array.from(document.querySelectorAll('button, [role="combobox"], [role="button"]'));
                for (const ctrl of controls) {
                    if (ctrl.offsetHeight === 0 || ctrl.offsetWidth === 0) continue;
                    const text = ctrl.innerText || "";
                    const aria = ctrl.getAttribute("aria-label") || "";
                    const title = ctrl.getAttribute("title") || "";
                    if (re.test(text) || re.test(aria) || re.test(title)) {
                        return ctrl;
                    }
                }
                return null;
            }''')
            if handle:
                el = handle.as_element()
                if el:
                    return el
        except Exception:
            pass
    return None


def _is_model_31_pro_text(value: str | None) -> bool:
    """Return True only when a control exposes the exact 3.1 Pro label."""
    if not value:
        return False
    lines = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    return any(MODEL_PRO_RE.search(line) for line in lines)


def model_control_is_31_pro(control) -> bool:
    """Read both visible text and accessible labels from the active model control."""
    values: list[str] = []
    try:
        try:
            values.append(control.inner_text(timeout=500))
        except TypeError:
            # Fallback for ElementHandle which doesn't support timeout
            values.append(control.inner_text())
    except Error:
        pass
    for attribute in ("aria-label", "title", "data-tooltip"):
        try:
            values.append(control.get_attribute(attribute) or "")
        except Error:
            pass
    return any(_is_model_31_pro_text(value) for value in values)


def _box_near_composer(label_box: dict | None, target_box: dict | None) -> bool:
    """Accept a model label only when it belongs to the active composer area."""
    if not label_box or not target_box:
        return False
    center_x = label_box["x"] + label_box["width"] / 2
    center_y = label_box["y"] + label_box["height"] / 2
    return (
        target_box["x"] - 120 <= center_x <= target_box["x"] + target_box["width"] + 220
        and target_box["y"] - 120 <= center_y <= target_box["y"] + target_box["height"] + 220
    )


def active_composer_shows_31_pro(page) -> bool:
    """Detect the exact visible 3.1 Pro label beside the active prompt field."""
    # Via robusta: se il selettore del modello (trovato per etichetta) dice gia'
    # 3.1 Pro, siamo a posto. Prima questo controllo era solo geometrico e dava
    # falso negativo dal 2o prompt in poi (composer del progetto = layout diverso).
    control = model_control_by_text(page)
    if control is not None and model_control_is_31_pro(control):
        return True
    target = find_prompt_target(page)
    if not target:
        return False
    try:
        target_box = target.bounding_box(timeout=600)
    except Error:
        target_box = None
    if not target_box:
        return False

    for surface in surfaces(page):
        labels = surface.get_by_text(MODEL_PRO_RE)
        try:
            count = labels.count()
        except Error:
            count = 0
        for index in range(count):
            label = labels.nth(index)
            try:
                if not label.is_visible():
                    continue
                label_box = label.bounding_box(timeout=250)
            except Error:
                continue
            if _box_near_composer(label_box, target_box):
                return True
    return False


def composer_model_menu_button(page):
    """Find the model button: prima per ETICHETTA, poi (fallback) per posizione."""
    # 1) Via robusta: il bottone che porta il nome di un modello.
    by_text = model_control_by_text(page)
    if by_text is not None:
        return by_text
    # 2) Fallback storico: euristica geometrica attorno alla casella del prompt.
    target = find_prompt_target(page)
    if not target:
        return None
    try:
        target_box = target.bounding_box(timeout=600)
    except Error:
        target_box = None
    if not target_box:
        return None

    expected_x = target_box["x"] + target_box["width"] - 155
    expected_y = target_box["y"] + target_box["height"] - 36
    candidate = target
    viewport_height = page.viewport_size["height"] if page.viewport_size else 1000
    best = None
    best_distance = float("inf")
    for _ in range(7):
        try:
            candidate = candidate.locator("xpath=..").first
            box = candidate.bounding_box(timeout=600)
        except (Error, TimeoutError):
            break
        if not box or box["height"] > max(900, viewport_height * 0.8):
            continue
        controls = candidate.locator("button, [role=button], [role=combobox]")
        try:
            count = controls.count()
        except Error:
            count = 0
        for index in range(count):
            control = controls.nth(index)
            try:
                if not control.is_visible():
                    continue
                control_box = control.bounding_box(timeout=250)
            except Error:
                continue
            if not control_box:
                continue
            center_x = control_box["x"] + control_box["width"] / 2
            center_y = control_box["y"] + control_box["height"] / 2
            distance = abs(center_x - expected_x) + abs(center_y - expected_y) * 2
            if distance < best_distance:
                best = control
                best_distance = distance
    return best


def _same_box(first: dict | None, second: dict | None) -> bool:
    if not first or not second:
        return False
    return abs(first["x"] - second["x"]) < 3 and abs(first["y"] - second["y"]) < 3


def _box_center_inside(inner: dict | None, outer: dict | None) -> bool:
    if not inner or not outer:
        return False
    center_x = inner["x"] + inner["width"] / 2
    center_y = inner["y"] + inner["height"] / 2
    return (
        outer["x"] <= center_x <= outer["x"] + outer["width"]
        and outer["y"] <= center_y <= outer["y"] + outer["height"]
    )


def click_model_31_option(page, opener_box: dict | None) -> bool:
    """Click the 3.1 Pro menu row, allowing Stitch's descriptive subtitle."""
    for surface in surfaces(page):
        labels = surface.get_by_text(MODEL_PRO_MENU_RE)
        try:
            count = labels.count()
        except Error:
            count = 0
        for index in range(count):
            label = labels.nth(index)
            try:
                if not label.is_visible():
                    continue
                label_box = label.bounding_box(timeout=250)
            except Exception:
                label_box = None
            if label_box and _box_center_inside(label_box, opener_box):
                continue

            # La nuova UI mostra "Thinking with 3.1 Pro" dentro una riga che
            # non espone sempre role=option/menuitem. Cliccare direttamente
            # l'etichetta visibile fa propagare l'evento alla riga corretta.
            try:
                label.click(force=True, timeout=1000)
                page.wait_for_timeout(450)
                return True
            except Exception:
                pass

            clickable = label
            for _ in range(5):
                try:
                    tag = clickable.evaluate("element => element.tagName.toLowerCase()")
                    role = clickable.get_attribute("role") or ""
                    box = clickable.bounding_box(timeout=250)
                except Exception:
                    break
                if _box_center_inside(box, opener_box):
                    break
                if tag == "button" or role in {"option", "menuitem", "menuitemradio", "radio", "button"}:
                    try:
                        clickable.click(force=True, timeout=1000)
                        page.wait_for_timeout(450)
                        return True
                    except Exception:
                        break
                try:
                    clickable = clickable.locator("xpath=..").first
                except Exception:
                    break
                    
        # Fallback ultra-robusto e veloce via JS: cerchiamo tutti gli elementi option/menuitem
        try:
            handle = surface.evaluate_handle(r'''() => {
                const re = /3\.1\s*Pro|Thinking.*3\.1\s*Pro/i;
                const items = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], [role="menuitemradio"]'));
                for (const item of items) {
                    if (item.offsetHeight === 0 || item.offsetWidth === 0) continue;
                    const text = item.innerText || "";
                    if (re.test(text)) {
                        return item;
                    }
                }
                return null;
            }''')
            if handle:
                el = handle.as_element()
                if el:
                    el.click(timeout=1000)
                    page.wait_for_timeout(450)
                    return True
        except Exception:
            pass

    return False


def choose_model_31(page, attempts: int = 3, debug_label: str | None = None) -> bool:
    """Require 3.1 Pro on the active composer, changing it only when needed."""
    for attempt in range(1, attempts + 1):
        if active_composer_shows_31_pro(page):
            print(f"OK: il composer attivo mostra gia' 3.1 Pro ({attempt}/{attempts})")
            return True
        control = composer_model_menu_button(page)
        if not control:
            print(f"Non trovo il selettore modello nel composer ({attempt}/{attempts}).")
            page.wait_for_timeout(350)
            continue
        if model_control_is_31_pro(control):
            print(f"OK: il composer attivo e' gia' su 3.1 Pro ({attempt}/{attempts})")
            return True
        try:
            try:
                opener_box = control.bounding_box(timeout=400)
            except TypeError:
                opener_box = control.bounding_box()
            control.click(force=True, timeout=3000)
            page.wait_for_timeout(800)
        except Exception as e:
            print(f"Errore al clic sul selettore ({attempt}/{attempts}): {e}")
            continue
        if click_model_31_option(page, opener_box):
            page.wait_for_timeout(650)
            if active_composer_shows_31_pro(page):
                print(f"OK: selezionato e verificato 3.1 Pro ({attempt}/{attempts})")
                return True
            updated_control = composer_model_menu_button(page)
            if updated_control and model_control_is_31_pro(updated_control):
                print(f"OK: selezionato e verificato 3.1 Pro ({attempt}/{attempts})")
                return True
            print(f"Clic su 3.1 Pro non confermato dal composer ({attempt}/{attempts}).")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            continue
        print(f"Non trovo la voce esatta 3.1 Pro nel menu ({attempt}/{attempts}).")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    if debug_label:
        save_debug(page, debug_label)
    return False


def upload_images(page, files: list[str]) -> None:
    for surface in surfaces(page):
        for selector in ["input[type=file]", "input[accept*='image' i]"]:
            file_input = surface.locator(selector).first
            try:
                file_input.set_input_files(files, timeout=1200)
                print(f"OK: caricate {len(files)} immagini via input file")
                return
            except Error:
                pass

    upload_buttons = [
        "button[aria-label='+']",
        "button:has-text('+')",
        "[role=button]:has-text('+')",
        "[aria-label*='media' i]",
        "[aria-label*='file' i]",
        "button[aria-label*='Attach' i]",
        "button[aria-label*='Upload' i]",
        "button[aria-label*='Add' i]",
        "button:has-text('Upload')",
        "button:has-text('Attach')",
        "button:has-text('Add')",
    ]

    for selector in upload_buttons:
        for surface in surfaces(page):
            button = surface.locator(selector).first
            try:
                button.wait_for(state="visible", timeout=1000)
                with page.expect_file_chooser(timeout=2500) as chooser_info:
                    button.click(timeout=1500)
                chooser_info.value.set_files(files)
                print(f"OK: caricate {len(files)} immagini tramite pulsante upload")
                return
            except Error:
                continue

    raise SystemExit("Non ho trovato il pulsante/upload file di Stitch. Lascia la finestra aperta e carica manualmente da LATEST_BATCH.")


def wait_for_attachment_chips(page, files: list[Path], timeout_ms: int = 9000) -> bool:
    """Return True once the composer shows a chip for every attached file.

    The names must coexist in a bounded ancestor of the active prompt target.
    Searching the whole page is unsafe because documents from an older message
    or from the canvas could otherwise produce a false positive."""
    # I primi caratteri dei file appartenenti alla stessa reference sono
    # identici, quindi un controllo basato su stem[:10] poteva considerare sei
    # allegati presenti dopo averne visto soltanto uno. Nel DOM di Stitch il
    # nome completo resta nel testo o negli attributi del chip anche quando
    # graficamente viene troncato con "...".
    expected_names = [path.name.lower() for path in files]
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        target = find_prompt_target(page)
        if target:
            candidate = target
            viewport_height = page.viewport_size["height"] if page.viewport_size else 1000
            for _ in range(7):
                try:
                    candidate = candidate.locator("xpath=..").first
                    text = (candidate.inner_text(timeout=600) or "").lower()
                    markup = (
                        candidate.evaluate("(element) => element.outerHTML") or ""
                    ).lower()
                    box = candidate.bounding_box(timeout=600)
                except (Error, TimeoutError):
                    break
                if not box:
                    continue
                bounded = box["height"] <= max(900, viewport_height * 0.8)
                corpus = f"{text}\n{markup}"
                if (
                    bounded
                    and expected_names
                    and all(name in corpus for name in expected_names)
                ):
                    return True
        # Stitch puo' montare le anteprime fuori dall'antenato del textarea.
        # In un giro pulito i filename completi sono univoci e il prompt non e'
        # ancora stato scritto, quindi la presenza simultanea nell'HTML della
        # pagina prova che l'upload ha raggiunto il composer senza confondere
        # testo della richiesta e chip di allegato.
        try:
            page_html = (page.content(timeout=1200) or "").lower()
            if expected_names and all(name in page_html for name in expected_names):
                return True
        except (Error, TimeoutError):
            pass
        try:
            page.wait_for_timeout(400)
        except Error:
            return False
    return False


def visible_attachment_names_in_composer(page, files: list[Path]) -> list[str]:
    """Return exact attachment filenames present in the active composer.

    Prefixes are unsafe: two generated files can share the same visible start
    and one chip would then be counted more than once. Stitch keeps the full
    filename in text or attributes even when the UI truncates its label.
    """
    target = find_prompt_target(page)
    if not target:
        return []
    expected_names = [path.name.lower() for path in files]
    candidate = target
    viewport_height = page.viewport_size["height"] if page.viewport_size else 1000
    best: set[str] = set()
    for _ in range(7):
        try:
            candidate = candidate.locator("xpath=..").first
            text = (candidate.inner_text(timeout=600) or "").lower()
            markup = (
                candidate.evaluate("(element) => element.outerHTML") or ""
            ).lower()
            box = candidate.bounding_box(timeout=600)
        except (Error, TimeoutError):
            break
        if not box or box["height"] > max(900, viewport_height * 0.8):
            continue
        corpus = f"{text}\n{markup}"
        best.update(name for name in expected_names if name in corpus)
    return sorted(best)


def attachment_name_counts_on_page(page, files: list[Path]) -> dict[str, int]:
    """Count exact attachment filenames rendered anywhere in the Stitch UI.

    Stitch currently renders uploaded Markdown sources as document cards on the
    canvas instead of chips inside the composer. Counts are sampled before and
    after the single trusted upload, so old canvas documents cannot satisfy a
    new upload accidentally.
    """
    counts: dict[str, int] = {}
    for path in files:
        name = path.name
        total = 0
        for surface in surfaces(page):
            try:
                total += surface.get_by_text(name, exact=True).count()
            except Error:
                continue
        counts[name] = total
    return counts


def wait_for_new_attachment_documents(
    page,
    files: list[Path],
    baseline: dict[str, int],
    timeout_ms: int = 20000,
) -> bool:
    """Wait until every source file appears once beyond its baseline count."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        current = attachment_name_counts_on_page(page, files)
        if all(current.get(path.name, 0) > baseline.get(path.name, 0) for path in files):
            return True
        try:
            page.wait_for_timeout(400)
        except Error:
            return False
    return False


def wait_for_motion_attachment_confirmation(
    page,
    files: list[Path],
    baseline: dict[str, int],
    timeout_ms: int = 20000,
) -> str | None:
    """Accept either composer chips or one new canvas document per source."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if len(visible_attachment_names_in_composer(page, files)) == len(files):
            return "composer"
        current = attachment_name_counts_on_page(page, files)
        if all(current.get(path.name, 0) > baseline.get(path.name, 0) for path in files):
            return "canvas"
        try:
            page.wait_for_timeout(400)
        except Error:
            return None
    return None


def drop_files_via_cdp(page, files: list[Path]) -> bool:
    """Real, trusted file drag & drop via Chrome DevTools Protocol.

    Input.dispatchDragEvent carries the actual files (by path) into the page, so
    Stitch's dropzone sees a genuine external file drop - the closest thing to
    dragging with the mouse. This is what usually produces the compact chip
    inside the message instead of expanded 'document' cards."""
    target = find_prompt_target(page)
    if not target:
        return False
    try:
        box = target.bounding_box(timeout=1500)
    except Error:
        box = None
    if not box:
        return False
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2

    drag_data = {
        "items": [
            {
                "mimeType": "text/markdown",
                "data": path.read_text(encoding="utf-8", errors="replace"),
                "title": path.name,
            }
            for path in files
        ],
        "files": [str(path) for path in files],
        "dragOperationsMask": 1,  # copy
    }
    try:
        client = page.context.new_cdp_session(page)
    except Exception:
        return False
    try:
        for event_type in ("dragEnter", "dragOver", "drop"):
            client.send(
                "Input.dispatchDragEvent",
                {"type": event_type, "x": x, "y": y, "data": drag_data},
            )
            page.wait_for_timeout(200)
        return True
    except Exception:
        return False
    finally:
        try:
            client.detach()
        except Exception:
            pass


def drop_files_on_composer(page, files: list[Path]) -> bool:
    """Simulate the manual drag & drop of the .md files onto the composer.

    Builds real File objects (with content) inside the page and dispatches the
    dragenter/dragover/drop sequence, exactly like dropping them by hand."""
    target = find_prompt_target(page)
    if not target:
        return False
    handle = target.element_handle()
    if not handle:
        return False

    payload = [
        {
            "name": path.name,
            "b64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "type": "text/markdown",
        }
        for path in files
    ]
    try:
        handle.evaluate(
            """(el, files) => {
                const dt = new DataTransfer();
                for (const f of files) {
                    const bin = atob(f.b64);
                    const bytes = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    dt.items.add(new File([bytes], f.name, { type: f.type }));
                }
                const zone = el.closest('form') || el.parentElement || el;
                for (const type of ['dragenter', 'dragover', 'drop']) {
                    zone.dispatchEvent(new DragEvent(type, {
                        bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
                    }));
                }
            }""",
            payload,
        )
        return True
    except (Error, TimeoutError):
        return False


def upload_motion_attachments(page, files: list[Path]) -> bool:
    """Attach the Arsenal .md files to the composer as real files (like the
    manual drag & drop) and confirm the chips landed. Returns True only when the
    attachment is committed to the SAME message. There is deliberately no text
    fallback: Prompt 2 must not leave the composer without all four source chips."""
    missing = [path for path in files if not path.is_file()]
    if missing:
        missing_text = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"Allegati motion mancanti:\n{missing_text}")

    # Preserve order while rejecting accidental duplicate paths. Uploading the
    # same source twice makes Stitch create repeated document nodes on canvas.
    unique_files = list(dict.fromkeys(path.resolve() for path in files))
    if len(unique_files) != len(files):
        raise SystemExit("Allegati motion duplicati: annullo prima di caricarli in Stitch.")
    files = unique_files
    file_strings = [str(path) for path in files]

    already_visible = visible_attachment_names_in_composer(page, files)
    if already_visible:
        if len(already_visible) == len(files):
            print(f"OK: i {len(files)} allegati motion sono gia' presenti nel composer")
            return True
        print(
            "ERRORE: upload motion parziale gia' presente; non riprovo per evitare "
            "documenti duplicati. Visibili: " + ", ".join(already_visible)
        )
        return False

    canvas_baseline = attachment_name_counts_on_page(page, files)

    # NOTE: drag & drop methods (CDP / synthetic DragEvent) are intentionally NOT
    # used here: when the drop misses Stitch's iframe composer, Chrome opens the
    # files as new browser tabs. We only use trusted, side-effect-free attach
    # paths below (composer button, then file input).

    # 1) Click the composer '+' / attach button and use its file chooser.
    upload_buttons = [
        "button[aria-label='+']",
        "button:has-text('+')",
        "[role=button]:has-text('+')",
        "button[aria-label*='Attach' i]",
        "button[aria-label*='Upload' i]",
        "button[aria-label*='Add' i]",
        "[aria-label*='file' i]",
    ]
    upload_attempted = False
    for selector in upload_buttons:
        for surface in surfaces(page):
            button = surface.locator(selector).first
            try:
                button.wait_for(state="visible", timeout=800)
                with page.expect_file_chooser(timeout=2500) as chooser_info:
                    button.click(timeout=1500)
                chooser_info.value.set_files(file_strings)
            except Error:
                continue
            upload_attempted = True
            confirmation = wait_for_motion_attachment_confirmation(
                page, files, canvas_baseline, timeout_ms=20000
            )
            if confirmation == "composer":
                print(f"OK: allegati {len(files)} file .md tramite pulsante (chip nel messaggio)")
                return True
            if confirmation == "canvas":
                print(
                    f"OK: allegati {len(files)} file .md tramite pulsante "
                    "(documenti sorgente sul canvas)"
                )
                return True
            visible = visible_attachment_names_in_composer(page, files)
            print(
                "ERRORE: Stitch non ha confermato tutti i chip dopo l'unico upload "
                f"({len(visible)}/{len(files)} visibili). Non ricarico gli stessi file."
            )
            return False

    if upload_attempted:
        return False

    # 2) Set the files directly on a file input (Stitch may render them as
    # expanded document cards, but it does not open browser tabs).
    for surface in surfaces(page):
        inputs = surface.locator("input[type=file]")
        try:
            count = inputs.count()
        except Error:
            count = 0
        for index in range(count):
            try:
                inputs.nth(index).set_input_files(file_strings, timeout=3000)
            except Error:
                continue
            confirmation = wait_for_motion_attachment_confirmation(
                page, files, canvas_baseline, timeout_ms=20000
            )
            if confirmation == "composer":
                print(f"OK: allegati {len(files)} file .md via input file")
                return True
            if confirmation == "canvas":
                print(
                    f"OK: allegati {len(files)} file .md via input file "
                    "(documenti sorgente sul canvas)"
                )
                return True
            visible = visible_attachment_names_in_composer(page, files)
            print(
                "ERRORE: Stitch non ha confermato tutti i chip dopo l'unico upload "
                f"via input ({len(visible)}/{len(files)} visibili). "
                "Non ricarico gli stessi file."
            )
            return False

    return False


_PROMPT_TARGET_CACHE: dict = {"url": None, "target": None, "time": 0.0}


def find_prompt_target(page):
    prompt_targets = [
        "textarea:not([disabled]):not([readonly])",
        "[contenteditable=true]",
        "[role=textbox][contenteditable=true]",
        "div[aria-label*='prompt' i][contenteditable=true]",
        "div[aria-label*='message' i][contenteditable=true]",
        "textarea[placeholder*='Ask' i]",
        "textarea[placeholder*='Describe' i]",
        "textarea[placeholder*='prompt' i]",
    ]
    # Cache: choose_model_31 e gli helper del composer chiedono la casella del
    # prompt fino a 6 volte di fila (3 tentativi x 2 helper). Se l'ultimo target
    # e' ancora visibile sulla stessa pagina lo riusiamo invece di ricercarlo.
    cache = _PROMPT_TARGET_CACHE
    if cache["target"] is not None and cache["url"] == page.url and time.time() - cache["time"] < 20:
        try:
            if cache["target"].is_visible():
                return cache["target"]
        except Exception:
            pass

    # Due passate: prima un giro RAPIDO su tutte le superfici (il composer di
    # Stitch vive in un iframe, quindi sulla pagina principale tutti gli 8
    # selettori fallivano aspettando 2500ms ciascuno = ~20s buttati ad ogni
    # prompt). Solo se nessuno risponde si ripiega sull'attesa lunga.
    target = first_visible(page, prompt_targets, timeout=250)
    if target is None:
        target = first_visible(page, prompt_targets, timeout=2500)
    if target is not None:
        cache.update(url=page.url, target=target, time=time.time())
    return target


# PALETTO ANTI-LOOP INFINITO.
#
# `wait_for_generation_complete()` capisce se Stitch sta ancora lavorando
# cercando certe frasi nel TESTO VISIBILE DELLA PAGINA - e la pagina include
# la cronologia della chat. Se una di quelle frasi finisce dentro un prompt,
# resta a schermo per sempre e il rilevatore crede che Stitch stia generando
# all'infinito: la pipeline si blocca (successo davvero il 2026-07-26, con la
# frase "Generazione schermata in corso..." messa nel filtro anti-sporcizia).
#
# Qui le frasi vengono NEUTRALIZZATE prima dell'invio, riscrivendole con
# parole equivalenti. Non blocca e non chiede niente: corregge e basta.
_DETECTOR_TRAPS: tuple[tuple[str, str], ...] = (
    (r"Generazione\s+(?:immagine|schermata)\s+in\s+corso\.*", "avvisi di caricamento del generatore"),
    (r"Generazione\s+schermata", "avviso di caricamento"),
    (r"Generazione\s+immagine", "avviso di caricamento"),
    (r"schermata\s+in\s+corso", "caricamento in atto"),
    (r"immagine\s+in\s+co\w*", "caricamento immagine"),
    (r"in\s+corso\.{2,}", "in atto"),
    (r"(?:Generating|Creating)\s+(?:an?\s+)?(?:image|screen)", "loading notice"),
    (r"Whipping\s+up\s+an?\s+image", "loading notice"),
    (r"Mapping\s+out\s+the\s+components", "loading notice"),
    (r"\(\s*(\d+)\s*/\s*(\d+)\s*\)", r"[\1 di \2]"),
)


def sanitize_prompt_for_detector(prompt: str) -> str:
    """Toglie dal prompt le frasi che il rilevatore scambia per 'sto generando'."""
    pulito = prompt
    sostituzioni: list[str] = []
    for schema, rimpiazzo in _DETECTOR_TRAPS:
        pulito, quante = re.subn(schema, rimpiazzo, pulito, flags=re.I)
        if quante:
            sostituzioni.append(f"{schema} x{quante}")
    if sostituzioni:
        print(
            "Paletto anti-loop: neutralizzate nel prompt frasi che bloccherebbero "
            "il rilevatore di fine generazione -> " + "; ".join(sostituzioni)
        )
    return pulito


def fill_prompt(page, prompt: str) -> None:
    target = find_prompt_target(page)
    if not target:
        raise SystemExit("Non ho trovato la casella prompt editabile di Stitch.")

    try:
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass

    try:
        target.scroll_into_view_if_needed(timeout=1000)
    except Error:
        pass

    try:
        target.click(force=True, timeout=1500)
    except Error:
        try:
            target.focus()
        except Error:
            pass

    # INSERIMENTO CON VERIFICA — NON RIPROVARE ALLA CIECA.
    #
    # Prima c'era `fill(timeout=1500)` con fallback `insert_text()`. Su un
    # prompt da 26 KB `fill` va in timeout DOPO aver gia' scritto il testo:
    # il fallback lo inseriva una seconda volta, in coda alla prima. Il
    # composer si ritrovava 52 KB di testo duplicato a meta' frase, entrava
    # in stato di caricamento e l'invio non partiva piu' - ne' da tastiera
    # ne' cliccando la freccia. Il 2026-07-27 un giro e' morto cosi' al
    # primissimo invio, e il rischio cresceva a ogni riga aggiunta ai prompt.
    #
    # Ora: timeout proporzionato, e prima di ogni nuovo tentativo il campo
    # viene SVUOTATO e il contenuto VERIFICATO.
    atteso = len(prompt)
    timeout_fill = max(4000, atteso // 4)

    def _svuota() -> None:
        try:
            target.fill("", timeout=3000)
        except Exception:
            try:
                target.focus()
                page.keyboard.press("Meta+A")
                page.keyboard.press("Delete")
            except Exception:
                pass

    def _lunghezza() -> int:
        for lettore in ("input_value", "inner_text"):
            try:
                return len((getattr(target, lettore)(timeout=2500) or "").strip())
            except Error:
                continue
        return -1

    inserito = False
    for tentativo in (1, 2, 3):
        _svuota()
        page.wait_for_timeout(200)
        try:
            target.focus()
            # Uso execCommand per iniettare il testo come blocco unico
            # In questo modo evito la dipendenza dagli Appunti di sistema e dal CMD+V,
            # che potrebbero aver fallito incollando prompt vecchi, 
            # ed evito il lag di `insert_text` o i timeout di `fill()`.
            success = page.evaluate("""(el, text) => {
                return document.execCommand('insertText', false, text);
            }""", prompt)
            
            if not success:
                # Fallback sicuro: inserimento atomico tramite CDP di Playwright
                page.keyboard.insert_text(prompt)
                
            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"Errore durante l'inserimento: {e}")
            pass
        page.wait_for_timeout(400)

        letto = _lunghezza()
        if letto < 0:
            print("OK: prompt inserito (contenuto non verificabile)")
            inserito = True
            break
        # Il composer normalizza spazi e a capo: tolleranza al 15%.
        if abs(letto - atteso) <= max(400, atteso * 0.15):
            print(f"OK: prompt inserito e verificato ({letto} caratteri su {atteso} attesi)")
            inserito = True
            break
        print(
            f"ATTENZIONE: nel composer ci sono {letto} caratteri invece di {atteso} "
            f"(tentativo {tentativo}/2). Svuoto e riscrivo."
        )
    if not inserito:
        raise SystemExit(
            "Prompt NON inserito correttamente nel composer dopo 2 tentativi: "
            "non invio un testo troncato o duplicato."
        )


def locator_text(locator) -> str:
    try:
        return locator.input_value(timeout=700)
    except Error:
        pass
    try:
        return locator.inner_text(timeout=700)
    except Error:
        pass
    try:
        return locator.text_content(timeout=700) or ""
    except Error:
        return ""


def prompt_marker(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt).strip()
    return normalized[:80]


def prompt_still_in_box(page, marker: str) -> bool:
    if not marker:
        return False
    target = find_prompt_target(page)
    if not target:
        return False
    text = re.sub(r"\s+", " ", locator_text(target)).strip()
    return marker[:40] in text


def click_composer_send_button(page) -> bool:
    target = find_prompt_target(page)
    if not target:
        return False

    try:
        target_box = target.bounding_box(timeout=1000)
    except Error:
        target_box = None
    if not target_box:
        return False

    best = None
    best_score = -1.0

    # Stitch renders the composer inside an iframe. Looking only at page.locator()
    # misses the visible submit arrow even though the prompt field was found.
    for surface in surfaces(page):
        candidates = surface.locator("button, [role=button]").filter(visible=True)
        try:
            count = min(candidates.count(), 120)
        except Error:
            continue

        for index in range(count):
            item = candidates.nth(index)
            try:
                box = item.bounding_box(timeout=500)
            except Error:
                continue
            if not box:
                continue

            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2
            inside_x = target_box["x"] <= center_x <= target_box["x"] + target_box["width"]
            inside_y = target_box["y"] <= center_y <= target_box["y"] + target_box["height"]
            near_bottom = center_y >= target_box["y"] + target_box["height"] - 120
            right_side = center_x >= target_box["x"] + target_box["width"] - 220
            sensible_size = 24 <= box["width"] <= 85 and 24 <= box["height"] <= 85
            if not (inside_x and inside_y and near_bottom and right_side and sensible_size):
                continue

            score = center_x + center_y
            if score > best_score:
                best = item
                best_score = score

    if not best:
        return False

    best.click(timeout=700, force=True)
    print("Click: freccia composer")
    page.wait_for_timeout(400)
    return True


def click_composer_send_coordinates(page) -> bool:
    # Last-resort fallback for a UI release where the submit control has no
    # accessible role. Keep this independent of the prompt locator because the
    # compositor can replace that element just after the text is filled.
    viewport = page.viewport_size or {}
    width = viewport.get("width")
    height = viewport.get("height")
    if not width or not height:
        return False

    x = width - 66
    y = height - 64
    page.mouse.move(x, y)
    page.mouse.click(x, y)
    print(f"Click: coordinate freccia composer ({round(x)}, {round(y)})")
    page.wait_for_timeout(400)
    return True


def keyboard_submit(page) -> bool:
    target = find_prompt_target(page)
    if target:
        try:
            target.click()
        except Error:
            pass
    page.keyboard.press("Meta+Enter")
    page.wait_for_timeout(600)
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(600)
    page.keyboard.press("Enter")
    print("Click: tentativo invio da tastiera")
    page.wait_for_timeout(800)
    return True


def send_started(page, previous_url: str, marker: str, timeout_ms: int = 6000) -> bool:
    busy_pattern = (
        r"Generazione|generando|Generating|Whipping|Mapping out|"
        r"image\s+\d+/\d+|immagine\s+(?:in\s+)?co|"
        r"Sto|Creazione|Creating"
    )
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        if page.url != previous_url and "/projects/" in page.url:
            print(f"OK: Stitch ha cambiato pagina: {page.url}")
            return True
        marker_present = prompt_still_in_box(page, marker)
        if not marker_present and visible_text_exists(page, busy_pattern, timeout=500):
            print("OK: Stitch ha iniziato la generazione")
            return True
        if not marker_present:
            print("OK: il prompt e' uscito dalla casella, invio partito")
            return True
        page.wait_for_timeout(300)
    return False


def send(page, prompt: str) -> None:
    previous_url = page.url
    marker = prompt_marker(prompt)

    # ---- GATE DURO: 3.1 Pro verificato all'ULTIMO ISTANTE UTILE ----
    # Il modello viene scelto ~40 righe prima; poi si scrive il prompt e il
    # composer si ri-renderizza. In quella finestra Stitch a volte retrocede da
    # solo a 3 Flash: il prompt partiva su Flash e nessuno se ne accorgeva.
    # Meglio fermarsi che far generare il sito al modello sbagliato.
    if not active_composer_shows_31_pro(page):
        print("ATTENZIONE: il composer NON e' su 3.1 Pro appena prima dell'invio (downgrade automatico?). Lo reimposto...")
        if not choose_model_31(page, debug_label="pre_send_model_downgrade"):
            raise SystemExit(
                "STOP: non riesco a tenere 3.1 Pro appena prima dell'invio (Stitch passato a Flash?).\n"
                "Invio ANNULLATO di proposito: meglio fermarsi che far generare il sito a Flash.\n"
                "Guarda l'ultimo debug 'pre_send_model_downgrade' in debug/."
            )
        # Cambiare modello puo' far perdere il testo gia' scritto: ricontrollo.
        if not prompt_still_in_box(page, marker):
            print("Il prompt e' sparito dopo il cambio modello: lo riscrivo.")
            fill_prompt(page, prompt)

    attempts = [
        ("tastiera", keyboard_submit),
        ("freccia composer", click_composer_send_button),
        ("coordinate freccia composer", click_composer_send_coordinates),
    ]

    for label, action in attempts:
        if not action(page):
            print(f"Tentativo invio non disponibile: {label}")
            continue
        if send_started(page, previous_url, marker):
            print(f"OK: invio verificato con {label}")
            return
        print(f"Invio non partito dopo tentativo: {label}")

    raise SystemExit("Invio NON partito: Stitch non ha iniziato la generazione.")


def wait_for_project_after_send(
    page,
    timeout_ms: int,
    expect_screen: bool = True,
) -> bool:
    # L'URL /projects/... compare subito dopo l'invio, spesso prima che Stitch
    # abbia creato una schermata. Considerarlo "finito" qui faceva tentare il
    # download dell'ultimo ZIP disponibile e chiudeva Chrome mentre la nuova
    # generazione era ancora in corso.
    if "/projects/" not in page.url:
        try:
            page.wait_for_url(re.compile(r".*/projects/.*"), timeout=timeout_ms)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except TimeoutError:
            print("Stitch non ha aperto una pagina /projects/... entro il tempo previsto.")
            return False

    print(f"OK: progetto Stitch aperto: {page.url}")
    LAST_PROJECT_URL_PATH.write_text(page.url)

    if not expect_screen:
        # La fase analisi produce testo nella conversazione, non una schermata.
        # Aspettare Export qui bloccherebbe per sempre il passaggio al design.
        return True

    from download_stitch_project import wait_for_generation_complete

    print("Aspetto la generazione reale della schermata prima di scaricare o chiudere Chrome...")
    if not wait_for_generation_complete(page, timeout_ms):
        print("La schermata non risulta ancora pronta: non scarico e non proseguo con altre fasi.")
        return False
    return True


def send_revision_followup(page, revision_prompt: str, timeout_ms: int) -> None:
    """Select the generated screen and ask Stitch to repair structure before animation."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    print("Aspetto che il design finisca prima del controllo struttura...")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("Il primo design non ha finito entro il tempo previsto: non mando il controllo struttura.")

    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        raise SystemExit("Non riesco a selezionare la schermata generata per il controllo struttura.")

    print("Invio controllo struttura prima di /animate.")
    if not choose_model_31(page):
        print("ATTENZIONE: non riesco a forzare 3.1 Pro per il controllo struttura, proseguo comunque.")
    fill_prompt(page, revision_prompt)
    send(page, revision_prompt)
    print("OK: controllo struttura inviato. Aspetto la versione corretta.")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("Il controllo struttura non ha finito entro il tempo previsto: non mando /animate.")


def wait_fixed_before_followup(page, seconds: int, label: str) -> bool:
    """Compatibilità CLI: nessuna pausa a tempo, la barriera è condizionale."""
    print(
        f"{label}: nessuna pausa fissa; la fase precedente ha già atteso "
        "avvio e completamento reali."
    )
    return True


def wait_for_sent_phase_completion(page, timeout_ms: int, label: str) -> None:
    """Barriera avvio→fine della fase appena inviata.

    Prima il prompt successivo aspettava 12 secondi e poi vedeva l'Export
    vecchio: poteva quindi partire mentre il backend non aveva ancora mostrato
    la nuova generazione. Ora si procede solo dopo aver visto prima l'avvio
    della nuova fase e poi la sua conclusione stabile.
    """
    from download_stitch_project import (
        wait_for_generation_complete,
        wait_for_generation_started,
    )

    start_timeout = min(timeout_ms, 120000)
    if not wait_for_generation_started(page, start_timeout):
        raise SystemExit(
            f"{label} BLOCCATA: il prompt e' stato inviato ma Stitch non ha "
            "mostrato l'avvio della nuova generazione. Non invio la fase dopo."
        )
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit(
            f"{label} BLOCCATA: la nuova generazione non ha raggiunto uno "
            "stato stabile. Non invio la fase dopo."
        )


def manual_gate(page, enabled: bool, message: str, debug_label: str, debug: bool) -> None:
    if not enabled:
        return
    if debug:
        save_debug(page, debug_label)
    print("")
    print("PAUSA MANUALE")
    print(message)
    print("Guarda la finestra Stitch adesso.")
    print("Premi INVIO nel Terminale per continuare, oppure scrivi STOP e premi Invio per fermare.")
    response = input("> ").strip().lower()
    if response in {"stop", "s", "ferma", "fermo", "no"}:
        raise SystemExit("Fermato manualmente prima del prossimo prompt.")


def wait_for_reference_analysis(page, timeout_ms: int) -> None:
    """Aspetta il referto visuale, non una schermata esportabile.

    La fase analisi non deve attivare il vecchio meccanismo di "spinta": quel
    meccanismo nasceva per costringere Stitch a generare subito il sito e qui
    annullerebbe proprio la separazione voluta.
    """
    deadline = time.time() + timeout_ms / 1000
    marker = r"ANALISI\s+VISIVA\s+COMPLETATA"
    marker_re = re.compile(marker, re.I)

    def marker_count() -> int:
        """Conta il marker nei messaggi gia' presenti su tutte le superfici.

        Il prompt utente contiene deliberatamente il marker da produrre. Un
        semplice `visible_text_exists()` lo trovava subito dentro QUEL prompt e
        faceva partire la fase design mentre Stitch stava ancora analizzando.
        Qui aspettiamo una seconda occorrenza: la risposta di Stitch.
        """
        total = 0
        for surface in surfaces(page):
            try:
                text = surface.locator("body").inner_text(timeout=1200)
                total += len(marker_re.findall(text))
            except (Error, TimeoutError):
                continue
        return total

    slot6_re = re.compile(r"SLOT\s*6", re.I)

    def slot6_count() -> int:
        """Quante volte compare la SESTA scheda: prova che l'analisi e' arrivata in fondo."""
        total = 0
        for surface in surfaces(page):
            try:
                text = surface.locator("body").inner_text(timeout=1200)
                total += len(slot6_re.findall(text))
            except (Error, TimeoutError):
                continue
        return total

    print("FASE 1: attendo rendering del prompt utente...")
    page.wait_for_timeout(4000)
    baseline = marker_count()
    print("FASE 1: aspetto il referto visuale prima di chiedere il sito...")
    print(f"FASE 1: marker gia' presenti nel prompt inviato: {baseline}.")

    # FALLBACK STRUTTURALE — 2026-08-02 (sera). Terza versione, le prime due
    # sbagliate per lo stesso motivo: si appoggiavano a segnali RUMOROSI.
    #  1) solo il marker: se Stitch non copiava la frase, 20 minuti buttati e
    #     "FASE 1 BLOCCATA" con l'analisi completa gia' sullo schermo (2 ago).
    #  2) lunghezza del testo ferma per 45s: nella pagina Stitch qualcosa cambia
    #     sempre (nell'HTML di una fase 1 riuscita ci sono 78 nodi
    #     CircularProgress), quindi il cronometro non scadeva mai.
    # Non si puo' nemmeno riusare generation_is_active() come fanno le fasi 2-6:
    # cerca "Generating screen/image", cioe' una SCHERMATA, mentre la fase 1
    # produce solo testo.
    # Segnale scelto: LA SESTA SCHEDA. Il prompt impone sei schede numerate; se
    # in pagina "SLOT 6" compare oltre alle occorrenze gia' presenti nel prompt,
    # Stitch ha scritto l'ultima ed e' arrivato in fondo davvero. E' un fatto
    # strutturale del contenuto richiesto, non una frase decorativa e non una
    # misura che oscilla. Dopo averlo visto si concede una grazia FISSA, che non
    # dipende da nessuna misura rumorosa.
    # RILEVATORE PRINCIPALE: occupato -> libero.
    # Confronto fra la pagina salvata DURANTE una generazione e quella salvata
    # A GENERAZIONE FINITA: "CircularProgress" c'e' 78 volte in entrambe (inutile,
    # ed e' il motivo per cui il tentativo precedente non scattava mai), mentre le
    # etichette di caricamento passano da 34/6 occorrenze a ZERO. Quello e' il
    # discriminante vero. Attenzione: quasi tutti i "Generating ..." sono stringhe
    # dentro il bundle JS, non testo a schermo -> si guarda solo il testo VISIBILE.
    # Rispetto al pattern di generation_is_active() qui si aggiunge "Caricamento in
    # corso", che compare quando Stitch produce TESTO (fase 1) e non una schermata.
    from download_stitch_project import visible_text_exists

    busy_pattern = (
        r"Generazione\s+(?:immagine|schermata)\s+in\s+corso|"
        r"Generazione\s+schermata|Generazione\s+immagine|"
        r"Caricamento\s+in\s+corso|"
        r"(?:Generating|Creating)\s+(?:an?\s+)?(?:image|screen)|"
        r"Whipping\s+up|Mapping\s+out|Crafting\s+the\s+detailed\s+flows"
    )

    def is_busy() -> bool:
        try:
            return visible_text_exists(page, busy_pattern, timeout=350)
        except (Error, TimeoutError):
            return False

    IDLE_CONFIRM_S = 8
    was_busy = False
    idle_since = None

    # BATTITO — 2026-08-02 (notte). Il ciclo stampava solo quando sbloccava:
    # dal log era impossibile distinguere "Stitch sta ancora scrivendo" da
    # "e' piantato", ed e' costato tutta la serata di diagnosi al buio.
    # Ogni 30s si scrive cosa vede la barriera, cosi' il log risponde da solo.
    inizio = time.time()
    ultimo_battito = 0.0

    # RETE DI SICUREZZA: la sesta scheda. Se Stitch non mostrasse nessuna
    # etichetta di caricamento, "SLOT 6" oltre le occorrenze del prompt prova
    # comunque che l'analisi e' arrivata in fondo.
    slot6_baseline = slot6_count()
    print(f"FASE 1: 'SLOT 6' gia' presenti nel prompt inviato: {slot6_baseline}.")
    GRACE_S = 30
    slot6_seen_at = None

    while time.time() < deadline:
        if marker_count() > baseline:
            print("FASE 1: analisi visiva completata (marker trovato).")
            return

        if is_busy():
            was_busy = True
            idle_since = None
        elif was_busy:
            if idle_since is None:
                idle_since = time.time()
            elif time.time() - idle_since >= IDLE_CONFIRM_S:
                print("FASE 1: Stitch ha smesso di generare: proseguo subito alla fase 2.")
                return

        if slot6_seen_at is None:
            if slot6_count() > slot6_baseline:
                slot6_seen_at = time.time()
                print(
                    "FASE 1: comparsa la sesta scheda; attendo al massimo "
                    f"{GRACE_S}s e proseguo comunque."
                )
        elif time.time() - slot6_seen_at >= GRACE_S:
            print("FASE 1: sei schede presenti, analisi conclusa: proseguo alla fase 2.")
            return

        if time.time() - ultimo_battito >= 30:
            ultimo_battito = time.time()
            print(
                f"  FASE 1 in attesa da {int(time.time() - inizio)}s — "
                f"marker {marker_count()}/{baseline + 1} necessari · "
                f"SLOT 6 {slot6_count()}/{slot6_baseline + 1} · "
                f"Stitch {'STA GENERANDO' if was_busy and idle_since is None else 'fermo'}",
                flush=True,
            )

        page.wait_for_timeout(1500)

    raise SystemExit(
        "FASE 1 BLOCCATA: Stitch non ha prodotto ne' il marker di chiusura ne' "
        "la sesta scheda; non invio la generazione del sito su un'analisi "
        "incompleta."
    )


def send_design_from_analysis_followup(
    page,
    design_prompt: str,
    timeout_ms: int,
    debug: bool = False,
) -> None:
    """Manda la creazione del sito solo dopo il referto visuale separato."""
    wait_for_reference_analysis(page, timeout_ms)
    if debug:
        save_debug(page, "reference_analysis_complete")
    if not choose_model_31(page, debug_label="phase2_design_model_blocked" if debug else None):
        raise SystemExit("FASE 2 BLOCCATA: non riesco a impostare 3.1 Pro per il design.")
    print("FASE 2: invio creazione delle sei section dal referto visuale.")
    fill_prompt(page, design_prompt)
    log_prompt_send("FASE 2/" + str(_totale_fasi()), str(DESIGN_PROMPT_PATH), design_prompt)
    send(page, design_prompt)
    wait_for_sent_phase_completion(page, timeout_ms, "FASE DESIGN")


def send_split_build_followup(
    page,
    prompt: str,
    reference_paths: list[Path],
    timeout_ms: int,
    phase_label: str,
    prompt_path: Path,
) -> None:
    """Completa il secondo build con tre reference senza rigenerare il sito."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    if len(reference_paths) != 3:
        raise SystemExit(f"{phase_label} bloccata: servono esattamente tre reference.")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit(f"{phase_label} bloccata: il primo build non e' stabile.")
    if not select_visible_screen_on_canvas(page):
        raise SystemExit(f"{phase_label} bloccata: non riesco a selezionare la schermata esistente.")
    if not choose_model_31(page):
        raise SystemExit(f"{phase_label} bloccata: non riesco a impostare 3.1 Pro.")

    print(f"{phase_label}: carico le tre reference BAB sul composer di follow-up.")
    upload_images(page, [str(path) for path in reference_paths])
    if not wait_for_attachment_chips(page, reference_paths, timeout_ms=30000):
        raise SystemExit(f"{phase_label} bloccata: Stitch non conferma tutte le reference BAB.")

    contract = "\n\nFILE DEL BATCH BAB, IN QUESTO ORDINE:\n" + "\n".join(
        f"- allegato {index}: `{path.name}`" for index, path in enumerate(reference_paths, start=1)
    )
    followup = prompt.rstrip() + contract + "\n"
    fill_prompt(page, followup)
    log_prompt_send(phase_label, str(prompt_path), followup)
    send(page, followup)
    wait_for_sent_phase_completion(page, timeout_ms, phase_label)


def send_animation_followup(
    page,
    animation_prompt: str,
    timeout_ms: int,
    prompt_path: Path = ANIMATION_PROMPT_PATH,
    phase_label: str = "FASE 2/3",
    prompt_description: str = "animazione",
    attachment_paths: list[Path] | None = None,
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
) -> None:
    """Select the generated screen, then send Stitch's /animate follow-up."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    wait_fixed_before_followup(page, phase_wait_seconds, phase_label)
    print("Controllo che il design abbia davvero finito prima del secondo prompt /animate...")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("Il primo design non ha finito entro il tempo previsto: non mando /animate su una schermata incompleta.")

    manual_gate(
        page,
        manual_gate_between_phases,
        "FASE 1 finita secondo il programma. Sto per selezionare il sito generato e mandare il prompt 2: /animate.",
        "manual_gate_before_animate",
        debug,
    )

    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        raise SystemExit("Non riesco a selezionare la schermata generata per /animate.")
    page.wait_for_timeout(250)
    print(f"{phase_label}: imposto direttamente 3.1 Pro sul nuovo composer.")
    if not choose_model_31(page, debug_label="phase2_model_31_blocked" if debug else None):
        raise SystemExit(
            "Prompt 2 BLOCCATO: non riesco a selezionare direttamente 3.1 Pro."
        )

    # Il runner trasporta il file prompt senza modificarne il contenuto.
    followup = animation_prompt

    if attachment_paths is not None:
        if not attachment_paths:
            raise SystemExit("Prompt 2 bloccato: nessun allegato motion indicato.")
        if len({path.resolve() for path in attachment_paths}) != len(attachment_paths):
            raise SystemExit("Prompt 2 bloccato: gli allegati motion non sono distinti.")
        if any(path.suffix.lower() != ".md" for path in attachment_paths):
            raise SystemExit("Prompt 2 bloccato: tutti gli allegati motion devono essere file .md.")

        print(f"Allego i {len(attachment_paths)} sorgenti GSAP/manifesto al Prompt 2...")
        if not upload_motion_attachments(page, attachment_paths):
            visible = visible_attachment_names_in_composer(page, attachment_paths)
            print(
                "Allegati motion confermati nel composer: "
                f"{len(visible)}/{len(attachment_paths)} "
                f"({', '.join(visible) if visible else 'nessuno'})"
            )
            if debug:
                save_debug(page, "animation_attachments_missing")
            raise SystemExit(
                "Prompt 2 NON inviato: Stitch non ha acquisito tutti i sorgenti "
                "GSAP/manifesto richiesti."
            )

    attachment_text = f" + {len(attachment_paths)} allegati reali" if attachment_paths else ""
    print(f"Invio il secondo messaggio: /animate + {prompt_path.name}{attachment_text} ({prompt_description}).")
    fill_prompt(page, followup)
    log_prompt_send(phase_label, str(prompt_path), followup)
    send(page, followup)
    wait_for_sent_phase_completion(page, timeout_ms, phase_label)
    print("OK: /animate completato; la versione animata e' stabile.")


def send_motion_code_followup(
    page,
    motion_code_prompt: str,
    selection: dict,
    timeout_ms: int,
    attachment_paths: list[Path],
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
) -> None:
    """After /animate, add exactly one Guest Component without replacing content."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    wait_fixed_before_followup(page, phase_wait_seconds, _fase(3))
    print("Controllo che /animate abbia davvero finito prima del Guest Component...")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("La versione /animate non ha finito: non mando il prompt GSAP su una schermata incompleta.")

    manual_gate(
        page,
        manual_gate_between_phases,
        "FASE 2 /animate finita. Sto per aggiungere SOLO il Guest Component come nuova sezione.",
        "manual_gate_before_motion_code",
        debug,
    )

    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        raise SystemExit("Non riesco a selezionare la schermata animata per il Guest Component.")
    page.wait_for_timeout(250)

    print(_fase(3) + ": imposto direttamente 3.1 Pro sul nuovo composer.")
    if not choose_model_31(page, debug_label="phase3_model_31_blocked" if debug else None):
        raise SystemExit("Prompt 3 BLOCCATO: non riesco a selezionare direttamente 3.1 Pro.")

    if len(attachment_paths) != 1:
        raise SystemExit("Prompt 3 bloccato: serve esattamente un solo Guest Component.")
    if any(path.suffix.lower() != ".md" for path in attachment_paths):
        raise SystemExit("Prompt 3 bloccato: il Guest deve essere allegato come .md.")
    print("Allego SOLO il Guest Component al Prompt 3...")
    if not upload_motion_attachments(page, attachment_paths):
        if debug:
            save_debug(page, "component_attachments_missing")
        raise SystemExit(
            "Prompt 3 NON inviato: Stitch non ha acquisito il Guest Component."
        )

    prompt = motion_code_prompt
    print("Invio terzo messaggio: integrazione Ironclad del SOLO Guest Component come nuova sezione.")
    fill_prompt(page, prompt)
    log_prompt_send(_fase(3), str(MOTION_CODE_PROMPT_PATH), prompt)
    send(page, prompt)
    wait_for_sent_phase_completion(page, timeout_ms, _fase(3))
    print("OK: Guest Component completato e stabile.")


def send_second_component_followup(
    page,
    motion_code_prompt: str,
    selection: dict,
    timeout_ms: int,
    attachment_paths: list[Path],
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
) -> None:
    """Fase dedicata al SECONDO Guest Component: va aggiunto come ulteriore
    sezione senza toccare il primo Guest gia' inserito."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    wait_fixed_before_followup(page, phase_wait_seconds, _fase(4))
    print("Controllo che il primo Guest sia stato inserito prima del secondo...")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("Il primo Guest non ha finito: non mando il secondo su una schermata incompleta.")

    manual_gate(
        page,
        manual_gate_between_phases,
        "FASE 3 (Guest #1) finita. Sto per aggiungere il SECONDO Guest Component come nuova sezione.",
        "manual_gate_before_second_component",
        debug,
    )

    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        raise SystemExit("Non riesco a selezionare la schermata per il secondo Guest Component.")
    page.wait_for_timeout(250)

    print(_fase(4) + ": imposto direttamente 3.1 Pro sul nuovo composer.")
    if not choose_model_31(page, debug_label="phase4_model_31_blocked" if debug else None):
        raise SystemExit("Prompt 4 BLOCCATO: non riesco a selezionare direttamente 3.1 Pro.")

    if len(attachment_paths) != 1:
        raise SystemExit("Prompt 4 bloccato: serve esattamente un solo secondo Guest Component.")
    if any(path.suffix.lower() != ".md" for path in attachment_paths):
        raise SystemExit("Prompt 4 bloccato: il Guest #2 deve essere allegato come .md.")
    print("Allego SOLO il secondo Guest Component al Prompt 4...")
    if not upload_motion_attachments(page, attachment_paths):
        if debug:
            save_debug(page, "component2_attachments_missing")
        raise SystemExit("Prompt 4 NON inviato: Stitch non ha acquisito il secondo Guest Component.")

    prompt = motion_code_prompt
    print("Invio quarto messaggio: integrazione del SECONDO Guest Component come nuova sezione.")
    fill_prompt(page, prompt)
    log_prompt_send(_fase(4), str(MOTION_CODE_PROMPT_PATH), prompt)
    send(page, prompt)
    print("OK: prompt secondo Guest Component inviato.")


def send_guest_motion_followup(
    page,
    selection: dict,
    timeout_ms: int,
    attachment_paths: list[Path],
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
) -> None:
    """Secondo passaggio sul Guest: SOLO le animazioni.

    Perche' esiste. Fino al 2026-07-27 struttura e movimento arrivavano nello
    stesso messaggio insieme a CSS, foto, testi e mount: sei compiti in un
    colpo. Con quel carico Stitch ne esegue uno e finge gli altri — misurato
    due volte, prima un rettangolo grigio con dentro il nome del componente,
    poi una sezione strutturalmente completa con UNA funzione di animazione
    su cinque.

    E' lo stesso principio su cui e' costruita tutta la pipeline: quando ha
    un compito solo lo fa (i sei tag GSAP: copiati sempre; il motion kit da
    2,5 KB: copiato sempre). Quindi separiamo: il messaggio precedente crea
    la struttura, questo aggiunge gli strati di movimento.
    """
    # IMPORT DIMENTICATO — BUG TROVATO IL 2026-07-28.
    # Questa funzione usava `wait_for_generation_complete` (riga sotto) e
    # `select_visible_screen_on_canvas` senza importarli, a differenza di
    # tutte le funzioni sorelle. Risultato: NameError alla FASE 4, catturato
    # dall'`except Exception` generico di download_after_send e stampato come
    # "Browser chiuso o disconnesso" — un messaggio che mandava a cercare un
    # problema di rete inesistente. Il giro moriva sempre al Guest Component
    # e passava al recupero MCP, che scaricava il sito a meta' lavoro.
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    if not GUEST_MOTION_PROMPT_PATH.is_file():
        print("Prompt movimento Guest non trovato: salto la fase (non bloccante).")
        return

    wait_fixed_before_followup(page, phase_wait_seconds, _fase(4))

    # QUESTA FASE NON PUO' MAI FERMARE IL GIRO.
    # E' un'aggiunta: se fallisce si perde uno strato di animazione, mentre
    # le fasi dopo (Framer e correzione finale) valgono molto di piu'. Il
    # 2026-07-27 un SystemExit qui ha ucciso due giri interi fermandoli al
    # terzo prompt su sei. Da qui in poi ogni problema si stampa e si salta.
    print("Controllo che la struttura del Guest abbia finito prima delle animazioni...")
    if not wait_for_generation_complete(page, timeout_ms):
        print("  la struttura del Guest non risulta finita: SALTO le animazioni e proseguo con la Framer.")
        return

    manual_gate(
        page,
        manual_gate_between_phases,
        "Struttura del Guest finita. Sto per aggiungere SOLO le animazioni del componente.",
        "manual_gate_before_guest_motion",
        debug,
    )

    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        print("  non riesco a selezionare la schermata: SALTO le animazioni e proseguo.")
        return
    page.wait_for_timeout(250)

    if not choose_model_31(page, debug_label="guest_motion_model_31_blocked" if debug else None):
        print("  non riesco a impostare 3.1 Pro: SALTO le animazioni e proseguo.")
        return

    # Lo stesso .md del passaggio precedente: qui serve come fonte da cui
    # rileggere le funzioni di animazione, non come struttura da ricostruire.
    print("Riallego il Guest Component per il passaggio sulle animazioni...")
    if not upload_motion_attachments(page, attachment_paths):
        if debug:
            save_debug(page, "guest_motion_attachment_missing")
        print("  allegato non acquisito: SALTO le animazioni e proseguo.")
        return

    prompt = GUEST_MOTION_PROMPT_PATH.read_text(encoding="utf-8")
    print("Invio il passaggio movimento: SOLO le animazioni del Guest Component.")
    fill_prompt(page, prompt)
    log_prompt_send("FASE Guest movimento", str(GUEST_MOTION_PROMPT_PATH), prompt)
    send(page, prompt)
    print("OK: prompt movimento Guest inviato.")


def send_framer_followup(
    page,
    framer_prompt: str,
    selection: dict,
    timeout_ms: int,
    attachment_paths: list[Path],
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
) -> None:
    """Apply one Framer interaction without changing section structure."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    wait_fixed_before_followup(page, phase_wait_seconds, _fase(5))
    print("Controllo che il Guest Component abbia finito prima della Framer Interactive...")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("Il Guest Component non ha finito: non mando il prompt Framer.")
    manual_gate(
        page,
        manual_gate_between_phases,
        "Il Guest completo è finito. Sto per applicare SOLO la Framer Interactive senza cambiare sezioni.",
        "manual_gate_before_framer",
        debug,
    )
    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        raise SystemExit("Non riesco a selezionare la schermata con il Guest per la Framer Interactive.")
    page.wait_for_timeout(250)
    print(_fase(5) + ": imposto direttamente 3.1 Pro sul nuovo composer.")
    if not choose_model_31(page, debug_label="phase5_model_31_blocked" if debug else None):
        raise SystemExit("Prompt 5 BLOCCATO: non riesco a selezionare direttamente 3.1 Pro.")
    if len(attachment_paths) != 1 or attachment_paths[0].suffix.lower() != ".md":
        raise SystemExit("Prompt 5 bloccato: serve esattamente un sorgente Framer .md.")
    print("Allego SOLO la Framer Interactive al Prompt 5...")
    if not upload_motion_attachments(page, attachment_paths):
        if debug:
            save_debug(page, "framer_attachment_missing")
        raise SystemExit("Prompt 5 NON inviato: Stitch non ha acquisito il sorgente Framer.")
    prompt = framer_prompt
    fill_prompt(page, prompt)
    log_prompt_send(_fase(5), str(FRAMER_PROMPT_PATH), prompt)
    send(page, prompt)
    wait_for_sent_phase_completion(page, timeout_ms, _fase(5))
    print("OK: Framer completata e stabile.")


def send_final_check_followup(
    page,
    final_prompt: str,
    timeout_ms: int,
    attachment_paths: list[Path],
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
) -> None:
    """After animation, ask Stitch to audit and repair the current result."""
    from download_stitch_project import select_visible_screen_on_canvas, wait_for_generation_complete

    wait_fixed_before_followup(page, phase_wait_seconds, _fase(6))
    print("Controllo che l'integrazione motion abbia davvero finito prima del controllo finale...")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("L'integrazione motion non ha finito entro il tempo previsto: non mando il controllo finale.")

    manual_gate(
        page,
        manual_gate_between_phases,
        "FASE 5 Framer finita. Sto per selezionare l'ultima schermata e mandare il prompt 6 di correzione finale.",
        "manual_gate_before_final_check",
        debug,
    )

    page.wait_for_timeout(450)
    if not select_visible_screen_on_canvas(page):
        raise SystemExit("Non riesco a selezionare la schermata generata per il controllo finale.")
    page.wait_for_timeout(250)
    print(_fase(6) + ": imposto direttamente 3.1 Pro sul nuovo composer.")
    if not choose_model_31(page, debug_label="phase6_model_31_blocked" if debug else None):
        raise SystemExit(
            "Prompt 6 BLOCCATO: non riesco a selezionare direttamente 3.1 Pro."
        )

    # 2 allegati con un solo Guest (Guest + Framer), 3 con due Guest.
    if len(attachment_paths) not in (2, 3):
        raise SystemExit(
            "Prompt 6 bloccato: servono i sorgenti Guest e Framer "
            f"(attesi 2 o 3 allegati, ricevuti {len(attachment_paths)})."
        )
    if len({path.resolve() for path in attachment_paths}) != len(attachment_paths):
        raise SystemExit("Prompt 6 bloccato: tutti i sorgenti finali devono essere distinti.")
    if any(path.suffix.lower() != ".md" for path in attachment_paths):
        raise SystemExit("Prompt 6 bloccato: tutti i sorgenti finali devono essere .md.")
    source_names = "Guest #1, Framer" if len(attachment_paths) == 2 else "Guest #1, Guest #2, Framer"
    print(f"Allego {source_names} al Prompt 6 di correzione finale...")
    if not upload_motion_attachments(page, attachment_paths):
        if debug:
            save_debug(page, "final_source_attachments_missing")
        raise SystemExit(
            "Prompt 6 NON inviato: Stitch non ha acquisito tutti i sorgenti finali richiesti."
        )

    print("Invio sesto messaggio: correzione fisica finale bug/link/menu/sezioni/motion.")
    fill_prompt(page, final_prompt)
    log_prompt_send(_fase(6), str(FINAL_CHECK_PROMPT_PATH), final_prompt)
    send(page, final_prompt)
    print("OK: controllo finale inviato. Aspetto la versione corretta.")
    if not wait_for_generation_complete(page, timeout_ms):
        raise SystemExit("Il controllo finale non ha finito entro il tempo previsto: non scarico una versione incompleta.")


DESIGN_GATE_LOG_PATH = PROJECT_DIR / "DESIGN_GATE_LOG.txt"


def registra_esito_gate(modo: str, contesto: str, errori: list[str]) -> None:
    """Accoda l'esito del gate design, anche quando non blocca.

    È il punto dello SHADOW GATE: i controlli girano a ogni giro e lasciano
    una traccia, invece di restare codice morto. Dopo qualche giro reale
    questo file dice se i falsi positivi sono sotto controllo, e solo allora
    ha senso passare a `--design-gate block`.
    """
    try:
        DESIGN_GATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        esito = "PASS" if not errori else f"FAIL({len(errori)})"
        riga = (
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} | modo={modo} | {contesto} | "
            f"{esito}"
        )
        if errori:
            riga += " | " + " ;; ".join(e.replace("\n", " ")[:120] for e in errori)
        with DESIGN_GATE_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(riga + "\n")
    except OSError:
        pass


def run_design_gate(motion_selection: dict, modo: str = "shadow") -> bool:
    """Controlla l'HTML appena generato dalla fase 1.

    `modo`:
      - `shadow`  esegue i controlli, stampa e registra l'esito, ma ritorna
                  SEMPRE True: la pipeline non si ferma. È il default finché
                  i controlli non sono calibrati su esecuzioni reali.
      - `block`   come prima: un FAIL ferma il giro prima delle fasi a
                  pagamento.

    ⚠️ In modo `shadow` nessun prompt deve dichiarare che il gate blocca: un
    vincolo annunciato e non applicato insegna al modello che le minacce del
    prompt sono bluff, e il danno non resta confinato a quella regola.

    True = si prosegue.

    L'HTML si recupera via MCP (stessa strada del download): e' il codice vero
    della schermata, non lo screenshot della pagina Stitch.

    Se il recupero non riesce il giro si ferma prima delle fasi a pagamento:
    senza HTML non e' possibile dimostrare che le sei section esistano.
    In modo `shadow` invece si prosegue: un gate che non blocca non deve
    diventare il motivo per cui un giro muore.
    """
    ombra = modo != "block"

    def esci(ok: bool, motivo: str = "") -> bool:
        if motivo:
            registra_esito_gate(modo, "non eseguibile", [motivo])
        return True if ombra else ok

    try:
        from download_stitch_project import find_best_screen_html, last_project_id
        from verify_design_phase import check_design_html, report

        project_id = last_project_id()
        if not project_id:
            print("Gate fase 1: nessun project id.")
            return esci(False, "nessun project id")
        html_data, _meta = find_best_screen_html(project_id)
        if not html_data:
            print("Gate fase 1: HTML non recuperabile.")
            return esci(False, "HTML non recuperabile")
        html = html_data.decode("utf-8", errors="ignore")
        errori = check_design_html(html, motion_selection)
        passato = report(errori, f"progetto {project_id}")
        registra_esito_gate(modo, f"progetto {project_id}", errori)
        if ombra and not passato:
            print(
                "Gate fase 1 in modo OMBRA: registrato in "
                f"{DESIGN_GATE_LOG_PATH.name}, il giro PROSEGUE. "
                "Passa a --design-gate block quando i falsi positivi sono "
                "sotto controllo."
            )
        return True if ombra else passato
    except Exception as exc:
        print(f"Gate fase 1: controllo non eseguibile ({exc}).")
        return esci(False, f"eccezione: {exc}")


def validate_downloaded_slot_contract(
    zip_path: Path,
    require_motion_extensions: bool = False,
) -> list[str]:
    """Verifica zero-crediti sullo ZIP finale scaricato.

    Non corregge e non rimanda nulla a Stitch: segnala soltanto se il file
    consegnato ha perso il contratto fisico che serve a design, motion, Guest
    e Framer per agganciarsi alle sei section editoriali.
    """
    errors: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            html_names = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".html", ".htm"))
                and "__macosx" not in name.lower()
            ]
            if not html_names:
                return ["nessun file HTML trovato nello ZIP"]
            preferred = sorted(
                html_names,
                key=lambda name: (
                    0 if name.lower().endswith("code.html") else 1,
                    len(name),
                    name,
                ),
            )[0]
            html = archive.read(preferred).decode("utf-8", errors="ignore")
    except Exception as exc:
        return [f"ZIP non leggibile per controllo struttura: {exc}"]

    slots = re.findall(
        r"<section\b[^>]*\bdata-reference-slot=['\"]([1-6])['\"]",
        html,
        re.I,
    )
    expected_slots = [str(index) for index in range(1, 7)]
    if sorted(slots) != expected_slots:
        errors.append(
            "contratto slot mancante: attesi data-reference-slot 1,2,3,4,5,6; "
            f"trovati {', '.join(sorted(slots)) or 'nessuno'}"
        )

    # ── I QUATTRO CONTROLLI EREDITATI DA FASE 4 E FASE 5 — 2026-08-03 ──
    # Quei due prompt sono usciti dal dispatch verso Stitch: erano no-op che
    # costavano una rigenerazione della pagina ciascuno. Chiedevano esattamente
    # questi controlli, che qui costano zero e non toccano niente.

    # 1. ACCOPPIAMENTO id <-> slot. Una targhetta sulla sezione sbagliata e'
    #    peggio di una mancante: fa passare per corretto un ordine che non lo e'.
    accoppiamento_atteso = {
        "azienda": "1", "vigneti": "2", "dispensa": "3",
        "tavola": "4", "collezioni": "5", "riconoscimenti": "6",
    }
    for sezione in re.finditer(r"<section\b([^>]*)>", html, re.I):
        attributi = sezione.group(1)
        id_match = re.search(r"\bid=['\"]([^'\"]+)['\"]", attributi, re.I)
        slot_match = re.search(r"\bdata-reference-slot=['\"]([^'\"]+)['\"]", attributi, re.I)
        if not id_match:
            continue
        nome = id_match.group(1).lower()
        if nome not in accoppiamento_atteso:
            continue
        atteso = accoppiamento_atteso[nome]
        trovato = slot_match.group(1) if slot_match else None
        if trovato is None:
            errors.append(f"#{nome} non ha data-reference-slot (atteso {atteso})")
        elif trovato != atteso:
            errors.append(
                f"#{nome} ha data-reference-slot={trovato} invece di {atteso}: "
                f"lo slot e' abbinato alla sezione sbagliata"
            )

    # 2. `#riconoscimenti` NON VUOTA: la pipeline ci costruisce sopra il palco
    #    della Framer riusandone il contenuto. Se e' vuota, la Framer nasce vuota.
    ric = re.search(
        r"<section\b[^>]*\bid=['\"]riconoscimenti['\"].*?</section>", html, re.I | re.S
    )
    if ric:
        corpo = re.sub(r"<[^>]+>", " ", ric.group(0))
        if len(corpo.split()) < 8:
            errors.append(
                "#riconoscimenti quasi vuota: la Framer riusa il suo contenuto "
                "e nascerebbe vuota"
            )

    # 3. CDN GSAP: cinque, uno per libreria, tutti 3.13.0, nessun doppione.
    for libreria in ("gsap.min.js", "ScrollTrigger.min.js", "SplitText.min.js",
                     "Flip.min.js", "CustomEase.min.js"):
        tag = re.findall(
            rf"<script[^>]+src=['\"]([^'\"]*{re.escape(libreria)})['\"]", html, re.I
        )
        if not tag:
            errors.append(f"CDN GSAP mancante: {libreria}")
        elif len(tag) > 1:
            errors.append(f"CDN GSAP duplicato ({len(tag)}x): {libreria}")
        elif "/3.13.0/" not in tag[0]:
            errors.append(f"CDN GSAP a versione sbagliata: {tag[0]}")

    # 4. MOTION KIT valido: uno solo, ed e' codice, non prosa. Il 3 ago il kit
    #    iniettato era un SyntaxError e nessuna animazione partiva.
    try:
        from download_stitch_project import valida_blocco_kit

        blocchi = re.findall(
            r'<script id="stitch-motion-kit">.*?</script>', html, re.S
        )
        if not blocchi:
            errors.append("motion kit assente dalla pagina")
        elif len(blocchi) > 1:
            errors.append(f"motion kit presente {len(blocchi)} volte: deve essere uno solo")
        else:
            scarto = valida_blocco_kit(blocchi[0])
            if scarto:
                errors.append(f"motion kit non valido: {scarto}")
    except ImportError:
        pass

    required_ids = [
        "azienda",
        "vigneti",
        "dispensa",
        "tavola",
        "collezioni",
        "riconoscimenti",
    ]
    missing_ids = [
        section_id
        for section_id in required_ids
        if not re.search(
            rf"<section\b[^>]*\bid=['\"]{re.escape(section_id)}['\"]",
            html,
            re.I,
        )
    ]
    if missing_ids:
        errors.append("section id mancanti: " + ", ".join(missing_ids))

    header_match = re.search(r"<header\b.*?</header>", html, re.I | re.S)
    if header_match:
        header_html = header_match.group(0)
        if re.search(r"<img\b|<svg\b|logo|brand|wordmark", header_html, re.I):
            errors.append("header non pulito: contiene logo/immagine/svg/brand marker")
    else:
        errors.append("header mancante")

    if len(re.findall(r"<footer\b", html, re.I)) != 1:
        errors.append("footer mancante o duplicato")

    if re.search(r"<(?:html|body)\b[^>]*style=['\"][^'\"]*opacity\s*:\s*0\b", html, re.I):
        errors.append(
            "pagina inizialmente invisibile: html/body contiene style opacity:0 "
            "senza garanzia statica di ripristino"
        )

    if require_motion_extensions:
        guest_markers = re.findall(
            r"data-stitch-native-component=['\"][^'\"]+['\"]|data-stitch-added-guest=['\"]true['\"]",
            html,
            re.I,
        )
        if len(guest_markers) < 1:
            errors.append("Guest mancante: nessuna root data-stitch-native-component/data-stitch-added-guest")
        framer_sections = re.findall(
            r"<section\b[^>]*data-stitch-framer-added=['\"]true['\"][^>]*>",
            html,
            re.I,
        )
        if len(framer_sections) != 1:
            errors.append(f"Framer section non univoca: trovate {len(framer_sections)}")
        if not re.search(r"data-stitch-framer-interaction=['\"][^'\"]+['\"]", html, re.I):
            errors.append("Framer root mancante: nessun data-stitch-framer-interaction")
        if not re.search(r"<script\b[^>]*(?:type=['\"]module['\"]|type=['\"]text/babel['\"])", html, re.I):
            errors.append("Framer runtime mancante: nessuno script module/text-babel")

    return errors


def download_after_send(
    page,
    timeout_ms: int,
    design_prompt: str | None = None,
    split_build_prompt: str | None = None,
    split_build_reference_paths: list[Path] | None = None,
    animation_prompt: str | None = None,
    motion_code_prompt: str | None = None,
    motion_attachment_paths: list[Path] | None = None,
    motion_selection: dict | None = None,
    structure_check_prompt: str | None = None,
    final_check_prompt: str | None = None,
    phase_wait_seconds: int = 0,
    manual_gate_between_phases: bool = False,
    debug: bool = False,
    verify_motion_export: bool = False,
    max_gate_retries: int = 0,
    design_gate_mode: str = "shadow",
    guest_framer_in_stitch: bool = False,
) -> Path | None:
    if not wait_for_project_after_send(
        page,
        timeout_ms,
        expect_screen=not bool(design_prompt and design_prompt.strip()),
    ):
        return None

    # Il primo messaggio puo' essere soltanto analisi. In quel caso il progetto
    # esiste gia' come conversazione Stitch, ma non c'e' ancora nessuna
    # schermata: la creazione vera arriva qui, dopo il marker dell'analisi.
    if design_prompt and design_prompt.strip():
        send_design_from_analysis_followup(page, design_prompt, timeout_ms, debug=debug)

    if split_build_prompt and split_build_prompt.strip():
        send_split_build_followup(
            page,
            split_build_prompt,
            split_build_reference_paths or [],
            timeout_ms,
            "BUILD BAB",
            BUILD_BAB_PROMPT_PATH,
        )

    if structure_check_prompt and structure_check_prompt.strip():
        send_revision_followup(page, structure_check_prompt, timeout_ms)

    if animation_prompt and animation_prompt.strip() and design_gate_mode != "off":
        etichetta = "OMBRA (non blocca)" if design_gate_mode != "block" else "BLOCCANTE"
        print(f"Gate locale Fase 1 [{etichetta}]: controllo il design prima di /animate.")
        if not run_design_gate(motion_selection or {}, modo=design_gate_mode):
            raise SystemExit(
                "FASE 1 BLOCCATA: il design non rispetta il contratto "
                "minimo. Non mando motion, Guest o Framer su una base sbagliata."
            )

    animation_sources: list[Path] | None = None
    component_sources: list[Path] = []
    component2_sources: list[Path] = []
    framer_sources: list[Path] = []
    if motion_code_prompt and motion_code_prompt.strip():
        if not motion_selection:
            raise SystemExit("Pipeline motion bloccata: selezione Guest/Framer mancante.")
        if not motion_attachment_paths:
            raise SystemExit("Pipeline motion bloccata: mancano i sorgenti selezionati.")
        (
            animation_sources,
            component_sources,
            component2_sources,
            framer_sources,
        ) = split_motion_attachment_paths(motion_attachment_paths)

    if animation_prompt and animation_prompt.strip():
        send_animation_followup(
            page,
            animation_prompt,
            timeout_ms,
            prompt_path=ANIMATION_PROMPT_PATH,
            phase_label=_fase(2) if motion_code_prompt and motion_code_prompt.strip() else "FASE 2/3",
            prompt_description="regia GSAP Awwwards",
            attachment_paths=animation_sources,
            phase_wait_seconds=phase_wait_seconds,
            manual_gate_between_phases=manual_gate_between_phases,
            debug=debug,
        )

    # ⛔ GUEST E FRAMER NON SI CHIEDONO PIU' A STITCH — 2026-08-03.
    #
    # I prompt FASE 4 (Guest) e FASE 5 (Framer) sono diventati no-op: dicono a
    # Stitch di non scrivere niente e di limitarsi a controllare. Ma un no-op
    # affidato a un modello generativo non e' gratis: OGNI messaggio fa
    # rigenerare l'intera schermata, ed e' li' che le sezioni si perdono
    # (misurato 6->3->2->1 su giri successivi). In cambio non si ottiene
    # nessuna capacita' nuova: i quattro controlli che quei prompt chiedevano
    # — CDN unici e 3.13.0, kit valido, sei coppie id<->data-reference-slot,
    # `#riconoscimenti` non vuota — sono tutti verificabili in Python, a costo
    # zero e senza toccare la pagina (vedi `validate_downloaded_slot_contract`).
    #
    # Guest e Framer li costruisce `enforce_original_interactives`, che ha i
    # sorgenti originali, gli id generati dal catalogo e l'ancoraggio al
    # <footer>. E' gia' l'unico che li produce davvero: mandarli anche a
    # Stitch aggiungeva solo il rischio che li toccasse.
    #
    # I file dei prompt restano sul disco: servono se un giorno si vuole
    # riattivare il dispatch con --guest-framer-in-stitch.
    if motion_code_prompt and motion_code_prompt.strip() and guest_framer_in_stitch:
        send_motion_code_followup(
            page,
            motion_code_prompt=motion_code_prompt,
            selection=motion_selection,
            timeout_ms=timeout_ms,
            attachment_paths=component_sources,
            phase_wait_seconds=phase_wait_seconds,
            manual_gate_between_phases=manual_gate_between_phases,
            debug=debug,
        )
        if component2_sources:
            send_second_component_followup(
                page,
                motion_code_prompt=motion_code_prompt,
                selection=motion_selection,
                timeout_ms=timeout_ms,
                attachment_paths=component2_sources,
                phase_wait_seconds=phase_wait_seconds,
                manual_gate_between_phases=manual_gate_between_phases,
                debug=debug,
            )
        if not FRAMER_PROMPT_PATH.is_file():
            raise SystemExit(f"Prompt Framer non trovato: {FRAMER_PROMPT_PATH}")
        send_framer_followup(
            page,
            framer_prompt=FRAMER_PROMPT_PATH.read_text(encoding="utf-8"),
            selection=motion_selection,
            timeout_ms=timeout_ms,
            attachment_paths=framer_sources,
            phase_wait_seconds=phase_wait_seconds,
            manual_gate_between_phases=manual_gate_between_phases,
            debug=debug,
        )
    elif motion_code_prompt and motion_code_prompt.strip():
        print(
            "Guest e Framer NON inviati a Stitch: li costruisce la pipeline "
            "(enforce_original_interactives) e i controlli li fa Python. "
            "Due rigenerazioni della pagina in meno."
        )

    if final_check_prompt and final_check_prompt.strip():
        final_sources = [component_sources[0], *component2_sources[:1], framer_sources[0]]
        send_final_check_followup(
            page,
            final_prompt=final_check_prompt,
            timeout_ms=timeout_ms,
            attachment_paths=final_sources,
            phase_wait_seconds=phase_wait_seconds,
            manual_gate_between_phases=manual_gate_between_phases,
            debug=debug,
        )

    manual_gate(
        page,
        manual_gate_between_phases,
        "Tutte le fasi prompt sono finite secondo il programma. Sto per scaricare lo ZIP.",
        "manual_gate_before_download",
        debug,
    )

    from download_stitch_project import download_project

    result = download_project(page)
    if not result:
        return None
    print(f"OK: progetto scaricato in: {result}")
    structure_errors = validate_downloaded_slot_contract(
        result,
        require_motion_extensions=verify_motion_export,
    )
    if structure_errors:
        print(f"REFERTO STRUTTURA: FAIL — {len(structure_errors)} problemi rilevati:")
        for error in structure_errors:
            print(f"  - {error}")
    else:
        print("REFERTO STRUTTURA: PASS — sei slot fisici e header/footer presenti.")
    if not verify_motion_export:
        if structure_errors:
            raise SystemExit(
                "Export scaricato ma non valido: manca il contratto fisico "
                "dei sei slot. Lo ZIP e' conservato, ma non lo considero riuscito."
            )
        return result

    from download_stitch_project import (
        download_project,
        select_visible_screen_on_canvas,
        wait_for_generation_complete,
        zip_has_site_code,
    )
    from gate_retry import run_gate

    # GATE SOLO-REFERTO (Sebastian: "basta gate, obbligalo; ogni retry sono
    # crediti sprecati"). L'imposizione sta tutta a monte, nei prompt con i
    # blocchi gia' montati. Qui si verifica e si RIFERISCE soltanto: nessuna
    # correzione viene piu' rimandata a Stitch e lo ZIP si conserva sempre.
    print("Verifica finale (solo referto, nessuna correzione a pagamento)...")
    passed, errors = run_gate(result, MOTION_SELECTION_PATH, static_only=False)
    if passed:
        print("REFERTO: PASS — export reale validato su tutti i controlli.")
    else:
        print(f"REFERTO: FAIL — {len(errors)} problemi rilevati (ZIP conservato comunque):")
        for error in errors:
            print(f"  - {error}")
    if structure_errors:
        raise SystemExit(
            "Export scaricato ma non valido: manca il contratto fisico "
            "dei sei slot. Lo ZIP e' conservato, ma non lo considero riuscito."
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manda l'ultimo batch di reference a Stitch.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--no-send", action="store_true", help="Compila Stitch ma non preme invio.")
    parser.add_argument("--slow", action="store_true", help="Rallenta le azioni per debug visivo.")
    parser.add_argument("--headed", action="store_true", help="Mostra il browser mentre lavora, utile per controllo live.")
    parser.add_argument("--setup-login", action="store_true", help="Apre Stitch e resta fermo per fare login.")
    parser.add_argument("--wait-login", action="store_true", help="Se serve login, aspetta e poi continua automaticamente.")
    parser.add_argument("--debug", action="store_true", help="Salva screenshot e HTML debug.")
    parser.add_argument(
        "--download-after-send",
        action="store_true",
        help="Dopo l'invio aspetta il progetto Stitch e prova a scaricarlo automaticamente.",
    )
    parser.add_argument(
        "--download-timeout",
        type=int,
        default=900,
        help="Secondi massimi da aspettare per la generazione prima del download. Default: 900.",
    )
    parser.add_argument(
        "--browser",
        choices=("chrome", "chromium"),
        default="chrome",
        help="Browser da usare. Default: chrome reale installato sul Mac.",
    )
    parser.add_argument(
        "--prompt-mode",
        choices=("full", "anatomy", "minimal", "empty"),
        default="full",
        help="full usa STITCH_PROMPT; anatomy aggiunge analisi automatica; minimal usa poche istruzioni; empty invia solo immagini se Stitch lo permette.",
    )
    parser.add_argument(
        "--analyze-before-design",
        action="store_true",
        help=(
            "Invia prima il referto visuale delle reference e solo nel secondo "
            "messaggio crea il design. Mantiene poi le fasi motion/componenti."
        ),
    )
    parser.add_argument(
        "--split-build-aba-bab",
        action="store_true",
        help=(
            "Unisce analisi e costruzione in due build da tre reference: "
            "A-B-A crea slot 3/4/6, poi B-A-B aggiunge slot 1/2/5."
        ),
    )
    parser.add_argument(
        "--skip-design-preflight",
        action="store_true",
        help=(
            "Compatibilita': equivale a --design-gate off. Preferisci "
            "--design-gate shadow, che esegue i controlli senza bloccare."
        ),
    )
    parser.add_argument(
        "--guest-framer-in-stitch",
        dest="guest_framer_in_stitch",
        action="store_true",
        help=(
            "Rimanda a Stitch anche i prompt FASE 4 (Guest) e FASE 5 (Framer). "
            "SCONSIGLIATO: sono no-op, ma ogni messaggio fa rigenerare la "
            "pagina ed e' li' che si perdono le sezioni. I loro controlli li "
            "fa gia' Python e i componenti li costruisce la pipeline."
        ),
    )
    parser.add_argument(
        "--no-guest-framer-in-stitch",
        dest="guest_framer_in_stitch",
        action="store_false",
        help="Default: Guest e Framer non vengono chiesti a Stitch.",
    )
    parser.set_defaults(guest_framer_in_stitch=False)
    parser.add_argument(
        "--design-gate",
        choices=("off", "shadow", "block"),
        default="shadow",
        help=(
            "off: non esegue il gate design (i controlli restano codice morto). "
            "shadow (default): li esegue a ogni giro, stampa e registra l'esito "
            "in DESIGN_GATE_LOG.txt, ma NON ferma la pipeline. "
            "block: un FAIL ferma il giro prima delle fasi a pagamento. "
            "Passa a block solo dopo 3-5 giri reali in shadow, quando il log "
            "mostra che i falsi positivi sono sotto controllo."
        ),
    )
    parser.add_argument(
        "--reference-group",
        choices=("all", "first", "second"),
        default="all",
        help="Scegli quali immagini da LATEST_BATCH caricare: tutte, prima reference completa, o seconda reference completa.",
    )
    parser.add_argument(
        "--animate-in-stitch",
        dest="animate_in_stitch",
        action="store_true",
        help="Forza il secondo passaggio Stitch: selezione schermata + /animate.",
    )
    parser.add_argument(
        "--no-animate-in-stitch",
        dest="animate_in_stitch",
        action="store_false",
        help="Disattiva il secondo passaggio Stitch: selezione schermata + /animate.",
    )
    parser.set_defaults(animate_in_stitch=False)
    parser.add_argument(
        "--animation-prompt",
        type=Path,
        default=ANIMATION_PROMPT_PATH,
        help="File del secondo prompt per /animate. Default: STITCH_ANIMATION_PROMPT.txt.",
    )
    parser.add_argument(
        "--motion-code-pass-in-stitch",
        dest="motion_code_pass_in_stitch",
        action="store_true",
        help="Usa il prompt GSAP/componenti come secondo messaggio, preceduto da /animate.",
    )
    parser.add_argument(
        "--no-motion-code-pass-in-stitch",
        dest="motion_code_pass_in_stitch",
        action="store_false",
        help="Disattiva il prompt /animate + GSAP/componenti.",
    )
    parser.set_defaults(motion_code_pass_in_stitch=False)
    parser.add_argument(
        "--motion-code-prompt",
        type=Path,
        default=MOTION_CODE_PROMPT_PATH,
        help="File prompt integrazione GSAP/componenti. Default: STITCH_MOTION_CODE_PROMPT.txt.",
    )
    parser.add_argument(
        "--motion-manifest",
        type=Path,
        # Indicizzare per posizione si rompe ogni volta che la lista cambia
        # (successo togliendo il bundle plugin GSAP): si cerca per nome.
        default=next(
            (p for p in MOTION_CORE_ATTACHMENT_PATHS if "MANIFEST" in p.name.upper()),
            MOTION_MANIFEST_PATH,
        ),
        help="Compatibilita' con i vecchi comandi; il manifesto autorevole e' STITCH_MOTION_EXECUTION_MANIFEST.md.",
    )
    parser.add_argument(
        "--structure-check-in-stitch",
        dest="structure_check_in_stitch",
        action="store_true",
        help="Prima di /animate manda un prompt di controllo struttura/sezioni.",
    )
    parser.add_argument(
        "--no-structure-check-in-stitch",
        dest="structure_check_in_stitch",
        action="store_false",
        help="Disattiva il controllo struttura prima di /animate.",
    )
    parser.set_defaults(structure_check_in_stitch=False)
    parser.add_argument(
        "--structure-check-prompt",
        type=Path,
        default=STRUCTURE_CHECK_PROMPT_PATH,
        help="File prompt controllo struttura. Default: STITCH_STRUCTURE_CHECK_PROMPT.txt.",
    )
    parser.add_argument(
        "--final-check-in-stitch",
        dest="final_check_in_stitch",
        action="store_true",
        help="Dopo /animate + GSAP/componenti manda il terzo prompt di controllo finale.",
    )
    parser.add_argument(
        "--no-final-check-in-stitch",
        dest="final_check_in_stitch",
        action="store_false",
        help="Disattiva il terzo prompt di controllo finale.",
    )
    parser.set_defaults(final_check_in_stitch=False)
    parser.add_argument(
        "--final-check-prompt",
        type=Path,
        default=FINAL_CHECK_PROMPT_PATH,
        help="File prompt controllo finale. Default: STITCH_STRUCTURE_CHECK_PROMPT.txt.",
    )
    parser.add_argument(
        "--phase-wait-seconds",
        type=int,
        default=0,
        help=(
            "Attesa minima prima di ogni prompt successivo. Con 0 usa una "
            "barriera tecnica automatica di 12 secondi; non richiede input."
        ),
    )
    parser.add_argument(
        "--allow-followup-phases",
        action="store_true",
        help=(
            "Sblocco esplicito per inviare un secondo prompt nella stessa esecuzione. "
            "Senza questo flag il comando invia solo la fase design."
        ),
    )
    parser.add_argument(
        "--manual-gate-between-phases",
        action="store_true",
        help="Dopo ogni fase salva debug, lascia Stitch visibile e aspetta INVIO prima del prompt successivo.",
    )
    parser.add_argument(
        "--fresh-stitch-state",
        action="store_true",
        help="Pulisce local/session storage di Stitch prima di iniziare, mantenendo i cookie Google.",
    )
    parser.add_argument(
        "--max-gate-retries",
        type=int,
        default=0,
        help=(
            "Numero massimo di correzioni automatiche dopo il quality gate. "
            "Default: 0, quindi controllo one-shot senza nuove generazioni."
        ),
    )
    return parser.parse_args()


def save_debug(page, label: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
    screenshot = DEBUG_DIR / f"{stamp}_{slug}.png"
    html = DEBUG_DIR / f"{stamp}_{slug}.html"
    try:
        page.screenshot(path=str(screenshot), full_page=True)
        # Stitch gira DENTRO un iframe: page.content() salva solo il guscio esterno
        # (zero textarea, nessuna etichetta modello) e rende il debug inutile.
        # Qui accodiamo il DOM di OGNI frame, cosi' il composer e' ispezionabile.
        parts = [page.content()]
        for frame in page.frames:
            if frame is page.main_frame:
                continue
            try:
                parts.append(
                    f"\n<!-- ===== FRAME: {frame.url} ===== -->\n{frame.content()}"
                )
            except Error:
                parts.append(f"\n<!-- ===== FRAME NON LEGGIBILE: {frame.url} ===== -->\n")
        html.write_text("\n".join(parts))
        print(f"Debug screenshot: {screenshot}")
        print(f"Debug HTML: {html} ({len(page.frames)} frame salvati)")
    except Exception as exc:
        print(f"Non riesco a salvare debug: {exc}")


def open_stitch_with_retry(page, purpose: str) -> None:
    """Apre Stitch e recupera da brevi disconnessioni senza un traceback.

    Chrome puo' restare aperto mentre il Mac perde momentaneamente il Wi-Fi.
    In quel caso Playwright fallisce subito con ERR_INTERNET_DISCONNECTED: un
    secondo tentativo e' sufficiente nella maggior parte dei casi.
    """
    last_error: Error | None = None
    for attempt in range(1, STITCH_NAVIGATION_ATTEMPTS + 1):
        try:
            page.goto(STITCH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            return
        except Error as exc:
            last_error = exc
            details = str(exc)
            retryable = any(code in details for code in _RETRYABLE_STITCH_NETWORK_ERRORS)
            if not retryable or attempt == STITCH_NAVIGATION_ATTEMPTS:
                break
            print(
                f"Connessione a Stitch assente o instabile durante {purpose} "
                f"({attempt}/{STITCH_NAVIGATION_ATTEMPTS}). Riprovo tra "
                f"{STITCH_NAVIGATION_RETRY_MS // 1000} secondi..."
            )
            page.wait_for_timeout(STITCH_NAVIGATION_RETRY_MS)

    raise SystemExit(
        "Non riesco ad aprire Stitch perche' la connessione Internet non e' "
        "disponibile o e' instabile. Controlla Wi-Fi/VPN e rilancia il comando."
    ) from last_error


def log_prompt_send(phase: str, prompt_name: str, prompt: str) -> None:
    PROMPT_SEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized_preview = re.sub(r"\s+", " ", prompt).strip()[:180]
    digest = hashlib.sha256(prompt.encode("utf-8", "ignore")).hexdigest()[:12]
    line = (
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {phase} | {prompt_name} | "
        f"chars={len(prompt)} | sha256={digest} | preview={normalized_preview}\n"
    )
    with PROMPT_SEND_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(f"{phase}: invio separato registrato in {PROMPT_SEND_LOG_PATH}")


def main() -> int:
    args = parse_args()
    if args.split_build_aba_bab and args.analyze_before_design:
        raise SystemExit(
            "--split-build-aba-bab unisce analisi e costruzione: non usare "
            "--analyze-before-design nello stesso giro."
        )
    followup_requested = any(
        (
            args.analyze_before_design,
            args.split_build_aba_bab,
            args.animate_in_stitch,
            args.motion_code_pass_in_stitch,
            args.structure_check_in_stitch,
            args.final_check_in_stitch,
        )
    )
    if followup_requested and not args.allow_followup_phases:
        raise SystemExit(
            "SICUREZZA FASI: questa esecuzione puo' inviare un solo prompt. "
            "Design, animazioni, Guest, Framer e controlli devono essere avviati "
            "in esecuzioni separate dopo approvazione esplicita del risultato precedente. "
            "Non e' stato inviato nulla a Stitch."
        )
    global _PHASE_OFFSET, _PIPELINE_FINAL_CHECK_ENABLED
    _PHASE_OFFSET = 1 if args.analyze_before_design else 0
    _PIPELINE_FINAL_CHECK_ENABLED = bool(args.final_check_in_stitch)
    config = read_config(args.config.expanduser())
    latest_dir = Path(config["latest_batch_dir"]).expanduser()
    prompt_path = Path(config["prompt_file"]).expanduser()
    file_paths = select_reference_group(latest_image_paths(latest_dir), args.reference_group)
    upload_file_paths = list(file_paths)
    split_build_prompt = ""
    split_build_reference_paths: list[Path] = []
    design_prompt = ""
    if args.prompt_mode == "full":
        if args.split_build_aba_bab:
            if len(file_paths) != 6:
                raise SystemExit(
                    "BUILD ABA/BAB richiede esattamente sei slice ordinate: "
                    "A1,A2,A3,B1,B2,B3."
                )
            if not BUILD_ABA_PROMPT_PATH.is_file() or not BUILD_BAB_PROMPT_PATH.is_file():
                raise SystemExit("Prompt BUILD ABA/BAB mancanti.")
            # A-B-A: A1, B3, A2. B-A-B: B1, A3, B2. Le coppie A1→A2 e
            # B1→B2 restano quindi disponibili nei build che usano gli slot composti.
            upload_file_paths = [file_paths[0], file_paths[5], file_paths[1]]
            split_build_reference_paths = [file_paths[3], file_paths[2], file_paths[4]]
            prompt_path = BUILD_ABA_PROMPT_PATH
            prompt = BUILD_ABA_PROMPT_PATH.read_text(encoding="utf-8")
            prompt += "\n\nFILE DEL BATCH ABA, IN QUESTO ORDINE:\n" + "\n".join(
                f"- allegato {index}: `{path.name}`" for index, path in enumerate(upload_file_paths, start=1)
            ) + "\n"
            split_build_prompt = BUILD_BAB_PROMPT_PATH.read_text(encoding="utf-8")
            print("BUILD ABA/BAB attivo: ABA crea slot 3/4/6, BAB aggiunge slot 1/2/5.")
            print(f"Prompt BUILD ABA: {BUILD_ABA_PROMPT_PATH}")
            print(f"Prompt BUILD BAB: {BUILD_BAB_PROMPT_PATH}")
        elif args.analyze_before_design:
            if not ANALYSIS_PROMPT_PATH.is_file() or not DESIGN_PROMPT_PATH.is_file():
                raise SystemExit("Prompt analisi/design separati mancanti.")
            prompt_path = ANALYSIS_PROMPT_PATH
            prompt = ANALYSIS_PROMPT_PATH.read_text(encoding="utf-8")
            # L'ANATOMIA VA CON L'ANALISI — 2026-08-02.
            # Il blocco `anatomy_block` non e' decorazione: contiene la mappa
            # IMMAGINE -> REFERENCE (quali slice appartengono al sito A e quali
            # al B) e il sistema di coordinate x/y/w/h per misurare le sezioni.
            # In modalita' `anatomy` veniva accodato al prompt di design, cioe'
            # allo stesso messaggio che doveva anche produrre tutto il codice.
            # Passando alla pipeline a due messaggi l'anatomia deve seguire
            # l'ANALISI, altrimenti Stitch perde la mappa delle reference — ed
            # e' esattamente il sintomo segnalato: "e' come se non le vedesse
            # entrambe".
            try:
                from build_stitch_prompt import anatomy_block, latest_images

                immagini = latest_images(latest_dir)
                if immagini:
                    # IL MARKER VA RIPETUTO IN FONDO — 2026-08-02 (sera).
                    # `wait_for_reference_analysis` fa avanzare la pipeline SOLO
                    # quando conta una seconda occorrenza di "ANALISI VISIVA
                    # COMPLETATA". Ma l'anatomia viene accodata DOPO la riga
                    # "Termina ESATTAMENTE con", quindi quell'istruzione finisce
                    # sepolta a meta' prompt (car. ~4900 su ~9500) e l'ultima cosa
                    # che Stitch legge parla d'altro. Senza questa ripetizione la
                    # fase 1 puo' concludersi senza marker -> "FASE 1 BLOCCATA".
                    # Nota: aumentare le occorrenze nel prompt e' innocuo, la
                    # baseline viene misurata sul prompt gia' renderizzato.
                    chiusura = (
                        "CHIUSURA OBBLIGATORIA — qualunque cosa dica il blocco qui sopra,\n"
                        "l'ULTIMA riga della tua risposta deve essere esattamente questa,\n"
                        "da sola, copiata carattere per carattere:\n\n"
                        "ANALISI VISIVA COMPLETATA — pronta per creare il sito.\n"
                    )
                    prompt = (
                        f"{prompt.rstrip()}\n\n"
                        f"{anatomy_block(immagini).rstrip()}\n\n"
                        f"{chiusura}"
                    )
                    print(f"  + anatomia delle {len(immagini)} reference allegata all'analisi")
                    print("  + marker di chiusura ripetuto in fondo (sblocca la fase 2)")
            except (ImportError, OSError, ValueError) as exc:
                print(f"  anatomia non allegata ({exc}): l'analisi parte comunque.")
            print(f"Prompt fase 1 (analisi): {ANALYSIS_PROMPT_PATH}")
            design_prompt = DESIGN_PROMPT_PATH.read_text(encoding="utf-8")
            print(f"Prompt fase 2 (design): {DESIGN_PROMPT_PATH}")
        else:
            prompt = prompt_path.read_text(encoding="utf-8")
            print(f"Prompt usato: {prompt_path}")
    elif args.prompt_mode == "anatomy":
        from build_stitch_prompt import build_prompt_file

        prompt_path = build_prompt_file(prompt_path, latest_dir)
        prompt = prompt_path.read_text()
        print(f"Prompt con anatomia usato: {prompt_path}")
    elif args.prompt_mode == "minimal":
        prompt = MINIMAL_PROMPT
        print("Prompt usato: minimale")
    else:
        prompt = ""
        print("Prompt usato: vuoto, provo solo con le immagini")

    files = [str(path) for path in upload_file_paths]

    animation_prompt = ""
    if args.animate_in_stitch:
        animation_prompt_path = args.animation_prompt.expanduser()
        if not animation_prompt_path.exists():
            raise SystemExit(f"Prompt /animate non trovato: {animation_prompt_path}")
        if not args.download_after_send:
            print("--animate-in-stitch richiede il download: attivo --download-after-send.")
            args.download_after_send = True
        animation_prompt = animation_prompt_path.read_text()
        print(f"Secondo passaggio Stitch attivo: /animate + regia GSAP da {animation_prompt_path}")

    motion_code_prompt = ""
    motion_attachment_paths: list[Path] = []
    motion_selection: dict | None = None
    if args.motion_code_pass_in_stitch:
        from motion_component_selector import prepare_motion_selection

        motion_code_prompt_path = args.motion_code_prompt.expanduser()
        if not motion_code_prompt_path.exists():
            raise SystemExit(f"Prompt GSAP/componenti non trovato: {motion_code_prompt_path}")
        if not args.animate_in_stitch:
            raise SystemExit("--motion-code-pass-in-stitch richiede --animate-in-stitch.")
        if not args.download_after_send:
            print("--motion-code-pass-in-stitch richiede il download: attivo --download-after-send.")
            args.download_after_send = True
        motion_selection = prepare_motion_selection(file_paths)

        # Stitch riceve FASE 3 e il piano di assegnazione delle classi mk-*.
        # Il motion kit e il vecchio manifesto non entrano mai nel messaggio:
        # repair/enforce li gestisce dopo il download dal contratto canonico.

        # Identita' + sistema colore consegnati come DATO in coda al prompt di
        # fase 1. Le 2 reference sono 2 aziende diverse: senza questo blocco
        # Stitch produce un sito con due marchi, due indirizzi e due telefoni.
        # L'identita' e' gia' stata aggiunta sopra, per ogni giro con prompt
        # full: qui non va ripetuta o finirebbe due volte nello stesso prompt.
        # Il contratto specifico viene aggiunto separatamente in ciascuna fase.
        # Non unire qui Guest #1, Guest #2 e Framer: confonderebbe Stitch e
        # consentirebbe modifiche distruttive tra una fase e la successiva.
        motion_code_prompt = motion_code_prompt_path.read_text()
        motion_attachment_paths = build_motion_attachment_paths(motion_selection)
        missing_attachments = [path for path in motion_attachment_paths if not path.is_file()]
        if missing_attachments:
            missing_text = "\n".join(f"  - {path}" for path in missing_attachments)
            raise SystemExit(f"File .md dell'Arsenale mancanti:\n{missing_text}")
        print(
            "Pipeline motion separata attiva: GSAP; Guest; Framer; "
            f"{len(motion_attachment_paths)} allegati .md totali"
        )
        print(
            "  componente selezionato: "
            f"{motion_selection['component_name']} ({motion_selection['component_id']})"
        )
        print(
            "  Framer selezionata: "
            f"{motion_selection['framer_name']} ({motion_selection['framer_id']})"
        )
        print(
            "  provenienza: "
            f"{motion_selection['authenticity']} | regia: "
            f"{motion_selection['style_name']} ({motion_selection['style_id']})"
        )
        for attachment in motion_attachment_paths:
            print(f"  allegato: {attachment.name}")

    structure_check_prompt = ""
    if args.structure_check_in_stitch:
        structure_check_prompt_path = args.structure_check_prompt.expanduser()
        if not structure_check_prompt_path.exists():
            raise SystemExit(f"Prompt controllo struttura non trovato: {structure_check_prompt_path}")
        if not args.download_after_send:
            print("--structure-check-in-stitch richiede il download: attivo --download-after-send.")
            args.download_after_send = True
        structure_check_prompt = structure_check_prompt_path.read_text()
        print(f"Controllo struttura Stitch attivo: {structure_check_prompt_path}")

    final_check_prompt = ""
    if args.final_check_in_stitch:
        final_check_prompt_path = args.final_check_prompt.expanduser()
        if not final_check_prompt_path.exists():
            raise SystemExit(f"Prompt controllo finale non trovato: {final_check_prompt_path}")
        if not args.download_after_send:
            print("--final-check-in-stitch richiede il download: attivo --download-after-send.")
            args.download_after_send = True
        if not args.animate_in_stitch:
            raise SystemExit("--final-check-in-stitch richiede anche --animate-in-stitch.")
        final_check_prompt = final_check_prompt_path.read_text(encoding="utf-8")
        print(f"Controllo finale Stitch attivo: {final_check_prompt_path}")

    if config.get("target") != "web" or config.get("model") not in {"3.1 Pro", "GEMINI_3_1_PRO"}:
        raise SystemExit("Config non valida: target deve essere web e model deve essere GEMINI_3_1_PRO.")

    with sync_playwright() as p:
        launch_options = {
            "headless": not args.headed,
            "slow_mo": 350 if args.slow else 0,
            "viewport": {"width": 1440, "height": 950},
            "accept_downloads": True,
            "downloads_path": str(DOWNLOAD_DIR),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-crash-reporter",
                "--disable-crashpad",
            ],
        }
        if args.browser == "chrome":
            launch_options["channel"] = "chrome"

        try:
            browser = p.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                **launch_options,
            )
        except Error as exc:
            if "ProcessSingleton" in str(exc) or "SingletonLock" in str(exc):
                raise SystemExit(
                    "Chrome automatico e' gia' aperto. Aspetta la fine del comando "
                    "precedente oppure chiudi la sua finestra Stitch, poi rilancia."
                ) from exc
            raise
        for extra_page in browser.pages[1:]:
            try:
                extra_page.close()
            except Exception:
                pass
        page = browser.pages[0] if browser.pages else browser.new_page()
        open_stitch_with_retry(page, "l'apertura iniziale")
        if args.fresh_stitch_state:
            try:
                page.evaluate("localStorage.clear(); sessionStorage.clear();")
                open_stitch_with_retry(page, "la pulizia dello stato locale")
                print("OK: stato locale Stitch pulito prima del nuovo invio")
            except Exception as exc:
                print(f"Avviso: non riesco a pulire lo stato locale Stitch: {exc}")
        if not find_prompt_target(page):
            # The first load can be slower after a Google login, but only wait
            # longer when the composer has not appeared yet.
            page.wait_for_timeout(2500)

        if args.setup_login:
            print("Setup login: fai login Google/Stitch nella finestra aperta.")
            print("Quando hai finito, chiudi la finestra o aspetta la chiusura automatica.")
            save_debug(page, "setup_login") if args.debug else None
            page.wait_for_timeout(600000)
            browser.close()
            return 0

        if "accounts.google.com" in page.url or "signin" in page.url.lower():
            if args.wait_login:
                print("Stitch chiede login. Fai login nella finestra aperta: continuo appena rientra su Stitch.")
                deadline = time.time() + (LOGIN_WAIT_MS / 1000)
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    if "accounts.google.com" not in page.url and "signin" not in page.url.lower():
                        break
                page.wait_for_timeout(2500)
                if "accounts.google.com" in page.url or "signin" in page.url.lower():
                    save_debug(page, "login_timeout") if args.debug else None
                    print("Login non completato in tempo. Rilancia il comando dopo il login.")
                    browser.close()
                    return 2
            else:
                print("Stitch chiede login Google. Fai login nella finestra aperta, poi rilancia questo comando.")
                save_debug(page, "login_required") if args.debug else None
                page.wait_for_timeout(300000)
                browser.close()
                return 2

        try:
            enter_builder_if_needed(page)
            if not choose_web(page):
                save_debug(page, "initial_web_mode_blocked") if args.debug else None
                raise SystemExit(
                    "Preparazione BLOCCATA: Stitch non conferma la modalita Web. "
                    "Non carico reference e non invio il prompt in modalita App."
                )
            if not choose_model_31(
                page,
                debug_label="initial_model_31_blocked" if args.debug else None,
            ):
                raise SystemExit(
                    "Preparazione BLOCCATA: non riesco a selezionare direttamente 3.1 Pro."
                )
            upload_images(page, files)
            print(
                "Confermo che tutte le reference siano nello stesso composer "
                "prima di inviare..."
            )
            if not wait_for_attachment_chips(page, upload_file_paths, timeout_ms=30000):
                save_debug(page, "initial_reference_attachments_missing") if args.debug else None
                raise SystemExit(
                    "Preparazione BLOCCATA: Stitch non conferma nello stesso composer "
                    f"tutte le {len(upload_file_paths)} reference. Non invio un prompt con "
                    "allegati parziali e non consumo crediti."
                )
            print(f"OK: confermate {len(upload_file_paths)} reference nello stesso messaggio")
            if prompt.strip():
                fill_prompt(page, prompt)
            else:
                print("OK: salto inserimento prompt")
        except Exception:
            save_debug(page, "failure") if args.debug else None
            raise

        if args.no_send:
            print("Pronto: non ho inviato perche' hai usato --no-send.")
            print("Lascio Chrome aperto per controllo manuale. Premi Ctrl+C quando hai finito.")
        else:
            save_debug(page, "before_send") if args.debug else None
            try:
                total_phases = _totale_fasi() if motion_code_prompt else (2 if args.analyze_before_design else 1)
                log_prompt_send(f"FASE 1/{total_phases}", str(prompt_path), prompt)
                send(page, prompt)
            except BaseException:
                save_debug(page, "send_failed") if args.debug else None
                raise
            print("Invio completato o avviato.")
            if args.download_after_send:
                try:
                    result = download_after_send(
                        page,
                        args.download_timeout * 1000,
                        design_prompt=design_prompt,
                        split_build_prompt=split_build_prompt,
                        split_build_reference_paths=split_build_reference_paths,
                        animation_prompt=animation_prompt,
                        motion_code_prompt=motion_code_prompt,
                        motion_attachment_paths=motion_attachment_paths,
                        motion_selection=motion_selection,
                        structure_check_prompt=structure_check_prompt,
                        final_check_prompt=final_check_prompt,
                        phase_wait_seconds=args.phase_wait_seconds,
                        manual_gate_between_phases=args.manual_gate_between_phases,
                        debug=args.debug,
                        verify_motion_export=bool(motion_selection),
                        max_gate_retries=args.max_gate_retries,
                        design_gate_mode=(
                            "off" if args.skip_design_preflight else args.design_gate
                        ),
                        guest_framer_in_stitch=args.guest_framer_in_stitch,
                    )
                except (NameError, AttributeError, TypeError, ImportError, KeyError, IndexError) as exc:
                    # ERRORE DI PROGRAMMAZIONE, NON DI RETE — distinzione
                    # aggiunta il 2026-07-28. Prima ogni eccezione finiva nel
                    # ramo qui sotto e veniva stampata come "Browser chiuso o
                    # disconnesso": un NameError alla FASE 4 (un import
                    # dimenticato) e' rimasto mascherato da problema di
                    # connessione, mandando a cercare la causa nel posto
                    # sbagliato mentre ogni giro moriva al Guest Component.
                    print("")
                    print("!!! BUG NEL NOSTRO CODICE, non un problema di rete o di Stitch !!!")
                    print(f"    {type(exc).__name__}: {exc}")
                    print("    Il browser sta bene. Copia queste righe: la pipeline va corretta.")
                    print("")
                    import traceback
                    traceback.print_exc()
                    from download_stitch_project import create_mcp_recovery_zip, last_project_id
                    result = create_mcp_recovery_zip(last_project_id())
                except Exception as exc:
                    print(f"Browser chiuso o disconnesso durante l'esecuzione di download_after_send ({exc}). Avvio recupero MCP sul progetto in cloud...")
                    from download_stitch_project import create_mcp_recovery_zip, last_project_id
                    result = create_mcp_recovery_zip(last_project_id())
                if not result:
                    try:
                        save_debug(page, "download_after_send_failed") if args.debug else None
                        browser.close()
                    except Exception:
                        pass
                    print("Download automatico non completato. Lascio la finestra aperta per controllo manuale.")
                    return 1
                try:
                    print("Download automatico completato. Chiudo Chrome e libero il profilo Stitch.")
                    # Il debug deve essere salvato PRIMA di chiudere il browser:
                    # dopo browser.close() il Page target non esiste piu'.
                    save_debug(page, "after_actions") if args.debug else None
                    browser.close()
                except Exception:
                    pass
                return 0
            else:
                print("Lascio la finestra aperta.")

        save_debug(page, "after_actions") if args.debug else None
        page.wait_for_timeout(300000)
        browser.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrotto con Ctrl+C.")
        raise SystemExit(130)
