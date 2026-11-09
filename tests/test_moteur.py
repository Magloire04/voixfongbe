import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy

from voixfongbe.moteur import ModeleIndisponible, Moteur
from voixfongbe.texte import charger_vocabulaire, identifiants, preparer

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "tests" / "donnees"
MODELE_REEL = RACINE / "modele"
VOCAB = charger_vocabulaire(DONNEES / "vocab.json")


class TestMoteur(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)

    def faux_modele(self, empreinte_juste: bool):
        (self.dossier / "model.onnx").write_bytes(b"pas un vrai modele")
        shutil.copy2(DONNEES / "vocab.json", self.dossier / "vocab.json")
        contenu = b"pas un vrai modele" if empreinte_juste else b"autre chose"
        (self.dossier / "empreinte.txt").write_text(hashlib.sha256(contenu).hexdigest() + "\n")

    def test_empreinte_fausse_rend_le_moteur_indisponible(self):
        self.faux_modele(empreinte_juste=False)
        self.assertFalse(Moteur(self.dossier).pret())
        with self.assertRaises(ModeleIndisponible):
            Moteur(self.dossier).synthetiser([0, 5, 0])

    def test_dossier_vide_rend_le_moteur_indisponible(self):
        moteur = Moteur(self.dossier)
        self.assertFalse(moteur.pret())
        self.assertIsNone(moteur.version)

    def test_empreinte_juste_donne_version_et_vocabulaire(self):
        self.faux_modele(empreinte_juste=True)
        moteur = Moteur(self.dossier)
        self.assertTrue(moteur.pret())
        self.assertEqual(moteur.version, hashlib.sha256(b"pas un vrai modele").hexdigest()[:12])
        self.assertEqual(moteur.vocabulaire["_"], 0)

    def test_modele_illisible_malgre_empreinte_juste_rend_indisponible(self):
        self.faux_modele(empreinte_juste=True)
        moteur = Moteur(self.dossier)
        with self.assertRaises(ModeleIndisponible):
            moteur.synthetiser([0, 5, 0])
        self.assertFalse(moteur.pret())

    @unittest.skipUnless((MODELE_REEL / "model.onnx").exists(), "modèle absent")
    def test_vraie_synthese_donne_un_son_de_16_khz(self):
        son = Moteur(MODELE_REEL).synthetiser(identifiants(preparer("Mi kú abɔ.", VOCAB), VOCAB))
        self.assertEqual(son.dtype, numpy.float32)
        self.assertEqual(son.ndim, 1)
        self.assertGreater(len(son), 16000 * 0.3)


if __name__ == "__main__":
    unittest.main()
