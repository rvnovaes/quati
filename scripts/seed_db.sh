#!/usr/bin/env bash
# Seed dos dados essenciais do banco do EZL.
#
# Aplica as migrations, carrega as fixtures base na ordem correta, cria grupos e
# permissões e garante um usuário administrador com escritório padrão e o Site.
#
# Uso (de fora dos containers):   docker compose run --rm web scripts/seed_db.sh
#     (de dentro do container):   scripts/seed_db.sh
#
# Variáveis opcionais:
#   SEED_ADMIN_USER      usuário administrador (padrão: admin)
#   SEED_ADMIN_PASSWORD  senha do administrador (padrão: admin; troque em produção)
#   SEED_ADMIN_EMAIL     e-mail do administrador (padrão: quati@labp2.direito.ufmg.br)
#   SEED_SITE_DOMAIN     domínio do Site id=1 (padrão: localhost:8000)
#   SEED_OFFICE_NAME     nome do escritório padrão criado se não houver nenhum (padrão: Escritório padrão)
#   SEED_OFFICE_CNPJ     CNPJ do escritório padrão (padrão: 00.000.000/0001-91)
#   SEED_SKIP_MIGRATE=1  não roda migrate
set -euo pipefail

cd "$(dirname "$0")/.."

SEED_ADMIN_USER="${SEED_ADMIN_USER:-admin}"
SEED_ADMIN_PASSWORD="${SEED_ADMIN_PASSWORD:-admin}"
SEED_ADMIN_EMAIL="${SEED_ADMIN_EMAIL:-quati@labp2.direito.ufmg.br}"
SEED_SITE_DOMAIN="${SEED_SITE_DOMAIN:-localhost:8000}"
SEED_OFFICE_NAME="${SEED_OFFICE_NAME:-Escritório padrão}"
SEED_OFFICE_CNPJ="${SEED_OFFICE_CNPJ:-00.000.000/0001-91}"

echo "==> Aguardando o banco de dados"
for i in $(seq 1 30); do
    python manage.py shell -c "from django.db import connection; connection.ensure_connection()" >/dev/null 2>&1 && break
    sleep 2
    [ "$i" -eq 30 ] && { echo "Banco indisponível."; exit 1; }
done

if [ "${SEED_SKIP_MIGRATE:-0}" != "1" ]; then
    echo "==> Aplicando migrations"
    python manage.py migrate --noinput
fi

# A ordem importa: office dispara signals que dependem de template (manager) e
# type_task_main (task); state depende de country; court_district de state.
echo "==> Carregando fixtures base"
python manage.py loaddata \
    auth_user \
    template \
    country \
    state \
    court_district \
    email_template \
    type_task_main \
    card line_chart doughnut_chart bar_chart

echo "==> Criando grupos e permissões"
python manage.py ezl_create_groups_and_permissions

echo "==> Configurando administrador, escritório padrão e Site"
SEED_ADMIN_USER="$SEED_ADMIN_USER" SEED_ADMIN_PASSWORD="$SEED_ADMIN_PASSWORD" \
SEED_ADMIN_EMAIL="$SEED_ADMIN_EMAIL" SEED_SITE_DOMAIN="$SEED_SITE_DOMAIN" \
SEED_OFFICE_NAME="$SEED_OFFICE_NAME" SEED_OFFICE_CNPJ="$SEED_OFFICE_CNPJ" \
python manage.py shell <<'PY'
import os
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from core.models import DefaultOffice, Office, OfficeMembership

username = os.environ['SEED_ADMIN_USER']
password = os.environ['SEED_ADMIN_PASSWORD']
email = os.environ['SEED_ADMIN_EMAIL']

user, created = User.objects.get_or_create(
    username=username,
    defaults={'first_name': 'Administrador', 'last_name': 'EZL', 'email': email})
user.email = email
user.is_active = user.is_staff = user.is_superuser = True
user.set_password(password)
user.save()

office = Office.objects.order_by('pk').first()
if office is None:
    office_name = os.environ['SEED_OFFICE_NAME']
    office = Office.objects.create(
        legal_name=office_name, name=office_name, legal_type='J',
        cpf_cnpj=os.environ['SEED_OFFICE_CNPJ'], create_user=user, is_active=True)
if hasattr(user, 'person'):
    OfficeMembership.objects.get_or_create(
        person=user.person, office=office,
        defaults={'create_user': user, 'is_active': True})
DefaultOffice.objects.get_or_create(auth_user=user, defaults={'office': office, 'create_user': user})

site, _ = Site.objects.get_or_create(pk=1, defaults={'domain': os.environ['SEED_SITE_DOMAIN'], 'name': 'EZL'})
site.domain = os.environ['SEED_SITE_DOMAIN']
site.name = 'EZL'
site.save()

print(f"Administrador: {username} ({'criado' if created else 'atualizado'}) | escritório padrão: {office.legal_name} | site: {site.domain}")
PY

echo "==> Seed concluído."
