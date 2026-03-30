.DEFAULT_GOAL := help

PYTHON ?= python3
PIP ?= pip
FLASK_APP ?= run.py
FLASK ?= flask --app $(FLASK_APP)
DOCKER_COMPOSE ?= docker compose
WEB_SERVICE ?= backend
DB_SERVICE ?= postgres
BACKEND_DIR ?= backend
DATABASE_URL_LOCAL ?= postgresql+psycopg://liquidacion:liquidacion@localhost:5432/liquidacion_granos

.PHONY: help \
	venv install env run test test-local hooks-install \
	create-admin create-admin-docker \
	db-upgrade db-migrate db-downgrade \
	build up up-build up-full down restart docker-ps logs \
	docker-db-upgrade docker-db-migrate docker-db-downgrade docker-test \
	shell db-shell landing-dev email-test docker-email-test \
	discovery docker-discovery \
	prod-up prod-down prod-logs prod-db-upgrade prod-shell prod-email-test

help: ## Mostrar comandos disponibles
	@awk 'BEGIN {FS = ":.*##"; printf "\nUso:\n  make <objetivo>\n\nObjetivos:\n"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Crear virtualenv en .venv
	$(PYTHON) -m venv .venv

install: ## Instalar dependencias locales backend
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

env: ## Copiar .env.example a .env si no existe
	@if [ ! -f .env ]; then cp .env.example .env && echo ".env creado"; else echo ".env ya existe"; fi

run: ## Levantar app local (Flask) en puerto 5001
	cd $(BACKEND_DIR) && $(FLASK) run --port 5001

create-admin: ## Crear admin local (usar USERNAME=admin PASSWORD=... NOMBRE="Administrador")
	@if [ -z "$(USERNAME)" ] || [ -z "$(PASSWORD)" ] || [ -z "$(NOMBRE)" ]; then \
		echo 'Uso: make create-admin USERNAME=admin PASSWORD=TuClave123 NOMBRE="Administrador"'; \
		exit 1; \
	fi
	cd $(BACKEND_DIR) && if [ -x ".venv/bin/python" ]; then \
		DATABASE_URL="$(DATABASE_URL_LOCAL)" .venv/bin/python -m flask --app run.py create-admin --username "$(USERNAME)" --password "$(PASSWORD)" --nombre "$(NOMBRE)"; \
	else \
		DATABASE_URL="$(DATABASE_URL_LOCAL)" $(FLASK) create-admin --username "$(USERNAME)" --password "$(PASSWORD)" --nombre "$(NOMBRE)"; \
	fi

create-admin-docker: ## Crear admin dentro de Docker (usar USERNAME=admin PASSWORD=... NOMBRE="Administrador")
	@if [ -z "$(USERNAME)" ] || [ -z "$(PASSWORD)" ] || [ -z "$(NOMBRE)" ]; then \
		echo 'Uso: make create-admin-docker USERNAME=admin PASSWORD=TuClave123 NOMBRE="Administrador"'; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) flask --app run.py create-admin --username "$(USERNAME)" --password "$(PASSWORD)" --nombre "$(NOMBRE)"

test-local: ## Ejecutar tests locales (si existen)
	cd $(BACKEND_DIR) && pytest

hooks-install: ## Instalar hooks locales versionados (si existe script)
	@if [ -f scripts/install-hooks.sh ]; then bash scripts/install-hooks.sh; else echo "No existe scripts/install-hooks.sh"; fi

db-upgrade: ## Ejecutar migraciones locales (upgrade)
	cd $(BACKEND_DIR) && $(FLASK) db upgrade

db-migrate: ## Crear migracion local (usar MSG="descripcion")
	cd $(BACKEND_DIR) && $(FLASK) db migrate -m "$(MSG)"

db-downgrade: ## Revertir una migracion local (usar REV=-1 por defecto)
	cd $(BACKEND_DIR) && $(FLASK) db downgrade $(or $(REV),-1)

build: ## Build de imagenes Docker
	$(DOCKER_COMPOSE) build

up: ## Levantar Docker sin rebuild
	$(DOCKER_COMPOSE) up -d

up-build: ## Levantar Docker con build
	$(DOCKER_COMPOSE) up --build -d

up-full: ## Levantar stack completo (foreground)
	$(DOCKER_COMPOSE) up --build

down: ## Bajar servicios Docker
	$(DOCKER_COMPOSE) down

restart: ## Reiniciar servicios Docker
	$(DOCKER_COMPOSE) restart

docker-ps: ## Ver estado de contenedores
	$(DOCKER_COMPOSE) ps

logs: ## Ver logs (usar SERVICE=backend y TAIL=200)
	$(DOCKER_COMPOSE) logs -f --tail $(or $(TAIL),200) $(SERVICE)

landing-dev: ## Levantar landing estatica en localhost:8080 (si existe /landing)
	$(PYTHON) -m http.server 8080 --directory landing

email-test: ## Enviar correo de prueba local (si el comando existe)
	cd $(BACKEND_DIR) && $(FLASK) send-test-email

docker-db-upgrade: ## Ejecutar migraciones en Docker (upgrade)
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) flask --app run.py db upgrade

docker-db-migrate: ## Crear migracion en Docker (usar MSG="descripcion")
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) flask --app run.py db migrate -m "$(MSG)"

docker-db-downgrade: ## Revertir migracion en Docker (usar REV=-1 por defecto)
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) flask --app run.py db downgrade $(or $(REV),-1)

test: ## Ejecutar tests dentro de Docker
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) pytest

docker-test: ## Alias para tests dentro de Docker
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) pytest

docker-email-test: ## Enviar correo de prueba en Docker (si el comando existe)
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) flask --app run.py send-test-email

shell: ## Abrir shell en contenedor backend
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) sh

db-shell: ## Abrir psql en contenedor postgres
	$(DOCKER_COMPOSE) exec $(DB_SERVICE) psql -U liquidacion -d liquidacion_granos

discovery: ## Ejecutar discovery WSLPG local (backend)
	cd $(BACKEND_DIR) && $(PYTHON) scripts_discover_wslpg.py

docker-discovery: ## Ejecutar discovery WSLPG dentro de Docker
	$(DOCKER_COMPOSE) exec $(WEB_SERVICE) python scripts_discover_wslpg.py

# --- Produccion ---

PROD_COMPOSE = $(DOCKER_COMPOSE) -f docker-compose.prod.yml

prod-up: ## Levantar entorno produccion
	$(PROD_COMPOSE) up --build -d

prod-down: ## Bajar entorno produccion
	$(PROD_COMPOSE) down

prod-logs: ## Ver logs produccion (usar SERVICE=backend y TAIL=200)
	$(PROD_COMPOSE) logs -f --tail $(or $(TAIL),200) $(SERVICE)

prod-db-upgrade: ## Ejecutar migraciones en produccion
	$(PROD_COMPOSE) exec backend flask --app run.py db upgrade

prod-shell: ## Abrir shell en contenedor backend produccion
	$(PROD_COMPOSE) exec backend sh

prod-email-test: ## Enviar correo de prueba en produccion (si el comando existe)
	$(PROD_COMPOSE) exec backend flask --app run.py send-test-email
