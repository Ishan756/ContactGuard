# syntax=docker/dockerfile:1
# 1. Build Stage
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# 2. Production Runtime Stage
FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html

# Custom Nginx configuration for React SPA routing
RUN cat <<EOF > /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name localhost;
    client_max_body_size 30m;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location = /health {
        proxy_pass http://backend:8000/health;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
