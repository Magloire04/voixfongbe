'use strict';
// Formulaire de demande d'accès. Tout texte affiché passe par textContent : rien n'est interprété.
(function () {
  const $ = (id) => document.getElementById(id);
  const formulaire = $('formulaire');
  const bouton = $('envoyer');
  const message = $('message');
  const CHAMPS = ['nom', 'courriel', 'organisation', 'description', 'accord'];

  function effacerErreurs() {
    message.textContent = '';
    for (const champ of CHAMPS) {
      $(champ).removeAttribute('aria-invalid');
      const zone = $('erreur-' + champ);
      zone.textContent = '';
      zone.hidden = true;
    }
  }

  function erreurDeChamp(champ, texte) {
    const zone = $('erreur-' + champ);
    if (!zone) {
      message.textContent = texte;
      return;
    }
    zone.textContent = texte;
    zone.hidden = false;
    $(champ).setAttribute('aria-invalid', 'true');
    $(champ).focus();
  }

  function compter() {
    $('compteur').textContent = $('description').value.length.toLocaleString('fr-FR');
  }

  async function verifierOuverture() {
    try {
      const r = await fetch('/api/demande', { credentials: 'same-origin' });
      const donnees = await r.json();
      if (!donnees.ouvertes) {
        formulaire.hidden = true;
        $('fermees').hidden = false;
      }
    } catch (e) {
      // Sans réponse, le formulaire reste : l'envoi dira ce qu'il en est.
    }
  }

  async function envoyer(evenement) {
    evenement.preventDefault();
    effacerErreurs();
    bouton.disabled = true;
    const corps = {
      nom: $('nom').value,
      courriel: $('courriel').value,
      organisation: $('organisation').value,
      description: $('description').value,
      accord: $('accord').checked,
      site_web: $('site_web').value,
    };
    try {
      const r = await fetch('/api/demande', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(corps),
      });
      let donnees = {};
      try { donnees = await r.json(); } catch (e) { donnees = {}; }
      if (r.ok) {
        formulaire.hidden = true;
        $('recue').hidden = false;
        $('recue').focus();
        return;
      }
      if (donnees.code === 'champ_invalide' && donnees.champ) {
        erreurDeChamp(donnees.champ, donnees.erreur);
      } else if (donnees.code === 'demandes_fermees') {
        formulaire.hidden = true;
        $('fermees').hidden = false;
      } else {
        message.textContent = donnees.erreur || 'La demande n\'a pas pu être envoyée. Réessayez dans un moment.';
      }
    } catch (e) {
      message.textContent = 'Envoi impossible : vérifiez votre connexion, puis réessayez.';
    } finally {
      bouton.disabled = false;
    }
  }

  $('description').addEventListener('input', compter);
  formulaire.addEventListener('submit', envoyer);
  compter();
  verifierOuverture();
})();
