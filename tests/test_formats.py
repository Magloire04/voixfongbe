import unittest

from voixfongbe.formats import LIMITE_MAX, valider_courriel, valider_limite


class TestFormats(unittest.TestCase):
    def test_courriel_valide(self):
        self.assertEqual(valider_courriel("  koffi@exemple.bj "), "koffi@exemple.bj")
        for mauvais in ("a@b", "<a@b.bj>", "x@y.bj\r\nBcc: z@w.bj", "x" * 245 + "@exemple.bj", "", None, 12):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                valider_courriel(mauvais)

    def test_limite_valide(self):
        self.assertEqual(valider_limite(1), 1)
        self.assertEqual(valider_limite(LIMITE_MAX), 1_000_000)
        for mauvaise in (0, 1_000_001, True, "100", 2.5, None):
            with self.assertRaises(ValueError, msg=repr(mauvaise)):
                valider_limite(mauvaise)


if __name__ == "__main__":
    unittest.main()
