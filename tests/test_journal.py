import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


if __name__ == "__main__":
    unittest.main()
