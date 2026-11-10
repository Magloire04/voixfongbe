"""Connexion de l'administrateur : mot de passe (empreinte scrypt, comme AgriFon), sessions partagées
entre les processus par le fichier admin.json, blocage après trois mots de passe faux, et code de
mot de passe oublié envoyé par e-mail.

Rien n'est gardé en clair : ni le mot de passe, ni les jetons de session, ni le code, ni l'IP.
"""

import hashlib
import hmac
import math
import re
import secrets
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from .quotas import FUSEAU
from .stockage import ecrire_json, lire_json, verrou

MDP_MIN = 12
DUREE_SESSION = timedelta(minutes=10)
ESSAIS_MDP = 3
BLOCAGE = timedelta(minutes=10)
DUREE_CODE = timedelta(minutes=10)
ESSAIS_CODE = 5
ECART_CODES = timedelta(minutes=10)
CODES_PAR_JOUR = 3
EMPREINTE = re.compile(r"^scrypt:([0-9a-f]{32}):([0-9a-f]{128})$")


class Bloque(Exception):
    def __init__(self, attente_s: int):
        super().__init__(attente_s)
        self.attente_s = attente_s


class TropDeCodes(Exception):
    def __init__(self, attente_s: int):
        super().__init__(attente_s)
        self.attente_s = attente_s


class PasConfigure(Exception):
    pass


def _scrypt(mdp: str, sel: bytes) -> bytes:
    # Réglages par défaut de crypto.scrypt de Node : la même empreinte qu'AgriFon.
    return hashlib.scrypt(str(mdp).encode("utf-8"), salt=sel, n=16384, r=8, p=1, dklen=64)


def empreinte_mdp(mdp: str) -> str:
    sel = secrets.token_bytes(16)
    return f"scrypt:{sel.hex()}:{_scrypt(mdp, sel).hex()}"


def mdp_correct(mdp: str, empreinte: str) -> bool:
    m = EMPREINTE.match(empreinte or "")
    if not m:
        return False
    return hmac.compare_digest(_scrypt(mdp, bytes.fromhex(m.group(1))).hex(), m.group(2))


