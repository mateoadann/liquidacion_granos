# INFRA.md - Infraestructura VPS Estudio Bavera

Documentacion de la infraestructura compartida del VPS en AWS para todos los proyectos de Estudio Bavera.
Los valores reales de passwords y secrets estan en los archivos `.env` de cada directorio en el VPS.

## Estructura de Directorios

```
/opt/apps/
├── infra/                      # Infraestructura compartida (PostgreSQL, Redis, Nginx)
│   ├── docker-compose.yml
│   ├── .env                    # Credenciales de PostgreSQL (superuser + 3 DBs)
│   ├── nginx/
│   │   ├── conf.d/
│   │   │   └── default.conf   # Virtual hosts para todos los dominios
│   │   └── ssl/
│   │       ├── origin.pem     # Cloudflare Origin Certificate
│   │       └── origin.key     # Cloudflare Origin Key (permisos 600)
│   └── postgres-init/
│       └── init-databases.sh  # Script que crea las 3 DBs al primer arranque
│
├── facturador/                 # App de facturacion electronica
│   ├── docker-compose.prod.yml
│   ├── Dockerfile.prod        # Backend Python + Playwright/Chromium
│   ├── .env                   # Credenciales de app (DB, JWT, ARCA, CORS)
│   ├── backend/               # Codigo fuente del backend Flask
│   ├── frontend/              # Codigo fuente del frontend React
│   │   └── Dockerfile.prod    # Multi-stage: Node build + Nginx serve
│   └── arca_integration/      # Modulo de integracion con ARCA
│
├── monitor/                   # App de monitoreo
│   ├── docker-compose.prod.yml
│   ├── .env                   # Credenciales de app (DB, secret, Playwright)
│   ├── backend/               # Codigo fuente
│   └── ...
│
├── granos/                    # App de granos (NO desplegada todavia)
│   ├── docker-compose.prod.yml
│   ├── docker-compose.yml
│   ├── backend/
│   ├── frontend/
│   ├── data/
│   └── docs/
│
└── dashboard/                 # Landing page estatica de estudiobavera.com
    ├── docker-compose.yml
    ├── index.html
    └── letter-b-2.png
```

## Infraestructura Compartida (`/opt/apps/infra/`)

Los tres servicios base corren desde un unico `docker-compose.yml`. Todos los proyectos se conectan a ellos via la red Docker `proxy_net`.

### PostgreSQL 16 (Alpine)

- **Container**: `infra_postgres`
- **Imagen**: `postgres:16-alpine`
- **Volumen**: `postgres_data` (Docker named volume)
- **Healthcheck**: `pg_isready` cada 10s

Tiene un superusuario y tres bases de datos, cada una con su propio usuario:

| Base de datos | Usuario | Proyecto |
|---|---|---|
| `facturador` | `facturador` | Facturador |
| `monitor` | `monitor` | Monitor |
| `granos` | `granos` | Granos (reservada) |

Las credenciales estan en `/opt/apps/infra/.env`. El script `postgres-init/init-databases.sh` se ejecuta SOLO en el primer arranque del container (cuando el volumen esta vacio). Crea los usuarios y bases de datos de forma idempotente.

**Connection string desde otros containers**:
```
postgresql://<DB_USER>:<DB_PASSWORD>@infra_postgres:5432/<DB_NAME>
```

### Redis 7 (Alpine)

- **Container**: `infra_redis`
- **Imagen**: `redis:7-alpine`
- **Sin password** (acceso solo via red Docker interna)
- **Healthcheck**: `redis-cli ping` cada 10s

Cada proyecto usa un numero de DB diferente:

| Redis DB | Proyecto | Uso |
|---|---|---|
| `0` | Monitor | Celery broker/backend |
| `1` | Facturador | Celery broker/backend |
| `2` | Granos | Reservada |

**Connection string desde otros containers**:
```
redis://infra_redis:6379/<DB_NUMBER>
```

### Nginx (Alpine)

