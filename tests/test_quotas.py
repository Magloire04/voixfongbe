import multiprocessing
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from voixfongbe.quotas import FUSEAU, Quotas

MIDI = datetime(2026, 11, 9, 12, 0, tzinfo=FUSEAU)


def _consommer_50(chemin: str) -> None:
    q = Quotas(Path(chemin), par_cle=1000, total=1000)
    for _ in range(50):
        q.consommer("demo", MIDI)


class TestQuotas(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "quotas.json"

    def test_centieme_demande_passe_la_suivante_attend_minuit(self):
        q = Quotas(self.chemin, par_cle=100, total=300)
        t = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
        for _ in range(100):
            self.assertIsNone(q.consommer("demo", t))
        self.assertEqual(q.consommer("demo", t), 5400)

    def test_heure_utc_ramenee_a_porto_novo(self):
        q = Quotas(self.chemin, par_cle=1, total=300)
        t = datetime(2026, 11, 9, 22, 30, tzinfo=timezone.utc)  # 23 h 30 à Porto-Novo
        self.assertIsNone(q.consommer("demo", t))
        self.assertEqual(q.consommer("demo", t), 1800)

    def test_compteurs_repartent_le_lendemain(self):
        q = Quotas(self.chemin, par_cle=2, total=300)
        soir = datetime(2026, 11, 9, 23, 59, tzinfo=FUSEAU)
        q.consommer("demo", soir)
        q.consommer("demo", soir)
        self.assertIsNotNone(q.consommer("demo", soir))
        self.assertIsNone(q.consommer("demo", soir + timedelta(minutes=2)))

    def test_plafond_total_tous_projets(self):
        q = Quotas(self.chemin, par_cle=100, total=3)
        for projet in ("a", "b", "c"):
            self.assertIsNone(q.consommer(projet, MIDI))
        self.assertIsNotNone(q.consommer("d", MIDI))

    def test_demande_refusee_ne_compte_pas(self):
        q = Quotas(self.chemin, par_cle=1, total=2)
        q.consommer("a", MIDI)
        q.consommer("a", MIDI)  # refusée
        self.assertIsNone(q.consommer("b", MIDI))

    def test_rendre_annule_une_consommation(self):
        q = Quotas(self.chemin, par_cle=1, total=300)
        q.consommer("demo", MIDI)
        q.rendre("demo", MIDI)
        self.assertIsNone(q.consommer("demo", MIDI))

    def test_rendre_sans_consommation_ne_fait_rien(self):
        q = Quotas(self.chemin, par_cle=1, total=300)
        q.rendre("demo", MIDI)
        self.assertIsNone(q.consommer("demo", MIDI))
        self.assertIsNotNone(q.consommer("demo", MIDI))

    def test_deux_processus_ne_perdent_aucun_decompte(self):
        processus = [multiprocessing.Process(target=_consommer_50, args=(str(self.chemin),)) for _ in range(2)]
        for p in processus:
            p.start()
        for p in processus:
            p.join(60)
            self.assertEqual(p.exitcode, 0)
        self.assertIsNotNone(Quotas(self.chemin, par_cle=100, total=1000).consommer("demo", MIDI))
        self.assertIsNone(Quotas(self.chemin, par_cle=101, total=1000).consommer("demo", MIDI))


if __name__ == "__main__":
    unittest.main()
