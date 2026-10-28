#!/usr/bin/env bash
# JARVIS — installation sur un serveur Debian/Ubuntu (VPS OVH ou autre).
#
#   sudo bash install.sh                         # domaine par défaut
#   sudo JARVIS_DOMAIN=jarvis.exemple.fr bash install.sh
#
# Le script est rejouable : relancé, il met simplement JARVIS à jour.
# Il installe Caddy en frontal (HTTPS automatique) et JARVIS derrière,
# accessible uniquement depuis la machine elle-même (127.0.0.1).
set -euo pipefail

DOMAIN="${JARVIS_DOMAIN:-jarvis.gabrielleorpel.com}"
APP_DIR="${JARVIS_DIR:-/opt/jarvis}"
PORT="${JARVIS_PORT:-4700}"
SERVICE_USER="jarvis"

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- vérifications
[ "$(id -u)" -eq 0 ] || die "Lance ce script avec sudo : sudo bash install.sh"
command -v apt-get >/dev/null 2>&1 || die "Ce script vise Debian/Ubuntu (apt-get introuvable)."
[ -f server.py ] || die "Lance le script depuis le dossier qui contient server.py (le dossier JARVIS)."

say "Installation de JARVIS pour https://$DOMAIN"

# ---------------------------------------------------------------- paquets de base
say "Paquets système"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 rsync ufw ca-certificates curl gnupg apt-transport-https >/dev/null
ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"

# ---------------------------------------------------------------- Caddy (HTTPS auto)
if ! command -v caddy >/dev/null 2>&1; then
    say "Installation de Caddy (certificat HTTPS automatique)"
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
        | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy >/dev/null
    ok "caddy $(caddy version 2>/dev/null | awk '{print $1}')"
else
    ok "caddy déjà installé"
fi

# ---------------------------------------------------------------- utilisateur dédié
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    ok "utilisateur système « $SERVICE_USER » créé"
else
    ok "utilisateur « $SERVICE_USER » déjà présent"
fi

# ---------------------------------------------------------------- copie du programme
say "Copie du programme dans $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --delete \
    --exclude '__pycache__' \
    --exclude 'access.json' \
    --exclude 'notes/' \
    ./ "$APP_DIR"/
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
chmod 700 "$APP_DIR"
ok "$(find "$APP_DIR" -type f | wc -l) fichiers copiés"

# ---------------------------------------------------------------- configuration
CONFIG="$APP_DIR/config.json"
if [ ! -f "$CONFIG" ]; then
    say "Identifiants Google"
    echo "  Colle l'ID client puis le code secret (Google Auth Platform → Clients)."
    echo "  Laisse vide si tu l'as déjà mis dans config.json."
    read -rp "  ID client      : " CLIENT_ID
    read -rsp "  Code secret    : " CLIENT_SECRET
    echo
    read -rp "  Ton adresse Gmail (administrateur) : " ADMIN_EMAIL

    [ -n "$CLIENT_ID" ] && [ -n "$CLIENT_SECRET" ] && [ -n "$ADMIN_EMAIL" ] \
        || die "Les trois valeurs sont nécessaires (réessaie en relançant le script)."

    python3 - "$CONFIG" "$CLIENT_ID" "$CLIENT_SECRET" "$ADMIN_EMAIL" "$DOMAIN" <<'PY'
import json, sys
path, cid, secret, admin, domain = sys.argv[1:6]
data = {
    "notes_dir": "examples/demo-notes",
    "auth": {
        "google_client_id": cid,
        "google_client_secret": secret,
        "allowed_emails": admin,
        "admin_email": admin,
        "public_url": f"https://{domain}",
    },
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY
    ok "config.json écrit"
else
    ok "config.json déjà présent (conservé)"
fi
chown "$SERVICE_USER":"$SERVICE_USER" "$CONFIG"
chmod 600 "$CONFIG"

# ---------------------------------------------------------------- service systemd
say "Service JARVIS"
cat > /etc/systemd/system/jarvis.service <<EOF
[Unit]
Description=JARVIS (briefing personnel)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment=PORT=$PORT
Environment=JARVIS_HOST=127.0.0.1
ExecStart=/usr/bin/python3 -u server.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now jarvis >/dev/null 2>&1
sleep 2
systemctl is-active --quiet jarvis && ok "jarvis démarré" || die "Le service n'a pas démarré : journalctl -u jarvis -n 40"

# ---------------------------------------------------------------- Caddy en frontal
say "Caddy en frontal (HTTPS automatique)"
cat > /etc/caddy/Caddyfile <<EOF
# JARVIS — HTTPS géré par Caddy, JARVIS n'écoute qu'en local.
$DOMAIN {
	encode zstd gzip
	reverse_proxy 127.0.0.1:$PORT
	log {
		output file /var/log/caddy/jarvis.log
		format console
	}
}
EOF
install -d -o caddy -g caddy -m 755 /var/log/caddy 2>/dev/null || mkdir -p /var/log/caddy
caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 || die "Caddyfile invalide."
systemctl enable --now caddy >/dev/null 2>&1
systemctl reload caddy 2>/dev/null || systemctl restart caddy
ok "caddy actif pour $DOMAIN"

# ---------------------------------------------------------------- pare-feu
say "Pare-feu"
ufw allow 22/tcp   >/dev/null 2>&1 || true
ufw allow 80/tcp   >/dev/null 2>&1 || true
ufw allow 443/tcp  >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
ok "seuls 22, 80 et 443 sont ouverts (JARVIS n'est jamais exposé en direct)"

# ---------------------------------------------------------------- bilan
say "Vérifications"
sleep 1
local_code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)"
case "$local_code" in
    200|302) ok "JARVIS répond en local ($local_code → redirection vers Google)" ;;
    *)       warn "JARVIS ne répond pas encore en local ($local_code)" ;;
esac

cat <<EOF

  ┌──────────────────────────────────────────────────────────────┐
  │  JARVIS est installé.                                        │
  └──────────────────────────────────────────────────────────────┘

  Adresse          : https://$DOMAIN
  Administrateur   : voir $APP_DIR/access.json
  Journaux         : journalctl -u jarvis -f
  Mise à jour      : relancer ce script
  Redémarrage      : systemctl restart jarvis

  Il reste deux choses à faire, une seule fois :
    1. dans la zone DNS du domaine, une entrée A « $(echo "$DOMAIN" | cut -d. -f1) »
       qui pointe vers l'adresse IP de ce serveur ;
    2. dans Google (Clients → ton application), ajouter l'adresse de retour :
       https://$DOMAIN/auth/callback

  Une fois le DNS propagé, ouvre https://$DOMAIN : la connexion Google
  s'affiche, et toi seul peux entrer.

EOF
