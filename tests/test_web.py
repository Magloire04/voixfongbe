import unittest

from voixfongbe.web import ip_client


def adresse(remote=None, xff=None):
    environ = {}
    if remote is not None:
        environ["REMOTE_ADDR"] = remote
    if xff is not None:
        environ["HTTP_X_FORWARDED_FOR"] = xff
    return ip_client(environ)


class TestIpClient(unittest.TestCase):
    def test_derriere_le_relais_local_derniere_entree(self):
        # LiteSpeed sur le même serveur : l'application voit 127.0.0.1, la vraie adresse est ajoutée en dernier.
        self.assertEqual(adresse("127.0.0.1", "10.0.0.1, 203.0.113.7"), "203.0.113.7")
        self.assertEqual(adresse("::1", "203.0.113.7"), "203.0.113.7")
        self.assertEqual(adresse("10.1.2.3", "203.0.113.7"), "203.0.113.7")

    def test_client_en_direct_en_tete_ignore(self):
        # Sans relais, l'en-tête vient du client : il ne doit pas choisir l'adresse comptée.
        self.assertEqual(adresse("41.138.89.7", "203.0.113.9"), "41.138.89.7")
        self.assertEqual(adresse("2a01:4f8::5", "203.0.113.9"), "2a01:4f8::5")

    def test_sans_en_tete(self):
        self.assertEqual(adresse("127.0.0.1"), "127.0.0.1")
        self.assertEqual(adresse("41.138.89.7"), "41.138.89.7")
        self.assertEqual(adresse(), "inconnue")
        self.assertEqual(adresse(None, "203.0.113.7"), "203.0.113.7")


if __name__ == "__main__":
    unittest.main()
