FROM public.ecr.aws/docker/library/python:3.14-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# nginx 사이트 설정: /health 직접 응답, 나머지는 streamlit(8501) 프록시
RUN cat > /etc/nginx/sites-available/default <<'EOF'
server {
    listen 8080;

    location /health {
        return 200 '{"status":"ok"}';
        add_header Content-Type application/json;
    }

    location / {
        proxy_pass         http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_read_timeout 86400;
    }
}
EOF

# nginx non-root 실행 설정
# conf.d 방식은 nginx.conf에 include가 없으면 무시되므로, http 블록에 직접 삽입
RUN sed -i '/^user /d' /etc/nginx/nginx.conf \
 && sed -i 's|pid /run/nginx.pid;|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
 && sed -i 's|http {|http {\n\tclient_body_temp_path /tmp/nginx-client;\n\tproxy_temp_path    /tmp/nginx-proxy;\n\tfastcgi_temp_path  /tmp/nginx-fastcgi;\n\tuwsgi_temp_path    /tmp/nginx-uwsgi;\n\tscgi_temp_path     /tmp/nginx-scgi;|' /etc/nginx/nginx.conf

# 시작 스크립트 (별도 파일로 관리)
COPY start.sh /app/start.sh
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# non-root 사용자 (UID/GID 1000)
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -s /bin/bash app \
 && chown -R app:app /app \
 && mkdir -p /var/cache/nginx /var/log/nginx \
 && chown -R app:app /var/cache/nginx /var/log/nginx \
 && mkdir -p /tmp/nginx-client /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi \
 && chown -R app:app /tmp/nginx-client /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi

ENV HOME=/home/app
USER 1000:1000

EXPOSE 8080

CMD ["/app/start.sh"]
