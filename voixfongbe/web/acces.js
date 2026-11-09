'use strict';
// Lien d'accès à usage unique. L'ouverture de la page ne consomme rien (les antivirus de messagerie
// ouvrent les liens) : seul le clic sur « Afficher ma clé » crée la clé, qui n'est montrée qu'une fois.
(function () {
  const $ = (id) => document.getElementById(id);
  const jeton = window.location.pathname.split('/').pop();
  const adresse = '/api/acces/' + encodeURIComponent(jeton);
  let cleNonCopiee = false;

  function montrer(id) {
    for (const zone of ['chargement', 'pret', 'zone-cle', 'invalide']) {
      $(zone).hidden = zone !== id;
    }
  }

  function avantDePartir(evenement) {
    if (cleNonCopiee) {
      evenement.preventDefault();
      evenement.returnValue = '';
    }
  }

  async function verifier() {
    try {
      const r = await fetch(adresse, { credentials: 'same-origin' });
      const donnees = await r.json();
      montrer(donnees.valide ? 'pret' : 'invalide');
    } catch (e) {
      montrer('pret');  // le clic dira si le lien est encore valable
    }
  }

  async function afficher() {
    const bouton = $('afficher');
    bouton.disabled = true;
    $('message').textContent = '';
    try {
      const r = await fetch(adresse, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      let donnees = {};
      try { donnees = await r.json(); } catch (e) { donnees = {}; }
      if (r.status === 410) {
        montrer('invalide');
        return;
      }
      if (!r.ok) {
        $('message').textContent = donnees.erreur || 'La clé n\'a pas pu être affichée. Réessayez dans un moment.';
        return;
      }
      $('cle').textContent = donnees.cle;
      $('projet').textContent = donnees.projet;
      $('limite').textContent = Number(donnees.limite).toLocaleString('fr-FR');
      if (donnees.guide) $('guide').setAttribute('href', donnees.guide);
      cleNonCopiee = true;
      window.addEventListener('beforeunload', avantDePartir);
      montrer('zone-cle');
      $('copier').focus();
    } catch (e) {
      $('message').textContent = 'Le service ne répond pas : vérifiez votre connexion, puis réessayez.';
    } finally {
      bouton.disabled = false;
    }
  }

  function selectionner() {
    const plage = document.createRange();
    plage.selectNodeContents($('cle'));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(plage);
  }

  async function copier() {
    try {
      await navigator.clipboard.writeText($('cle').textContent);
      $('copie').textContent = 'Clé copiée.';
      cleNonCopiee = false;
    } catch (e) {
      selectionner();
      $('copie').textContent = 'Clé sélectionnée : copiez-la avec Ctrl+C (ou Cmd+C).';
      cleNonCopiee = false;
    }
  }

  $('afficher').addEventListener('click', afficher);
  $('copier').addEventListener('click', copier);
  verifier();
})();