- **Container**: `infra_nginx`
- **Imagen**: `nginx:alpine`
- **Puertos**: `80:80`, `443:443` (unicos puertos expuestos al host)
- **Volumenes**: configs en `conf.d/` y certificados SSL en `ssl/`

Funciona como reverse proxy. Redirige TODO el trafico HTTP a HTTPS. Rutea por `server_name` a los containers internos.

### Red Docker `proxy_net`

Red externa que conecta TODOS los servicios. Se crea manualmente antes del primer despliegue:

```bash
docker network create proxy_net
```

Todos los `docker-compose.yml` la referencian como `external: true`.

## Configuracion por Proyecto

### Facturador (`/opt/apps/facturador/`)

**Containers**:

| Container | Imagen | Puerto interno | Funcion |
|---|---|---|---|
| `facturador_api` | Build local (`Dockerfile.prod`) | 5000 | API Flask + Gunicorn (2 workers) |
| `facturador_worker` | Build local (`Dockerfile.prod`) | - | Celery worker (facturacion masiva) |
| `facturador_frontend` | Build local (`frontend/Dockerfile.prod`) | 80 | SPA React servida con Nginx |

**Dockerfile.prod del backend** (`Dockerfile.prod`):
- Base: `python:3.11-slim`
- Instala Playwright + Chromium (para renderizado de PDFs)
- Copia `backend/` y `arca_integration/` al container
- El comando de arranque ejecuta `flask db upgrade` antes de iniciar Gunicorn

**Dockerfile.prod del frontend** (`frontend/Dockerfile.prod`):
- Multi-stage: `node:20-alpine` para build, `nginx:alpine` para servir
- Copia el resultado de `npm run build` a Nginx

**Variables de entorno** (`.env`):

| Variable | Descripcion |
|---|---|
| `POSTGRES_DB` | Nombre de la base de datos |
| `POSTGRES_USER` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | `<POSTGRES_PASSWORD>` |
| `SECRET_KEY` | `<SECRET_KEY>` - Flask secret |
| `JWT_SECRET_KEY` | `<JWT_SECRET_KEY>` - Firma de tokens JWT |
| `ENCRYPTION_KEY` | `<ENCRYPTION_KEY>` - 32 chars, Fernet para certificados |
| `ARCA_AMBIENTE` | `production` |
| `CORS_ORIGINS` | `https://facturador.estudiobavera.com` |

**Redis DB**: `1`

**Nginx routing**:
- `/api/*` -> `facturador_api:5000`
- `/*` -> `facturador_frontend:80`
- `client_max_body_size 10M`

### Monitor (`/opt/apps/monitor/`)

**Containers**:

| Container | Imagen | Puerto interno | Funcion |
|---|---|---|---|
| `monitor_web` | Build local | 5000 | App Flask (web + API) |
| `monitor_worker` | Build local | - | Worker Python (`worker.py`) |

**Variables de entorno** (`.env`):

| Variable | Descripcion |
|---|---|
| `MONITOR_DB_USER` | Usuario de PostgreSQL |
| `MONITOR_DB_PASSWORD` | `<MONITOR_DB_PASSWORD>` |
| `MONITOR_DB_NAME` | Nombre de la base de datos |
| `MONITOR_SECRET_KEY` | `<MONITOR_SECRET_KEY>` |
| `ARCA_WEB` | URL de AFIP/ARCA para scraping |
| `PLAYWRIGHT_HEADLESS` | `1` (headless mode) |
| `RECORDING` | `FALSE` |

**Redis DB**: `0`

**Volumen**: `uploads_data` para archivos subidos

**Nota**: La DB fue migrada desde el VPS anterior en Hostinger.

### Dashboard (`/opt/apps/dashboard/`)

Pagina estatica simple. Un container Nginx que sirve `index.html`.

- **Container**: `bavera_dashboard`
- **Imagen**: `nginx:alpine` (no build, imagen directa)
- **Sin .env**: No necesita variables de entorno

### Granos (`/opt/apps/granos/`)

**Estado**: NO desplegado. El repo esta clonado pero no hay un build funcional en `main`. El subdominio responde con `503 Servicio en construccion`.

