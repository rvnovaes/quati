"""
Carrega as cidades brasileiras a partir de core/fixtures/city.xml.

A fixture referencia comarcas que não existem na fixture de comarcas, por isso o
loaddata falha. Aqui a comarca é mantida só quando existe; caso contrário fica vazia.
Idempotente: cidades já existentes (mesma chave) não são recriadas.
"""
import os
import xml.etree.ElementTree as ET

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.models import City, State
from lawsuit.models import CourtDistrict


class Command(BaseCommand):
    help = 'Carrega as cidades da fixture city.xml, ignorando comarcas inexistentes.'

    def handle(self, *args, **options):
        path = os.path.join(settings.BASE_DIR, 'core', 'fixtures', 'city.xml')
        if not os.path.exists(path):
            raise CommandError('Fixture não encontrada: {}'.format(path))
        admin = User.objects.filter(is_superuser=True).order_by('pk').first()
        if admin is None:
            raise CommandError('Nenhum superusuário encontrado.')

        states = set(State.objects.values_list('pk', flat=True))
        districts = set(CourtDistrict.objects.values_list('pk', flat=True))
        existing = set(City.objects.values_list('pk', flat=True))

        cities, skipped = [], 0
        for obj in ET.parse(path).getroot().iter('object'):
            pk = int(obj.get('pk'))
            if pk in existing:
                continue
            fields = {f.get('name'): f for f in obj.iter('field')}
            state_id = int(fields['state'].text)
            if state_id not in states:
                skipped += 1
                continue
            district = fields.get('court_district')
            district_id = int(district.text) if district is not None and district.text and district.text.strip().isdigit() else None
            if district_id not in districts:
                district_id = None
            cities.append(City(pk=pk, name=fields['name'].text, state_id=state_id, court_district_id=district_id,
                               create_user=admin, is_active=True))

        City.objects.bulk_create(cities, batch_size=1000)
        self.stdout.write(self.style.SUCCESS('Cidades criadas: {} (já existiam: {}, ignoradas: {})'.format(
            len(cities), len(existing), skipped)))
