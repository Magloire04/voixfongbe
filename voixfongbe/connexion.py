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
CODES_PAR_JOUR = 3  # par adresse
CODES_PAR_JOUR_EN_TOUT = 10  # pour tout le service : la boîte de l'administrateur n'est pas inondée
SEUIL_ALERTE = 10  # mots de passe faux en une heure, toutes adresses confondues
FENETRE_ALERTE = timedelta(hours=1)
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
        d.setdefault("codes", [])
        if d.get("code"):  # première version : un seul code en cours
            d["codes"].append(d["code"])
        d.pop("code", None)
        d.setdefault("envois", {"jour": None, "n": 0, "dernier": None})
        d.setdefault("echecs_globaux", [])  # heures des mots de passe faux de la dernière heure
        d.setdefault("alerte_le", None)
        return d

    @staticmethod
    def _poser_mdp(d: dict, mdp: str) -> None:
        # Un nouveau mot de passe lève aussi les blocages : qui l'a changé peut se connecter tout de suite.
        d.update(mdp=empreinte_mdp(mdp), sessions={}, codes=[], echecs={})

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

    @staticmethod
    def _recents(d: dict, maintenant: datetime) -> list[str]:
        return [t for t in d["echecs_globaux"] if maintenant - _date(t) <= FENETRE_ALERTE]

    def alerte_due(self, maintenant: datetime) -> int | None:
        """Le nombre de mots de passe faux de la dernière heure, toutes adresses confondues, s'il atteint
        le seuil et qu'aucune alerte n'est partie dans l'heure ; sinon None. Le blocage par adresse ne voit
        pas un attaquant qui change d'adresse ; un blocage commun, lui, l'empêcherait de se connecter
        aussi : on prévient donc l'administrateur, sans rien bloquer de plus."""
        with verrou(self.chemin):
            d = self._lire()
            recents = self._recents(d, maintenant)
            deja = d["alerte_le"] and maintenant - _date(d["alerte_le"]) <= FENETRE_ALERTE
            if len(recents) < SEUIL_ALERTE or deja:
                return None
            d["alerte_le"] = _iso(maintenant)
            ecrire_json(self.chemin, d)
        return len(recents)

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
        return self._essayer(mdp, ip, maintenant, session=True)

    def confirmer(self, mdp: str, ip: str, maintenant: datetime) -> bool:
        """Revérifie le mot de passe avant une action sensible, sans ouvrir de session. Une erreur
        compte comme une erreur de connexion : trois en 10 minutes bloquent l'adresse."""
        return self._essayer(mdp, ip, maintenant, session=False) is not None

    def _essayer(self, mdp: str, ip: str, maintenant: datetime, session: bool) -> str | None:
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
                d["echecs_globaux"] = self._recents(d, maintenant)[-999:] + [_iso(maintenant)]
                ecrire_json(self.chemin, d)
                return None
            d["echecs"].pop(cle_ip, None)
            jeton = ""
            if session:
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
    def demander_code(self, maintenant: datetime, ip: str = "inconnue") -> str:
        """Un code de 8 chiffres, valable 10 minutes. Par adresse : un code toutes les 10 minutes et 3 par
        jour ; pour tout le service : 10 par jour (la boîte de l'administrateur). Ainsi une seule adresse ne
        peut pas épuiser les codes des autres. Un nouveau code s'ajoute à ceux en cours sans les remplacer."""
        local = maintenant.astimezone(FUSEAU)
        jour = local.date().isoformat()
        minuit = datetime.combine(local.date() + timedelta(days=1), time(0), FUSEAU)
        cle_ip = _sha(f"code|{ip}")
        with verrou(self.chemin):
            d = self._lire()
            if not d["mdp"]:
                raise PasConfigure()
            envois = d["envois"] if d["envois"].get("jour") == jour else {"jour": jour, "n": 0, "ips": {}}
            envois.setdefault("ips", {})
            par_ip = envois["ips"].get(cle_ip, {"n": 0, "dernier": None})
            if par_ip["dernier"] and maintenant - _date(par_ip["dernier"]) < ECART_CODES:
                raise TropDeCodes(_secondes(_date(par_ip["dernier"]) + ECART_CODES - maintenant))
            if par_ip["n"] >= CODES_PAR_JOUR or envois["n"] >= CODES_PAR_JOUR_EN_TOUT:
                raise TropDeCodes(_secondes(minuit - local))
            code = f"{secrets.randbelow(10 ** 8):08d}"
            sel = secrets.token_hex(16)
            d["codes"] = self._codes_ouverts(d, maintenant) + [{
                "sel": sel, "empreinte": _sha(sel + code), "expire_le": _iso(maintenant + DUREE_CODE),
                "essais": ESSAIS_CODE}]
            envois["ips"][cle_ip] = {"n": par_ip["n"] + 1, "dernier": _iso(maintenant)}
            envois["n"] += 1
            d["envois"] = envois
            ecrire_json(self.chemin, d)
        return code

    @staticmethod
    def _codes_ouverts(d: dict, maintenant: datetime) -> list[dict]:
        return [c for c in d["codes"] if c["essais"] > 0 and maintenant <= _date(c["expire_le"])]

    def changer_avec_code(self, code: str, nouveau: str, maintenant: datetime) -> bool:
        if not isinstance(nouveau, str) or len(nouveau) < MDP_MIN:
            raise ValueError(f"le mot de passe doit faire au moins {MDP_MIN} caractères")
        with verrou(self.chemin):
            d = self._lire()
            ouverts = self._codes_ouverts(d, maintenant)
            if not ouverts:
                return False
            bon = False
            for attendu in ouverts:  # tout comparer : durée constante
                if hmac.compare_digest(_sha(attendu["sel"] + str(code)), attendu["empreinte"]):
                    bon = True
            if not bon:
                # Chaque erreur coûte un essai à tous les codes en cours : 5 essais en tout, même si
                # plusieurs codes ont été demandés.
                for attendu in ouverts:
                    attendu["essais"] -= 1
                d["codes"] = ouverts
                ecrire_json(self.chemin, d)
                return False
            self._poser_mdp(d, nouveau)
            ecrire_json(self.chemin, d)
        return True
