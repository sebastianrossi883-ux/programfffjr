#!/usr/bin/env python3
"""Static and browser QA for a downloaded Stitch motion ZIP."""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import re
import shutil
import socketserver
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_SELECTION = Path("/Users/utente/Downloads/reference_splitter/CURRENT_MOTION_SELECTION.json")
DEBUG_ROOT = Path("/Users/utente/Downloads/reference_splitter/debug/motion_qa")
# Derive the known component ids from the selector's own catalog so this set can
# never go stale (it previously missed "reveal-slideshow", making every
# reveal-slideshow site fail the gate). Fall back to the static list if the
# selector cannot be imported.
try:
    from motion_component_selector import CATALOG as _MOTION_CATALOG

    KNOWN_COMPONENT_IDS = {entry["id"] for entry in _MOTION_CATALOG}
except Exception:
    KNOWN_COMPONENT_IDS = {
        "codrops-scroll-carousel",
        "reveal-slideshow",
        "onscroll-filter",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica componente motion reale nello ZIP Stitch.")
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--static-only", action="store_true")
    return parser.parse_args()


def load_selection(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Selezione motion non valida: {path}: {exc}") from exc
    required = {
        "component_id",
        "component_name",
        "function_name",
        "dom_value",
        "required_tokens",
        "authenticity",
        "source_hashes",
        "style_id",
        "manifest_version",
        "framer_id",
        "framer_name",
        "framer_function_name",
        "framer_dom_value",
        "framer_required_tokens",
        "framer_source_hash",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise SystemExit(f"Selezione motion incompleta: mancano {', '.join(missing)}")
    return value


def html_entries(archive: zipfile.ZipFile) -> list[str]:
    return [
        name
        for name in archive.namelist()
        if not name.endswith("/") and Path(name).suffix.lower() in {".html", ".htm"}
    ]


def select_candidate(archive: zipfile.ZipFile, selection: dict) -> tuple[str, str]:
    marker = f'data-stitch-native-component="{selection["component_id"]}"'
    marker2 = (f'data-stitch-native-component="{selection["component2_id"]}"'
               if selection.get("component2_id") else None)
    framer_marker = f'data-stitch-framer-interaction="{selection["framer_id"]}"'
    candidates: list[tuple[int, str, str]] = []
    for name in html_entries(archive):
        text = archive.read(name).decode("utf-8", "ignore")
        score = 0
        score += 100 if marker in text else 0
        score += 100 if marker2 and marker2 in text else 0
        score += 100 if framer_marker in text else 0
        score += 20 if selection["function_name"] in text else 0
        score += 20 if selection.get("component2_function_name", "") and selection["component2_function_name"] in text else 0
        score += 20 if selection["framer_function_name"] in text else 0
        score += 10 if "ScrollTrigger" in text else 0
        score += 10 if re.search(r"gsap\.(?:timeline|to|from|fromTo|set)\s*\(", text) else 0
        score += 5 if "code-animated" in name.lower() else 0
        candidates.append((score, name, text))
    if not candidates:
        raise SystemExit("ZIP senza file HTML.")
    _, name, text = max(candidates, key=lambda item: item[0])
    return name, text


def _component_invocations(html: str, function_name: str) -> list[int]:
    """Return calls to the selected mount function, excluding its declaration."""
    positions: list[int] = []
    for match in re.finditer(rf"\b{re.escape(function_name)}\s*\(", html):
        prefix = html[max(0, match.start() - 80):match.start()]
        if re.search(r"function\s+$", prefix):
            continue
        positions.append(match.start())
    return positions


def _balanced_call_end(source: str, open_paren: int) -> int:
    """Find the closing parenthesis of a JS call while respecting string literals."""
    depth = 0
    quote_char = ""
    escaped = False
    for index in range(open_paren, len(source)):
        char = source[index]
        if quote_char:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = ""
            continue
        if char in {"'", '"', "`"}:
            quote_char = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _is_scroll_gated_invocation(html: str, position: int) -> bool:
    """Accept only calls physically inside a ScrollTrigger/IntersectionObserver gate."""
    gate_specs = (
        (r"ScrollTrigger\.create\s*\(", ("onEnter",)),
        (r"new\s+IntersectionObserver\s*\(", ("isIntersecting", "intersectionRatio")),
    )
    for pattern, required_tokens in gate_specs:
        for gate in re.finditer(pattern, html):
            open_paren = html.find("(", gate.start())
            close_paren = _balanced_call_end(html, open_paren)
            if close_paren < 0 or not (open_paren < position < close_paren):
                continue
            gate_source = html[gate.start():close_paren]
            if any(token in gate_source for token in required_tokens):
                return True
    return False


def static_checks(html: str, selection: dict) -> list[str]:
    errors: list[str] = []
    component_id = selection["component_id"]
    function_name = selection["function_name"]
    marker = f'data-stitch-native-component="{component_id}"'
    framer_id = selection["framer_id"]
    framer_function = selection["framer_function_name"]
    framer_marker = f'data-stitch-framer-interaction="{framer_id}"'
    transparent_nav_marker = 'data-stitch-transparent-nav="true"'
    top_only_nav_marker = 'data-scroll-visibility="top-only"'

    if html.count(marker) != 1:
        errors.append(f"attesa una sola root {marker}; trovate {html.count(marker)}")
    if f'data-motion-component="{selection["dom_value"]}"' not in html:
        errors.append("manca il data-motion-component richiesto sul DOM reale")
    if 'data-motion-activation="scroll"' not in html and "data-motion-activation='scroll'" not in html:
        errors.append("manca data-motion-activation=scroll sulla root Guest")
    if 'data-motion-mounted="false"' not in html and "data-motion-mounted='false'" not in html:
        errors.append("manca lo stato iniziale data-motion-mounted=false sulla root Guest")
    if transparent_nav_marker not in html and transparent_nav_marker.replace('"', "'") not in html:
        errors.append("manca data-stitch-transparent-nav=true sulla root del menu")
    if top_only_nav_marker not in html and top_only_nav_marker.replace('"', "'") not in html:
        errors.append("manca data-scroll-visibility=top-only sulla root del menu")
    if len(re.findall(r"\binitTransparentScrollNav\s*\(", html)) < 2:
        errors.append("initTransparentScrollNav non risulta sia definita sia invocata")

    nav_match = re.search(
        r"<header\b[^>]*data-stitch-transparent-nav=['\"]true['\"][^>]*>.*?</header>",
        html,
        re.I | re.S,
    )
    if nav_match:
        nav_html = nav_match.group(0)
        invalid_links = re.findall(
            r"<a\b[^>]*href=['\"](?:#|\s*|javascript:[^'\"]*)['\"]",
            nav_html,
            re.I,
        )
        if invalid_links:
            errors.append(
                f"menu con {len(invalid_links)} link senza destinazione reale: "
                "usa anchor verso id di sezione esistenti"
            )
        for anchor in re.finditer(r"<a\b[^>]*href=['\"]#([^'\"]+)['\"]", nav_html, re.I):
            target = anchor.group(1)
            if not re.search(rf"\bid=['\"]{re.escape(target)}['\"]", html, re.I):
                errors.append(f"link menu verso id inesistente: #{target}")

        if re.search(
            r"<a\b[^>]*class=['\"][^'\"]*\b(?:border|rounded|shadow|backdrop-blur)(?:-|\b)",
            nav_html,
            re.I,
        ):
            errors.append(
                "menu non solo-testo: trovati bordi, pillole, ombre o blur sulle voci"
            )
        nav_without_mobile_button = re.sub(
            r"<button\b[^>]*>.*?</button>", "", nav_html, flags=re.I | re.S
        )
        if re.search(r"material-symbols|\bw-px\b|divider", nav_without_mobile_button, re.I):
            errors.append(
                "menu non solo-testo: trovati icone o divisori fuori dall'hamburger mobile"
            )

        mobile_button = re.search(
            r"<button\b(?=[^>]*(?:md:hidden|aria-label=['\"][^'\"]*menu))[^>]*>.*?</button>",
            nav_html,
            re.I | re.S,
        )
        if mobile_button:
            button_tag = mobile_button.group(0).split(">", 1)[0] + ">"
            has_inline_handler = bool(re.search(r"\bonclick\s*=", button_tag, re.I))
            button_id = re.search(r"\bid=['\"]([^'\"]+)['\"]", button_tag, re.I)
            has_bound_listener = bool(
                button_id
                and re.search(
                    rf"(?:getElementById\(['\"]{re.escape(button_id.group(1))}['\"]\)|"
                    rf"querySelector\([^)]*#{re.escape(button_id.group(1))}[^)]*\))"
                    r"[\s\S]{0,500}?addEventListener\(['\"]click['\"]",
                    html,
                    re.I,
                )
            )
            if not has_inline_handler and not has_bound_listener:
                errors.append("hamburger mobile presente ma privo di una logica click verificabile")
    if not re.search(
        rf"window\.__STITCH_SELECTED_COMPONENT__\s*=\s*['\"]{re.escape(component_id)}['\"]",
        html,
    ):
        errors.append("manca window.__STITCH_SELECTED_COMPONENT__ con l'ID selezionato")
    if html.count(framer_marker) != 1:
        errors.append(f"attesa una sola root {framer_marker}; trovate {html.count(framer_marker)}")
    if f'data-motion-framer="{selection["framer_dom_value"]}"' not in html:
        errors.append("manca il data-motion-framer richiesto sulla Framer reale")
    if not re.search(
        rf"window\.__STITCH_SELECTED_FRAMER__\s*=\s*['\"]{re.escape(framer_id)}['\"]",
        html,
    ):
        errors.append("manca window.__STITCH_SELECTED_FRAMER__ con l'ID selezionato")
    if not re.search(
        rf"window\.__STITCH_MOTION_MANIFEST__\s*=\s*['\"]{re.escape(selection['manifest_version'])}['\"]",
        html,
    ):
        errors.append("manca il marker del manifesto arsenal-v7.1")
    if not re.search(
        rf"window\.__STITCH_MOTION_STYLE__\s*=\s*['\"]{re.escape(selection['style_id'])}['\"]",
        html,
    ):
        errors.append("manca window.__STITCH_MOTION_STYLE__ con la regia selezionata")
    if "window.__STITCH_GUEST_SOURCE_SHA256__" not in html:
        errors.append("manca la dichiarazione SHA256 dei sorgenti Guest")
    else:
        for source_hash in selection["source_hashes"].values():
            if source_hash not in html:
                errors.append(f"manca hash Guest originale: {source_hash}")
    if not re.search(
        rf"window\.__STITCH_FRAMER_SOURCE_SHA256__\s*=\s*['\"]{re.escape(selection['framer_source_hash'])}['\"]",
        html,
    ):
        errors.append("manca o non coincide lo SHA256 della Framer originale")
    for token in selection["required_tokens"]:
        if token not in html:
            errors.append(f"manca token del sorgente reale: {token}")
    for token in selection["framer_required_tokens"]:
        if token not in html:
            errors.append(f"manca token Framer reale: {token}")

    # --- GUEST COMPONENT #2: stesse verifiche 1:1 del primo -------------------
    component2_id = selection.get("component2_id")
    if component2_id:
        marker2 = f'data-stitch-native-component="{component2_id}"'
        if html.count(marker2) != 1:
            errors.append(
                f"attesa una sola root {marker2}; trovate {html.count(marker2)}"
            )
        dom2 = selection.get("component2_dom_value")
        if dom2 and f'data-motion-component="{dom2}"' not in html:
            errors.append(f"manca il data-motion-component del Guest #2: {dom2}")
        for token in selection.get("component2_required_tokens", []):
            if token not in html:
                errors.append(f"manca token del sorgente reale Guest #2: {token}")
        function2 = selection.get("component2_function_name")
        if function2 and len(re.findall(rf"\b{re.escape(function2)}\s*\(", html)) < 2:
            errors.append(f"{function2} (Guest #2) non risulta sia definita sia invocata")
        if not re.search(
            rf"window\.__STITCH_SELECTED_COMPONENT_2__\s*=\s*['\"]{re.escape(component2_id)}['\"]",
            html,
        ):
            errors.append("manca window.__STITCH_SELECTED_COMPONENT_2__ con l'ID selezionato")
        if "window.__STITCH_GUEST_2_SOURCE_SHA256__" not in html:
            errors.append("manca la dichiarazione SHA256 dei sorgenti Guest #2")
        else:
            for source_hash in selection.get("component2_source_hashes", {}).values():
                if source_hash not in html:
                    errors.append(f"manca hash Guest #2 originale: {source_hash}")
        if component2_id == component_id:
            errors.append("i due Guest Component devono essere diversi tra loro")

    if len(re.findall(rf"\b{re.escape(function_name)}\s*\(", html)) < 2:
        errors.append(f"{function_name} non risulta sia definita sia invocata")
    if html.count(framer_function) < 2:
        errors.append(f"{framer_function} non risulta sia definita sia montata/invocata")
    if not re.search(r"<script[^>]*type=['\"]module['\"]", html, re.I):
        errors.append("manca <script type=module> per il componente Framer/React")
    if not re.search(r"gsap\.(?:timeline|to|from|fromTo|set)\s*\(", html):
        errors.append("manca una chiamata GSAP reale")

    # LE LIBRERIE SONO DAVVERO CARICATE?
    # Il 2026-07-26 e' uscito un sito che chiamava gsap.from() ovunque ma non
    # caricava GSAP: ogni chiamata lanciava ReferenceError e la pagina era
    # immobile. Il gate non se n'era accorto perche' controllava solo i
    # DUPLICATI (>1) e mai lo zero. Questo e' il controllo che mancava.
    if not re.search(
        r"<script\b[^>]*src=['\"][^'\"]*gsap[^'\"]*\.js", html, re.I
    ) and not re.search(r"['\"]gsap['\"]\s*:\s*['\"]", html, re.I):
        errors.append(
            "GSAP non e' caricato da nessuna parte: nessun <script src=...gsap...js> "
            "e nessun importmap. Ogni gsap.from()/to() lancia ReferenceError e il "
            "sito resta immobile."
        )
    if re.search(r"\bnew\s+Lenis\s*\(", html) and not re.search(
        r"<script\b[^>]*src=['\"][^'\"]*lenis[^'\"]*\.js", html, re.I
    ):
        errors.append("il sito usa `new Lenis()` ma non carica la libreria Lenis")

    # PLUGIN BONUS CHIESTI A UNA VERSIONE CHE NON LI HA.
    # I plugin ex-Club (SplitText, MorphSVG, DrawSVG, ScrollSmoother, Inertia)
    # sono arrivati sul CDN pubblico solo con GSAP 3.13. Su 3.12.x l'URL
    # risponde 404: lo <script> non carica, il simbolo resta undefined e la
    # prima `registerPlugin(...)` che lo nomina lancia ReferenceError,
    # spegnendo TUTTO il codice che segue. Bug reale del 2026-07-27: una cifra
    # sbagliata nell'URL ha reso invisibili l'hero e tutti i titoli.
    BONUS_PLUGINS = ("SplitText", "MorphSVGPlugin", "DrawSVGPlugin",
                     "ScrollSmoother", "InertiaPlugin")
    for match in re.finditer(
        r"cdnjs\.cloudflare\.com/ajax/libs/gsap/(\d+)\.(\d+)[.\d]*/([A-Za-z]+)\.min\.js",
        html,
    ):
        major, minor, plugin_file = match.group(1), int(match.group(2)), match.group(3)
        if major == "3" and minor < 13 and plugin_file in BONUS_PLUGINS:
            errors.append(
                f"{plugin_file}.min.js chiesto a GSAP {major}.{minor}.x: quell'URL "
                f"risponde 404 (i plugin bonus sono sul CDN pubblico solo da 3.13.0). "
                f"Lo script non carica, `{plugin_file}` resta undefined e la prima "
                f"registerPlugin() che lo nomina uccide tutto il JS che segue."
            )

    # CONTENUTO NASCOSTO DAL CSS IN ATTESA DEL JAVASCRIPT.
    # Se una classe di contenuto e' messa a opacity:0 / visibility:hidden in un
    # <style> e solo il JS la riporta visibile, allora QUALUNQUE errore JS
    # svuota la pagina. Il kit usa gsap.from(), che degrada bene: se GSAP non
    # c'e' il testo resta visibile. Stitch aggiunge di sua iniziativa un
    # "anti-FOUC" in CSS che annulla questa protezione.
    for style_block in re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.I | re.S):
        style_block = re.sub(r"/\*.*?\*/", " ", style_block, flags=re.S)
        for rule in re.finditer(
            r"([^{}]*?)\{([^{}]*?)\}", style_block, re.S
        ):
            selector, body = rule.group(1).strip(), rule.group(2)
            if not re.search(r"opacity\s*:\s*0(?:\.0*)?\s*[;!}]|visibility\s*:\s*hidden", body):
                continue
            if not re.search(r"\.(?:mk-|reveal|split|line|fade|anim)", selector, re.I):
                continue
            errors.append(
                f"contenuto nascosto dal CSS in attesa del JS: `{selector} "
                f"{{ {body.strip()[:60]} }}`. Se una libreria non carica, quel "
                f"testo resta invisibile per sempre. Nascondi dal JavaScript "
                f"(gsap.from) e mai da un <style>."
            )
            break

    # PLUGIN FINTI: stub vuoti al posto della libreria vera.
    # Stitch ha scritto `window.Flip = window.Flip || {};` dichiarandolo un
    # "simulated block for brevity": l'oggetto esiste ma e' vuoto, quindi
    # `Flip.getState` non esiste e il componente muore in silenzio, senza
    # errori visibili in console.
    for plugin in ("Flip", "SplitText", "ScrollSmoother", "ScrollTrigger", "Draggable"):
        if re.search(
            rf"window\.{plugin}\s*=\s*window\.{plugin}\s*\|\|\s*\{{\s*\}}", html
        ) or re.search(rf"window\.{plugin}\s*=\s*\{{\s*\}}", html):
            errors.append(
                f"plugin FINTO: `window.{plugin} = {{}}` e' uno stub vuoto, non la "
                f"libreria. Va caricato dal CDN, i plugin GSAP sono gratuiti."
            )
    # QUANTO DELLE REFERENCE E' FINITO DAVVERO NEL SITO.
    # Non e' una stima: `REFERENCE_TEXT_CACHE.json` contiene il testo letto
    # dalle immagini con l'OCR. Qui contiamo quante di quelle frasi compaiono
    # nell'HTML consegnato. E' l'unico controllo che misura la FEDELTA' invece
    # della forma, e il 2026-07-27 sarebbe stato l'unico a vedere il sito
    # "corretto ma vuoto": 4 immagini e sezioni da 105 caratteri.
    try:
        cache = json.loads(
            (Path(__file__).parent / "generated_motion" / "REFERENCE_TEXT_CACHE.json")
            .read_text(encoding="utf-8")
        )
        frasi = [
            riga["text"].strip()
            for gruppo in cache.get("groups", {}).values()
            for riga in gruppo
            if len(riga.get("text", "").strip()) >= 25
        ]
        if frasi:
            testo_sito = re.sub(r"<[^>]+>", " ", html)
            testo_sito = re.sub(r"\s+", " ", testo_sito).lower()
            usate = [f for f in frasi if f.lower()[:40] in testo_sito]
            quota = len(usate) / len(frasi)
            print(
                f"  Fedelta' ai testi delle reference: {len(usate)}/{len(frasi)} "
                f"frasi lunghe presenti ({quota:.0%})."
            )
            if quota < 0.45:
                errors.append(
                    f"solo {len(usate)} delle {len(frasi)} frasi lunghe lette nelle "
                    f"reference sono finite nel sito ({quota:.0%}): il sito e' fedele "
                    "ma vuoto, i contenuti sono stati buttati via invece che trascritti"
                )
    except (OSError, ValueError, KeyError) as exc:
        print(f"  Fedelta' testi: confronto non eseguito ({exc}).")

    if re.search(r"simulated block|for brevity|full source.*expected here", html, re.I):
        errors.append(
            "il codice ammette di contenere una simulazione ('simulated block' / "
            "'for brevity'): sostituiscila con la libreria vera dal CDN"
        )

    # JSX CRUDO NEL BODY: il componente React e' stato incollato come HTML
    # invece che dentro <script type="text/babel">. Nel browser `ref={...}` e
    # `style={{...}}` non fanno nulla: il componente non si monta e restano
    # blocchi colorati fantasma nella pagina (visto il 2026-07-26).
    corpo_senza_script = re.sub(
        r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I
    )
    for firma in (r"ref=\{", r"style=\{\{", r"className="):
        if re.search(firma, corpo_senza_script):
            errors.append(
                f"JSX crudo nell'HTML: trovato `{firma.replace(chr(92),'')}` fuori da "
                f"<script type=\"text/babel\">. Il browser non lo interpreta: il "
                f"componente React non si monta e lascia blocchi fantasma."
            )
            break

    # COLORI TAILWIND NON VALIDI: `bg-cda722` senza `#` e senza parentesi
    # quadre non e' una classe valida e non colora nulla, a meno che quel nome
    # sia dichiarato nella tailwind.config.
    config = ""
    match_config = re.search(r"tailwind\.config\s*=(.*?)</script>", html, re.S)
    if match_config:
        config = match_config.group(1)
    esadecimali_nudi = set(re.findall(r"\b(?:bg|text|border)-([0-9a-f]{6})\b", html, re.I))
    non_dichiarati = sorted(c for c in esadecimali_nudi if c.lower() not in config.lower())
    if non_dichiarati:
        errors.append(
            "classi colore Tailwind non valide (non colorano nulla): "
            + ", ".join(f"bg-{c}" for c in non_dichiarati[:4])
            + ". Usa la sintassi bg-[#" + non_dichiarati[0] + "] oppure dichiarale "
            "tutte nella tailwind.config."
        )
    gsap_versions = set(
        re.findall(
            r"(?:cdnjs\.cloudflare\.com/ajax/libs/gsap/|(?:esm\.sh/|unpkg\.com/)?gsap@)"
            r"(\d+\.\d+\.\d+)",
            html,
            re.I,
        )
    )
    if len(gsap_versions) > 1:
        errors.append(
            "runtime GSAP in conflitto: trovate versioni multiple "
            + ", ".join(sorted(gsap_versions))
        )
    gsap_core_sources = set(
        re.findall(
            r"<script\b[^>]*src=['\"]([^'\"]*(?:/|@)gsap(?:@[^/'\"]+)?(?:\.min)?\.js[^'\"]*)['\"]",
            html,
            re.I,
        )
    )
    importmap_gsap = re.findall(r"['\"]gsap['\"]\s*:\s*['\"]([^'\"]+)['\"]", html, re.I)
    gsap_core_sources.update(importmap_gsap)
    if len(gsap_core_sources) > 1:
        errors.append("runtime GSAP duplicata: carica una sola istanza core di GSAP")
    function_start = re.search(rf"function\s+{re.escape(function_name)}\s*\([^)]*\)\s*{{", html)
    function_body = ""
    if function_start:
        end_positions = [
            value
            for value in (
                html.find("</script>", function_start.end()),
                html.find("\nfunction ", function_start.end()),
            )
            if value >= 0
        ]
        function_end = min(end_positions) if end_positions else len(html)
        function_body = html[function_start.end():function_end]
    uses_native_scroll_timeline = component_id == "codrops-scroll-carousel" and all(
        token in html for token in ("animation-timeline", "scroll-timeline", "view-timeline")
    )
    if not uses_native_scroll_timeline and (
        "ScrollTrigger" not in html or "scrollTrigger" not in function_body
    ):
        errors.append("manca attivazione reale tramite ScrollTrigger nella funzione selezionata")
    if re.search(r"setInterval\s*\(", function_body):
        errors.append("il componente selezionato usa setInterval invece dello scroll")
    if not uses_native_scroll_timeline:
        invocations = _component_invocations(html, function_name)
        if not invocations:
            errors.append(f"{function_name} non viene invocata dal gate di scroll")
        elif any(not _is_scroll_gated_invocation(html, position) for position in invocations):
            errors.append(
                f"{function_name} contiene un'invocazione eager/globale fuori da "
                "ScrollTrigger.onEnter o IntersectionObserver"
            )
    if component2_id:
        function2 = selection.get("component2_function_name", "")
        function2_start = re.search(
            rf"function\s+{re.escape(function2)}\s*\([^)]*\)\s*{{", html
        )
        function2_body = ""
        if function2_start:
            end_positions = [
                value for value in (
                    html.find("</script>", function2_start.end()),
                    html.find("\nfunction ", function2_start.end()),
                ) if value >= 0
            ]
            function2_end = min(end_positions) if end_positions else len(html)
            function2_body = html[function2_start.end():function2_end]
        native_scroll_guest2 = component2_id == "codrops-scroll-carousel" and all(
            token in html for token in ("animation-timeline", "scroll-timeline", "view-timeline")
        )
        if not native_scroll_guest2:
            invocations2 = _component_invocations(html, function2)
            if not invocations2:
                errors.append(f"{function2} (Guest #2) non viene invocata dal gate di scroll")
            elif any(not _is_scroll_gated_invocation(html, position) for position in invocations2):
                errors.append(
                    f"{function2} (Guest #2) contiene un'invocazione eager/globale fuori da "
                    "ScrollTrigger.onEnter o IntersectionObserver"
                )
            if "ScrollTrigger" not in html or "scrollTrigger" not in function2_body:
                errors.append("manca attivazione reale tramite ScrollTrigger nel Guest #2")
        if re.search(r"setInterval\s*\(", function2_body):
            errors.append("il Guest #2 usa setInterval invece dello scroll")
    if not re.search(r"prefers-reduced-motion", html, re.I):
        errors.append("manca gestione prefers-reduced-motion")

    # --- LEGGE DELLO SCROLL: vale su TUTTO il sito, non solo sui Guest -------
    # Prima questo controllo esisteva solo per le due funzioni Guest, quindi il
    # resto delle animazioni poteva partire al caricamento. Qui si verifica che
    # ogni animazione GSAP sia guidata dallo scroll, con l'unica eccezione
    # dell'ingresso dell'hero (gia' a schermo al load: se aspettasse lo scroll
    # resterebbe fermo).
    HERO_LOAD_ALLOWANCE = 4
    eager_animations = 0
    for match in re.finditer(r"\bgsap\s*\.\s*(?:to|from|fromTo|timeline)\s*\(", html):
        open_paren = html.index("(", match.end() - 1)
        close_paren = _balanced_call_end(html, open_paren)
        if close_paren < 0:
            continue
        call_source = html[open_paren:close_paren]
        # Una timeline puo' dichiarare lo scrollTrigger nei metodi concatenati
        # subito dopo la parentesi di chiusura: guardiamo anche li'.
        chained = html[close_paren:close_paren + 400]
        if "scrollTrigger" in call_source or "scrollTrigger" in chained:
            continue
        # Le animazioni dentro un handler di interazione (hover, click, tap)
        # sono legittime: partono da un gesto dell'utente, non al caricamento.
        # Senza questa esenzione il gate boccerebbe ogni sito con effetti hover.
        preceding = html[max(0, match.start() - 400):match.start()]
        if re.search(
            r"addEventListener\s*\(\s*['\"](?:mouse|pointer|click|touch|focus|"
            r"blur|drag|key)",
            preceding,
        ) or re.search(r"\bon(?:mouse|click|pointer|touch|focus)\w*\s*=", preceding):
            continue
        eager_animations += 1
    # NON e' un errore bloccante: stampato e basta. Un errore qui farebbe
    # ripartire Stitch (= crediti bruciati) per una cosa che va imposta PRIMA,
    # nel prompt, consegnandogli il motion kit gia' scritto. Il gate qui serve
    # solo a farci vedere se il kit ha funzionato.
    if eager_animations > HERO_LOAD_ALLOWANCE:
        print(
            f"  NOTA (non bloccante): {eager_animations} animazioni GSAP non "
            f"sono guidate dallo scroll (atteso <= {HERO_LOAD_ALLOWANCE}, "
            f"riservate all'ingresso dell'hero)."
        )
    for trigger in ("DOMContentLoaded", "window.onload", "setInterval"):
        for match in re.finditer(re.escape(trigger), html):
            window_source = html[match.end():match.end() + 600]
            if re.search(r"\bgsap\s*\.\s*(?:to|from|fromTo|timeline)\s*\(", window_source):
                print(f"  NOTA (non bloccante): animazioni GSAP avviate da {trigger}.")
                break
    # Contratto sezioni: 6 sezioni ORIGINALI (ricavate solo dalle reference)
    # + 2 sezioni dedicate ai Guest Component = 8 totali. I Guest non vengono
    # conteggiato tra le originali, altrimenti basterebbe aggiungere il
    # componente per soddisfare il minimo.
    all_section_tags = re.findall(r"<section\b[^>]*>", html, re.I)
    sections = len(all_section_tags)
    guest_tag_pattern = re.compile(
        rf"data-stitch-added-guest=['\"]true['\"]|"
        rf"data-stitch-native-component=['\"](?:{re.escape(component_id)}|{re.escape(component2_id or '')})['\"]",
        re.I,
    )
    original_sections = sum(1 for tag in all_section_tags if not guest_tag_pattern.search(tag))
    guests_attesi = 2 if component2_id else 1
    if original_sections < 6:
        errors.append(
            f"solo {original_sections} sezioni originali (servono 6 + {guests_attesi} Guest): implementa le "
            "sezioni REALI delle reference non ancora presenti; e' VIETATO inventarne di nuove"
        )
    guest_sections = []
    guest_ids = (component_id, component2_id) if component2_id else (component_id,)
    for selected_id in guest_ids:
        match = re.search(
            rf"<section\b[^>]*data-stitch-native-component=['\"]{re.escape(selected_id)}['\"][^>]*>",
            html,
            re.I,
        ) if selected_id else None
        if not match:
            errors.append(f"il Guest {selected_id or '#2'} non e montato dentro una nuova <section> dedicata")
        else:
            guest_sections.append(match)
            # Sezione presente ma VUOTA: Stitch scrive `<section ...> ... </section>`
            # abbreviando il markup con tre puntini. La sezione risulta 0x0, senza
            # figli, e il componente non si vede. Visto dal vivo il 24/07.
            chiusura = html.lower().find("</section>", match.end())
            contenuto = html[match.end():chiusura if chiusura > 0 else match.end()]
            senza_spazi = contenuto.strip()
            if len(re.findall(r"<\w+", contenuto)) < 3:
                errors.append(
                    f"la <section> del Guest {selected_id} e' VUOTA "
                    f"(contenuto: {senza_spazi[:40]!r}): il markup e' stato "
                    "abbreviato invece di essere incollato per intero"
                )
            elif re.match(r"^(\.{3}|…|<!--\s*\.{3})", senza_spazi):
                errors.append(
                    f"la <section> del Guest {selected_id} inizia con un segnaposto "
                    "'...': il markup non e' stato incollato davvero"
                )
    if len(all_section_tags) < 6 + guests_attesi:
        errors.append(
            f"solo {len(all_section_tags)} sezioni totali (servono 6 originali + {guests_attesi} Guest)"
        )
    if len(guest_sections) == guests_attesi and guest_sections:
        footer_position = html.lower().find("<footer", guest_sections[-1].end())
        tail_end = footer_position if footer_position >= 0 else len(html)
        if not re.search(r"<section\b", html[guest_sections[-1].end():tail_end], re.I):
            errors.append("l'ultimo Guest e ultimo prima del footer: manca una section originale successiva scroll-safe")
    section_tags = re.findall(r"<section\b[^>]*>", html, re.I)
    for index, tag in enumerate(section_tags, 1):
        missing_phases = [
            name for name in (
                "data-motion-section", "data-motion-entry",
                "data-motion-traverse", "data-motion-exit",
            ) if name not in tag
        ]
        if missing_phases:
            errors.append(
                f"sezione {index} senza contratto motion completo: {', '.join(missing_phases)}"
            )
    families = set(re.findall(r"data-motion-family=['\"]([^'\"]+)['\"]", html, re.I))
    if len(families) < 6:
        errors.append(f"solo {len(families)} famiglie motion distinte; minimo richiesto 6")
    required_roles = {"logo", "nav", "title", "body", "media", "caption", "cta", "icon", "control", "footer"}
    roles = set(re.findall(r"data-motion-role=['\"]([^'\"]+)['\"]", html, re.I))
    missing_roles = sorted(required_roles - roles)
    if missing_roles:
        errors.append("ruoli motion mancanti: " + ", ".join(missing_roles))
    present_ids = {value for value in KNOWN_COMPONENT_IDS if f'data-stitch-native-component="{value}"' in html}
    expected_ids = {component_id, component2_id}
    if present_ids != expected_ids:
        errors.append(f"Guest Component non univoci/completi: trovati {sorted(present_ids) or 'nessuno'}")
    if re.search(
        rf"function\s+{re.escape(function_name)}\s*\([^)]*\)\s*{{\s*(?:console\.log\([^)]*\);?|return(?:\s+[^;]+)?;?)?\s*}}",
        html,
        re.S,
    ):
        errors.append(f"{function_name} sembra uno stub/simulazione")
    if component_id == "codrops-scroll-carousel" and not all(
        token in html for token in ("animation-timeline", "scroll-timeline", "view-timeline")
    ):
        errors.append("Codrops Carousel è stato semplificato: manca il meccanismo CSS scroll-driven originale")
    if component_id == "reveal-slideshow" and not re.search(r"\b(slide--current|btnPrev|btnNext|clipPath)\b", html, re.I) and not re.search(r"<script[^>]*type=[\"']module[\"']", html, re.I):
        errors.append("reveal-slideshow è stato reinventato o semplificato: manca il codice sorgente reale del bundle con cambio slide e clipPath")
    if component_id == "onscroll-filter" and not all(
        token in html for token in ("Flip.getState", "Flip.from", "new Item")
    ):
        errors.append("On-Scroll Filter è stato semplificato: manca la logica Flip/Item originale")
    if re.search(r"\b(?:TODO|FIXME|placeholder adapter|fake adapter)\b", html, re.I):
        errors.append("sono presenti TODO o adapter placeholder")
    explicit_simulation_patterns = (
        r"placeholder\s+for\s+(?:premium plugins|framer|codrops|component|mount|hydration)",
        r"(?:module|grid|component|interaction)\s+loaded\s*\[sha256:",
        r"(?:hover grid|framer\s+\w+\s+interactive)\s+(?:active|module loaded)",
        r"\bmock(?:ing|ed)?\s+(?:the\s+)?original\b",
        r"\b(?:simulat(?:e|ed|ing|ion)|surrogate)\b[^<\n]{0,100}\b(?:component|interaction|framer|codrops|logic)\b",
        r"\b(?:simplified|semplificat[oa])\b[^<\n]{0,100}\b(?:component|interaction|framer|codrops|logic|source)\b",
    )
    if any(re.search(pattern, html, re.I) for pattern in explicit_simulation_patterns):
        errors.append(
            "Guest Component o Framer sembra uno stub/simulazione: "
            "rilevati placeholder, mock, simulazioni o semplificazioni al posto del sorgente reale"
        )
    if len(re.sub(r"<[^>]+>", "", html).strip()) < 300:
        errors.append("pagina quasi vuota")
    return errors


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


@contextlib.contextmanager
def local_server(root: Path):
    handler = functools.partial(QuietHandler, directory=str(root))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=2)


def browser_checks(extract_root: Path, html_name: str, selection: dict, output_dir: Path) -> list[str]:
    errors: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    # Risorse (script/CSS) che il browser NON e' riuscito a scaricare. Vanno
    # registrate a parte perche' il filtro sulla console scarta i messaggi
    # "Failed to load resource": e' cosi' che un <script> GSAP con la versione
    # sbagliata (3.12.5/SplitText.min.js -> 404) e' passato inosservato,
    # uccidendo l'intera regia motion del sito del 2026-07-27.
    dead_resources: list[str] = []
    component_id = selection["component_id"]
    framer_id = selection["framer_id"]
    relative = quote(html_name, safe="/")

    with local_server(extract_root) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )

        def _note_response(response) -> None:
            if response.status < 400:
                return
            kind = (response.request.resource_type or "").lower()
            if kind not in ("script", "stylesheet", "font", "image"):
                return
            dead_resources.append(f"{response.status} {kind} {response.url}")

        page.on("response", _note_response)
        page.on(
            "requestfailed",
            lambda request: dead_resources.append(
                f"FAILED {request.resource_type} {request.url}"
            )
            if (request.resource_type or "").lower() in ("script", "stylesheet")
            else None,
        )
        try:
            page.goto(f"http://127.0.0.1:{port}/{relative}", wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(1500)

            selector = f'[data-stitch-native-component="{component_id}"]'
            framer_selector = f'[data-stitch-framer-interaction="{framer_id}"]'
            nav_selector = (
                '[data-stitch-transparent-nav="true"]'
                '[data-scroll-visibility="top-only"]'
            )
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(350)
            baseline = page.evaluate(
                """([selector, framerSelector, navSelector]) => {
                  const root = document.querySelector(selector);
                  const framer = document.querySelector(framerSelector);
                  const nav = document.querySelector(navSelector);
                  const navStyle = nav ? getComputedStyle(nav) : null;
                  const navBox = nav?.getBoundingClientRect();
                  const rgbaAlpha = value => {
                    if (!value || value === 'transparent') return 0;
                    const match = value.match(/rgba?\\(([^)]+)\\)/i);
                    if (!match) return 1;
                    const parts = match[1].split(/[ ,/]+/).filter(Boolean);
                    return parts.length > 3 ? Number(parts[3]) : 1;
                  };
                  const navItems = nav ? [...nav.querySelectorAll('a, button')].filter(el => {
                    const box = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return box.width > 1 && box.height > 1 && style.display !== 'none' &&
                      style.visibility !== 'hidden' && Number(style.opacity) > 0.1;
                  }).map(el => {
                    const box = el.getBoundingClientRect();
                    return { centerY: box.top + box.height / 2 };
                  }) : [];
                  return {
                    text: document.body.innerText.trim().length,
                    sections: document.querySelectorAll('section').length,
                    roots: document.querySelectorAll(selector).length,
                    framerRoots: document.querySelectorAll(framerSelector).length,
                    scrollHeight: document.documentElement.scrollHeight,
                    widthOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    gsap: !!window.gsap,
                    scrollTrigger: !!window.ScrollTrigger,
                    triggerCount: window.ScrollTrigger?.getAll?.().length || 0,
                    marker: window.__STITCH_SELECTED_COMPONENT__ || null,
                    framerMarker: window.__STITCH_SELECTED_FRAMER__ || null,
                    manifest: window.__STITCH_MOTION_MANIFEST__ || null,
                    guestHashes: window.__STITCH_GUEST_SOURCE_SHA256__ || null,
                    framerHash: window.__STITCH_FRAMER_SOURCE_SHA256__ || null,
                    brokenImages: [...document.images].filter(img => img.complete && img.naturalWidth === 0).length,
                    rootBox: root ? root.getBoundingClientRect().toJSON() : null,
                    framerBox: framer ? framer.getBoundingClientRect().toJSON() : null,
                    guestActivation: root?.dataset.motionActivation || null,
                    guestMounted: root?.dataset.motionMounted || null,
                    navCount: document.querySelectorAll(navSelector).length,
                    navBox: navBox ? navBox.toJSON() : null,
                    navOpacity: navStyle ? Number(navStyle.opacity) : 0,
                    navVisibility: navStyle?.visibility || null,
                    navDisplay: navStyle?.display || null,
                    navBackgroundAlpha: navStyle ? rgbaAlpha(navStyle.backgroundColor) : 1,
                    navBackdrop: navStyle ? (navStyle.backdropFilter || navStyle.webkitBackdropFilter) : null,
                    navShadow: navStyle?.boxShadow || null,
                    navBorder: navStyle ? [
                      navStyle.borderTopWidth, navStyle.borderRightWidth,
                      navStyle.borderBottomWidth, navStyle.borderLeftWidth
                    ].map(parseFloat) : [],
                    navItemCenters: navItems.map(item => item.centerY)
                  };
                }""",
                [selector, framer_selector, nav_selector],
            )
            page.screenshot(path=str(output_dir / "desktop.png"), full_page=True)

            # ---------------------------------------------------------------
            # CONTROLLI GENERICI DI INTEGRITA' VISIVA
            #
            # Tutti gli altri controlli di questo file nominano UN bug preciso
            # ("root del componente assente", "menu con fondo opaco"): trovano
            # quindi solo i guasti gia' visti almeno una volta. Il 2026-07-27
            # sono passati inosservati foto che erano screenshot di reference,
            # un titolo tagliato dal bordo ("' Azienda"), sezioni illeggibili e
            # rettangoli colorati vuoti: nessuno era in elenco.
            #
            # Questi controlli non nominano il bug: misurano PROPRIETA' che un
            # sito sano non puo' violare, quindi intercettano anche guasti che
            # non abbiamo ancora incontrato.
            # ---------------------------------------------------------------
            integrita = page.evaluate(
                """() => {
                  const visibile = (el) => {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden'
                           && r.width > 1 && r.height > 1;
                  };
                  const risultato = {
                    testoTagliato: [], invisibili: [], immaginiRotte: [],
                    blocchiVuoti: [], contrastoBasso: [],
                    menuSuPiuRighe: 0, vociSpezzate: [], ancoreMorte: [],
                    sezioniCollassate: [], sezioniPovere: [], immaginiTotali: 0
                  };

                  // 9. SEZIONI POVERE — il sito e' fedele ma vuoto.
                  //    Il 2026-07-27 e' uscito un sito con 4 immagini in tutto
                  //    e sezioni da 105 caratteri, mentre nelle reference le
                  //    stesse sezioni hanno paragrafi interi e piu' foto.
                  //    Non aveva inventato niente: aveva buttato via quasi
                  //    tutto. Misurato, non giudicato.
                  risultato.immaginiTotali = document.querySelectorAll('img').length;
                  for (const sec of document.querySelectorAll('section')) {
                    if (sec.hasAttribute('data-stitch-native-component')) continue;
                    if (sec.hasAttribute('data-stitch-framer-interaction')) continue;
                    if (sec.getBoundingClientRect().height < 200) continue;
                    const testo = (sec.innerText || '').split(/\u0020+/).join(' ').trim();
                    const foto = sec.querySelectorAll('img, [style*="background-image"]').length;
                    if (testo.length < 350 || foto === 0) {
                      risultato.sezioniPovere.push(
                        (sec.id || 'section') + ': ' + testo.length + ' car., '
                        + foto + ' foto'
                      );
                    }
                  }

                  // 8. SEZIONI ALTE ZERO (o quasi)
                  //    Succede quando TUTTI i figli sono position:absolute o
                  //    fixed: escono dal flusso e il contenitore collassa. Il
                  //    contenuto c'e' nel codice ma non occupa spazio, quindi
                  //    non si vede e non produce scroll: ogni ScrollTrigger
                  //    agganciato li' non avanza mai. E' quello che ha reso
                  //    inerte il Guest Component il 2026-07-27 (sezione alta
                  //    0px con 6 scene dentro). Misurato, non dedotto.
                  for (const sec of document.querySelectorAll('section')) {
                    const h = sec.getBoundingClientRect().height;
                    if (h >= 80) continue;
                    const figli = [...sec.children];
                    const fuoriFlusso = figli.filter((e) => {
                      const pos = getComputedStyle(e).position;
                      return pos === 'absolute' || pos === 'fixed';
                    }).length;
                    risultato.sezioniCollassate.push(
                      (sec.id || sec.className || 'section').slice(0, 30)
                      + ' = ' + Math.round(h) + 'px'
                      + (figli.length && fuoriFlusso === figli.length
                         ? ' (tutti i figli fuori dal flusso)' : '')
                    );
                  }

                  // 6. IL MENU E' ANDATO A CAPO SU PIU' RIGHE
                  //    Misurato, non dedotto: se le voci del menu non hanno
                  //    tutte lo stesso `top`, il menu si e' spezzato. E' il
                  //    bug del 2026-07-27 ("I NOSTRI / PRODOTTI" su due righe)
                  //    ed esce da un flex senza flex-nowrap.
                  //    Due modi di spezzarsi, entrambi misurati:
                  //    a) le voci stanno su `top` diversi -> il flex e' andato
                  //       a capo (manca flex-nowrap);
                  //    b) il testo DENTRO una voce si spezza su piu' righe ->
                  //       manca whitespace-nowrap. E' il caso reale del
                  //       2026-07-27: "I NOSTRI / PRODOTTI" su due righe pur
                  //       con un flex che non wrappa, perche' le voci si
                  //       restringono e il testo va a capo.
                  const nav = document.querySelector('nav, header nav, [data-stitch-transparent-nav]');
                  if (nav) {
                    const voci = [...nav.querySelectorAll('a')].filter(visibile);
                    const righe = new Set(voci.map((a) =>
                      Math.round(a.getBoundingClientRect().top / 6)));
                    if (voci.length > 2 && righe.size > 1) {
                      risultato.menuSuPiuRighe = righe.size;
                    }
                    for (const a of voci) {
                      const range = document.createRange();
                      range.selectNodeContents(a);
                      if (range.getClientRects().length > 1) {
                        risultato.vociSpezzate.push((a.textContent || '').trim().slice(0, 24));
                      }
                    }
                  }

                  // 7. LINK CHE NON PORTANO DA NESSUNA PARTE
                  //    href="#" oppure href="#sezione" con quell'id assente:
                  //    il click non fa niente. Generico: nessun nome di bug.
                  for (const a of document.querySelectorAll('a[href^="#"]')) {
                    if (!visibile(a)) continue;
                    const href = a.getAttribute('href');
                    const etichetta = (a.textContent || '').trim().slice(0, 24);
                    if (href === '#') {
                      risultato.ancoreMorte.push(etichetta + ' -> #');
                    } else if (!document.querySelector(
                        '[id="' + href.slice(1) + '"], [name="' + href.slice(1) + '"]')) {
                      risultato.ancoreMorte.push(etichetta + ' -> ' + href);
                    }
                  }

                  // 1. TESTO CHE ESCE DAL SUO CONTENITORE
                  for (const el of document.querySelectorAll('h1,h2,h3,h4,p,span,a,li')) {
                    if (!visibile(el) || el.children.length) continue;
                    const testo = (el.textContent || '').trim();
                    if (testo.length < 3) continue;
                    const s = getComputedStyle(el);
                    if (s.overflow === 'visible' && el.scrollWidth > el.clientWidth + 8
                        && s.whiteSpace !== 'nowrap') {
                      risultato.testoTagliato.push(testo.slice(0, 45));
                    }
                  }

                  // 2. TESTO INVISIBILE A PAGINA FERMA (opacita' 0 mai animata)
                  for (const el of document.querySelectorAll('h1,h2,h3,p')) {
                    const testo = (el.textContent || '').trim();
                    if (testo.length < 10) continue;
                    const s = getComputedStyle(el);
                    if (parseFloat(s.opacity) < 0.05) {
                      risultato.invisibili.push(testo.slice(0, 45));
                    }
                  }

                  // 3. IMMAGINI CHE NON SI CARICANO
                  for (const img of document.querySelectorAll('img')) {
                    if (img.complete && img.naturalWidth === 0) {
                      risultato.immaginiRotte.push((img.getAttribute('src') || '').slice(-45));
                    }
                  }

                  // 4. BLOCCHI COLORATI GRANDI E COMPLETAMENTE VUOTI
                  for (const el of document.querySelectorAll('div,span')) {
                    if (!visibile(el) || el.children.length) continue;
                    if ((el.textContent || '').trim()) continue;
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    const haSfondo = s.backgroundColor
                      && s.backgroundColor !== 'rgba(0, 0, 0, 0)'
                      && s.backgroundColor !== 'transparent';
                    const haImmagine = s.backgroundImage && s.backgroundImage !== 'none';
                    if (haSfondo && !haImmagine && r.width > 180 && r.height > 120) {
                      risultato.blocchiVuoti.push(
                        Math.round(r.width) + 'x' + Math.round(r.height));
                    }
                  }

                  // 5. TESTO DELLO STESSO COLORE DEL SUO FONDO
                  const rgb = (c) => (c.match(/\\d+/g) || [0,0,0]).slice(0,3).map(Number);
                  const lum = ([r,g,b]) => {
                    const f = (v) => { v/=255; return v<=0.03928 ? v/12.92
                                        : Math.pow((v+0.055)/1.055, 2.4); };
                    return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b);
                  };
                  for (const el of document.querySelectorAll('h1,h2,h3,p')) {
                    if (!visibile(el)) continue;
                    const testo = (el.textContent || '').trim();
                    if (testo.length < 10) continue;
                    const s = getComputedStyle(el);
                    let sfondo = null, p = el;
                    while (p && !sfondo) {
                      const ps = getComputedStyle(p);
                      if (ps.backgroundColor && ps.backgroundColor !== 'rgba(0, 0, 0, 0)'
                          && ps.backgroundColor !== 'transparent') sfondo = ps.backgroundColor;
                      if (ps.backgroundImage && ps.backgroundImage !== 'none') break;
                      p = p.parentElement;
                    }
                    if (!sfondo) continue;
                    const l1 = lum(rgb(s.color)), l2 = lum(rgb(sfondo));
                    const rapporto = (Math.max(l1,l2)+0.05) / (Math.min(l1,l2)+0.05);
                    if (rapporto < 1.6) risultato.contrastoBasso.push(testo.slice(0, 45));
                  }
                  return risultato;
                }"""
            )
            if integrita["testoTagliato"]:
                errors.append(
                    f"testo tagliato dal contenitore ({len(integrita['testoTagliato'])} casi): "
                    + " | ".join(integrita["testoTagliato"][:3])
                )
            if integrita["invisibili"]:
                errors.append(
                    f"testo invisibile a pagina ferma, opacita' 0 mai animata "
                    f"({len(integrita['invisibili'])} casi): "
                    + " | ".join(integrita["invisibili"][:3])
                )
            if integrita["immaginiRotte"]:
                errors.append(
                    f"immagini che non si caricano ({len(integrita['immaginiRotte'])}): "
                    + " | ".join(integrita["immaginiRotte"][:3])
                )
            if integrita["blocchiVuoti"]:
                errors.append(
                    f"blocchi di colore grandi e vuoti ({len(integrita['blocchiVuoti'])}): "
                    + ", ".join(integrita["blocchiVuoti"][:4])
                    + " — devono avere contenuto sopra, o vanno eliminati"
                )
            if integrita["contrastoBasso"]:
                errors.append(
                    f"testo quasi illeggibile sul suo fondo "
                    f"({len(integrita['contrastoBasso'])} casi): "
                    + " | ".join(integrita["contrastoBasso"][:3])
                )
            if integrita["menuSuPiuRighe"]:
                errors.append(
                    f"il menu e' andato a capo su {integrita['menuSuPiuRighe']} righe: "
                    "serve flex-nowrap sul contenitore"
                )
            if integrita["vociSpezzate"]:
                errors.append(
                    f"voci di menu spezzate su due righe "
                    f"({len(integrita['vociSpezzate'])}): "
                    + " | ".join(integrita["vociSpezzate"][:4])
                    + " — serve whitespace-nowrap su ogni voce e flex-shrink-0"
                )
            if integrita["immaginiTotali"] < 6:
                errors.append(
                    f"solo {integrita['immaginiTotali']} immagini in tutto il sito "
                    "(minimo 6): le reference ne hanno molte di piu', sono state "
                    "buttate via"
                )
            if integrita["sezioniPovere"]:
                errors.append(
                    f"sezioni povere ({len(integrita['sezioniPovere'])}): "
                    + " | ".join(integrita["sezioniPovere"][:4])
                    + " — minimo 350 caratteri e almeno una foto per sezione"
                )
            if integrita["sezioniCollassate"]:
                errors.append(
                    f"sezioni alte quasi zero ({len(integrita['sezioniCollassate'])}): "
                    + " | ".join(integrita["sezioniCollassate"][:4])
                    + " — il contenuto c'e' nel codice ma non occupa spazio, "
                    "quindi non si vede e non produce scroll"
                )
            if integrita["ancoreMorte"]:
                errors.append(
                    f"link che non portano da nessuna parte "
                    f"({len(integrita['ancoreMorte'])}): "
                    + " | ".join(integrita["ancoreMorte"][:5])
                    + " — ogni voce deve puntare all'id di una sezione esistente"
                )

            if baseline["text"] < 300:
                errors.append(f"render quasi vuoto: solo {baseline['text']} caratteri visibili")
            if baseline["sections"] < 7:
                errors.append(
                    f"runtime: solo {baseline['sections']} sezioni (servono 6 originali dalle "
                    "reference + 1 Guest, senza inventarne)"
                )
            if baseline["roots"] != 1 or not baseline["rootBox"]:
                errors.append("runtime: root del componente assente o duplicata")
            elif baseline["rootBox"]["width"] < 20 or baseline["rootBox"]["height"] < 20:
                errors.append("runtime: root del componente senza dimensioni utili")
            if baseline["marker"] != component_id:
                errors.append("runtime: marker JavaScript del componente errato")
            if baseline["guestActivation"] != "scroll":
                errors.append("runtime: root Guest priva di data-motion-activation=scroll")
            native_scroll_guest = component_id == "codrops-scroll-carousel"
            guest_outside_initial_viewport = bool(
                baseline["rootBox"]
                and (
                    baseline["rootBox"]["top"] >= 1000
                    or baseline["rootBox"]["bottom"] <= 0
                )
            )
            if (
                not native_scroll_guest
                and guest_outside_initial_viewport
                and baseline["guestMounted"] == "true"
            ):
                errors.append("runtime: Guest montato prima di raggiungerlo con lo scroll")
            if baseline["framerRoots"] != 1 or not baseline["framerBox"]:
                errors.append("runtime: root Framer assente o duplicata")
            elif baseline["framerBox"]["width"] < 20 or baseline["framerBox"]["height"] < 20:
                errors.append("runtime: root Framer senza dimensioni utili")
            if baseline["framerMarker"] != framer_id:
                errors.append("runtime: marker JavaScript Framer errato")
            if baseline["manifest"] != selection["manifest_version"]:
                errors.append("runtime: manifesto motion errato o assente")
            expected_guest_hashes = sorted(selection["source_hashes"].values())
            if sorted(baseline["guestHashes"] or []) != expected_guest_hashes:
                errors.append("runtime: hash dei sorgenti Guest errati o assenti")
            if baseline["framerHash"] != selection["framer_source_hash"]:
                errors.append("runtime: hash del sorgente Framer errato o assente")
            if not baseline["gsap"] or not baseline["scrollTrigger"]:
                errors.append("runtime: GSAP o ScrollTrigger non disponibili")
            if baseline["triggerCount"] < 6:
                errors.append(f"runtime: solo {baseline['triggerCount']} ScrollTrigger; minimo 6")
            if baseline["brokenImages"]:
                errors.append(f"runtime: {baseline['brokenImages']} immagini rotte")
            if baseline["widthOverflow"] > 4:
                errors.append(f"runtime: overflow orizzontale di {baseline['widthOverflow']}px")

            if baseline["navCount"] != 1 or not baseline["navBox"]:
                errors.append("runtime: menu trasparente top-only assente o duplicato")
            else:
                nav_visible_at_top = (
                    baseline["navDisplay"] != "none"
                    and baseline["navVisibility"] != "hidden"
                    and baseline["navOpacity"] >= 0.9
                    and baseline["navBox"]["bottom"] > 0
                )
                if not nav_visible_at_top:
                    errors.append("runtime: menu non visibile quando la pagina e in cima")
                if baseline["navBackgroundAlpha"] > 0.03:
                    errors.append("runtime: menu con fondo opaco invece che trasparente")
                if baseline["navBackdrop"] not in (None, "none", ""):
                    errors.append("runtime: menu usa backdrop blur/filter")
                if baseline["navShadow"] not in (None, "none", ""):
                    errors.append("runtime: menu usa un'ombra visibile")
                if any(width > 0.5 for width in baseline["navBorder"]):
                    errors.append("runtime: menu usa un bordo visibile")
                centers = baseline["navItemCenters"]
                if len(centers) >= 2 and max(centers) - min(centers) > 6:
                    errors.append("runtime: voci del menu non allineate verticalmente")

                page.evaluate("window.scrollTo(0, Math.min(180, document.documentElement.scrollHeight - innerHeight))")
                page.wait_for_timeout(700)
                nav_after_scroll = page.evaluate(
                    """selector => {
                      const nav = document.querySelector(selector);
                      if (!nav) return null;
                      const style = getComputedStyle(nav);
                      const box = nav.getBoundingClientRect();
                      return {
                        opacity: Number(style.opacity),
                        visibility: style.visibility,
                        display: style.display,
                        top: box.top,
                        bottom: box.bottom,
                        height: box.height
                      };
                    }""",
                    nav_selector,
                )
                nav_hidden = bool(
                    nav_after_scroll
                    and (
                        nav_after_scroll["display"] == "none"
                        or nav_after_scroll["visibility"] == "hidden"
                        or nav_after_scroll["opacity"] <= 0.1
                        or nav_after_scroll["bottom"] <= 1
                        or nav_after_scroll["top"] <= -max(1, nav_after_scroll["height"] * 0.7)
                    )
                )
                if not nav_hidden:
                    errors.append("runtime: menu non scompare dopo l'inizio dello scroll")

                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(700)
                nav_returned = page.evaluate(
                    """selector => {
                      const nav = document.querySelector(selector);
                      if (!nav) return false;
                      const style = getComputedStyle(nav);
                      const box = nav.getBoundingClientRect();
                      return style.display !== 'none' && style.visibility !== 'hidden' &&
                        Number(style.opacity) >= 0.9 && box.bottom > 0;
                    }""",
                    nav_selector,
                )
                if not nav_returned:
                    errors.append("runtime: menu non ricompare tornando in cima")

            if baseline["roots"] == 1 and not native_scroll_guest:
                page.locator(selector).scroll_into_view_if_needed(timeout=10000)
                page.wait_for_timeout(700)
                mounted_after_scroll = page.locator(selector).get_attribute("data-motion-mounted")
                if mounted_after_scroll != "true":
                    errors.append(
                        "runtime: Guest non montato dopo che la sua sezione entra nel viewport"
                    )

            motion_results = page.evaluate(
                """async () => {
                  const sections = [...document.querySelectorAll('section')].slice(0, 6);
                  const signature = section => {
                    const nodes = [section, ...section.querySelectorAll('[data-motion-role], img, h1, h2, h3, p, a, button')].slice(0, 18);
                    return nodes.map(el => {
                      const s = getComputedStyle(el);
                      return [s.transform, s.clipPath, s.opacity, s.filter].join('|');
                    }).join(';;');
                  };
                  const results = [];
                  for (const section of sections) {
                    const beforeStyles = signature(section);
                    const relatedBefore = (window.ScrollTrigger?.getAll?.() || []).filter(t => {
                      const trigger = t.trigger;
                      return trigger && (trigger === section || section.contains(trigger) || trigger.contains?.(section));
                    });
                    const beforeProgress = relatedBefore.map(t => t.progress);
                    window.scrollTo(0, Math.max(0, section.offsetTop - innerHeight * 0.75));
                    await new Promise(resolve => setTimeout(resolve, 160));
                    window.scrollBy(0, Math.max(240, Math.min(innerHeight * 0.45, section.offsetHeight * 0.35)));
                    await new Promise(resolve => setTimeout(resolve, 380));
                    const afterStyles = signature(section);
                    const relatedAfter = (window.ScrollTrigger?.getAll?.() || []).filter(t => {
                      const trigger = t.trigger;
                      return trigger && (trigger === section || section.contains(trigger) || trigger.contains?.(section));
                    });
                    const afterProgress = relatedAfter.map(t => t.progress);
                    const progressChanged = afterProgress.some((value, index) => Math.abs(value - (beforeProgress[index] || 0)) > 0.001);
                    results.push({ changed: beforeStyles !== afterStyles || progressChanged, triggers: relatedAfter.length });
                  }
                  return results;
                }"""
            )
            moving_sections = sum(1 for item in motion_results if item["changed"] and item["triggers"] > 0)
            if moving_sections < 4:
                errors.append(f"runtime: movimento misurabile solo in {moving_sections} sezioni")

            # Anti-sovrapposizione: un overlay (es. il pannello del wiper creato
            # con position:absolute su un contenitore NON posizionato) puo'
            # ancorarsi alla pagina invece che alla propria sezione e coprire il
            # contenuto di altre sezioni. Lo rileviamo con elementFromPoint:
            # per ogni sezione campioniamo dei punti e verifichiamo che l'elemento
            # in cima appartenga davvero a quella sezione.
            covered = page.evaluate(
                """() => {
                  const problems = [];
                  const sections = Array.from(document.querySelectorAll('section, header, footer'));
                  sections.forEach((sec, i) => {
                    const rect = sec.getBoundingClientRect();
                    const absTop = rect.top + window.scrollY;
                    if (rect.height < 80) return;
                    window.scrollTo(0, Math.max(0, absTop - 60));
                    const r = sec.getBoundingClientRect();
                    const xs = [0.25, 0.5, 0.75];
                    const ys = [0.3, 0.6];
                    let blocked = 0, total = 0, culprit = '';
                    xs.forEach(fx => ys.forEach(fy => {
                      const x = r.left + r.width * fx;
                      const y = r.top + r.height * fy;
                      if (y < 0 || y > window.innerHeight || x < 0 || x > window.innerWidth) return;
                      total++;
                      const top = document.elementFromPoint(x, y);
                      if (!top) return;
                      if (top !== sec && !sec.contains(top)) {
                        blocked++;
                        const cs = getComputedStyle(top);
                        culprit = (top.tagName.toLowerCase()
                          + (top.className && typeof top.className === 'string'
                             ? '.' + top.className.trim().split(/\\s+/).slice(0,2).join('.') : '')
                          + ' [pos:' + cs.position + ']');
                      }
                    }));
                    if (total > 0 && blocked / total >= 0.5) {
                      problems.push({ index: i + 1, id: sec.id || sec.tagName.toLowerCase(), blocked, total, culprit });
                    }
                  });
                  window.scrollTo(0, 0);
                  return problems;
                }"""
            )
            for problem in covered:
                errors.append(
                    f"sovrapposizione: la sezione '{problem['id']}' e' coperta da un elemento "
                    f"esterno ({problem['culprit']}) in {problem['blocked']}/{problem['total']} punti; "
                    "gli overlay (wiper/mask) devono stare dentro un contenitore con position:relative"
                )

            for special_selector, label in ((selector, "Guest"), (framer_selector, "Framer")):
                linked = page.evaluate(
                    """selector => (window.ScrollTrigger?.getAll?.() || []).filter(t => {
                      const root = document.querySelector(selector);
                      const trigger = t.trigger;
                      return root && trigger && (trigger === root || root.contains(trigger) || trigger.contains?.(root));
                    }).length""",
                    special_selector,
                )
                if linked < 1:
                    errors.append(f"runtime: nessun ScrollTrigger collegato alla root {label}")

            mobile = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
            mobile_page = mobile.new_page()
            mobile_page.goto(f"http://127.0.0.1:{port}/{relative}", wait_until="domcontentloaded", timeout=30000)
            mobile_page.wait_for_timeout(1000)
            mobile_stats = mobile_page.evaluate(
                """([selector, framerSelector]) => {
                  const roots = [document.querySelector(selector), document.querySelector(framerSelector)];
                  return {
                    text: document.body.innerText.trim().length,
                    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    visible: roots.every(root => {
                      if (!root) return false;
                      const style = getComputedStyle(root);
                      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0;
                    })
                  };
                }""",
                [selector, framer_selector],
            )
            mobile_page.screenshot(path=str(output_dir / "mobile-reduced-motion.png"), full_page=True)
            if mobile_stats["text"] < 300 or not mobile_stats["visible"]:
                errors.append("mobile/reduced-motion: contenuto o componente non visibile")
            if mobile_stats["overflow"] > 4:
                errors.append(f"mobile: overflow orizzontale di {mobile_stats['overflow']}px")
            mobile.close()
        except Exception as exc:
            errors.append(f"browser QA non completato: {exc}")
        finally:
            context.close()
            browser.close()

    noisy = [
        message
        for message in console_errors
        if "favicon" not in message.lower()
        and "failed to load resource" not in message.lower()
        and "tailwindcss.com should not be used in production" not in message.lower()
    ]
    if page_errors:
        errors.append("errori JavaScript: " + " | ".join(page_errors[:4]))
    if noisy:
        errors.append("errori console: " + " | ".join(noisy[:4]))
    if dead_resources:
        unique = list(dict.fromkeys(dead_resources))
        errors.append(
            "risorse non caricate (uno script morto puo' spegnere tutta la "
            "regia motion): " + " | ".join(unique[:5])
        )
    return errors


def main() -> int:
    args = parse_args()
    zip_path = args.zip_path.expanduser().resolve()
    if not zip_path.is_file():
        print(f"MOTION QUALITY GATE: FAIL - ZIP non trovato: {zip_path}")
        return 2
    selection = load_selection(args.selection.expanduser())
    output_dir = DEBUG_ROOT / time.strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        html_name, html = select_candidate(archive, selection)
        errors = static_checks(html, selection)
        if not args.static_only and not errors:
            extract_root = Path(tempfile.mkdtemp(prefix="stitch-motion-qa-"))
            try:
                archive.extractall(extract_root)
                errors.extend(browser_checks(extract_root, html_name, selection, output_dir))
            finally:
                shutil.rmtree(extract_root, ignore_errors=True)

    report = {
        "zip": str(zip_path),
        "html": html_name,
        "component": selection["component_id"],
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "screenshots": str(output_dir),
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if errors:
        print("STITCH MOTION QUALITY GATE: FAIL")
        for error in errors:
            print(f"  - {error}")
        print(f"Report: {output_dir / 'report.json'}")
        return 1
    print("STITCH MOTION QUALITY GATE: PASS")
    print(f"  componente reale: {selection['component_name']}")
    print(f"  HTML verificato: {html_name}")
    print(f"  screenshot QA: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
