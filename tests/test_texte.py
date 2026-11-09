import json
import unicodedata
import unittest
from pathlib import Path

from voixfongbe.texte import caracteres_ignores, charger_vocabulaire, identifiants, preparer

DONNEES = Path(__file__).resolve().parent / "donnees"
VOCAB = charger_vocabulaire(DONNEES / "vocab.json")


def reference():
    return json.loads((DONNEES / "reference_identifiants.json").read_text(encoding="utf-8"))


class TestTexte(unittest.TestCase):
    def test_identiques_au_tokenizer_de_reference(self):
        cas = reference()
        self.assertGreaterEqual(len(cas), 30)
        for c in cas:
            self.assertEqual(preparer(c["phrase"], VOCAB), c["preparee"], c["phrase"])
            self.assertEqual(identifiants(c["preparee"], VOCAB), c["identifiants"], c["phrase"])

    def test_nfd_et_nfc_donnent_le_meme_texte(self):
        phrase = "Mi kú abɔ ɖo AgriFon ji."
        self.assertEqual(preparer(unicodedata.normalize("NFD", phrase), VOCAB), preparer(phrase, VOCAB))

    def test_ponctuation_devient_espace_unique(self):
        self.assertEqual(preparer("Mi zìn,  fí élɔ !", VOCAB), "mi zìn fí élɔ")

    def test_texte_sans_symbole_connu_devient_vide(self):
        self.assertEqual(preparer("300 ? 🙂 qr", VOCAB), "")

    def test_accent_inconnu_retire_lettre_gardee(self):
        self.assertEqual(preparer("Ɔ̀ nɔ̀", VOCAB), "ɔ nɔ")

    def test_identifiants_intercales_de_zero(self):
        ids = identifiants("mi", VOCAB)
        self.assertEqual(ids, [0, VOCAB["m"], 0, VOCAB["i"], 0])

    def test_caracteres_ignores_compte_les_chiffres(self):
        self.assertEqual(caracteres_ignores("È nɔ sa 300 F", VOCAB), 3)

    def test_caracteres_ignores_ne_compte_ni_espaces_ni_ponctuation(self):
        self.assertEqual(caracteres_ignores("Mi kú,  abɔ !", VOCAB), 0)

    # Relecture finale
    def test_aucune_lettre_latine_ne_fait_planter_les_identifiants(self):
        for code in [*range(0x41, 0x7B), *range(0xC0, 0x250), *range(0x1E00, 0x1F00)]:
            texte = "ma" + chr(code) + "ma"
            identifiants(preparer(texte, VOCAB), VOCAB)  # ne lève pas KeyError

    def test_lettre_et_accent_connus_gardes_en_deux_symboles(self):
        self.assertEqual(preparer("Mi ń yì", VOCAB), "mi ń yì")

    def test_texte_sans_lettre_devient_vide(self):
        for texte in ("300 - 400", "97-00-00-00", "___", "' - '"):
            self.assertEqual(preparer(texte, VOCAB), "", texte)

    def test_symbole_de_remplissage_retire(self):
        self.assertEqual(preparer("mi_kú", VOCAB), "mikú")

    def test_blancs_deviennent_une_espace(self):
        for texte in ("Mi kú\nabɔ", "Mi kú\tabɔ", "Mi kú abɔ", "Mi kú\r\n abɔ"):
            self.assertEqual(preparer(texte, VOCAB), "mi kú abɔ", repr(texte))

    def test_apostrophe_typographique_devient_apostrophe(self):
        for apostrophe in ("’", "‘", "ʼ"):
            self.assertEqual(preparer(f"n{apostrophe}a", VOCAB), "n'a")


if __name__ == "__main__":
    unittest.main()
