import struct
import unittest

import numpy

from voixfongbe.audio import TAUX, en_mp3, en_wav


class TestAudio(unittest.TestCase):
    def test_wav_a_le_bon_entete(self):
        wav = en_wav(numpy.zeros(16000, numpy.float32))
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(struct.unpack("<H", wav[22:24])[0], 1)  # mono
        self.assertEqual(struct.unpack("<I", wav[24:28])[0], TAUX)
        self.assertEqual(struct.unpack("<H", wav[34:36])[0], 16)  # 16 bits

    def test_wav_ecrete_les_valeurs_hors_bornes(self):
        wav = en_wav(numpy.array([2.0, -2.0], numpy.float32))
        self.assertEqual(struct.unpack("<hh", wav[-4:]), (32767, -32767))

    def test_mp3_commence_par_une_trame_mp3(self):
        mp3 = en_mp3(numpy.sin(numpy.linspace(0, 2000, 16000)).astype(numpy.float32))
        self.assertGreater(len(mp3), 1000)
        self.assertTrue(mp3[:3] == b"ID3" or (mp3[0] == 0xFF and mp3[1] & 0xE0 == 0xE0))


if __name__ == "__main__":
    unittest.main()
