"""Encodage du son de la voix : WAV (PCM 16 bits) ou MP3 (lameenc), mono, 16 kHz."""

import io
import wave

import lameenc
import numpy

TAUX = 16000


def _pcm16(echantillons: numpy.ndarray) -> bytes:
    return (numpy.clip(echantillons, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def en_wav(echantillons: numpy.ndarray, taux: int = TAUX) -> bytes:
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taux)
        w.writeframes(_pcm16(echantillons))
    return tampon.getvalue()


def en_mp3(echantillons: numpy.ndarray, taux: int = TAUX, debit_kbps: int = 48) -> bytes:
    encodeur = lameenc.Encoder()
    encodeur.set_bit_rate(debit_kbps)
    encodeur.set_in_sample_rate(taux)
    encodeur.set_channels(1)
    encodeur.set_quality(2)
    return bytes(encodeur.encode(_pcm16(echantillons)) + encodeur.flush())
