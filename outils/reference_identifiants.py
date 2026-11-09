"""Écrit tests/donnees/reference_identifiants.json : pour chaque phrase de tests/donnees/phrases.txt,
le texte préparé par voixfongbe.texte.preparer et les identifiants donnés par le vrai tokenizer de
Meta (VitsTokenizer de transformers). Le service doit retrouver exactement ces identifiants.

    python outils/reference_identifiants.py      (dans l'environnement des outils)
"""

import json
import sys
from pathlib import Path

from transformers import AutoTokenizer

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from voixfongbe.texte import charger_vocabulaire, preparer  # noqa: E402

DONNEES = RACINE / "tests" / "donnees"


def main() -> None:
    tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-fon")
    vocab = charger_vocabulaire(DONNEES / "vocab.json")
    cas = []
    for phrase in (DONNEES / "phrases.txt").read_text(encoding="utf-8").splitlines():
        if not phrase.strip():
            continue
        preparee = preparer(phrase, vocab)
        cas.append({"phrase": phrase, "preparee": preparee, "identifiants": tokenizer(preparee).input_ids})
    (DONNEES / "reference_identifiants.json").write_text(
        json.dumps(cas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(cas)} phrases de référence écrites.")


if __name__ == "__main__":
    main()
