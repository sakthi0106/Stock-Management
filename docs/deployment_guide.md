# Production Cloud Deployment Guide

This document details the production architecture, security practices, and deployment steps for deploying **StockGuard Enterprise** to a secure cloud environment.

---

## 1. Production Architecture Overview

```
                      +------------------------------------------+
                      |         Office Private Network           |
                      |                                          |
                      |  [ Excel File Share ]                    |
                      |  (\\nas\warehouse\stock.xlsx)            |
                      |          | (Read-Only Shadow Copy)       |
                      |          v                               |
                      |  [ Sync Agent Service ]                  |
                      +----------|-------------------------------+
                                 | Outbound HTTPS (Port 443)
                                 | Header: X-Agent-Key
                                 v
       ===================== INTERNET =====================
                                 |
                                 v
                      +------------------------------------------+
                      |              Cloud DMZ                   |
                      |  Nginx Reverse Proxy / Cloudflare        |
                      |  - TLS 1.3 Termination (HTTPS)           |
                      |  - IP Rate Limiting                      |
                      |  - Strict CSP & CORS                     |
                      +------------------|-----------------------+
                                         |
                                         v
                      +------------------------------------------+
                      |          Application Cluster             |
                      |                                          |
                      |  [ FastAPI Backend ]                     |
                      |  - Role-Based Access Control             |
                      |  - SHA-256 Deduplication                 |
                      |  - Export Generation Engine              |
                      +------------------|-----------------------+
                                         | Internal Private VPC
                                         v
                      +------------------------------------------+
                      |           Managed Database               |
                      |  PostgreSQL 16 Private Instance          |
                      |  - SSL Required                          |
                      |  - Automated Daily Backups               |
                      |  - Zero Public IP Access                 |
                      +------------------------------------------+
```

---

## 2. Environment Variables Configuration

Create a secure `.env` file on the production server (never commit secrets to version control):

```bash
# Server Environment
ENV=production
DEBUG=false
PROJECT_NAME="StockGuard Enterprise"
API_V1_STR="/api/v1"

# Security Secrets (Generate using openssl rand -hex 32)
SECRET_KEY=9d784a1e944c6838842e61df38d212fb947198bb9910e53a2992ef13715b9c33
ACCESS_TOKEN_EXPIRE_MINUTES=720

# Sync Agent Pre-Shared Key
SYNC_AGENT_API_KEY=corp-sync-agent-secret-auth-token-2026-prod

# Database Connection (Private VPC endpoint)
DATABASE_URL=postgresql+psycopg2://stock_app_user:StrongPassword987!@db-prod-private.internal:5432/stock_db

# Allowed CORS Origins (FQDNs of authorized web clients)
BACKEND_CORS_ORIGINS=["https://stock.company.com"]
```

---

## 3. PostgreSQL Database Setup & Hardening

1. Connect to PostgreSQL as superuser:
   ```sql
   CREATE DATABASE stock_db;
   CREATE USER stock_app_user WITH ENCRYPTED PASSWORD 'StrongPassword987!';
   GRANT ALL PRIVILEGES ON DATABASE stock_db TO stock_app_user;
   ALTER DATABASE stock_db OWNER TO stock_app_user;
   ```

2. Enforce SSL in `pg_hba.conf`:
   ```text
   hostssl stock_db stock_app_user 10.0.0.0/16 scram-sha-256
   ```

3. Ensure PostgreSQL is bound only to internal VPC addresses (`listen_addresses = '10.0.1.5'`) and is never reachable from public internet interfaces.

---

## 4. Containerized Docker Deployment

### Backend Dockerfile (`backend/Dockerfile`)
```dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Docker Compose (`docker-compose.yml`)
```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_DB: stock_db
      POSTGRES_USER: stock_app_user
      POSTGRES_PASSWORD: StrongPassword987!
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - internal-net

  backend:
    build: ./backend
    restart: always
    env_file: .env
    depends_on:
      - db
    networks:
      - internal-net
      - proxy-net

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: always
    networks:
      - proxy-net

networks:
  internal-net:
    internal: true
  proxy-net:

volumes:
  pgdata:
```

---

## 5. Nginx Reverse Proxy with TLS & Rate Limiting

```nginx
# Rate limiting zone for API
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;

server {
    listen 443 ssl http2;
    server_name stock.company.com;

    ssl_certificate /etc/letsencrypt/live/stock.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/stock.company.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # Frontend Static Distribution
    location / {
        root /var/www/stock-frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API Routing
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 6. Backup & Restoration Procedures

### Automated Daily PostgreSQL Backup
Schedule a cron job on the database server:
```bash
# /etc/cron.daily/backup-stock-db
#!/bin/bash
BACKUP_DIR="/backups/postgresql"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"
pg_dump -U stock_app_user -h localhost -d stock_db -F c -b -v -f "$BACKUP_DIR/stock_db_$TIMESTAMP.dump"
# Retain backups for 30 days
find "$BACKUP_DIR" -type f -name "*.dump" -mtime +30 -delete
```

### Point-in-Time Database Restoration
To restore a snapshot:
```bash
pg_restore -U stock_app_user -h localhost -d stock_db -v -c "/backups/postgresql/stock_db_20261026_120000.dump"
```
