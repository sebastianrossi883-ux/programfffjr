"""Simulazione della logica di attesa, senza browser.

Si lancia a mano: python3 test_wait_for_generation.py

Playwright non c'e' in questo ambiente: si stubba il modulo e si guida un
finto orologio, cosi' i 900s di timeout scorrono in millisecondi reali.
"""
import pathlib
import sys, types, importlib

# --- stub playwright ---
pw = types.ModuleType("playwright")
sync_api = types.ModuleType("playwright.sync_api")
class Error(Exception): pass
class TimeoutError(Error): pass
sync_api.Error = Error
sync_api.TimeoutError = TimeoutError
sync_api.sync_playwright = lambda: None
pw.sync_api = sync_api
sys.modules["playwright"] = pw
sys.modules["playwright.sync_api"] = sync_api

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
dsp = importlib.import_module("download_stitch_project")


class FakeClock:
    def __init__(self): self.t = 1000.0
    def time(self): return self.t
    def sleep(self, s): self.t += s


class FakeLocator:
    def __init__(self, owner): self.owner = owner
    def inner_text(self, timeout=0): return self.owner.text


class FakeFrame:
    def __init__(self, url, text): self.url, self.text = url, text
    def locator(self, sel): return FakeLocator(self)


class FakePage:
    """La pagina e' guidata da uno script: (secondi, testo UI, [anteprime]).

    `pre_send` e' lo stato al momento di mark_generation_baseline(): il canvas
    della fase precedente, con la chat com'era prima di premere invio.
    """
    def __init__(self, clock, script, pre_send):
        self.clock, self.script, self.pre_send = clock, script, pre_send
        self.url = "https://stitch.withgoogle.com/projects/123"
        self.main_frame = FakeFrame(self.url, "")
        self._previews = []
        self.congelata = True  # finche' True mostra lo stato pre-invio
        self.keyboard = types.SimpleNamespace(press=lambda k: None)
        self._apply()

    def _apply(self):
        if self.congelata:
            self.main_frame.text, self._previews = self.pre_send
            return
        trascorso = self.clock.t - 1000.0
        for inizio, testo, previews in self.script:
            if trascorso >= inizio:
                self.main_frame.text = testo
                self._previews = previews

    def wait_for_timeout(self, ms):
        self.clock.sleep(ms / 1000.0)
        self._apply()

    @property
    def frames(self):
        self._apply()
        return [self.main_frame] + [FakeFrame(u, t) for u, t in self._previews]


CHAT_FASE1 = "Generazione schermata in corso...\nEcco il sito.\nEsporta\n"
SITO_V1 = [("about:screen1", "Tenuta Montelvino " + "x" * 4000)]
SITO_V2 = [("about:screen1", "Tenuta Montelvino animata " + "y" * 9000)]


def run(nome, script, pre_send, attesi):
    clock = FakeClock()
    dsp.time = clock
    page = FakePage(clock, script, pre_send)
    dsp.mark_generation_baseline(page)  # come fa send() prima di premere invio
    page.congelata = False
    page._apply()
    t0 = clock.t
    esito = dsp.wait_for_generation_complete(page, 900_000)
    durata = int(clock.t - t0)
    ok = esito is attesi[0]
    nota = ""
    if len(attesi) > 1:  # soglia: non deve concludere prima di N secondi
        ok = ok and durata >= attesi[1]
        nota = f", non prima di {attesi[1]}s"
    print(f"[{'OK ' if ok else 'KO '}] {nome}: esito={esito} dopo {durata}s (atteso {attesi[0]}{nota})")
    return ok


print("=" * 78)
tutti = []

# 1. IL BUG SEGNALATO: fase 1 finita, ma la frase di stato resta in chat.
#    Il vecchio codice restava incastrato fino ai 900s e non mandava mai /animate.
tutti.append(run(
    "fase 1 finita, frase 'in corso' rimasta in cronologia",
    [(0, CHAT_FASE1, SITO_V2)],
    pre_send=("Fase 1 inviata.\nEsporta\n", SITO_V1),
    attesi=(True,),
))

# 2. NON DEVE PARTIRE PRIMA: 200s di generazione vera, testo che cambia.
tutti.append(run(
    "generazione vera lunga: non conclude prima della fine",
    [(0, "Generazione schermata in corso... (1/6)", SITO_V1),
     (60, "Generazione schermata in corso... (3/6)", SITO_V1),
     (140, "Generazione schermata in corso... (5/6)", SITO_V1),
     (200, CHAT_FASE1, SITO_V2)],
    pre_send=("Fase 1 inviata.\nEsporta\n", SITO_V1),
    attesi=(True, 200),
))

# 3. Stitch risponde solo a parole e non genera niente: deve dire NO, presto.
tutti.append(run(
    "Stitch risponde a parole e non genera: rifiuto rapido",
    [(0, "Ho preparato l'inventario. Procedo ora alla generazione.\nEsporta\n", SITO_V1)],
    pre_send=("Fase 1 inviata.\nEsporta\n", SITO_V1),
    attesi=(False,),
))

# 4. Il canvas di prima e' ancora li' e non succede niente: non deve concludere.
tutti.append(run(
    "solo la schermata vecchia, nessun lavoro nuovo: non conclude",
    [(0, "Esporta\n", SITO_V1)],
    pre_send=("Esporta\n", SITO_V1),
    attesi=(False,),
))

# 5. Gli allegati .md diventano schede documento e MUOVONO il canvas senza
#    che sia stato generato niente. Non deve bastare per dire "finito".
DOCS = SITO_V1 + [("about:doc1", "CURRENT_MOTION_DIRECTION.md"),
                  ("about:doc2", "stitch_motion_preview_kit.md")]
#    Con la sola prova debole la conclusione arriva solo in fondo al budget
#    (60% di 900s = 540s), mai nei primi minuti.
tutti.append(run(
    "allegati che muovono il canvas: non li scambia per generazione",
    [(0, "/animate ... \nEsporta\n", DOCS)],
    pre_send=("Esporta\n", SITO_V1),
    attesi=(True, 540),
))

# 6. Stesso avvio (allegati sul canvas), ma poi la generazione parte davvero:
#    deve concludere, e solo dopo che il sito animato e' comparso.
tutti.append(run(
    "allegati sul canvas, poi generazione vera: conclude alla fine",
    [(0, "/animate ...\nEsporta\n", DOCS),
     (20, "Generazione schermata in corso...", DOCS),
     (90, "Generazione schermata in corso... (4/6)", DOCS),
     (150, "Generazione schermata in corso...\nEcco il sito animato.\nEsporta\n",
      SITO_V2 + DOCS[1:])],
    pre_send=("Esporta\n", SITO_V1),
    attesi=(True, 150),
))

print("=" * 78)
print("TUTTI OK" if all(tutti) else "QUALCOSA NON VA")
sys.exit(0 if all(tutti) else 1)
