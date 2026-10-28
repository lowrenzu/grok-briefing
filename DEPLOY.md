# Mettre JARVIS en privé sur votre propre serveur

JARVIS est une petite application : **Python 3.9 ou plus, aucune dépendance à installer**. Elle tient sur un serveur modeste (512 Mo de RAM suffisent) et n'ouvre aucune connexion sortante, sauf pour la météo et, si vous branchez une IA, vers le fournisseur choisi.

Trois façons de le mettre en ligne, de la plus simple à la plus « serveur ». **La première est la plus sûre**, et c'est celle que je recommande si le but est simplement d'y accéder depuis votre tablette ou votre téléphone.

---

> **Version pas à pas, sans jargon** : `INSTALLER-SUR-OVH.md` (peut être transmise telle quelle à quelqu'un qui gère le serveur).

## ⚡ Installation automatique (une commande)

Sur un VPS Debian/Ubuntu neuf, placez le dossier JARVIS sur la machine puis :

```bash
sudo bash install.sh
```

Le script, rejouable sans risque, s'occupe de tout :

- installe Python, **Caddy** (certificat HTTPS automatique) et un pare-feu limité à 22/80/443 ;
- crée un utilisateur système `jarvis` et copie le programme dans `/opt/jarvis` ;
- demande une seule fois l'**ID client**, le **code secret** et l'adresse **administrateur**, puis écrit `config.json` en droits `600` ;
- installe le service `jarvis` (redémarrage automatique, JARVIS n'écoute qu'en `127.0.0.1`) ;
- configure Caddy en frontal pour `jarvis.gabrielleorpel.com` (ou `JARVIS_DOMAIN=...`).

```bash
sudo JARVIS_DOMAIN=jarvis.exemple.fr bash install.sh   # autre domaine
journalctl -u jarvis -f                                # journaux
systemctl restart jarvis                               # redémarrage
sudo bash install.sh                                   # mise à jour
```

Ensuite, deux gestes manuels restent : l'entrée DNS `A` et l'adresse de retour Google (`https://VOTRE-DOMAINE/auth/callback`). Le script les rappelle à la fin.

## ⚠️ À lire avant tout

JARVIS n'a **pas de mot de passe** : l'identité passe par **Google** (section « Connexion Google obligatoire »). Si vous ouvrez le port sur Internet sans configurer Google, n'importe qui peut lire vos notes et discuter avec votre assistant. Ne vous contentez jamais d'un `JARVIS_HOST=0.0.0.0` exposé directement : sans identifiants Google, le serveur vous le signale au démarrage.

Autre point : la clé API et vos notes vivent **sur la machine qui fait tourner le serveur**. Si c'est un serveur distant, elles y sont stockées — c'est vous qui devez en garder la maîtrise (sauvegardes, accès SSH par clé).

---

## Option A — Tailscale : privé, sans ouvrir de port (recommandé)

Vous installez Tailscale sur le PC (ou le serveur) et sur la tablette. Les deux apparaissent dans un réseau privé chiffré, et **aucun port n'est ouvert sur Internet**.

1. Sur la machine qui héberge JARVIS, installez Tailscale et connectez-vous.
2. Lancez JARVIS en écoute locale élargie :

   ```bash
   JARVIS_HOST=0.0.0.0 python3 server.py
   ```

3. Depuis la tablette (elle aussi connectée à Tailscale), ouvrez :

   ```
   http://<nom-tailscale-de-la-machine>:4700
   ```

   Le nom ressemble à `jarvis-pc.tailXXXX.ts.net`.

C'est accessible de partout, et strictement par vos appareils. C'est la solution que je conseille dans 90 % des cas.

---

## Option B — Un VPS, derrière un mot de passe (Caddy)

Sur un serveur loué (OVH, Hetzner, Scaleway…), on n'expose jamais JARVIS directement : un reverse proxy s'occupe du HTTPS et du mot de passe.

### 1. Installer Python et récupérer le projet

```bash
sudo apt update && sudo apt install -y python3 unzip
sudo mkdir -p /srv/jarvis && cd /srv/jarvis
sudo unzip ~/JARVIS-app.zip      # ou git clone de votre dépôt
sudo mv JARVIS/* . && sudo rmdir JARVIS
```

### 2. Préparer la configuration

```bash
sudo cp config.example.json config.json
sudo nano config.json            # notes_dir, provider, api_key, model
```

- Pour vos vraies notes, déposez-les dans `/srv/jarvis/notes` et mettez `"notes_dir": "notes"`.
- Verrouillez le fichier : `sudo chmod 600 config.json`.

### 3. Lancer JARVIS en service permanent

```bash
sudo tee /etc/systemd/system/jarvis.service > /dev/null <<'EOF'
[Unit]
Description=JARVIS cockpit
After=network.target

[Service]
WorkingDirectory=/srv/jarvis
# Écoute locale seulement : seul le proxy peut l'atteindre.
Environment=JARVIS_HOST=127.0.0.1
Environment=PORT=4700
# Réglages en lecture seule : la clé se change à la main dans config.json.
Environment=JARVIS_SETTINGS=0
ExecStart=/usr/bin/python3 server.py
Restart=always
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
EOF
sudo chown -R www-data:www-data /srv/jarvis
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis
sudo systemctl status jarvis --no-pager
```

### 4. Le mot de passe et le HTTPS avec Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
caddy hash-password --plaintext 'votre-mot-de-passe'   # copiez la ligne affichée
```

Puis `/etc/caddy/Caddyfile` (remplacez le domaine et l'empreinte) :

```
jarvis.mondomaine.fr {
    basic_auth {
        moi <collez-ici-la-ligne-de-caddy-hash-password>
    }
    reverse_proxy 127.0.0.1:4700
}
```

```bash
sudo systemctl reload caddy
```

Caddy obtient le certificat HTTPS tout seul (le domaine doit pointer vers votre serveur). Vous ouvrez ensuite `https://jarvis.mondomaine.fr` : le navigateur demande le mot de passe une fois.

> **Pourquoi `JARVIS_SETTINGS=0` ?** Derrière un proxy, toutes les requêtes semblent venir de la machine elle-même : la protection « réglages réservés au PC local » ne joue plus. Ce verrou ferme le panneau en écriture, pour que personne ne puisse changer la clé, même avec le mot de passe. Pour modifier la clé, éditez `config.json` puis `sudo systemctl restart jarvis`.

### 5. Vérifier

```bash
curl -s http://127.0.0.1:4700/api/status
sudo journalctl -u jarvis -n 30 --no-pager
```

---

## Option C — Sans rien exposer : un tunnel SSH

Si vous avez déjà un accès SSH à votre serveur, inutile d'installer quoi que ce soit côté web :

```bash
ssh -L 4700:127.0.0.1:4700 moi@mon-serveur
```

Puis ouvrez `http://127.0.0.1:4700` sur votre PC : le trafic passe dans le tunnel SSH, chiffré, sans port ouvert. Pratique ponctuellement, moins confortable sur tablette.

---

---

## 🔐 Connexion Google obligatoire

Depuis cette version, JARVIS peut exiger une **connexion Google** avant d'afficher quoi que ce soit, et n'accepter qu'une liste d'adresses (la vôtre). C'est la bonne réponse au problème « pas de mot de passe » : plus besoin de retenir un mot de passe de plus, et vous pouvez révoquer l'accès à tout moment.

### 1. Créer l'identifiant dans Google Cloud (5 minutes, gratuit)

> **La console en français** : ajoutez `?hl=fr` à n'importe quelle adresse `console.cloud.google.com`, ou choisissez *Français* dans le sélecteur de langue en bas de page. Les libellés ci-dessous sont donnés dans les deux langues.

> **Attention, l'interface a changé** : depuis 2025, l'ancien « Écran de consentement OAuth » s'appelle **Google Auth Platform** / **Plateforme d'authentification Google**, avec quatre onglets : **Branding / Image de marque**, **Audience**, **Data access / Accès aux données**, **Clients**. Les anciens tutoriels avec captures ne correspondent plus.

1. Ouvrez <https://console.cloud.google.com/?hl=fr> et **créez un projet** (par exemple `jarvis`).
2. **API et services → Plateforme d'authentification Google** (`APIs & Services → Google Auth Platform`) :
   - cliquez sur **Commencer / Get started** et remplissez l'assistant ;
   - **Image de marque** (*Branding*) : nom de l'application `JARVIS`, votre adresse e-mail comme contact. C'est aussi ici que se trouve **Langues / Languages** : ajoutez le **français** pour que la page de connexion Google s'affiche en français ;
   - **Audience** : type **Externe** (*External*), puis dans **Utilisateurs tests** (*Test users*) ajoutez `funk.e.lee@gmail.com` et, plus tard, Anna. En mode **Test**, Google n'autorise que ces comptes : c'est voulu, et aucune vérification n'est demandée pour un usage personnel.
3. **Clients** (`Clients`, anciennement *Credentials / Identifiants*) → **Créer un client** (*Create client*) :
   - type d'application : **Application Web** (*Web application*) ;
   - nom : `JARVIS web` ;
   - **URI de redirection autorisés** (*Authorized redirect URIs*) : `https://jarvis.mondomaine.fr/auth/callback` (le domaine exact que vous utiliserez) ;
   - pour un essai sur votre PC, ajoutez aussi `http://localhost:4700/auth/callback`.
4. Copiez le **ID client** (*Client ID*) et le **Code secret du client** (*Client secret*).

> ⚠️ Le **code secret n'est affiché qu'une seule fois** à la création. Copiez-le tout de suite. Si vous le perdez, créez-en un nouveau dans l'onglet **Clients** (l'ancien peut être supprimé).