def _sha(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _date(texte: str) -> datetime:
    return datetime.fromisoformat(texte)


def _secondes(duree: timedelta) -> int:
    return max(1, math.ceil(duree.total_seconds()))


class Connexion:
    def __init__(self, chemin: Path):
        self.chemin = Path(chemin)

    def _lire(self) -> dict:
        d = lire_json(self.chemin, {})
        d.setdefault("mdp", None)
        d.setdefault("sessions", {})
        d.setdefault("echecs", {})
        d.setdefault("code", None)
        d.setdefault("envois", {"jour": None, "n": 0, "dernier": None})
        return d

    @staticmethod
    def _poser_mdp(d: dict, mdp: str) -> None:
        # Un nouveau mot de passe lève aussi les blocages : qui l'a changé peut se connecter tout de suite.
        d.update(mdp=empreinte_mdp(mdp), sessions={}, code=None, echecs={})

    @staticmethod
    def _echecs_vivants(d: dict, maintenant: datetime) -> dict:
        """Les échecs qui comptent encore : un blocage en cours, ou des erreurs de moins de 10 minutes."""
        vivants = {}
        for cle, echec in d["echecs"].items():
            fin = echec.get("bloque_jusqu")
            debut = echec.get("depuis")
            if (fin and maintenant < _date(fin)) or (debut and maintenant - _date(debut) <= BLOCAGE):
                vivants[cle] = echec
        return vivants

    def configure(self) -> bool:
        return bool(self._lire()["mdp"])

    def definir_mdp(self, mdp: str, maintenant: datetime) -> None:
        if not isinstance(mdp, str) or len(mdp) < MDP_MIN:
            raise ValueError(f"le mot de passe doit faire au moins {MDP_MIN} caractères")
        with verrou(self.chemin):
            d = self._lire()
            self._poser_mdp(d, mdp)
            ecrire_json(self.chemin, d)

    # Sessions
    def ouvrir(self, mdp: str, ip: str, maintenant: datetime) -> str | None:
        cle_ip = _sha(f"ip|{ip}")
        neuf = {"n": 0, "depuis": None, "bloque_jusqu": None}
        with verrou(self.chemin):
            d = self._lire()
            echec = {**neuf, **d["echecs"].get(cle_ip, {})}
            if echec["bloque_jusqu"]:
                fin = _date(echec["bloque_jusqu"])
                if maintenant < fin:
                    raise Bloque(_secondes(fin - maintenant))
                echec = dict(neuf)
            elif echec["depuis"] and maintenant - _date(echec["depuis"]) > BLOCAGE:
                echec = dict(neuf)  # trois erreurs comptent si elles tombent dans les mêmes 10 minutes
            if not d["mdp"]:
                return None
            if not mdp_correct(mdp, d["mdp"]):
                if not echec["n"]:
                    echec["depuis"] = _iso(maintenant)
                echec["n"] += 1
                if echec["n"] >= ESSAIS_MDP:
                    echec = {**neuf, "bloque_jusqu": _iso(maintenant + BLOCAGE)}
                d["echecs"] = {**self._echecs_vivants(d, maintenant), cle_ip: echec}
                ecrire_json(self.chemin, d)
                return None
            d["echecs"].pop(cle_ip, None)
            jeton = secrets.token_urlsafe(32)
            d["sessions"][_sha(jeton)] = _iso(maintenant)
            ecrire_json(self.chemin, d)
        return jeton

    def valide(self, jeton: str | None, maintenant: datetime) -> bool:
        if not jeton:
            return False
        empreinte = _sha(jeton)
        with verrou(self.chemin):
            d = self._lire()
            vivantes = {e: vu for e, vu in d["sessions"].items() if maintenant - _date(vu) <= DUREE_SESSION}
            trouve = None
            for e in vivantes:
                if hmac.compare_digest(e, empreinte):
                    trouve = e
            if trouve:
                vivantes[trouve] = _iso(maintenant)
            if trouve or vivantes != d["sessions"]:
                d["sessions"] = vivantes
                ecrire_json(self.chemin, d)
        return trouve is not None

    def fermer(self, jeton: str | None) -> None:
        if not jeton:
            return
        with verrou(self.chemin):
            d = self._lire()
            if d["sessions"].pop(_sha(jeton), None) is not None:
                ecrire_json(self.chemin, d)

    # Mot de passe oublié
    def demander_code(self, maintenant: datetime) -> str:
        local = maintenant.astimezone(FUSEAU)
        jour = local.date().isoformat()
        with verrou(self.chemin):
            d = self._lire()
            if not d["mdp"]:
                raise PasConfigure()
            envois = d["envois"] if d["envois"]["jour"] == jour else {"jour": jour, "n": 0, "dernier": None}
            if envois["dernier"] and maintenant - _date(envois["dernier"]) < ECART_CODES:
                raise TropDeCodes(_secondes(_date(envois["dernier"]) + ECART_CODES - maintenant))
            if envois["n"] >= CODES_PAR_JOUR:
                minuit = datetime.combine(local.date() + timedelta(days=1), time(0), FUSEAU)
                raise TropDeCodes(_secondes(minuit - local))
            code = f"{secrets.randbelow(10 ** 8):08d}"
            sel = secrets.token_hex(16)
            d["code"] = {"sel": sel, "empreinte": _sha(sel + code), "expire_le": _iso(maintenant + DUREE_CODE),
                         "essais": ESSAIS_CODE}
            d["envois"] = {"jour": jour, "n": envois["n"] + 1, "dernier": _iso(maintenant)}
            ecrire_json(self.chemin, d)
        return code

    def changer_avec_code(self, code: str, nouveau: str, maintenant: datetime) -> bool:
        if not isinstance(nouveau, str) or len(nouveau) < MDP_MIN:
            raise ValueError(f"le mot de passe doit faire au moins {MDP_MIN} caractères")
        with verrou(self.chemin):
            d = self._lire()
            attendu = d["code"]
            if not attendu or attendu["essais"] <= 0 or maintenant > _date(attendu["expire_le"]):
                return False
            if not hmac.compare_digest(_sha(attendu["sel"] + str(code)), attendu["empreinte"]):
                attendu["essais"] -= 1
                ecrire_json(self.chemin, d)
                return False
            self._poser_mdp(d, nouveau)
            ecrire_json(self.chemin, d)
        return True