**Redis DB reservada**: `2`
**Base de datos reservada**: `granos` (ya creada en PostgreSQL)

## SSL/TLS

### Arquitectura

```
Usuario -> Cloudflare (edge SSL) -> VPS Nginx (origin SSL) -> Containers
```

- **Cloudflare**: Proxy habilitado (nube naranja) en modo **Full (Strict)**
- **Origin Certificate**: Emitido por Cloudflare, almacenado en `/opt/apps/infra/nginx/ssl/`
  - `origin.pem` - Certificado
  - `origin.key` - Clave privada (permisos `600`)
- **NO se usa certbot/Let's Encrypt**: Cloudflare maneja el certificado de cara al usuario
- El Origin Certificate es valido por 15 anios (vencimiento lejos)

### Todos los virtual hosts usan el mismo certificado

El wildcard de Cloudflare cubre `estudiobavera.com` y `*.estudiobavera.com`.

## DNS / Dominios

Todos los registros DNS estan en Cloudflare con proxy habilitado (nube naranja).

| Dominio | Tipo | Destino | Proyecto |
|---|---|---|---|
| `estudiobavera.com` | A | IP del VPS | Dashboard |
| `facturador.estudiobavera.com` | A/CNAME | IP del VPS | Facturador |
| `monitor.estudiobavera.com` | A/CNAME | IP del VPS | Monitor |
| `granos.estudiobavera.com` | A/CNAME | IP del VPS | Granos (503) |

## Seguridad del VPS

| Componente | Configuracion |
|---|---|
| **SO** | Ubuntu 24.04.4 LTS (Noble Numbat), kernel 6.17 |
| **SSH** | Solo por clave publica, sin password, sin root login |
| **Firewall (UFW)** | Solo puertos 22 (SSH), 80 (HTTP), 443 (HTTPS) |
| **fail2ban** | Proteccion contra fuerza bruta en SSH |
| **unattended-upgrades** | Parches de seguridad automaticos |
| **Swap** | 2GB configurado |
| **Usuario** | `ubuntu` (con sudo) |
| **SSH alias local** | `aws-bavera-vps` (configurado en `~/.ssh/config`) |

## Operaciones Comunes

### Conectarse al VPS

```bash
ssh aws-bavera-vps
```

### Desplegar actualizaciones de un proyecto

Ejemplo para **facturador**:

```bash
ssh aws-bavera-vps
cd /opt/apps/facturador
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

Para **monitor**:

```bash
cd /opt/apps/monitor
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

Para **dashboard** (no necesita build):

```bash
cd /opt/apps/dashboard
# Editar index.html directamente o reemplazarlo
docker compose restart
```

### Ver logs de un servicio

```bash
# Logs en tiempo real
docker logs -f facturador_api
docker logs -f facturador_worker
docker logs -f monitor_web

# Ultimas 100 lineas
docker logs --tail 100 facturador_api

# Logs de infraestructura
docker logs -f infra_nginx
docker logs -f infra_postgres
docker logs -f infra_redis
```

### Reiniciar servicios

```bash
# Reiniciar un container especifico
docker restart facturador_api

# Reiniciar todo un proyecto
cd /opt/apps/facturador
docker compose -f docker-compose.prod.yml restart

# Reiniciar infraestructura (afecta a TODOS los proyectos)
cd /opt/apps/infra
docker compose restart
```

### Ver estado de los containers

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Acceder a PostgreSQL

```bash
# Conectarse al container
docker exec -it infra_postgres psql -U admin

# Conectarse a una DB especifica
docker exec -it infra_postgres psql -U facturador -d facturador

# Listar bases de datos
docker exec -it infra_postgres psql -U admin -c "\l"

# Listar tablas de una DB
docker exec -it infra_postgres psql -U facturador -d facturador -c "\dt"
```

### Acceder a Redis

```bash
docker exec -it infra_redis redis-cli

# Seleccionar una DB especifica
docker exec -it infra_redis redis-cli -n 1
```

### Backup de base de datos

