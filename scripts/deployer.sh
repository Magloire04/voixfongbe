#!/usr/bin/env bash
# Installe ou met à jour le service de voix fon sur un hébergement cPanel avec
# « Setup Python App » (CloudLinux). À lancer sur le serveur :
#
#   git clone https://github.com/Magloire04/voixfongbe.git ~/voixfongbe-app
#   cd ~/voixfongbe-app && bash scripts/deployer.sh voix.bytechnum.com
#
# Relancer la même commande pour mettre à jour : modele/ et stockage/ sont conservés.
# Le modèle n'est pas dans Git : l'envoyer à part (voir EXPLOITATION.md).

set -euo pipefail

DOMAINE=${1:?"Usage : bash scripts/deployer.sh <domaine>"}
PYTHON_VERSION=${PYTHON_VERSION:-3.13}
RACINE=$(cd "$(dirname "$0")/.." && pwd)
DOSSIER_APP=${RACINE#"$HOME"/} # cloudlinux-selector attend un chemin relatif au dossier personnel
ENV_PYTHON="$HOME/virtualenv/$DOSSIER_APP/$PYTHON_VERSION"

etape() { printf '\n== %s\n' "$*"; }
echec() {
  printf '\nÉCHEC : %s\n' "$*" >&2
  exit 1
}
selecteur() { cloudlinux-selector "$@" --json --interpreter=python; }

[ "$DOSSIER_APP" != "$RACINE" ] || echec "le dépôt doit être cloné dans votre dossier personnel ($HOME)."
command -v cloudlinux-selector >/dev/null ||
  echec "cloudlinux-selector introuvable : créer l'application dans cPanel > Setup Python App."

etape "Mise à jour du code"
# Si le code change, le script est relancé dans sa nouvelle version.
if [ -z "${VOIX_CODE_A_JOUR:-}" ]; then
  AVANT=$(git -C "$RACINE" rev-parse HEAD)
  git -C "$RACINE" pull --ff-only
  if [ "$(git -C "$RACINE" rev-parse HEAD)" != "$AVANT" ]; then
    echo "Code mis à jour : suite du déploiement avec la nouvelle version de ce script."
    VOIX_CODE_A_JOUR=1 exec bash "$RACINE/scripts/deployer.sh" "$@"
  fi
else
  echo "Code à jour."
fi

etape "Application Python $PYTHON_VERSION"
if grep -q "\"$DOSSIER_APP\"" <<<"$(selecteur get)"; then
  echo "Application déjà déclarée pour ~/$DOSSIER_APP."
else
  creer() {
    selecteur create --version="$PYTHON_VERSION" --app-root="$DOSSIER_APP" --domain="$DOMAINE" \
      --app-uri="$1" --startup-file=passenger_wsgi.py --entry-point=application
  }
  # L'adresse racine s'écrit vide ou « / » selon les versions du sélecteur.
  creer "" || creer "/" || echec "la création de l'application a été refusée (message ci-dessus)."
fi
# Le sélecteur peut remplacer passenger_wsgi.py par un fichier d'exemple : on remet celui du dépôt.
git -C "$RACINE" checkout -- passenger_wsgi.py

etape "Dépendances"
[ -x "$ENV_PYTHON/bin/pip" ] || echec "environnement Python introuvable : $ENV_PYTHON"
"$ENV_PYTHON/bin/pip" install --quiet --upgrade pip
"$ENV_PYTHON/bin/pip" install --quiet -r "$RACINE/requirements.txt"
"$ENV_PYTHON/bin/python" -c "import onnxruntime, numpy, lameenc; print('onnxruntime', onnxruntime.__version__)"

etape "Stockage et modèle"
mkdir -p "$RACINE/stockage" "$RACINE/modele"
chmod 700 "$RACINE/stockage"
if [ -d "$RACINE/public" ] && [ -n "$(ls -A "$RACINE/public" 2>/dev/null)" ]; then
  echo "ATTENTION : $RACINE/public n'est pas vide. Passenger sert ces fichiers sans contrôle : le vider."
fi
MODELE="$RACINE/modele"
if [ -f "$MODELE/model.onnx" ] && [ -f "$MODELE/vocab.json" ] && [ -f "$MODELE/empreinte.txt" ]; then
  if [ "$(sha256sum "$MODELE/model.onnx" | cut -d' ' -f1)" = "$(tr -d '[:space:]' <"$MODELE/empreinte.txt")" ]; then
    echo "Modèle présent, empreinte vérifiée."
  else
    echo "ATTENTION : l'empreinte de modele/model.onnx ne correspond pas : la voix restera indisponible."
  fi
else
  echo "ATTENTION : modèle absent de $MODELE (model.onnx, vocab.json, empreinte.txt) : voir EXPLOITATION.md."
fi
# Une empreinte juste ne garantit pas qu'onnxruntime sait lire le fichier : vrai essai de la voix.
"$ENV_PYTHON/bin/python" "$RACINE/scripts/essayer_voix.py" ||
  echo "ATTENTION : la voix ne parle pas encore (message ci-dessus) : /v1/synthese répondra 503."

etape "Redémarrage"
selecteur restart --app-root="$DOSSIER_APP"

etape "Vérification"
for _ in 1 2 3 4 5; do
  if ETAT=$(curl -fsS --max-time 30 "https://$DOMAINE/v1/etat" 2>/dev/null); then
    printf '%s\n' "$ETAT"
    grep -q '"pret": true' <<<"$ETAT" || echo "La voix n'est pas prête : vérifier le modèle."
    printf '\nService en ligne : https://%s\n' "$DOMAINE"
    exit 0
  fi
  sleep 3
done
echec "https://$DOMAINE/v1/etat ne répond pas. Voir ~/$DOSSIER_APP/stderr.log et cPanel > Setup Python App."
