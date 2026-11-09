import shutil
import tempfile
import unittest
from pathlib import Path

from voixfongbe.cache import Cache


class TestCache(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)

    def test_cache_meme_texte_meme_cle(self):
        self.assertEqual(Cache.cle("v1", "mp3", "mi kú"), Cache.cle("v1", "mp3", "mi kú"))
        self.assertNotEqual(Cache.cle("v1", "mp3", "mi kú"), Cache.cle("v1", "wav", "mi kú"))
        self.assertNotEqual(Cache.cle("v1", "mp3", "mi kú"), Cache.cle("v2", "mp3", "mi kú"))

    def test_cache_absent_rend_none(self):
        self.assertIsNone(Cache(self.dossier).lire(Cache.cle("v1", "mp3", "x")))

    def test_cache_ecrire_puis_lire(self):
        cache = Cache(self.dossier)
        cle = Cache.cle("v1", "mp3", "mi")
        cache.ecrire(cle, b"son")
        self.assertEqual(cache.lire(cle), b"son")

    def test_cache_purge_les_plus_anciens(self):
        cache = Cache(self.dossier, plafond=10)
        cles = [Cache.cle("v1", "mp3", t) for t in ("a", "b", "c")]
        for cle in cles:
            cache.ecrire(cle, b"123456")
        self.assertEqual([cache.lire(c) for c in cles], [None, None, b"123456"])


if __name__ == "__main__":
    unittest.main()
