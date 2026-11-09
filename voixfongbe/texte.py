"""Préparation du texte fon pour la voix, et identifiants des symboles.

La voix ne connaît que les 46 symboles de son vocabulaire (vocab.json). La préparation reprend
celle d'AgriFon (scripts/voix/generer.py) : un caractère du vocabulaire est gardé ; sinon on
garde sa lettre de base et les seuls accents connus (aigu, caron) ; la ponctuation devient une
pause ; tout le reste disparaît. Les identifiants reproduisent VitsTokenizer (add_blank) : le
symbole de remplissage (0) est intercalé entre chaque symbole et aux deux bouts.
"""

import json
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path

ACCENTS_CONNUS = {"́", "̌"}  # aigu, caron
PONCTUATION = set(".,;:?!")
APOSTROPHES = {"’": "'", "‘": "'", "ʼ": "'"}
REMPLISSAGE = "_"  # symbole 0 de la voix : jamais pris dans le texte reçu
BLANC = 0


def charger_vocabulaire(chemin: Path) -> dict[str, int]:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def _symboles(c: str, vocabulaire: Mapping[str, int]) -> str | None:
    """Ce que devient un caractère : des symboles connus, une espace, ou None s'il disparaît."""
    if c.isspace():  # retour à la ligne, tabulation, espace insécable : une pause, pas des mots collés
        return " "
    c = APOSTROPHES.get(c, c)
    if c == REMPLISSAGE:
        return None
    if c in vocabulaire:
        return c
    d = unicodedata.normalize("NFD", c)
    if d[0] in vocabulaire:
        return d[0] + "".join(m for m in d[1:] if m in ACCENTS_CONNUS)
    if c in PONCTUATION:
        return " "
    return None


def preparer(texte: str, vocabulaire: Mapping[str, int]) -> str:
    morceaux = []
    for c in unicodedata.normalize("NFC", texte.lower()):
        s = _symboles(c, vocabulaire)
        if s is not None:
            morceaux.append(s)
    # NFC peut recomposer une lettre et son accent en un caractère absent du vocabulaire
    # (n + aigu donne « ń ») : on le garde alors décomposé, en symboles que la voix connaît.
    sortie = []
    for c in unicodedata.normalize("NFC", "".join(morceaux)):
        if c in vocabulaire:
            sortie.append(c)
        else:
            d = unicodedata.normalize("NFD", c)
            if all(x in vocabulaire for x in d):
                sortie.append(d)
    prepare = re.sub(r" {2,}", " ", "".join(sortie)).strip()
    # Sans aucune lettre (« 300 - 400 » devient « - »), la voix ne rendrait qu'un souffle.
    if not any(unicodedata.category(c).startswith("L") for c in prepare):
        return ""
    return prepare


def identifiants(texte_prepare: str, vocabulaire: Mapping[str, int]) -> list[int]:
    if not texte_prepare:
        return []  # comme VitsTokenizer
    ids = [BLANC]
    for c in texte_prepare:
        ids += [vocabulaire[c], BLANC]
    return ids


def decouper(texte: str, maximum: int) -> list[str]:
    """Coupe le texte en morceaux d'au plus `maximum` caractères, dits l'un après l'autre.

    La mémoire de la voix croît avec la longueur de ce qu'elle dit d'un coup (400 Mo pour 100
    caractères, 1,5 Go pour 1 000) : par morceaux, elle reste bornée. Les phrases sont regroupées
    tant qu'elles tiennent ; une phrase trop longue est coupée après ses virgules, puis entre ses
    mots. Aucun mot n'est coupé.
    """
    morceaux: list[str] = []

    def ajouter(bout: str) -> None:
        if morceaux and len(morceaux[-1]) + 1 + len(bout) <= maximum:
            morceaux[-1] += " " + bout
        else:
            morceaux.append(bout)

    for phrase in re.findall(r"[^.?!]+[.?!]*", " ".join(texte.split())):
        phrase = phrase.strip()
        if not phrase:
            continue
        if len(phrase) <= maximum:
            ajouter(phrase)
            continue
        for proposition in re.findall(r"[^,;:]+[,;:]*", phrase):
            proposition = proposition.strip()
            if not proposition:
                continue
            if len(proposition) <= maximum:
                ajouter(proposition)
                continue
            # Trop longue même seule : morceaux de mots, commencés à neuf pour garder la coupure.
            courant = ""
            for mot in proposition.split():
                while len(mot) > maximum:  # un « mot » sans espace plus long que le maximum est coupé
                    if courant:
                        morceaux.append(courant)
                        courant = ""
                    morceaux.append(mot[:maximum])
                    mot = mot[maximum:]
                if courant and len(courant) + 1 + len(mot) > maximum:
                    morceaux.append(courant)
                    courant = mot
                else:
                    courant = f"{courant} {mot}" if courant else mot
            if courant:
                morceaux.append(courant)
    return morceaux


def borner(texte_prepare: str, maximum: int) -> list[str]:
    """Dernier garde-fou après preparer() : une lettre accentuée peut y devenir deux symboles (ń
    devient n + accent), donc un morceau peut s'allonger. Aucun morceau ne dépasse `maximum`
    symboles, et un accent n'est jamais séparé de sa lettre."""
    morceaux, debut = [], 0
    while debut < len(texte_prepare):
        fin = min(debut + maximum, len(texte_prepare))
        while debut + 1 < fin < len(texte_prepare) and unicodedata.combining(texte_prepare[fin]):
            fin -= 1
        morceaux.append(texte_prepare[debut:fin])
        debut = fin
    return morceaux


def caracteres_ignores(texte: str, vocabulaire: Mapping[str, int]) -> int:
    """Caractères qui ne laissent aucun symbole (chiffres, émojis, lettres inconnues...),
    sans compter les espaces ni la ponctuation, qui deviennent des pauses."""
    return sum(1 for c in unicodedata.normalize("NFC", texte.lower())
               if not c.isspace() and c not in PONCTUATION and _symboles(c, vocabulaire) is None)
