#!/bin/sh
if [ -f /app/.env ]; then
  . /app/.env
fi
mkdir -p /app/.streamlit
cat > /app/.streamlit/secrets.toml <<EOF
[notion]
token = "${NOTION_TOKEN}"
database_id = "${NOTION_DATABASE_ID}"

auth_key = "${AUTH_KEY}"
EOF
mkdir -p /tmp/nginx-client /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi
nginx
exec streamlit run /app/app.py --server.port=8501 --server.address=127.0.0.1 --server.headless=true
