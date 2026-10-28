# Mettre JARVIS en privé sur votre propre serveur

JARVIS est une petite application : **Python 3.9 ou plus, aucune dépendance à installer**. Elle tient sur un serveur modeste (512 Mo de RAM suffisent) et n'ouvre aucune connexion sortante, sauf pour la météo et, si vous branchez une IA, vers le fournisseur choisi.

Trois façons de le mettre en ligne, de la plus simple à la plus « serveur ». **La première est la plus sûre**, et c'est celle que je recommande si le but est simplement d'y accéder depuis votre tablette ou votre téléphone.

---

## ⚠️ À lire avant tout

JARVIS **n'a pas de mot de passe**. Si vous ouvrez le port sur Internet sans protection, n'importe qui peut lire vos notes et discuter avec votre assistant. Les trois méthodes ci-dessous règlent ce problème ; ne vous contentez jamais d'un `JARVIS_HOST=0.0.0.0` exposé directement.

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

## Sauvegardes

Trois choses à conserver :

| Quoi | Où |
| --- | --- |
| Vos notes | le dossier `notes_dir` (par défaut `notes/`) |
| Vos réglages et la clé | `config.json` (droits `600`) |
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
| Le laisser tourner en permanence sur un VPS | **Option B**, Caddy + mot de passe + `JARVIS_SETTINGS=0` |
| Test rapide via SSH | **Option C**, tunnel |
| Tout garder sur mon PC | `python3 server.py`, rien d'autre |

Dans tous les cas : **ne jamais** exposer le port 4700 directement sur Internet sans mot de passe.