### 1 bis. Vérifier que la porte est fermée

Une fois les identifiants en place, JARVIS refuse tout visiteur sans session :

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:4700/   # 302 .../auth/login
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4700/api/status         # 401
```

Pour voir l'interface sans configurer Google (développement uniquement) :

```bash
JARVIS_AUTH=off python3 server.py    # ⚠ jamais sur un serveur accessible depuis Internet
```

### 2. Renseigner JARVIS

Dans `config.json` :

```json
{
  "auth": {
    "google_client_id": "123456789-abc.apps.googleusercontent.com",
    "google_client_secret": "GOCSPX-...",
    "allowed_emails": "vous@gmail.com",
    "public_url": "https://jarvis.mondomaine.fr"
  }
}
```

Puis `sudo systemctl restart jarvis` (ou relancez `python3 server.py`).

Les mêmes réglages existent en variables d'environnement : `JARVIS_GOOGLE_CLIENT_ID`, `JARVIS_GOOGLE_CLIENT_SECRET`, `JARVIS_ALLOWED_EMAILS`, `JARVIS_PUBLIC_URL`.

### 3. Ce qui se passe ensuite

- Un visiteur non connecté est **redirigé vers Google**, même s'il connaît l'adresse de votre serveur.
- Sans session, **aucune** route ne répond : pas la page, pas les scripts, pas les API (401).
- Une adresse absente de `allowed_emails` est refusée avec un message clair, et un message est écrit dans le journal.
- Une adresse Google **non vérifiée** est refusée.
- La session dure 7 jours, avec un cookie `HttpOnly` + `Secure` (en HTTPS) + `SameSite=Lax`.
- Le bouton **SORTIR** apparaît en haut à droite à côté de votre adresse.
- L'administrateur gère la liste dans **Réglages → Accès** (voir 3 bis).

### 3 bis. Gérer les comptes autorisés depuis l'interface (administrateur)

Le premier compte de la liste, ou celui indiqué dans `auth.admin_email`, est **administrateur**. En ouvrant **Réglages → Accès**, il voit la liste et peut :

- **ajouter** une adresse (par exemple `anna@gmail.com`, puis `maman@gmail.com`) : l'accès est immédiat, sans redémarrage ;
- **retirer** une adresse : ses sessions en cours sont fermées dans la seconde ;
- voir **qui est connecté** et **la dernière connexion** de chaque compte.

La liste vit dans **`access.json`** (droits `600`), créé automatiquement au premier démarrage à partir de `auth.allowed_emails`. Ce fichier ne contient que des adresses, jamais de mot de passe. Les autres comptes, eux, ne voient que leur propre fiche : pas d'annuaire.

Deux garde-fous : le compte administrateur ne peut pas se retirer lui-même, et il reste toujours au moins une adresse (sinon plus personne ne pourrait entrer).

Pour désigner un autre administrateur, modifiez `"admin": "..."` dans `access.json` et redémarrez.

### 4. Vérifier

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://jarvis.mondomaine.fr/        # attendu : 302
curl -s https://jarvis.mondomaine.fr/api/status                                # attendu : 401
```

