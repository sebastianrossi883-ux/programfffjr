#!/usr/bin/env python3
"""Fa girare la pipeline vera contro una Stitch finta, senza browser.

A cosa serve
------------
I bug di questo progetto si scoprivano sempre nello stesso modo: lanciando il
robot, aspettando dieci minuti, guardando cosa NON era successo. Qui invece la
sequenza delle fasi si esercita in un secondo, con una Stitch di cartone che
risponde in inglese come quella vera ("Thinking...", "Export") e che si puo'
far comportare male apposta.

Non sostituisce un giro vero: i selettori del browser restano da verificare
sul campo. Serve a controllare cio' che dipende solo da noi - l'ordine delle
fasi, cosa viene inviato, cosa succede quando una fase non risponde.

    python3 simula_giro.py
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

# --- Stitch di cartone: playwright non serve --------------------------------
_pw = types.ModuleType("playwright")
_sync = types.ModuleType("playwright.sync_api")


class Error(Exception):
    pass


class TimeoutError(Error):  # noqa: A001 - deve chiamarsi cosi'
    pass


_sync.Error = Error
_sync.TimeoutError = TimeoutError
_sync.sync_playwright = lambda: None
_pw.sync_api = _sync
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _sync)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import download_stitch_project as dsp  # noqa: E402
import send_to_stitch as sts  # noqa: E402


class Orologio:
    def __init__(self) -> None:
        self.t = 1000.0

    def time(self) -> float:
        return self.t

    def sleep(self, secondi: float) -> None:
        self.t += secondi


class Elemento:
    def __init__(self, proprietario) -> None:
        self.proprietario = proprietario

    def inner_text(self, timeout: int = 0) -> str:
        return self.proprietario.testo


class Frame:
    def __init__(self, url: str, testo: str) -> None:
        self.url, self.testo = url, testo

    def locator(self, selettore: str):
        return Elemento(self)


class StitchFinta:
    """Risponde come Stitch: prende il messaggio, "pensa", produce una schermata."""

    def __init__(self, orologio: Orologio, secondi_di_lavoro: int = 90) -> None:
        self.orologio = orologio
        self.secondi_di_lavoro = secondi_di_lavoro
        self.url = "https://stitch.withgoogle.com/projects/1599933938923682070"
        self.main_frame = Frame(self.url, "Export\n")
        self.inviati: list[str] = []
        self.versione_sito = 1
        self.fine_lavoro = None
        self.istanti_invio: list[float] = []
        self.keyboard = types.SimpleNamespace(press=lambda tasto: None)
        self.viewport_size = {"width": 1440, "height": 950}

    # --- quello che fa il robot su di lei ---
    def riceve(self, messaggio: str) -> None:
        self.inviati.append(messaggio)
        self.fine_lavoro = self.orologio.t + self.secondi_di_lavoro
        self.main_frame.testo = (
            f"{messaggio[:40]}\nThinking...\nExport\n"  # UI inglese, come nella foto
        )

    def _aggiorna(self) -> None:
        if self.fine_lavoro is not None and self.orologio.t >= self.fine_lavoro:
            self.fine_lavoro = None
            self.versione_sito += 1
            self.main_frame.testo = (
                f"{self.inviati[-1][:40]}\nHere is your screen.\nExport\n"
            )

    def wait_for_timeout(self, ms: int) -> None:
        self.orologio.sleep(ms / 1000.0)
        self._aggiorna()

    @property
    def frames(self) -> list[Frame]:
        self._aggiorna()
        corpo = "Tenuta Montelvino " + "x" * (3000 * self.versione_sito)
        return [self.main_frame, Frame("blob:https://anteprima/schermo", corpo)]


def prepara(pagina: StitchFinta, orologio: Orologio, registro: list[str]):
    """Sostituisce solo cio' che tocca il browser vero. La logica resta quella."""
    dsp.time = orologio
    sts.time = orologio

    sts.select_visible_screen_on_canvas = lambda page: registro.append("seleziona schermata") or True
    dsp.select_visible_screen_on_canvas = sts.select_visible_screen_on_canvas
    sts.choose_model_31 = lambda page, debug_label=None: registro.append("imposta 3.1 Pro") or True
    sts.active_composer_shows_31_pro = lambda page: True
    sts.fill_prompt = lambda page, prompt: registro.append(f"scrive prompt ({len(prompt)} car.)")
    sts.upload_motion_attachments = lambda page, files: (
        registro.append(f"allega {len(files)} file -> chip") or "composer"
    )
    sts.visible_attachment_names_in_composer = lambda page, files: [f.name for f in files]
    sts.save_debug = lambda page, etichetta: None
    dsp.save_debug = sts.save_debug
    sts.log_prompt_send = lambda fase, percorso, prompt: registro.append(
        f"REGISTRA {fase} ({len(prompt)} car.)"
    )

    def invia(page, prompt: str) -> None:
        dsp.mark_generation_baseline(page)
        page.riceve(prompt)
        page.istanti_invio.append(orologio.t)
        registro.append(f"INVIA {len(prompt)} car. al secondo {int(orologio.t - 1000)}")

    sts.send = invia


