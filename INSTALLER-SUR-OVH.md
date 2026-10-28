# Installer JARVIS sur un serveur OVH — pas à pas

Ce guide est fait pour être **suivi sans connaissances techniques**, ou **transmis à quelqu'un qui s'y connaît**. Chaque étape est une copie à faire.

- Domaine : `gabrielleorpel.com`
- Adresse voulue : **`https://jarvis.gabrielleorpel.com`**
- Administrateur : `funk.e.lee@gmail.com`

---

## 0. Ce qu'il faut

Un **VPS** (une machine louée chez OVH, Debian ou Ubuntu). Un hébergement web classique ne suffit pas : il ne fait pas tourner de programme Python.

Pour savoir ce que vous avez : espace client OVH → les tuiles à l'accueil. Si vous voyez **VPS**, c'est bon. Si vous ne voyez que **Hébergements**, il faut commander un VPS (les plus petits suffisent, 1 à 2 Go de RAM).

---

## 1. Se connecter à la machine

Deux possibilités :

- **Terminal dans le navigateur** : espace client OVH → votre VPS → bouton **Console** / **KVM**. C'est le plus simple, rien à installer.
- **Depuis un Mac ou un PC** : ouvrir le Terminal et taper `ssh root@ADRESSE_IP_DU_VPS`

> Le mot de passe root est celui reçu par e-mail à la création du VPS, ou celui que vous avez défini.

---

## 2. Installer JARVIS (une seule commande)

Copiez-collez ce bloc entier dans la fenêtre noire, puis appuyez sur Entrée :

```bash
cd /root && curl -sL https://codeload.github.com/lowrenzu/grok-briefing/zip/refs/heads/arena/b5439b0b-grok-briefing -o jarvis.zip && python3 -m zipfile -e jarvis.zip . && cd grok-briefing-arena-b5439b0b-grok-briefing && sudo bash install.sh
```

Le script pose **une seule question** — trois valeurs à coller, une par ligne :

| Ce qu'il demande | Quoi répondre |
|---|---|
| `ID client` | ton ID client Google — celui qui finit par `apps.googleusercontent.com` (dans `config.json`, ou dans le message privé) |
| `Code secret` | le code qui commence par `GOCSPX-` (même endroit) |

> Ces deux valeurs ne sont **pas** écrites ici : ce dépôt est public. Ne les colle
> dans aucun fichier versionné.
| `Ton adresse Gmail` | `funk.e.lee@gmail.com` |

Ensuite il installe tout seul : Python, Caddy (le certificat HTTPS), le service qui redémarre JARVIS en cas de coupure, et le pare-feu. Comptez 2 à 3 minutes.

À la fin, il affiche un récapitulatif. JARVIS tourne déjà sur la machine.

---

## 3. Faire pointer `jarvis.` vers le serveur (OVH)

Espace client OVH → **Noms de domaine** → `gabrielleorpel.com` → onglet **Zone DNS** → **Ajouter une entrée** :

- Type : **A**
- Sous-domaine : `jarvis`
- Cible : **l'adresse IP du VPS** (affichée dans l'espace client, rubrique VPS)

Compter 5 à 30 minutes de propagation.

---

## 4. Autoriser l'adresse de retour chez Google

<https://console.cloud.google.com/auth/clients?hl=fr> → projet **JarvisLowrenzu** → **JARVIS web** → **URI de redirection autorisés** → **Ajouter un URI** :

```
https://jarvis.gabrielleorpel.com/auth/callback
```

Puis **Enregistrer**.

---

## 5. Vérifier

1. Ouvrir `https://jarvis.gabrielleorpel.com` : la page **Google** doit s'afficher (c'est bon signe : personne n'entre sans compte).
2. Se connecter avec `funk.e.lee@gmail.com` : JARVIS s'ouvre.
3. Ouvrir l'adresse dans une fenêtre de navigation privée : la page Google revient, et aucune note n'est visible.

En ligne de commande, depuis le serveur :

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4700/   # 302 → redirection Google
journalctl -u jarvis -n 30                                        # journaux
```

---

## 6. Ajouter Anna (ou toute autre personne)

Deux endroits, deux minutes :

1. **Google** → <https://console.cloud.google.com/auth/audience?hl=fr> → **Utilisateurs tests** → **Ajouter des utilisateurs** → son adresse Gmail. (Tant que l'application reste en mode « Test », Google n'autorise que ces adresses.)
2. **JARVIS** → ⚙ **Réglages** → **Accès** → taper son adresse → **Ajouter**.

Pour lui retirer l'accès plus tard : une croix dans le même panneau, sa session se ferme immédiatement.

---

## 7. À savoir

- **Sauvegardes** : `/opt/jarvis/` contient `config.json` (identifiants Google) et `access.json` (liste des accès). En cas de réinstallation, il suffit de remettre ces deux fichiers.
- **Mise à jour** : relancer `sudo bash install.sh` depuis le dossier JARVIS.
- **Ne jamais** lancer `JARVIS_AUTH=off` sur un serveur accessible depuis Internet : cela supprime la porte Google.
- **Coût** : 0 € de plus que le VPS. L'identifiant Google en mode Test est gratuit et illimité dans le temps pour un usage personnel (jusqu'à 100 comptes).