Puis ouvrez la page dans un navigateur : vous devez passer par Google.

> En mode **Testing**, Google limite à 100 comptes de test et fait expirer les jetons au bout de 7 jours : il suffit de se reconnecter. Pour un usage strictement personnel, ne passez pas en « Published ».

## Sauvegardes

Trois choses à conserver :

| Quoi | Où |
| --- | --- |
| Vos notes | le dossier `notes_dir` (par défaut `notes/`) |
| Vos réglages, la clé et la config Google | `config.json` (droits `600`) |
| L'index | `viewer/graph-data.js` — **généré**, inutile de le sauvegarder |

Exemple de sauvegarde simple :

```bash
tar czf ~/jarvis-sauvegarde-$(date +%F).tar.gz -C /srv/jarvis config.json notes
```

---

## Récapitulatif

| Situation | Ce qu'il faut faire |
| --- | --- |
| Juste y accéder depuis ma tablette | **Option A**, Tailscale |
| Le laisser tourner en permanence sur un VPS (OVH) | **Option B** + **connexion Google** |
| Test rapide via SSH | **Option C**, tunnel |
| Tout garder sur mon PC | `python3 server.py`, rien d'autre |

Dans tous les cas : **ne jamais** exposer le port 4700 directement sur Internet sans protection (Google ou mot de passe).

### Et sur un VPS OVH ?

Oui, c'est un bon usage, à trois conditions :

1. **Enregistrement DNS** : un `A` qui pointe votre domaine vers l'IP du VPS, sinon Caddy ne peut pas délivrer de certificat.
2. **Pare-feu** : `sudo ufw allow 22,80,443/tcp` puis `sudo ufw enable`. Le port 4700 reste fermé de l'extérieur, seul le proxy local y accède.
3. **Connexion Google activée** (section précédente) : c'est ce qui remplace le mot de passe.

Ce que ça apporte : JARVIS disponible en permanence, sans laisser un PC allumé. Ce que ça coûte : vos notes vivent sur la machine louée, donc sauvegardez le dossier de notes et `config.json`, et gardez l'accès SSH par clé.
