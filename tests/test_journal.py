import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from voixfongbe.journal import Journal

T = datetime(2026, 11, 9, 23, 30, tzinfo=timezone.utc)  # déjà le 10 novembre à Porto-Novo


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)

    def noter(self, journal, maintenant=T):
        journal.noter(projet="demo", caracteres=42, format="mp3", duree_ms=850, cache=False, code=200,
                      maintenant=maintenant)

    def test_journal_ne_contient_jamais_le_texte(self):
        self.noter(Journal(self.dossier))
        ligne = json.loads((self.dossier / "journal-2026-11-10.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(set(ligne), {"date", "projet", "caracteres", "format", "duree_ms", "cache", "code"})
        self.assertEqual((ligne["projet"], ligne["caracteres"], ligne["code"]), ("demo", 42, 200))

    def test_une_ligne_par_demande(self):
        journal = Journal(self.dossier)
        self.noter(journal)
        self.noter(journal)
        self.assertEqual(len((self.dossier / "journal-2026-11-10.jsonl").read_text().splitlines()), 2)

    def test_journal_purge_apres_90_jours(self):
        jour = datetime(2026, 11, 10).date()
        vieux = self.dossier / f"journal-{jour - timedelta(days=91)}.jsonl"
        recent = self.dossier / f"journal-{jour - timedelta(days=89)}.jsonl"
        vieux.write_text("{}\n")
        recent.write_text("{}\n")
        self.noter(Journal(self.dossier, jours=90))
        self.assertFalse(vieux.exists())
        self.assertTrue(recent.exists())

    # Lecture pour l'onglet Appels
    JOUR = date(2026, 11, 10)

    def ligne(self, journal, minute, projet="demo", code=200, duree_ms=850, cache=False):
        journal.noter(projet=projet, caracteres=42, format="mp3", duree_ms=duree_ms, cache=cache, code=code,
                      maintenant=T + timedelta(minutes=minute))

    def test_lire_filtre_par_projet(self):
        journal = Journal(self.dossier)
        self.ligne(journal, 0, "demo")
        self.ligne(journal, 1, "alpha")
        self.ligne(journal, 2, None, code=401)
        lu = journal.lire(self.JOUR, projet="alpha")
        self.assertEqual((lu["total"], [x["projet"] for x in lu["lignes"]]), (1, ["alpha"]))
        self.assertEqual(journal.lire(self.JOUR)["total"], 3)

    def test_pagination(self):
        journal = Journal(self.dossier)
        for minute in range(120):
            self.ligne(journal, minute)
        page1 = journal.lire(self.JOUR)
        self.assertEqual((page1["total"], page1["page"], page1["pages"], len(page1["lignes"])), (120, 1, 3, 50))
        self.assertTrue(page1["lignes"][0]["date"].endswith("T02:29:00+01:00"))  # la plus récente d'abord
        page3 = journal.lire(self.JOUR, page=3)
        self.assertEqual(len(page3["lignes"]), 20)
        self.assertEqual(journal.lire(self.JOUR, page=4)["lignes"], [])

    def test_jour_sans_fichier(self):
        lu = Journal(self.dossier).lire(self.JOUR)
        self.assertEqual((lu["total"], lu["pages"], lu["lignes"]), (0, 1, []))
        self.assertEqual(Journal(self.dossier).resume(self.JOUR),
                         {"demandes": 0, "erreurs": 0, "temps_moyen_ms": None})

    def test_ligne_abimee_sautee(self):
        journal = Journal(self.dossier)
        self.ligne(journal, 0)
        with open(self.dossier / "journal-2026-11-10.jsonl", "a", encoding="utf-8") as f:
            f.write("{pas du json\n\n[1, 2]\n")
        self.ligne(journal, 1)
        self.assertEqual(journal.lire(self.JOUR)["total"], 2)

    def test_resume(self):
        journal = Journal(self.dossier)
        self.ligne(journal, 0, duree_ms=1000)
        self.ligne(journal, 1, duree_ms=3000)
        self.ligne(journal, 2, duree_ms=10, cache=True)
        self.ligne(journal, 3, None, code=401, duree_ms=1)
        self.ligne(journal, 4, code=429, duree_ms=2)
        self.assertEqual(journal.resume(self.JOUR), {"demandes": 5, "erreurs": 2, "temps_moyen_ms": 2000})

    def test_jours(self):
        journal = Journal(self.dossier)
        self.ligne(journal, 0)
        self.ligne(journal, 60 * 24)
        (self.dossier / "autre.txt").write_text("x")
        self.assertEqual(journal.jours_disponibles(), ["2026-11-11", "2026-11-10"])


if __name__ == "__main__":
    unittest.main()