```bash
# Backup de una DB
docker exec infra_postgres pg_dump -U facturador facturador > facturador_backup_$(date +%Y%m%d).sql

# Backup de todas las DBs
docker exec infra_postgres pg_dumpall -U admin > all_databases_backup_$(date +%Y%m%d).sql
```

### Restaurar base de datos

```bash
# Restaurar una DB (primero borrar y recrear si es necesario)
cat facturador_backup.sql | docker exec -i infra_postgres psql -U facturador -d facturador
```

### Agregar un nuevo proyecto

1. **Crear directorio y clonar repo**:
```bash
cd /opt/apps
git clone <REPO_URL> <nombre_proyecto>
cd <nombre_proyecto>
```

2. **Agregar DB y usuario en infra** (si el proyecto usa PostgreSQL):
   - Editar `/opt/apps/infra/.env`: agregar `NUEVO_DB_NAME`, `NUEVO_DB_USER`, `NUEVO_DB_PASSWORD`
   - Editar `/opt/apps/infra/postgres-init/init-databases.sh`: agregar llamada a `create_user_and_db`
   - **IMPORTANTE**: El init script solo corre en el primer arranque. Para agregar DBs despues, hay que crearlas manualmente:
   ```bash
   docker exec -it infra_postgres psql -U admin
   CREATE ROLE nuevo_user WITH LOGIN PASSWORD '<password>';
   CREATE DATABASE nuevo_db OWNER nuevo_user;
   GRANT ALL PRIVILEGES ON DATABASE nuevo_db TO nuevo_user;
   ```

3. **Crear `docker-compose.prod.yml`** en el directorio del proyecto:
   - NO incluir postgres ni redis (usar los compartidos)
   - Conectar a la red `proxy_net` (external: true)
   - Referenciar `infra_postgres` y `infra_redis` por nombre de container
   - Asignar un numero de Redis DB que no este en uso

4. **Crear `.env`** con las credenciales del proyecto

5. **Agregar virtual host en Nginx**:
   - Editar `/opt/apps/infra/nginx/conf.d/default.conf`
   - Agregar server block para el nuevo subdominio
   - Agregar el subdominio al server block de redirect HTTP (puerto 80)
   - Reiniciar Nginx: `docker restart infra_nginx`

6. **Agregar registro DNS en Cloudflare**:
   - Tipo A apuntando a la IP del VPS
   - Proxy habilitado (nube naranja)

7. **Levantar el proyecto**:
```bash
cd /opt/apps/<nombre_proyecto>
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

## Containers en Ejecucion (referencia)

```
NAMES                 IMAGE                 STATUS                PORTS
facturador_frontend   facturador-frontend   Up                    80/tcp
facturador_worker     facturador-worker     Up                    5000/tcp
facturador_api        facturador-api        Up                    5000/tcp
bavera_dashboard      nginx:alpine          Up                    80/tcp
monitor_worker        monitor-worker        Up                    5000/tcp
monitor_web           monitor-web           Up                    5000/tcp
infra_nginx           nginx:alpine          Up                    0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
infra_redis           redis:7-alpine        Up (healthy)          6379/tcp
infra_postgres        postgres:16-alpine    Up (healthy)          5432/tcp
```

**Nota**: Solo `infra_nginx` expone puertos al host (80 y 443). Todos los demas containers solo exponen puertos internos a la red Docker.

## Notas Importantes

- **Produccion siempre usa la rama `main`** de cada repositorio.
- **`docker-compose.prod.yml` y `.env` viven SOLO en el VPS**, no estan versionados en los repos.
- **Granos todavia no esta desplegado** (el subdominio devuelve 503).
- **La DB de Monitor fue migrada desde un VPS anterior en Hostinger**.
- **Los certificados SSL son Origin Certificates de Cloudflare**, no Let's Encrypt. No necesitan renovacion automatica (validos 15 anios).
- **No hay CI/CD configurado**. Los deploys son manuales (SSH + git pull + rebuild).
- **El superusuario de PostgreSQL es `admin`**, no el default `postgres`.
