"""
Dados de demonstração para o Quati.

Cria, no primeiro escritório cadastrado, correspondentes, solicitantes, clientes,
pastas, processos e ordens de serviço distribuídas pelos status do fluxo, com prazos
nos próximos dias, para o dashboard e as listagens ficarem povoados.

Uso: python manage.py seed_demo            (idempotente: não duplica se já rodou)
     python manage.py seed_demo --reset    (apaga as OS de demonstração e recria)
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (CONTACT_MECHANISM_TYPE, EMAIL, PHONE, ContactMechanism, ContactMechanismType,
                         Office, OfficeMembership, Person)
from lawsuit.models import CourtDistrict, Folder, LawSuit, Movement, TypeLawsuit, TypeMovement
from task.models import Task, TaskStatus, TypeTask

DEMO_MARK = '[demo]'
SENHA_DEMO = 'quati123'

CORRESPONDENTES = [
    ('ana.ribeiro', 'Ana Paula', 'Ribeiro', '31 98877-1201', 'Uberlândia'),
    ('carlos.mota', 'Carlos Eduardo', 'Mota', '31 98877-1202', 'Belo Horizonte'),
    ('juliana.ferraz', 'Juliana', 'Ferraz', '37 98877-1203', 'Divinópolis'),
    ('marcos.lima', 'Marcos', 'Lima', '38 98877-1204', 'Montes Claros'),
]
SOLICITANTES = [
    ('beatriz.campos', 'Beatriz', 'Campos'),
    ('rafael.nunes', 'Rafael', 'Nunes'),
]
CLIENTES = [
    ('Construtora Horizonte Ltda.', '12.345.678/0001-90'),
    ('Cooperativa Agrícola do Vale', '23.456.789/0001-01'),
    ('Comércio de Alimentos Serra Azul S.A.', '34.567.890/0001-12'),
]
COMARCAS = ['Belo Horizonte', 'Uberlândia', 'Contagem', 'Montes Claros', 'Divinópolis', 'Juiz de Fora']
PARTES = ['João da Silva', 'Maria Oliveira', 'Transportadora Rápido Ltda.', 'Banco Nacional S.A.',
          'Pedro Henrique Souza', 'Distribuidora Minas Norte']

# (status, dias até o prazo fatal, tipo de serviço, descrição)
OS_DEMO = [
    (TaskStatus.REQUESTED, 1, 'Audiência cível - apenas advogado', 'Audiência de instrução e julgamento.'),
    (TaskStatus.REQUESTED, 4, 'Cópia', 'Extrair cópia integral dos autos físicos.'),
    (TaskStatus.REQUESTED, 9, 'Certidão', 'Certidão de objeto e pé.'),
    (TaskStatus.OPEN, 1, 'Protocolo', 'Protocolar contestação com documentos anexos.'),
    (TaskStatus.OPEN, 3, 'Audiência trabalhista una/instrução - advogado e preposto', 'Audiência una. Preposto confirmado.'),
    (TaskStatus.OPEN, 12, 'Alvará', 'Levantamento de alvará expedido.'),
    (TaskStatus.ACCEPTED, 0, 'Audiência cível - advogado e preposto', 'Audiência de conciliação.'),
    (TaskStatus.ACCEPTED, 2, 'Outros Serviços', 'Diligência em cartório de registro de imóveis.'),
    (TaskStatus.ACCEPTED, 5, 'Audiência criminal - apenas advogado', 'Audiência de instrução criminal.'),
    (TaskStatus.ACCEPTED, 15, 'Protocolo', 'Protocolo de recurso de apelação.'),
    (TaskStatus.RETURN, 2, 'Cópia', 'Cópia retornada: faltou a certidão de trânsito em julgado.'),
    (TaskStatus.DONE, -2, 'Certidão', 'Certidão negativa obtida e anexada.'),
    (TaskStatus.DONE, -5, 'Audiência cível - apenas advogado', 'Audiência realizada, acordo homologado.'),
    (TaskStatus.FINISHED, -10, 'Protocolo', 'Petição protocolada, guia paga.'),
    (TaskStatus.FINISHED, -14, 'Audiência trabalhista inicial/conciliação/encerramento - apenas advogado', 'Audiência inicial realizada.'),
    (TaskStatus.FINISHED, -20, 'Alvará', 'Alvará levantado e valor depositado.'),
    (TaskStatus.FINISHED, -25, 'Cópia', 'Cópia digitalizada entregue.'),
    (TaskStatus.REFUSED, 6, 'Audiência criminal - advogado e preposto', 'Correspondente recusou por conflito de agenda.'),
    (TaskStatus.BLOCKEDPAYMENT, -30, 'Outros Serviços', 'Glosada: diligência não comprovada.'),
]


class Command(BaseCommand):
    help = 'Cria dados de demonstração (correspondentes, clientes, processos e OS) no primeiro escritório.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Apaga as OS de demonstração antes de recriar.')

    def handle(self, *args, **options):
        random.seed(42)
        office = Office.objects.order_by('pk').first()
        if office is None:
            raise CommandError('Nenhum escritório cadastrado. Rode o seed principal antes (scripts/seed_db.sh).')
        admin = User.objects.filter(is_superuser=True).order_by('pk').first()
        if admin is None:
            raise CommandError('Nenhum superusuário encontrado.')

        with transaction.atomic():
            self.ensure_contact_types(admin)
            if options['reset']:
                deleted, _ = Task.objects.filter(office=office, description__endswith=DEMO_MARK).delete()
                self.stdout.write('OS de demonstração removidas: {}'.format(deleted))
            elif Task.objects.filter(office=office, description__endswith=DEMO_MARK).exists():
                self.stdout.write('Dados de demonstração já existem. Use --reset para recriar as OS.')
                return

            correspondentes = [self.pessoa_com_usuario(office, admin, Person.CORRESPONDENT_GROUP, *c[:3], phone=c[3], cidade=c[4], is_lawyer=True)
                               for c in CORRESPONDENTES]
            solicitantes = [self.pessoa_com_usuario(office, admin, Person.REQUESTER_GROUP, *s) for s in SOLICITANTES]
            clientes = [self.cliente(office, admin, nome, cnpj) for nome, cnpj in CLIENTES]
            tipo_mov = TypeMovement.objects.filter(office=office).order_by('pk').first() \
                or TypeMovement.objects.create(office=office, name='OS Avulsa', uses_wo=True, create_user=admin)
            processos = self.processos(office, admin, clientes, tipo_mov)
            criadas = self.ordens_de_servico(office, admin, processos, correspondentes, solicitantes)

        self.stdout.write(self.style.SUCCESS(
            'Demo criada: {} correspondentes, {} solicitantes, {} clientes, {} processos, {} OS. '
            'Senha dos usuários de demonstração: {}'.format(
                len(correspondentes), len(solicitantes), len(clientes), len(processos), criadas, SENHA_DEMO)))

    # ------------------------------------------------------------------ pessoas
    def ensure_contact_types(self, admin):
        for pk, name in CONTACT_MECHANISM_TYPE:
            ContactMechanismType.objects.get_or_create(pk=pk, defaults={'name': name.title(), 'create_user': admin})

    def grupo(self, office, base):
        group, _ = Group.objects.get_or_create(name='{}-{}'.format(base, office.pk))
        return group

    def pessoa_com_usuario(self, office, admin, grupo, username, first_name, last_name, phone=None, cidade=None, is_lawyer=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'first_name': first_name, 'last_name': last_name,
                      'email': '{}@labp2.direito.ufmg.br'.format(username)})
        if created:
            user.set_password(SENHA_DEMO)
            user.save()
        user.groups.add(self.grupo(office, grupo))
        person = Person.objects.filter(auth_user=user).first()
        if person is None:  # o signal create_person só roda quando o app está carregado; garante aqui
            person = Person.objects.create(legal_name='{} {}'.format(first_name, last_name), name='{} {}'.format(first_name, last_name),
                                           legal_type='F', auth_user=user, create_user=admin, is_active=True)
        person.is_lawyer = is_lawyer
        person.legal_type = 'F'
        person.save()
        OfficeMembership.objects.get_or_create(person=person, office=office, defaults={'create_user': admin, 'is_active': True})
        self.contato(person, admin, EMAIL, user.email)
        if phone:
            self.contato(person, admin, PHONE, phone)
        return person

    def cliente(self, office, admin, nome, cnpj):
        person, _ = Person.objects.get_or_create(
            legal_name=nome, defaults={'name': nome, 'legal_type': 'J', 'cpf_cnpj': cnpj, 'is_customer': True,
                                       'create_user': admin, 'is_active': True})
        OfficeMembership.objects.get_or_create(person=person, office=office, defaults={'create_user': admin, 'is_active': True})
        return person

    def contato(self, person, admin, tipo_pk, valor):
        ContactMechanism.objects.get_or_create(
            person=person, contact_mechanism_type_id=tipo_pk, description=valor, defaults={'create_user': admin})

    # ---------------------------------------------------------------- processos
    def processos(self, office, admin, clientes, tipo_mov):
        comarcas = {c.name: c for c in CourtDistrict.objects.filter(name__in=COMARCAS, state__initials='MG')}
        movimentos = []
        numero = 0
        for i, cliente in enumerate(clientes, start=1):
            folder, _ = Folder.objects.get_or_create(
                office=office, person_customer=cliente, folder_number=i,
                defaults={'create_user': admin, 'is_active': True})
            for j in range(2):
                numero += 1
                cnj = '{:07d}-{:02d}.2026.8.13.{:04d}'.format(100000 + numero * 137, 10 + numero, 24 + numero)
                comarca = comarcas.get(COMARCAS[(numero - 1) % len(COMARCAS)])
                lawsuit, _ = LawSuit.objects.get_or_create(
                    office=office, folder=folder, law_suit_number=cnj,
                    defaults={'create_user': admin, 'is_active': True, 'court_district': comarca,
                              'type_lawsuit': TypeLawsuit.JUDICIAL.name, 'is_current_instance': True,
                              'opposing_party': PARTES[(numero - 1) % len(PARTES)]})
                movement, _ = Movement.objects.get_or_create(
                    office=office, folder=folder, law_suit=lawsuit, type_movement=tipo_mov,
                    defaults={'create_user': admin, 'is_active': True})
                movimentos.append(movement)
        return movimentos

    # ----------------------------------------------------------------------- OS
    def ordens_de_servico(self, office, admin, movimentos, correspondentes, solicitantes):
        agora = timezone.localtime()
        tipos = {t.name: t for t in TypeTask.objects.filter(office=office)}
        fallback = TypeTask.objects.filter(office=office).order_by('pk').first()
        criadas = 0
        for i, (status, dias, nome_tipo, descricao) in enumerate(OS_DEMO):
            movimento = movimentos[i % len(movimentos)]
            prazo = (agora + timedelta(days=dias)).replace(hour=random.choice([9, 10, 11, 14, 15, 16]), minute=0, second=0, microsecond=0)
            executor = None if status is TaskStatus.REQUESTED else correspondentes[i % len(correspondentes)]
            valor = Decimal(random.choice([180, 250, 320, 400, 550, 700]))
            comarca = movimento.law_suit.court_district
            task = Task(
                office=office, create_user=admin, is_active=True,
                movement=movimento, type_task=tipos.get(nome_tipo, fallback),
                task_status=status.value,
                person_asked_by=solicitantes[i % len(solicitantes)],
                person_distributed_by=admin.person if hasattr(admin, 'person') else None,
                person_executed_by=executor,
                final_deadline_date=prazo,
                requested_date=agora - timedelta(days=max(abs(dias) + 3, 5)),
                description='{} {}'.format(descricao, DEMO_MARK),
                performance_place='{} - {}'.format(comarca.name, comarca.state.initials) if comarca else 'Belo Horizonte - MG',
                amount=valor, amount_delegated=valor, amount_to_receive=valor,
                amount_to_pay=(valor * Decimal('0.7')).quantize(Decimal('0.01')),
            )
            self.datas_por_status(task, status, agora, dias)
            task.save(skip_signal=True, skip_mail=True)
            criadas += 1
        return criadas

    @staticmethod
    def datas_por_status(task, status, agora, dias):
        base = agora - timedelta(days=max(abs(dias) + 2, 4))
        if status in (TaskStatus.OPEN, TaskStatus.ACCEPTED, TaskStatus.RETURN, TaskStatus.DONE,
                      TaskStatus.FINISHED, TaskStatus.REFUSED, TaskStatus.BLOCKEDPAYMENT):
            task.delegation_date = base
        if status in (TaskStatus.ACCEPTED, TaskStatus.RETURN, TaskStatus.DONE, TaskStatus.FINISHED, TaskStatus.BLOCKEDPAYMENT):
            task.acceptance_date = base + timedelta(hours=6)
        if status in (TaskStatus.DONE, TaskStatus.FINISHED, TaskStatus.BLOCKEDPAYMENT):
            task.execution_date = task.final_deadline_date - timedelta(hours=2)
        if status is TaskStatus.RETURN:
            task.return_date = base + timedelta(days=1)
        if status is TaskStatus.REFUSED:
            task.refused_date = base + timedelta(hours=3)
        if status is TaskStatus.FINISHED:
            task.finished_date = task.final_deadline_date + timedelta(days=1)
        if status is TaskStatus.BLOCKEDPAYMENT:
            task.blocked_payment_date = task.final_deadline_date + timedelta(days=2)
