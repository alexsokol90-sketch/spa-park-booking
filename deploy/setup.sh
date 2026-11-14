#!/usr/bin/env bash
# Развёртывание платформы «СПА-парк» на чистом сервере Ubuntu 24.04 (РФ).
# Запуск от root:  DOMAIN=spa.example.ru bash deploy/setup.sh
# Код должен лежать в /opt/spa-park (rsync или git clone), секреты — в /opt/spa-park/.env.
set -euo pipefail

APP_DIR=/opt/spa-park
DOMAIN="${DOMAIN:?Укажите DOMAIN, например DOMAIN=spa.example.ru}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"

echo "== Пакеты"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q postgresql postgresql-contrib python3-venv python3-pip \
    debian-keyring debian-archive-keyring apt-transport-https curl ufw
if ! command -v caddy >/dev/null; then
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q && apt-get install -y -q caddy
fi

echo "== База данных"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname = 'spa'" | grep -q 1 \
    || sudo -u postgres psql -qc "CREATE ROLE spa LOGIN PASSWORD '${DB_PASSWORD}'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'spa'" | grep -q 1 \
    || sudo -u postgres psql -qc "CREATE DATABASE spa OWNER spa"
sudo -u postgres psql -d spa -qc "CREATE EXTENSION IF NOT EXISTS btree_gist"
grep -q '^DATABASE_URL=' "$APP_DIR/.env" 2>/dev/null \
    || echo "DATABASE_URL=postgresql://spa:${DB_PASSWORD}@127.0.0.1:5432/spa" >> "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

echo "== Приложение"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

cat > /etc/systemd/system/spa-park.service <<UNIT
[Unit]
Description=SPA-park booking platform
After=network.target postgresql.service

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 3030 --timeout-graceful-shutdown 3
Restart=always
RestartSec=2
TimeoutStopSec=8

[Install]
WantedBy=multi-user.target
UNIT

echo "== HTTPS (Caddy, Let's Encrypt)"
cat > /etc/caddy/Caddyfile <<CADDY
{
	servers {
		protocols h1 h2
	}
}

$DOMAIN {
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options nosniff
		X-Frame-Options SAMEORIGIN
		Referrer-Policy strict-origin-when-cross-origin
	}
	reverse_proxy 127.0.0.1:3030 {
		flush_interval -1
	}
}
CADDY

echo "== Файрвол: только SSH и HTTPS"
ufw allow OpenSSH >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null && ufw --force enable >/dev/null

systemctl daemon-reload
systemctl enable --now spa-park
systemctl reload caddy || systemctl restart caddy
echo "== Готово: https://$DOMAIN"
