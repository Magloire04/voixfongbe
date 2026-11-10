'use strict';
// Espace d'administration de la voix fon. Tout texte venu du serveur (noms, descriptions, motifs)
// passe par textContent ou setAttribute : une balise saisie par un demandeur reste du texte.
(function () {
  const $ = (id) => document.getElementById(id);
  const ONGLETS = ['demandes', 'projets', 'appels', 'reglages'];
  const ETATS = { active: 'Active', lien_en_attente: 'Lien envoyé', lien_expire: 'Lien expiré', revoquee: 'Révoquée' };
  const RESULTATS = { 200: 'son rendu', 400: 'demande invalide', 401: 'clé refusée', 405: 'méthode refusée',
    413: 'demande trop grande', 415: 'type refusé', 429: 'quota atteint', 500: 'erreur interne',
    503: 'voix indisponible' };
  let ongletActif = 'demandes';
  let derniersProjets = [];
  let dernierCode = null;
  const appels = { jour: '', projet: '', page: 1, pages: 1 };

  class Arret extends Error {}  // session terminée : l'écran de connexion est déjà affiché

  function formateur(options) {
    for (const zone of ['Africa/Porto-Novo', 'Africa/Lagos']) {
      try { return new Intl.DateTimeFormat('fr-FR', { ...options, timeZone: zone }); } catch (e) { /* zone inconnue */ }
    }
    return new Intl.DateTimeFormat('fr-FR', options);
  }
  const FORMAT_DATE = formateur({ day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  const FORMAT_JOUR = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

  const date = (iso) => (iso ? FORMAT_DATE.format(new Date(iso)) : '');
  const jourLisible = (jour) => FORMAT_JOUR.format(new Date(jour + 'T12:00:00Z'));
  const nombre = (n) => Number(n).toLocaleString('fr-FR');
  const secondes = (ms) => (ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' s';

  function el(balise, options, ...enfants) {
    const noeud = document.createElement(balise);
    const o = options || {};
    if (o.classe) noeud.className = o.classe;
    if (o.texte !== undefined && o.texte !== null) noeud.textContent = String(o.texte);
    for (const [cle, valeur] of Object.entries(o.attributs || {})) {
      if (valeur === null || valeur === undefined || valeur === false) continue;
      noeud.setAttribute(cle, valeur === true ? '' : String(valeur));
    }
    for (const enfant of enfants) {
      if (enfant === null || enfant === undefined || enfant === false) continue;
      noeud.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
    }
    return noeud;
  }

  function bouton(texte, classe, type) {
    return el('button', { classe: 'bouton ' + (classe || ''), texte: texte, attributs: { type: type || 'button' } });
  }

  function ligneVide(texte, colonnes) {
    return el('tr', {}, el('td', { classe: 'vide', texte: texte, attributs: { colspan: colonnes } }));
  }

  function annoncer(texte, genre) {
    const zone = $('annonce');
    zone.className = 'annonce' + (genre ? ' ' + genre : '');
    zone.textContent = texte || '';
  }

  async function api(methode, chemin, corps) {
    const options = { method: methode, credentials: 'same-origin', headers: {} };
    if (methode === 'POST') {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(corps || {});
    }
    let reponse;
    try {
      reponse = await fetch(chemin, options);
    } catch (e) {
      throw new Error('Le service ne répond pas : vérifiez votre connexion.');
    }
    let donnees = {};
    try { donnees = await reponse.json(); } catch (e) { donnees = {}; }
    if (reponse.status === 401 && donnees.code === 'non_connecte') {
      montrerConnexion(donnees.erreur);
      throw new Arret();
    }
    if (!reponse.ok) {
      const erreur = new Error(donnees.erreur || 'Erreur ' + reponse.status + '.');
      erreur.code = donnees.code;
      throw erreur;
    }
    return donnees;
  }

  // Lance une action ; une erreur s'affiche dans la ligne d'annonce, et la fonction rend null.
  async function agir(action, boutons) {
    dernierCode = null;
    const actifs = (boutons || []).filter(Boolean);
    for (const b of actifs) b.disabled = true;
    try {
      return await action();
    } catch (e) {
      if (!(e instanceof Arret)) {
        dernierCode = e.code || null;
        annoncer(e.message, 'erreur');
      }
      return null;
    } finally {
      for (const b of actifs) b.disabled = false;
    }
  }

  function annoncerEnvoi(reponse, reussite, echec) {
    if (reponse.courriel_envoye) annoncer(reussite, 'ok');
    else annoncer(echec, 'erreur');
  }

  // Écrans
  function montrerSeul(id) {
    for (const zone of ['non-configure', 'ecran-connexion', 'espace']) $(zone).hidden = zone !== id;
    $('deconnexion').hidden = id !== 'espace';
  }

  function montrerConnexion(texte) {
    montrerSeul('ecran-connexion');
    annoncer('');
    $('msg-connexion').textContent = texte || '';
    $('mdp').value = '';
    $('mdp').focus();
  }

  async function ouvrirEspace() {
    montrerSeul('espace');
    annoncer('');
    await chargerReglages();
    await choisirOnglet(ongletActif, false);
  }

  async function demarrer() {
    let etat;
    try {
      etat = await api('GET', '/api/admin/etat');
    } catch (e) {
      annoncer(e.message, 'erreur');
      return;
    }
    if (!etat.configure) montrerSeul('non-configure');
    else if (etat.connecte) ouvrirEspace();
    else montrerConnexion('');
  }

  // Onglets
  const CHARGEURS = {};

  function choisirOnglet(nom, focus) {
    ongletActif = nom;
    for (const o of ONGLETS) {
      const actif = o === nom;
      $('t-' + o).setAttribute('aria-selected', String(actif));
      $('t-' + o).tabIndex = actif ? 0 : -1;
      $('p-' + o).hidden = !actif;
    }
    if (focus) $('t-' + nom).focus();
    return CHARGEURS[nom]();
  }

  for (const o of ONGLETS) $('t-' + o).addEventListener('click', () => choisirOnglet(o, false));
  document.querySelector('.onglets').addEventListener('keydown', (ev) => {
    const i = ONGLETS.indexOf(ongletActif);
    const cible = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: ONGLETS.length - 1 }[ev.key];
    if (cible === undefined) return;
    ev.preventDefault();
    choisirOnglet(ONGLETS[(cible + ONGLETS.length) % ONGLETS.length], true);
  });

  // Demandes
  function carteDemande(d) {
    const id = d.id;
    const champProjet = el('input', { attributs: { type: 'text', id: 'projet-' + id, value: d.projet_propose,
      maxlength: 40, required: true, spellcheck: 'false' } });
    const champLimite = el('input', { attributs: { type: 'number', id: 'limite-' + id, value: 100, min: 1,
      max: 1000000, step: 1, required: true } });
    const approuver = bouton('Approuver', '', 'submit');
    const refuser = bouton('Refuser', 'danger');
    const formulaire = el('form', { classe: 'decision' },
      el('div', { classe: 'champ' },
        el('label', { attributs: { for: 'projet-' + id } }, 'Nom du projet ',
          el('span', { classe: 'facultatif', texte: '(a-z, chiffres, tirets)' })), champProjet),
      el('div', { classe: 'champ' },
        el('label', { texte: 'Limite par jour', attributs: { for: 'limite-' + id } }), champLimite),
      el('div', { classe: 'actions' }, approuver, refuser));

    const motif = el('textarea', { attributs: { id: 'motif-' + id, maxlength: 500, rows: 3 } });
    const confirmer = bouton('Confirmer le refus', 'danger');
    const zoneRefus = el('div', { classe: 'refus', attributs: { hidden: true } },
      el('label', { texte: 'Motif, facultatif (il sera dans l\'e-mail)', attributs: { for: 'motif-' + id } }), motif,
      el('div', { classe: 'actions' }, confirmer));

    formulaire.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const projet = champProjet.value.trim();
      const r = await agir(() => api('POST', '/api/admin/demandes/' + id + '/approuver',
        { projet: projet, limite: Number(champLimite.value) }), [approuver, refuser]);
      if (!r) {
        if (dernierCode === 'deja_decidee') chargerDemandes();
        return;
      }
      annoncerEnvoi(r, 'Accès accordé au projet ' + projet + ' : le lien est parti à ' + d.courriel + '.',
        'Accès accordé au projet ' + projet + ', mais l\'e-mail n\'est pas parti. Onglet Projets et limites : « Nouveau lien » le renverra.');
      chargerDemandes();
    });
    refuser.addEventListener('click', () => {
      zoneRefus.hidden = false;
      motif.focus();
    });
    confirmer.addEventListener('click', async () => {
      if (!window.confirm('Refuser la demande de ' + d.nom + ' ? Un e-mail le lui dira.')) return;
      const r = await agir(() => api('POST', '/api/admin/demandes/' + id + '/refuser',
        { motif: motif.value.trim() || null }), [confirmer]);
      if (!r) {
        if (dernierCode === 'deja_decidee') chargerDemandes();
        return;
      }
      annoncerEnvoi(r, 'Demande de ' + d.nom + ' refusée. L\'e-mail est parti.',
        'Demande de ' + d.nom + ' refusée, mais l\'e-mail n\'est pas parti.');
      chargerDemandes();
    });

    return el('article', { classe: 'demande' },
      el('div', { classe: 'qui', texte: d.nom }),
      el('div', { classe: 'coord' },
        el('span', { texte: d.courriel }),
        d.organisation ? el('span', { texte: ', ' + d.organisation }) : null,
        el('span', { texte: ', reçue le ' + date(d.recue_le) })),
      el('p', { classe: 'texte', texte: d.description }),
      formulaire, zoneRefus);
  }

  async function chargerDemandes() {
    const d = await agir(() => api('GET', '/api/admin/demandes'));
    if (!d) return;
    $('nb-attente').textContent = d.en_attente.length ? String(d.en_attente.length) : '';
    const liste = $('liste-attente');
    liste.replaceChildren();
    if (!d.en_attente.length) liste.append(el('p', { classe: 'vide', texte: 'Aucune demande en attente.' }));
    for (const demande of d.en_attente) liste.append(carteDemande(demande));

    const corps = $('historique');
    corps.replaceChildren();
    if (!d.historique.length) corps.append(ligneVide('Aucune décision pour le moment.', 3));
    for (const h of d.historique) {
      const decision = h.etat === 'approuvee'
        ? el('span', {}, 'Approuvée, projet ', el('strong', { texte: h.projet }))
        : el('span', {}, 'Refusée', h.motif ? el('span', { classe: 'petit-texte', texte: 'Motif : ' + h.motif }) : null);
      corps.append(el('tr', {},
        el('td', { texte: date(h.decidee_le) }),
        el('td', {}, el('span', { texte: h.nom }), el('span', { classe: 'petit-texte', texte: h.courriel })),
        el('td', {}, decision)));
    }
  }
  CHARGEURS.demandes = chargerDemandes;

  // Projets et limites
  async function actionProjet(nom, action, corps, boutons) {
    return agir(() => api('POST', '/api/admin/projets/' + encodeURIComponent(nom) + '/' + action, corps), boutons);
  }

  function celluleLimite(p, plafond) {
    const champ = el('input', { attributs: { type: 'number', min: 1, max: 1000000, step: 1, value: p.limite,
      'aria-label': 'Limite par jour de ' + p.projet } });
    const enregistrer = bouton('Enregistrer', 'second petit', 'submit');
    const formulaire = el('form', { classe: 'limite' }, champ, enregistrer);
    formulaire.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const r = await actionProjet(p.projet, 'limite', { limite: Number(champ.value) }, [enregistrer]);
      if (!r) return;
      annoncer('Limite de ' + p.projet + ' : ' + nombre(champ.value) + ' demandes par jour.', 'ok');
      chargerProjets();
    });
    return el('td', {}, formulaire, p.depasse_plafond
      ? el('div', { classe: 'alerte-limite', texte: 'Au-dessus du plafond commun (' + nombre(plafond) + ') : ce projet ne pourra pas le dépasser.' })
      : null);
  }

  function celluleAdresse(p) {
    const champ = el('input', { attributs: { type: 'email', value: p.courriel || '', placeholder: 'adresse@exemple.bj',
      'aria-label': 'Adresse e-mail de ' + p.projet } });
    const enregistrer = bouton('Enregistrer', 'second petit', 'submit');
    const formulaire = el('form', { classe: 'adresse-form', attributs: { hidden: Boolean(p.courriel) } }, champ, enregistrer);
    formulaire.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const r = await actionProjet(p.projet, 'courriel', { courriel: champ.value.trim() }, [enregistrer]);
      if (!r) return;
      annoncer('Adresse de ' + p.projet + ' enregistrée.', 'ok');
      chargerProjets();
    });
    if (!p.courriel) return el('td', {}, formulaire);
    const modifier = el('button', { classe: 'lien', texte: 'Modifier', attributs: { type: 'button' } });
    const affichage = el('span', {}, el('span', { texte: p.courriel + ' ' }), modifier);
    modifier.addEventListener('click', () => {
      affichage.hidden = true;
      formulaire.hidden = false;
      champ.focus();
    });
    return el('td', {}, affichage, formulaire);
  }

  function celluleActions(p) {
    const nom = p.projet;
    const actions = el('div', { classe: 'actions' });
    const ajouter = (texte, classe, action, question, reussite) => {
      const b = bouton(texte, classe + ' petit');
      b.addEventListener('click', async () => {
        if (question && !window.confirm(question)) return;
        const r = await actionProjet(nom, action, {}, [b]);
        if (!r) return;
        if ('courriel_envoye' in r) {
          annoncerEnvoi(r, 'Nouveau lien envoyé à ' + p.courriel + '.',
            'Le lien est prêt, mais l\'e-mail n\'est pas parti. Réessayez « Nouveau lien » plus tard.');
        } else {
          annoncer(reussite, 'ok');
        }
        chargerProjets();
      });
      actions.append(b);
    };
    const nouvelleCle = () => ajouter('Nouvelle clé', 'second', 'nouvelle-cle',
      'Envoyer une nouvelle clé à ' + (p.courriel || 'ce projet') + ' ? L\'ancienne cessera de marcher tout de suite.');
    const nouveauLien = () => ajouter('Nouveau lien', 'second', 'nouveau-lien', null);
    const revoquer = () => ajouter('Révoquer', 'danger', 'revoquer',
      'Révoquer ' + nom + ' ? Sa clé cessera de marcher tout de suite, et un lien en attente ne servira plus.',
      nom + ' est révoqué.');
    if (p.etat === 'active') { nouvelleCle(); revoquer(); }
    if (p.etat === 'lien_en_attente' || p.etat === 'lien_expire') { nouveauLien(); revoquer(); }
    if (p.etat === 'revoquee') {
      nouvelleCle();
      ajouter('Supprimer', 'danger', 'supprimer',
        'Supprimer ' + nom + ' ? Sa fiche et sa demande d\'origine (nom, adresse, organisation) seront effacées.',
        nom + ' est supprimé.');
    }
    return el('td', {}, actions);
  }

  function ligneProjet(p, plafond) {
    const qui = [p.nom, p.organisation].filter(Boolean).join(', ');
    const etat = el('td', {}, el('span', { classe: 'etat ' + p.etat, texte: ETATS[p.etat] || p.etat }),
      p.etat === 'lien_en_attente' && p.lien_expire_le
        ? el('span', { classe: 'petit-texte', texte: 'valable jusqu\'au ' + date(p.lien_expire_le) }) : null);
    return el('tr', {},
      el('td', {}, el('strong', { texte: p.projet }),
        qui ? el('span', { classe: 'petit-texte', texte: qui }) : null,
        p.cree_le ? el('span', { classe: 'petit-texte', texte: 'créé le ' + date(p.cree_le) }) : null),
      etat,
      el('td', { texte: nombre(p.aujourd_hui) }),
      celluleLimite(p, plafond),
      celluleAdresse(p),
      celluleActions(p));
  }

  async function chargerProjets() {
    const d = await agir(() => api('GET', '/api/admin/projets'));
    if (!d) return;
    derniersProjets = d.projets.map((p) => p.projet);
    $('total-jour').textContent = nombre(d.total_jour);
    $('plafond-affiche').textContent = nombre(d.plafond);
    if (document.activeElement !== $('plafond')) $('plafond').value = d.plafond;
    const corps = $('projets');
    corps.replaceChildren();
    if (!d.projets.length) corps.append(ligneVide('Aucun projet pour le moment.', 6));
    for (const p of d.projets) corps.append(ligneProjet(p, d.plafond));
  }
  CHARGEURS.projets = chargerProjets;

  $('form-plafond').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const valeur = Number($('plafond').value);
    const r = await agir(() => api('POST', '/api/admin/reglages', { plafond: valeur }), [ev.submitter]);
    if (!r) return;
    annoncer('Plafond commun : ' + nombre(valeur) + ' demandes par jour, tous projets.', 'ok');
    chargerProjets();
  });

  // Appels
  function remplirListe(liste, valeurs, choisie, libelle) {
    liste.replaceChildren();
    for (const v of valeurs) {
      liste.append(el('option', { texte: libelle(v), attributs: { value: v, selected: v === choisie } }));
    }
  }

  async function chargerAppels() {
    if (!derniersProjets.length) {
      const p = await agir(() => api('GET', '/api/admin/projets'));
      if (p) derniersProjets = p.projets.map((x) => x.projet);
    }
    const requete = new URLSearchParams();
    if (appels.jour) requete.set('jour', appels.jour);
    if (appels.projet) requete.set('projet', appels.projet);
    requete.set('page', String(appels.page));
    const d = await agir(() => api('GET', '/api/admin/appels?' + requete.toString()));
    if (!d) return;
    appels.jour = d.jour;
    appels.page = d.page;
    appels.pages = d.pages;

    const jours = Array.from(new Set([d.jour, ...d.jours])).sort().reverse();
    remplirListe($('f-jour'), jours, d.jour, jourLisible);
    const projets = Array.from(new Set(['', ...derniersProjets, ...(d.projet ? [d.projet] : [])]));
    remplirListe($('f-projet'), projets, d.projet || '', (p) => p || 'Tous les projets');

    $('r-demandes').textContent = nombre(d.resume.demandes);
    $('r-erreurs').textContent = nombre(d.resume.erreurs);
    $('r-temps').textContent = d.resume.temps_moyen_ms === null ? '-' : secondes(d.resume.temps_moyen_ms);

    const corps = $('appels');
    corps.replaceChildren();
    if (!d.lignes.length) corps.append(ligneVide('Aucun appel ce jour-là.', 7));
    for (const l of d.lignes) {
      const code = Number(l.code);
      corps.append(el('tr', { classe: code >= 400 ? 'erreur' : '' },
        el('td', { texte: String(l.date || '').slice(11, 16) }),
        el('td', { texte: l.projet || 'clé inconnue' }),
        el('td', { texte: nombre(l.caracteres || 0) }),
        el('td', { texte: l.format || '-' }),
        el('td', { texte: secondes(l.duree_ms || 0) }),
        el('td', { texte: l.cache ? 'oui' : 'non' }),
        el('td', { classe: 'resultat', texte: code + ' ' + (RESULTATS[code] || '') })));
    }
    $('page-texte').textContent = 'Page ' + d.page + ' sur ' + d.pages;
    $('page-avant').disabled = d.page <= 1;
    $('page-apres').disabled = d.page >= d.pages;
  }
  CHARGEURS.appels = chargerAppels;

  $('f-jour').addEventListener('change', () => { appels.jour = $('f-jour').value; appels.page = 1; chargerAppels(); });
  $('f-projet').addEventListener('change', () => { appels.projet = $('f-projet').value; appels.page = 1; chargerAppels(); });
  $('page-avant').addEventListener('click', () => { appels.page = Math.max(1, appels.page - 1); chargerAppels(); });
  $('page-apres').addEventListener('click', () => { appels.page = Math.min(appels.pages, appels.page + 1); chargerAppels(); });

  // Réglages
  async function chargerReglages() {
    const d = await agir(() => api('GET', '/api/admin/reglages'));
    if (!d) return;
    const voix = $('etat-voix');
    voix.textContent = d.voix.pret ? 'Voix prête, version ' + d.voix.version : 'Voix indisponible';
    voix.className = 'etat-voix ' + (d.voix.pret ? 'ok' : 'non');
    $('etat-voix-detail').textContent = d.voix.pret
      ? 'La voix est prête (version ' + d.voix.version + ').'
      : 'La voix est indisponible : vérifiez le modèle sur le serveur (EXPLOITATION.md).';
    if (document.activeElement !== $('adresse')) $('adresse').value = d.adresse;
    $('etat-smtp').textContent = d.smtp.configure
      ? 'La boîte d\'envoi est configurée. L\'essai part vers l\'adresse des annonces.'
      : 'La boîte d\'envoi n\'est pas configurée : ses identifiants se saisissent en SSH, avec scripts/admin.py smtp.';
    $('essai').disabled = !d.smtp.configure;
  }
  CHARGEURS.reglages = chargerReglages;

  $('form-adresse').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const corps = { adresse: $('adresse').value.trim(), mot_de_passe: $('adresse-mdp').value };
    const r = await agir(() => api('POST', '/api/admin/reglages', corps), [ev.submitter]);
    $('adresse-mdp').value = '';
    if (r) annoncer('Adresse des annonces enregistrée. L\'ancienne adresse en a été prévenue.', 'ok');
  });

  $('essai').addEventListener('click', async () => {
    const r = await agir(() => api('POST', '/api/admin/reglages/essai', {}), [$('essai')]);
    if (r) annoncerEnvoi(r, 'E-mail d\'essai envoyé à ' + $('adresse').value + '.',
      'L\'e-mail d\'essai n\'est pas parti : vérifiez les identifiants (scripts/admin.py smtp).');
  });

  // Connexion, déconnexion, mot de passe oublié
  $('form-connexion').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    $('msg-connexion').textContent = '';
    try {
      await api('POST', '/api/admin/connexion', { mot_de_passe: $('mdp').value });
      $('mdp').value = '';
      ouvrirEspace();
    } catch (e) {
      if (!(e instanceof Arret)) $('msg-connexion').textContent = e.message;
    }
  });

  $('deconnexion').addEventListener('click', async () => {
    try { await api('POST', '/api/admin/deconnexion', {}); } catch (e) { /* déjà déconnecté */ }
    montrerConnexion('');
    annoncer('Vous êtes déconnecté.', 'ok');
  });

  function messageOubli(texte, genre) {
    const m = $('msg-oubli');
    m.className = 'message' + (genre ? ' ' + genre : '');
    m.textContent = texte;
  }

  $('vers-oubli').addEventListener('click', () => {
    $('oubli').hidden = false;
    $('envoyer-code').focus();
  });

  $('envoyer-code').addEventListener('click', async () => {
    messageOubli('');
    try {
      const r = await api('POST', '/api/admin/oubli', {});
      if (r.courriel_envoye) {
        messageOubli('Code envoyé à l\'adresse de l\'administrateur. Il reste valable 10 minutes.', 'ok');
        $('form-code').hidden = false;
        $('code').focus();
      } else {
        messageOubli('Le code n\'est pas parti : vérifiez la boîte d\'envoi en SSH.', 'erreur');
      }
    } catch (e) {
      messageOubli(e.message, 'erreur');
    }
  });

  $('form-code').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if ($('nouveau').value !== $('nouveau-bis').value) {
      messageOubli('Les deux mots de passe ne sont pas identiques.', 'erreur');
      return;
    }
    try {
      await api('POST', '/api/admin/oubli/changer', { code: $('code').value.trim(), mot_de_passe: $('nouveau').value });
      for (const id of ['code', 'nouveau', 'nouveau-bis']) $(id).value = '';
      $('form-code').hidden = true;
      messageOubli('Mot de passe changé. Connectez-vous avec le nouveau.', 'ok');
      $('mdp').focus();
    } catch (e) {
      messageOubli(e.message, 'erreur');
    }
  });

  demarrer();
})();