def giro(nome: str, secondi_di_lavoro: int, atteso_fasi: int) -> bool:
    orologio = Orologio()
    pagina = StitchFinta(orologio, secondi_di_lavoro)
    registro: list[str] = []
    prepara(pagina, orologio, registro)

    print(f"\n--- {nome} (Stitch impiega {secondi_di_lavoro}s per fase) ---")
    partenza = orologio.t
    # La fase 1 e' gia' partita da main(): passa da send(), quindi la foto del
    # canvas viene scattata anche li'. Saltarla falserebbe tutto il resto.
    dsp.mark_generation_baseline(pagina)
    pagina.riceve("PROMPT FASE 1 ...")
    pagina.istanti_invio.append(orologio.t)
    registro.append("INVIA fase 1 al secondo 0")

    animazione = (Path(__file__).resolve().parent / "STITCH_ANIMATION_PROMPT.txt").read_text(
        encoding="utf-8"
    )
    try:
        sts.send_animation_followup(
            pagina,
            animazione,
            timeout_ms=900_000,
            attachment_paths=list(sts.MOTION_CORE_ATTACHMENT_PATHS),
            modo_allegati="file",
        )
    except SystemExit as uscita:
        print(f"  FERMATO: {uscita}")

    inviati = len(pagina.inviati)
    durata = int(orologio.t - partenza)
    esito = inviati == atteso_fasi
    if len(pagina.istanti_invio) >= 2:
        ritardo = int(pagina.istanti_invio[1] - pagina.istanti_invio[0])
        troppo_presto = ritardo < secondi_di_lavoro
        print(
            f"  /animate inviato {ritardo}s dopo la fase 1 "
            f"(Stitch finisce a {secondi_di_lavoro}s)"
            + ("   <<< TROPPO PRESTO" if troppo_presto else "   ok, dopo la fine")
        )
        esito = esito and not troppo_presto
    print(f"  messaggi arrivati a Stitch: {inviati} (attesi {atteso_fasi}) in {durata}s simulati")
    for riga in registro:
        print(f"     . {riga}")
    print(f"  [{'OK' if esito else 'PROBLEMA'}]")
    return esito


def giro_senza_foto() -> bool:
    """download_stitch_project lanciato da solo: nessuna foto di partenza.

    La chat contiene ancora la frase di lavoro della fase precedente e la
    pagina non cambia piu'. Senza una via d'uscita a tempo il robot resterebbe
    fermo fino al timeout: e' esattamente lo stallo da cui siamo partiti.
    """
    print("\n--- download lanciato da solo, frase vecchia in chat, nessuna foto ---")
    orologio = Orologio()
    pagina = StitchFinta(orologio, secondi_di_lavoro=0)
    registro: list[str] = []
    prepara(pagina, orologio, registro)
    dsp._GENERATION_BASELINE.clear()  # nessuno ha scattato la foto
    pagina.main_frame.testo = "Generate a website\nThinking...\nExport\n"
    pagina.fine_lavoro = None

    esito = dsp.wait_for_generation_complete(pagina, 900_000)
    durata = int(orologio.t - 1000)
    ok = esito is True and durata < 600
    print(f"  esito={esito} dopo {durata}s (deve concludere, non incastrarsi fino ai 900s)")
    print(f"  [{'OK' if ok else 'PROBLEMA'}]")
    return ok


def main() -> int:
    esiti = [
        # Stitch normale: la fase 1 finisce in 90s, /animate deve partire dopo.
        giro("giro normale, UI inglese", secondi_di_lavoro=90, atteso_fasi=2),
        # Stitch lento: 7 minuti di "Thinking...". Non deve mandare /animate
        # prima, ne' arrendersi.
        giro("Stitch lentissimo (7 min di Thinking)", secondi_di_lavoro=420, atteso_fasi=2),
        giro_senza_foto(),
    ]
    print("\n" + "=" * 70)
    print("TUTTI OK" if all(esiti) else "QUALCOSA NON VA")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
