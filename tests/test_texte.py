import json
import unicodedata
import unittest
from pathlib import Path

from voixfongbe.texte import borner, caracteres_ignores, charger_vocabulaire, decouper, identifiants, preparer

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

    # Synthèse par morceaux (mémoire bornée)
    def test_decouper_garde_un_texte_court_entier(self):
        self.assertEqual(decouper("Mi kú abɔ. Un na xlɛ́ mi.", 120), ["Mi kú abɔ. Un na xlɛ́ mi."])

    def test_decouper_regroupe_les_phrases_jusqu_au_maximum(self):
        phrases = ["Mi kú abɔ ɖo gle ɔ mɛ."] * 10  # 22 caractères chacune
        morceaux = decouper(" ".join(phrases), 50)
        self.assertEqual(morceaux, ["Mi kú abɔ ɖo gle ɔ mɛ. Mi kú abɔ ɖo gle ɔ mɛ."] * 5)

    def test_decouper_coupe_une_phrase_trop_longue_aux_virgules_puis_aux_espaces(self):
        texte = "mi zìn mikló ɔ, mi ɖɔ nǔ ɔ sín nyǐkɔ kpo axi ɔ sín nyǐkɔ kpo, bo lɛ́ zìn ényí mi fó xó ɔ"
        morceaux = decouper(texte, 30)
        self.assertTrue(all(len(m) <= 30 for m in morceaux), morceaux)
        self.assertEqual(" ".join(morceaux).split(), texte.split())  # aucun mot coupé ni perdu
        self.assertTrue(morceaux[0].endswith(","))

    def test_decouper_ne_garde_pas_de_morceau_vide(self):
        self.assertEqual(decouper("  Mi kú.  \n\n  Abɔ !  ", 120), ["Mi kú. Abɔ !"])
        self.assertEqual(decouper("   ", 120), [])

    def test_decouper_coupe_un_mot_trop_long(self):
        morceaux = decouper("a" * 300, 120)
        self.assertTrue(all(len(m) <= 120 for m in morceaux), [len(m) for m in morceaux])
        self.assertEqual("".join(morceaux), "a" * 300)

    def test_borner_coupe_un_texte_prepare_trop_long_sans_isoler_un_accent(self):
        prepare = "ń" * 100  # 200 symboles : ń décomposé
        morceaux = borner(prepare, 120)
        self.assertTrue(all(len(m) <= 120 for m in morceaux), [len(m) for m in morceaux])
        self.assertEqual("".join(morceaux), prepare)
        self.assertFalse(any(unicodedata.combining(m[0]) for m in morceaux))

    def test_borner_laisse_un_texte_court_intact(self):
        self.assertEqual(borner("mi kú abɔ", 120), ["mi kú abɔ"])

    def test_apostrophe_typographique_devient_apostrophe(self):
        for apostrophe in ("’", "‘", "ʼ"):
            self.assertEqual(preparer(f"n{apostrophe}a", VOCAB), "n'a")


if __name__ == "__main__":
    unittest.main()
