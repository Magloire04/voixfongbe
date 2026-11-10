"""Contrôle des valeurs saisies à l'écran : adresse e-mail et limite quotidienne."""

import re

LIMITE_MAX = 1_000_000
COURRIEL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24}")


def valider_courriel(valeur) -> str:
    """L'adresse sans blancs aux bouts, ou ValueError. Le motif exclut tout retour à la ligne :
    une adresse acceptée ne peut rien ajouter aux en-têtes d'un e-mail."""
    if not isinstance(valeur, str):
        raise ValueError("adresse e-mail invalide")
    valeur = valeur.strip()
    if len(valeur) > 254 or not COURRIEL.fullmatch(valeur):
        raise ValueError("adresse e-mail invalide")
    return valeur


def valider_limite(valeur) -> int:
    """Un nombre entier de demandes par jour, de 1 à 1 000 000, ou ValueError."""
    if isinstance(valeur, bool) or not isinstance(valeur, int) or not 1 <= valeur <= LIMITE_MAX:
        raise ValueError(f"la limite doit être un nombre entier de 1 à {LIMITE_MAX:,}".replace(",", " "))
    return valeur
