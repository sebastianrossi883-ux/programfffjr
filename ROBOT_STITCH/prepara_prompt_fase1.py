#!/usr/bin/env python3
"""Ricava il prompt di FASE 1 dalla guida, invece di mandare la guida.

Il problema
-----------
`STITCH_PROMPT_LATEST.txt` oggi contiene "Prompt universale — da reference a
sito": un DOCUMENTO PER UNA PERSONA. Ha PASSO 0, PASSO 1, PASSO 2, PASSO 3,
"Perche' due passaggi", le note operative, l'appendice con il DNA di un'altra
cantina e la checklist finale. Dentro ci sono undici blocchi di codice, e solo
UNO di questi va davvero mandato a Stitch: quello sotto "PASSO 2 —
costruzione (questo va in Stitch)".

Mandare tutto il documento significa consegnare a Stitch, nello stesso
messaggio:

- l'istruzione buona, `STRUCTURE — exactly 6 full-width sections`, sepolta a
  meta' documento dentro un recinto ```text;
- una riga che dice l'opposto: "Per 5 sezioni invece di 6: togli la sezione 4";
- segnaposto mai compilati: {BRAND}, {DESIGN_DNA}, {LANGUAGE}, {VARIABILI};
- il prompt del PASSO 1, che chiede di ANALIZZARE le immagini e restituire una
  scheda - cioe' di non costruire niente;
- un esempio gia' pronto di sito finito, nell'appendice.

Non c'e' modo di indovinare quale pezzo eseguire. Il risultato povero -
due sezioni invece di sei - viene da qui.

Cosa fa questo script
---------------------
Prende la guida, tiene SOLO il blocco del PASSO 2, ci mette dentro il DNA e la
lingua, e scrive un prompt che contiene istruzioni e basta. Se resta anche un
solo segnaposto non compilato, si ferma: meglio non partire che bruciare una
generazione su un prompt incompleto.

    python3 prepara_prompt_fase1.py --dna DNA_CANTINA.txt
    python3 prepara_prompt_fase1.py --dna-da-appendice     # per provare subito
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
GUIDA_DEFAULT = PROJECT_DIR / "STITCH_PROMPT_LATEST.txt"
USCITA_DEFAULT = PROJECT_DIR / "STITCH_PROMPT_FASE1.txt"


def blocco_passo2(guida: str) -> str:
    """Il recinto ```text sotto l'intestazione del PASSO 2, e nessun altro."""
    posizione = re.search(r"^##\s*PASSO\s*2\b.*$", guida, re.M | re.I)
    if not posizione:
        raise SystemExit("Nella guida non trovo l'intestazione '## PASSO 2'.")
    resto = guida[posizione.end():]
    recinto = re.search(r"```[a-zA-Z]*\n(.*?)```", resto, re.S)
    if not recinto:
        raise SystemExit("Sotto il PASSO 2 non trovo nessun blocco di codice.")
    return recinto.group(1).strip()


def dna_dallappendice(guida: str) -> str:
    """Il DNA di esempio in fondo alla guida: serve per provare, non e' il tuo.

    E' il distillato di ALTRE reference. Va bene per verificare che la catena
    funzioni; per il sito vero il DNA si rifa' con il PASSO 1 sulle immagini
    che si stanno usando davvero.
    """
    posizione = re.search(r"^##\s*Appendice\b.*$", guida, re.M | re.I)
    if not posizione:
        raise SystemExit("Nella guida non trovo l'appendice con il DNA di esempio.")
    recinto = re.search(r"```[a-zA-Z]*\n(.*?)```", guida[posizione.end():], re.S)
    if not recinto:
        raise SystemExit("Nell'appendice non trovo il blocco del DNA.")
    return recinto.group(1).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guida", type=Path, default=GUIDA_DEFAULT)
    parser.add_argument("--uscita", type=Path, default=USCITA_DEFAULT)
    parser.add_argument("--dna", type=Path, help="File con il DNA compilato dal PASSO 1.")
    parser.add_argument(
        "--dna-da-appendice",
        action="store_true",
        help="Usa il DNA di esempio della guida. Per provare la catena, non per il sito vero.",
    )
    parser.add_argument("--brand", default="", help="Nome del sito. Vuoto = lo mette il robot.")
    parser.add_argument("--lingua", default="Italian")
    parser.add_argument("--sottotitolo", default="", help="La riga '{ONE LINE: ...}'.")
    args = parser.parse_args()

    guida = args.guida.read_text(encoding="utf-8")
    prompt = blocco_passo2(guida)
    print(f"Blocco PASSO 2 estratto: {len(prompt)} caratteri su {len(guida)} della guida.")

    if args.dna:
        dna = args.dna.read_text(encoding="utf-8").strip()
    elif args.dna_da_appendice:
        dna = dna_dallappendice(guida)
        print("ATTENZIONE: DNA preso dall'appendice. E' il distillato di ALTRE reference:")
        print("            va bene per provare, non per il sito vero.")
    else:
        raise SystemExit(
            "Serve il DNA del PASSO 1: --dna FILE, oppure --dna-da-appendice per una prova."
        )

    prompt = prompt.replace("{DESIGN_DNA}", dna).replace("{LANGUAGE}", args.lingua)
    if args.brand:
        prompt = prompt.replace("{BRAND}", args.brand)
    else:
        # Il robot ha gia' il suo blocco identita' (nome inventato + marchi da
        # escludere) e lo aggiunge in coda: qui si lascia una riga neutra
        # invece di un segnaposto che Stitch stamperebbe cosi' com'e'.
        prompt = prompt.replace(
            'Subject: {BRAND} — {ONE LINE: what it is, where it is}.',
            "Subject: see the IDENTITY block appended at the end of this message.",
        )
        prompt = prompt.replace("{BRAND}", "the brand named in the IDENTITY block")
    if args.sottotitolo:
        prompt = re.sub(r"\{ONE LINE:[^}]*\}", args.sottotitolo, prompt)

    rimasti = sorted(set(re.findall(r"\{[A-Z][A-Z_ ]*[A-Z}]", prompt)))
    if rimasti:
        raise SystemExit(
            f"Segnaposto ancora da compilare: {rimasti}\n"
            "Non scrivo il prompt: Stitch li stamperebbe alla lettera."
        )

    for vietato, perche in (
        ("PASSO 1", "il prompt di analisi: chiederebbe a Stitch di non costruire"),
        ("sezioni invece di 6", "la riga che contraddice le sei sezioni"),
        ("Checklist", "la checklist di verifica, roba per te"),
    ):
        if vietato in prompt:
            raise SystemExit(f"Nel prompt e' rimasto '{vietato}': {perche}.")

    args.uscita.write_text(prompt + "\n", encoding="utf-8")
    print(f"\nScritto: {args.uscita} ({len(prompt)} caratteri)")
    print("Contiene 'exactly 6 full-width sections':", "exactly 6 full-width sections" in prompt)
    print("\nPer usarlo, in STITCH_API_CONFIG.json:")
    print(f'  "prompt_file": "{args.uscita}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
