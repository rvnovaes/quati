COMPOSE = docker compose
MANAGE = $(COMPOSE) run --rm web python manage.py

.PHONY: help build up down restart logs ps shell psql migrate migrations collectstatic \
        seed load_fixtures load_fixtures0 createsuperuser bootstrap test check \
        set_env_development set_env_production check_env

help:
	@grep -E '^[a-zA-Z0-9_-]+:' Makefile | cut -d: -f1 | sort | tr '\n' ' '; echo

check_env:
	@test -s .env || { echo ".env não encontrado. Copie .env.example para .env e ajuste."; exit 1; }
	@test -e docker-compose.override.yml || { echo "docker-compose.override.yml não encontrado. Rode 'make set_env_development' ou 'make set_env_production'."; exit 1; }

set_env_development:
	@rm -f docker-compose.override.yml
	ln -s docker-compose.development.yml docker-compose.override.yml

set_env_production:
	@rm -f docker-compose.override.yml
	ln -s docker-compose.production.yml docker-compose.override.yml

build: check_env
	$(COMPOSE) build web

up: check_env
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart web ws worker beat

logs:
	$(COMPOSE) logs --follow --tail=100

ps:
	$(COMPOSE) ps

shell: check_env
	$(COMPOSE) run --rm web bash

psql: check_env
	$(COMPOSE) exec db psql -U $${DB_USER:-ezl} $${DB_NAME:-ezl}

migrate: check_env
	$(MANAGE) migrate --noinput

migrations: check_env
	$(MANAGE) makemigrations --noinput

collectstatic: check_env
	$(MANAGE) collectstatic --noinput

seed: check_env
	$(COMPOSE) run --rm web scripts/seed_db.sh

load_fixtures0: seed

load_fixtures: check_env
	$(MANAGE) ezl_create_groups_and_permissions

createsuperuser: check_env
	$(MANAGE) createsuperuser

check: check_env
	$(COMPOSE) run --rm web python -W error::DeprecationWarning manage.py check
	$(MANAGE) makemigrations --check --dry-run

test: check_env
	$(COMPOSE) run --rm web pytest

# Primeira subida: constrói, sobe infraestrutura, migra, carrega fixtures e sobe tudo.
bootstrap: check_env build
	$(COMPOSE) up -d db redis queues
	$(MAKE) seed
	$(MANAGE) collectstatic --noinput
	$(COMPOSE) up -d
	@echo "Pronto. Web: http://localhost:8000  nginx: http://localhost:8080  Mailpit: http://localhost:8026  Flower: http://localhost:5555"
