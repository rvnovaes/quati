"""
Dados de demonstração para o Quati.

Povoa todos os cadastros do sistema no escritório padrão: pessoas (correspondentes,
solicitantes, clientes, preposto), endereços, instâncias, órgãos, varas,
complementos de comarca, centros de custo, tipos de movimentação, políticas e
tabelas de preço, equipes, questionários, regras de anexo, um escritório
correspondente em rede, pastas, processos e ordens de serviço distribuídas pelos
status (inclusive delegadas ao escritório correspondente), com prazos nos
próximos dias e histórico nos meses anteriores.

Uso: python manage.py seed_demo            (idempotente: não duplica se já rodou)
     python manage.py seed_demo --reset    (apaga as OS de demonstração e recria)
Pré-requisito: seed principal (scripts/seed_db.sh) e cidades (seed_cities).
"""
import json
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (CONTACT_MECHANISM_TYPE, EMAIL, PHONE, Address, AddressType, City, Company, ContactMechanism,
                         ContactMechanismType, Country, CustomMessage, DefaultOffice, Office, OfficeMembership,
                         OfficeNetwork, OfficeOffices, Person, State, Team)
from ecm.models import DefaultAttachmentRule
from financial.enums import BillingMoment, CategoryPrice, RateType
from financial.models import CostCenter, PolicyPrice, ServicePriceTable
from lawsuit.models import (CourtDistrict, CourtDistrictComplement, CourtDivision, Folder, Instance, LawSuit,
                            Movement, Organ, TypeLawsuit, TypeMovement)
from survey.models import Survey
from task.models import Task, TaskStatus, TypeTask
from task.utils import delegate_child_task

DEMO_MARK = '[demo]'
SENHA_DEMO = 'quati123'

CORRESPONDENTES = [
    ('ana.ribeiro', 'Ana Paula', 'Ribeiro', '34 98877-1201', 'Uberlândia', '123.456.789-01'),
    ('carlos.mota', 'Carlos Eduardo', 'Mota', '31 98877-1202', 'Belo Horizonte', '234.567.890-12'),
    ('juliana.ferraz', 'Juliana', 'Ferraz', '37 98877-1203', 'Divinópolis', '345.678.901-23'),
    ('marcos.lima', 'Marcos', 'Lima', '38 98877-1204', 'Montes Claros', '456.789.012-34'),
]
SOLICITANTES = [('beatriz.campos', 'Beatriz', 'Campos'), ('rafael.nunes', 'Rafael', 'Nunes')]
SUPERVISOR = ('helena.prado', 'Helena', 'Prado')
FINANCEIRO = ('otavio.reis', 'Otávio', 'Reis')
CLIENTES = [
    ('Construtora Horizonte Ltda.', '12.345.678/0001-90', 'Belo Horizonte'),
    ('Cooperativa Agrícola do Vale', '23.456.789/0001-01', 'Uberlândia'),
    ('Comércio de Alimentos Serra Azul S.A.', '34.567.890/0001-12', 'Contagem'),
]
PREPOSTO = ('lucas.andrade', 'Lucas', 'Andrade')
COMARCAS = ['Belo Horizonte', 'Uberlândia', 'Contagem', 'Montes Claros', 'Divinópolis', 'Juiz de Fora']
PARTES = ['João da Silva', 'Maria Oliveira', 'Transportadora Rápido Ltda.', 'Banco Nacional S.A.',
          'Pedro Henrique Souza', 'Distribuidora Minas Norte', 'Município de Contagem', 'Seguradora Atlas S.A.']
INSTANCIAS = ['1ª instância', '2ª instância', 'Instância superior', 'Administrativa']
VARAS = ['1ª Vara Cível', '2ª Vara Cível', '3ª Vara Cível', '1ª Vara Criminal', '1ª Vara do Trabalho',
         '2ª Vara do Trabalho', 'Vara de Família e Sucessões', 'Juizado Especial Cível', 'Vara da Fazenda Pública']
ORGAOS = [
    ('TJMG - Fórum Lafayette', 'Belo Horizonte'), ('TRT 3ª Região - Fórum Trabalhista de Belo Horizonte', 'Belo Horizonte'),
    ('Justiça Federal - Subseção de Belo Horizonte', 'Belo Horizonte'), ('TJMG - Fórum de Uberlândia', 'Uberlândia'),
    ('TRT 3ª Região - Vara do Trabalho de Uberlândia', 'Uberlândia'), ('TJMG - Fórum de Contagem', 'Contagem'),
    ('TJMG - Fórum de Montes Claros', 'Montes Claros'), ('TJMG - Fórum de Divinópolis', 'Divinópolis'),
    ('TJMG - Fórum Benjamin Colucci', 'Juiz de Fora'),
]
COMPLEMENTOS = [('Venda Nova', 'Belo Horizonte'), ('Barreiro', 'Belo Horizonte'), ('Justiça Federal', 'Uberlândia'),
                ('Juizados Especiais', 'Contagem')]
CENTROS_DE_CUSTO = ['Contencioso cível', 'Contencioso trabalhista', 'Criminal', 'Consultivo', 'Recuperação de crédito']
TIPOS_MOVIMENTACAO = [('Audiência', True), ('Protocolo', True), ('Diligência', True), ('Cópia de autos', True),
                      ('Despacho', False), ('Sentença', False)]
EQUIPES = [('Equipe cível', ['beatriz.campos', 'carlos.mota', 'juliana.ferraz']),
           ('Equipe trabalhista', ['rafael.nunes', 'ana.ribeiro', 'marcos.lima'])]

SURVEY_AUDIENCIA = {
    'title': 'Relatório de audiência',
    'pages': [{'name': 'page1', 'elements': [
        {'type': 'radiogroup', 'name': 'comparecimentoAudiencia', 'title': 'Você compareceu à audiência?', 'isRequired': True, 'choices': ['Sim', 'Não']},
        {'type': 'radiogroup', 'name': 'audienciaRealizada', 'title': 'A audiência foi realizada?', 'isRequired': True, 'choices': ['Sim', 'Não', 'Adiada']},
        {'type': 'radiogroup', 'name': 'resultado', 'title': 'Resultado', 'choices': ['Acordo', 'Sem acordo', 'Instrução encerrada', 'Redesignada']},
        {'type': 'text', 'name': 'novaData', 'title': 'Nova data (se redesignada)', 'inputType': 'date', 'visibleIf': "{resultado} = 'Redesignada'"},
        {'type': 'comment', 'name': 'observacoes', 'title': 'Observações relevantes'},
    ]}],
}
SURVEY_PROTOCOLO = {
    'title': 'Comprovante de protocolo',
    'pages': [{'name': 'page1', 'elements': [
        {'type': 'text', 'name': 'numeroProtocolo', 'title': 'Número do protocolo', 'isRequired': True},
        {'type': 'text', 'name': 'dataProtocolo', 'title': 'Data do protocolo', 'inputType': 'date', 'isRequired': True},
        {'type': 'radiogroup', 'name': 'guiaPaga', 'title': 'Havia guia de custas? Foi paga?', 'choices': ['Não havia', 'Sim, paga', 'Pendente']},
        {'type': 'comment', 'name': 'observacoes', 'title': 'Observações'},
    ]}],
}
SURVEY_PREPOSTO = {
    'title': 'Avaliação do preposto',
    'pages': [{'name': 'page1', 'elements': [
        {'type': 'rating', 'name': 'atendimento', 'title': 'Como foi o atendimento do correspondente?', 'rateMax': 5},
        {'type': 'radiogroup', 'name': 'pontualidade', 'title': 'O correspondente chegou no horário?', 'choices': ['Sim', 'Não']},
        {'type': 'comment', 'name': 'comentarios', 'title': 'Comentários'},
    ]}],
}

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
# histórico: OS finalizadas nos meses anteriores (para relatórios a pagar/receber)
HISTORICO_TIPOS = ['Protocolo', 'Cópia', 'Certidão', 'Audiência cível - apenas advogado', 'Alvará',
                   'Audiência trabalhista una/instrução - apenas advogado']
# OS delegadas ao escritório correspondente (status da OS filha)
DELEGADAS = [
    (TaskStatus.REQUESTED, 3, 'Audiência cível - apenas advogado', 'Delegada à rede: audiência em Contagem.'),
    (TaskStatus.ACCEPTED, 6, 'Protocolo', 'Delegada à rede: protocolo em Juiz de Fora.'),
    (TaskStatus.DONE, -3, 'Cópia', 'Delegada à rede: cópia de autos entregue.'),
]


class Command(BaseCommand):
    help = 'Cria dados de demonstração em todos os cadastros do primeiro escritório.'

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
        if not City.objects.exists():
            self.stdout.write(self.style.WARNING('Nenhuma cidade cadastrada: rode "manage.py seed_cities" para ter endereços completos.'))

        with transaction.atomic():
            self.ensure_reference_types(admin)
            if options['reset']:
                deleted, _ = Task.objects.filter(description__endswith=DEMO_MARK).order_by('-parent_id').delete()
                self.stdout.write('OS de demonstração removidas: {}'.format(deleted))
            elif Task.objects.filter(office=office, description__endswith=DEMO_MARK).exists():
                self.stdout.write('Dados de demonstração já existem. Use --reset para recriar as OS.')
                return

            self.office, self.admin = office, admin
            self.comarcas = {c.name: c for c in CourtDistrict.objects.filter(name__in=COMARCAS, state__initials='MG')}
            self.mg = State.objects.filter(initials='MG').first()
            self.brasil = Country.objects.order_by('pk').first()
            self.tipos_os = {t.name: t for t in TypeTask.objects.filter(office=office)}

            correspondentes = [self.pessoa_com_usuario(Person.CORRESPONDENT_GROUP, u, f, l, phone=ph, cidade=cid, cpf=cpf, is_lawyer=True)
                               for u, f, l, ph, cid, cpf in CORRESPONDENTES]
            solicitantes = [self.pessoa_com_usuario(Person.REQUESTER_GROUP, *s, cidade='Belo Horizonte') for s in SOLICITANTES]
            self.pessoa_com_usuario(Person.SUPERVISOR_GROUP, *SUPERVISOR, cidade='Belo Horizonte')
            self.pessoa_com_usuario(Person.FINANCE_GROUP, *FINANCEIRO, cidade='Belo Horizonte')
            clientes = [self.cliente(nome, cnpj, cidade) for nome, cnpj, cidade in CLIENTES]
            empresa, preposto = self.empresa_e_preposto(clientes[0])
            self.endereco_do_escritorio()

            instancias = self.simples(Instance, INSTANCIAS)
            varas = self.simples(CourtDivision, VARAS)
            centros = self.simples(CostCenter, CENTROS_DE_CUSTO)
            orgaos = self.orgaos()
            self.complementos()
            tipos_mov = self.tipos_movimentacao()
            politicas = self.politicas_de_preco()
            office2 = self.escritorio_correspondente()
            self.rede(office2)
            self.tabela_de_precos(office2, politicas)
            self.equipes()
            self.questionarios()
            self.regras_de_anexo(clientes)
            self.novidade()

            movimentos = self.processos(clientes, centros, instancias, varas, orgaos, tipos_mov, correspondentes)
            criadas = self.ordens_de_servico(movimentos, correspondentes, solicitantes, preposto)
            criadas += self.historico(movimentos, correspondentes, solicitantes)
            criadas += self.delegadas(movimentos, correspondentes, solicitantes, office2)

        self.stdout.write(self.style.SUCCESS(
            'Demo criada: {} correspondentes, {} solicitantes, {} clientes, {} processos, {} OS (incluindo {} delegadas ao '
            'escritório correspondente). Senha dos usuários de demonstração: {}'.format(
                len(correspondentes), len(solicitantes), len(clientes), len(movimentos), criadas, len(DELEGADAS), SENHA_DEMO)))

    # -------------------------------------------------------------- referência
    def ensure_reference_types(self, admin):
        for pk, name in CONTACT_MECHANISM_TYPE:
            ContactMechanismType.objects.get_or_create(pk=pk, defaults={'name': name.title(), 'create_user': admin})
        for name in ('Comercial', 'Residencial', 'Correspondência'):
            AddressType.objects.get_or_create(name=name, defaults={'create_user': admin})

    def grupo(self, base, office=None):
        group, _ = Group.objects.get_or_create(name='{}-{}'.format(base, (office or self.office).pk))
        return group

    def cidade(self, nome):
        return City.objects.filter(name=nome, state=self.mg).order_by('pk').first()

    # ------------------------------------------------------------------ pessoas
    def usuario(self, username, first_name, last_name):
        user, created = User.objects.get_or_create(
            username=username, defaults={'first_name': first_name, 'last_name': last_name,
                                         'email': '{}@labp2.direito.ufmg.br'.format(username)})
        if created:
            user.set_password(SENHA_DEMO)
            user.save()
        person = Person.objects.filter(auth_user=user).first()
        if person is None:
            nome = '{} {}'.format(first_name, last_name)
            person = Person.objects.create(legal_name=nome, name=nome, legal_type='F', auth_user=user,
                                           create_user=self.admin, is_active=True)
        return user, person

    def pessoa_com_usuario(self, grupo, username, first_name, last_name, phone=None, cidade=None, cpf=None,
                           is_lawyer=False, office=None):
        office = office or self.office
        user, person = self.usuario(username, first_name, last_name)
        user.groups.add(self.grupo(grupo, office))
        person.is_lawyer = is_lawyer
        person.legal_type = 'F'
        if cpf and not person.cpf_cnpj:
            person.cpf_cnpj = cpf
        person.save()
        OfficeMembership.objects.get_or_create(person=person, office=office, defaults={'create_user': self.admin, 'is_active': True})
        self.contato(person, EMAIL, user.email)
        if phone:
            self.contato(person, PHONE, phone)
        if cidade:
            self.endereco(person=person, cidade=cidade, tipo='Residencial')
        return person

    def cliente(self, nome, cnpj, cidade):
        person, _ = Person.objects.get_or_create(
            legal_name=nome, defaults={'name': nome, 'legal_type': 'J', 'cpf_cnpj': cnpj, 'is_customer': True,
                                       'create_user': self.admin, 'is_active': True})
        OfficeMembership.objects.get_or_create(person=person, office=self.office, defaults={'create_user': self.admin, 'is_active': True})
        self.contato(person, EMAIL, 'juridico@{}.com.br'.format(nome.split()[0].lower().replace('.', '')))
        self.contato(person, PHONE, '31 3{:03d}-{:04d}'.format(random.randint(100, 999), random.randint(1000, 9999)))
        self.endereco(person=person, cidade=cidade, tipo='Comercial')
        return person

    def empresa_e_preposto(self, cliente):
        empresa, _ = Company.objects.get_or_create(name=cliente.legal_name)
        if cliente.company_id != empresa.pk:
            cliente.company = empresa
            cliente.save()
        preposto = self.pessoa_com_usuario(Person.COMPANY_REPRESENTATIVE, *PREPOSTO, phone='31 98877-1300', cidade='Belo Horizonte')
        if preposto.company_id != empresa.pk:
            preposto.company = empresa
            preposto.save()
        return empresa, preposto

    def contato(self, person, tipo_pk, valor):
        ContactMechanism.objects.get_or_create(
            person=person, contact_mechanism_type_id=tipo_pk, description=valor, defaults={'create_user': self.admin})

    def endereco(self, cidade, tipo, person=None, office=None):
        city = self.cidade(cidade)
        if city is None or self.brasil is None:
            return None
        address_type = AddressType.objects.get(name=tipo)
        existing = Address.objects.filter(person=person, office=office, city=city).first()
        if existing:
            return existing
        ruas = ['Rua da Bahia', 'Avenida Afonso Pena', 'Rua Goitacazes', 'Avenida João Naves de Ávila', 'Rua Tiradentes', 'Avenida Amazonas']
        return Address.objects.create(
            address_type=address_type, street=random.choice(ruas), number=str(random.randint(100, 2500)),
            complement='', city_region=random.choice(['Centro', 'Funcionários', 'Savassi', 'Santo Agostinho', 'Lourdes']),
            zip_code='{:05d}-{:03d}'.format(random.randint(30100, 38400), random.randint(0, 999)),
            city=city, state=city.state, country=self.brasil, person=person, office=office,
            create_user=self.admin, is_active=True, business_address=(tipo == 'Comercial'), home_address=(tipo == 'Residencial'))

    def endereco_do_escritorio(self):
        self.endereco(office=self.office, cidade='Belo Horizonte', tipo='Comercial')
        ContactMechanism.objects.get_or_create(
            office=self.office, contact_mechanism_type_id=PHONE, description='31 3222-1000', defaults={'create_user': self.admin})
        ContactMechanism.objects.get_or_create(
            office=self.office, contact_mechanism_type_id=EMAIL, description='contato@{}'.format(self.admin.email.split('@')[-1]),
            defaults={'create_user': self.admin})

    # ---------------------------------------------------------------- cadastros
    def simples(self, model, nomes):
        objetos = []
        for nome in nomes:
            obj, _ = model.objects.get_or_create(office=self.office, name=nome, defaults={'create_user': self.admin, 'is_active': True})
            objetos.append(obj)
        return objetos

    def orgaos(self):
        objetos = []
        for nome, comarca in ORGAOS:
            cd = self.comarcas.get(comarca)
            if cd is None:
                continue
            organ = Organ.objects.filter(office=self.office, legal_name=nome).first()
            if organ is None:
                organ = Organ.objects.create(office=self.office, legal_name=nome, name=nome, legal_type='J',
                                             court_district=cd, create_user=self.admin, is_active=True)
            objetos.append(organ)
        return objetos

    def complementos(self):
        for nome, comarca in COMPLEMENTOS:
            cd = self.comarcas.get(comarca)
            if cd:
                CourtDistrictComplement.objects.get_or_create(
                    office=self.office, name=nome, court_district=cd, defaults={'create_user': self.admin, 'is_active': True})

    def tipos_movimentacao(self):
        objetos = []
        for nome, uses_wo in TIPOS_MOVIMENTACAO:
            obj, _ = TypeMovement.objects.get_or_create(
                office=self.office, name=nome, defaults={'create_user': self.admin, 'is_active': True, 'uses_wo': uses_wo})
            objetos.append(obj)
        return objetos

    def politicas_de_preco(self):
        politicas = {}
        for nome, categoria, momento in [('Tabela padrão', CategoryPrice.DEFAULT, BillingMoment.POST_PAID),
                                         ('Pré-pago', CategoryPrice.DEFAULT, BillingMoment.PRE_PAID),
                                         ('Rede de correspondentes', CategoryPrice.NETWORK, BillingMoment.POST_PAID),
                                         ('Preço público', CategoryPrice.PUBLIC, BillingMoment.POST_PAID)]:
            obj, _ = PolicyPrice.objects.get_or_create(
                office=self.office, name=nome,
                defaults={'category': categoria.name, 'billing_moment': momento.name, 'create_user': self.admin, 'is_active': True})
            politicas[nome] = obj
        return politicas

    def escritorio_correspondente(self):
        nome = 'Lima & Souza Advogados Associados'
        office2 = Office.objects.filter(legal_name=nome).first()
        user, person = self.usuario('lima.souza', 'Fernanda', 'Lima')
        if office2 is None:
            office2 = Office.objects.create(legal_name=nome, name='Lima & Souza', legal_type='J',
                                            cpf_cnpj='45.678.901/0001-23', create_user=user, is_active=True, public_office=True)
        OfficeMembership.objects.get_or_create(person=person, office=office2, defaults={'create_user': user, 'is_active': True})
        user.groups.add(self.grupo(Person.ADMINISTRATOR_GROUP, office2))
        DefaultOffice.objects.get_or_create(auth_user=user, defaults={'office': office2, 'create_user': user})
        self.pessoa_com_usuario(Person.CORRESPONDENT_GROUP, 'paulo.souza', 'Paulo', 'Souza', phone='32 98877-1401',
                                cidade='Juiz de Fora', cpf='567.890.123-45', is_lawyer=True, office=office2)
        self.endereco(office=office2, cidade='Juiz de Fora', tipo='Comercial')
        OfficeOffices.objects.get_or_create(from_office=self.office, to_office=office2,
                                            defaults={'create_user': self.admin, 'is_active': True, 'person_reference': person})
        return office2

    def rede(self, office2):
        rede, _ = OfficeNetwork.objects.get_or_create(name='Rede Minas de correspondentes', defaults={'create_user': self.admin, 'is_active': True})
        rede.members.add(self.office, office2)
        return rede

    def tabela_de_precos(self, office2, politicas):
        linhas = [
            ('Audiência cível - apenas advogado', 'Belo Horizonte', 350, 250), ('Audiência cível - apenas advogado', 'Contagem', 400, 280),
            ('Audiência cível - advogado e preposto', 'Belo Horizonte', 550, 400), ('Audiência trabalhista una/instrução - apenas advogado', 'Uberlândia', 500, 350),
            ('Protocolo', 'Belo Horizonte', 120, 80), ('Protocolo', 'Juiz de Fora', 180, 120),
            ('Cópia', 'Belo Horizonte', 150, 100), ('Cópia', 'Montes Claros', 220, 150),
            ('Certidão', 'Belo Horizonte', 130, 90), ('Alvará', 'Divinópolis', 300, 200),
            ('Outros Serviços', 'Belo Horizonte', 200, 140),
        ]
        for tipo, comarca, receber, pagar in linhas:
            type_task = self.tipos_os.get(tipo)
            cd = self.comarcas.get(comarca)
            if not type_task or not cd:
                continue
            ServicePriceTable.objects.get_or_create(
                office=self.office, office_correspondent=office2, type_task=type_task, court_district=cd, state=self.mg,
                defaults={'policy_price': politicas['Rede de correspondentes'], 'value': Decimal(receber),
                          'value_to_receive': Decimal(receber), 'value_to_pay': Decimal(pagar),
                          'rate_type_receive': RateType.VALUE.name, 'rate_type_pay': RateType.VALUE.name,
                          'create_user': self.admin, 'is_active': True})
        # tabela pública: sem correspondente fixo, por estado
        for tipo, receber, pagar in [('Protocolo', 150, 100), ('Cópia', 180, 120), ('Certidão', 160, 110)]:
            type_task = self.tipos_os.get(tipo)
            if type_task:
                ServicePriceTable.objects.get_or_create(
                    office=self.office, office_correspondent=None, type_task=type_task, court_district=None, state=self.mg,
                    policy_price=politicas['Preço público'],
                    defaults={'value': Decimal(receber), 'value_to_receive': Decimal(receber), 'value_to_pay': Decimal(pagar),
                              'rate_type_receive': RateType.VALUE.name, 'rate_type_pay': RateType.VALUE.name,
                              'create_user': self.admin, 'is_active': True})

    def equipes(self):
        supervisor = User.objects.filter(username=SUPERVISOR[0]).first()
        for nome, membros in EQUIPES:
            team, _ = Team.objects.get_or_create(office=self.office, name=nome, defaults={'create_user': self.admin, 'is_active': True})
            team.members.set(User.objects.filter(username__in=membros))
            if supervisor:
                team.supervisors.set([supervisor])

    def questionarios(self):
        surveys = {}
        for nome, data in [('Relatório de audiência', SURVEY_AUDIENCIA), ('Comprovante de protocolo', SURVEY_PROTOCOLO),
                           ('Avaliação do preposto', SURVEY_PREPOSTO)]:
            survey, _ = Survey.objects.get_or_create(
                office=self.office, name=nome, defaults={'data': json.dumps(data, ensure_ascii=False), 'create_user': self.admin, 'is_active': True})
            surveys[nome] = survey
        audiencias = TypeTask.objects.filter(office=self.office, name__istartswith='Audiência')
        audiencias.filter(survey__isnull=True).update(survey=surveys['Relatório de audiência'])
        audiencias.filter(name__icontains='preposto', survey_company_representative__isnull=True) \
            .update(survey_company_representative=surveys['Avaliação do preposto'])
        TypeTask.objects.filter(office=self.office, name='Protocolo', survey__isnull=True).update(survey=surveys['Comprovante de protocolo'])

    def regras_de_anexo(self, clientes):
        regras = [
            ('Carta de preposição', 'Anexar carta de preposição assinada e documento do preposto.', 'Audiência cível - advogado e preposto', None),
            ('Substabelecimento', 'Substabelecimento sem reserva de poderes para o correspondente.', 'Audiência cível - apenas advogado', None),
            ('Guia de custas', 'Guia de custas e comprovante de pagamento.', 'Protocolo', None),
            ('Procuração do cliente', 'Procuração atualizada da Construtora Horizonte.', None, clientes[0]),
        ]
        for nome, descricao, tipo, cliente in regras:
            DefaultAttachmentRule.objects.get_or_create(
                office=self.office, name=nome,
                defaults={'description': descricao, 'type_task': self.tipos_os.get(tipo) if tipo else None,
                          'person_customer': cliente, 'state': self.mg, 'create_user': self.admin, 'is_active': True})

    def novidade(self):
        agora = timezone.now()
        CustomMessage.objects.get_or_create(
            title='Bem-vindo ao Quati',
            defaults={'message': 'Este ambiente contém dados de demonstração. Explore o dashboard, as OS e os cadastros à vontade.',
                      'initial_date': agora - timedelta(days=1), 'finish_date': agora + timedelta(days=365),
                      'link': 'https://labp2.direito.ufmg.br/'})

    # ---------------------------------------------------------------- processos
    def processos(self, clientes, centros, instancias, varas, orgaos, tipos_mov, correspondentes):
        movimentos = []
        numero = 0
        advogados = [p for p in correspondentes]
        for i, cliente in enumerate(clientes, start=1):
            folder, _ = Folder.objects.get_or_create(
                office=self.office, person_customer=cliente, folder_number=i,
                defaults={'create_user': self.admin, 'is_active': True, 'cost_center': centros[i % len(centros)]})
            for j in range(3):
                numero += 1
                cnj = '{:07d}-{:02d}.2026.8.13.{:04d}'.format(100000 + numero * 137, 10 + numero, 24 + numero)
                comarca_nome = COMARCAS[(numero - 1) % len(COMARCAS)]
                comarca = self.comarcas.get(comarca_nome)
                orgao = next((o for o in orgaos if o.court_district_id == (comarca.pk if comarca else None)), None)
                lawsuit, _ = LawSuit.objects.get_or_create(
                    office=self.office, folder=folder, law_suit_number=cnj,
                    defaults={'create_user': self.admin, 'is_active': True, 'court_district': comarca,
                              'type_lawsuit': TypeLawsuit.JUDICIAL.name, 'is_current_instance': True,
                              'opposing_party': PARTES[(numero - 1) % len(PARTES)],
                              'instance': instancias[numero % 2], 'organ': orgao, 'court_division': varas[numero % len(varas)],
                              'person_lawyer': advogados[numero % len(advogados)], 'city': self.cidade(comarca_nome)})
                tipo = tipos_mov[numero % 4]
                movement, _ = Movement.objects.get_or_create(
                    office=self.office, folder=folder, law_suit=lawsuit, type_movement=tipo,
                    defaults={'create_user': self.admin, 'is_active': True})
                movimentos.append(movement)
        return movimentos

    # ----------------------------------------------------------------------- OS
    def nova_os(self, movimento, status, prazo, tipo_nome, descricao, solicitante, executor, preposto=None, office=None, extra=None):
        agora = timezone.localtime()
        valor = Decimal(random.choice([180, 250, 320, 400, 550, 700]))
        comarca = movimento.law_suit.court_district
        fallback = TypeTask.objects.filter(office=self.office).order_by('pk').first()
        task = Task(
            office=office or self.office, create_user=self.admin, is_active=True,
            movement=movimento, type_task=self.tipos_os.get(tipo_nome, fallback),
            task_status=status.value, person_asked_by=solicitante,
            person_distributed_by=getattr(self.admin, 'person', None), person_executed_by=executor,
            person_company_representative=preposto,
            final_deadline_date=prazo,
            requested_date=min(agora, prazo) - timedelta(days=random.randint(3, 8)),
            description='{} {}'.format(descricao, DEMO_MARK),
            performance_place='{} - {}'.format(comarca.name, comarca.state.initials) if comarca else 'Belo Horizonte - MG',
            amount=valor, amount_delegated=valor, amount_to_receive=valor,
            amount_to_pay=(valor * Decimal('0.7')).quantize(Decimal('0.01')),
        )
        self.datas_por_status(task, status, agora, prazo)
        for k, v in (extra or {}).items():
            setattr(task, k, v)
        task.save(skip_signal=True, skip_mail=True)
        return task

    def ordens_de_servico(self, movimentos, correspondentes, solicitantes, preposto):
        agora = timezone.localtime()
        criadas = 0
        for i, (status, dias, nome_tipo, descricao) in enumerate(OS_DEMO):
            prazo = (agora + timedelta(days=dias)).replace(hour=random.choice([9, 10, 11, 14, 15, 16]), minute=0, second=0, microsecond=0)
            executor = None if status is TaskStatus.REQUESTED else correspondentes[i % len(correspondentes)]
            usa_preposto = 'preposto' in nome_tipo and 'apenas advogado' not in nome_tipo
            self.nova_os(movimentos[i % len(movimentos)], status, prazo, nome_tipo, descricao,
                         solicitantes[i % len(solicitantes)], executor, preposto if usa_preposto else None)
            criadas += 1
        return criadas

    def historico(self, movimentos, correspondentes, solicitantes):
        """OS finalizadas nos últimos 5 meses, com faturamento e recebimento, para os relatórios."""
        agora = timezone.localtime()
        criadas = 0
        for mes in range(1, 6):
            for k in range(3):
                dias = mes * 30 + k * 7
                prazo = (agora - timedelta(days=dias)).replace(hour=14, minute=0, second=0, microsecond=0)
                i = criadas
                task = self.nova_os(movimentos[i % len(movimentos)], TaskStatus.FINISHED, prazo, HISTORICO_TIPOS[i % len(HISTORICO_TIPOS)],
                                    'Serviço concluído e conferido.', solicitantes[i % len(solicitantes)],
                                    correspondentes[i % len(correspondentes)],
                                    extra={'billing_date': prazo + timedelta(days=5), 'receipt_date': prazo + timedelta(days=20)})
                criadas += 1
        return criadas

    def delegadas(self, movimentos, correspondentes, solicitantes, office2):
        """OS do escritório padrão delegadas ao escritório correspondente (OS pai + OS filha)."""
        agora = timezone.localtime()
        executor2 = Person.objects.filter(auth_user__username='paulo.souza').first()
        criadas = 0
        for i, (status_filha, dias, nome_tipo, descricao) in enumerate(DELEGADAS):
            prazo = (agora + timedelta(days=dias)).replace(hour=10, minute=0, second=0, microsecond=0)
            pai = self.nova_os(movimentos[(i + 5) % len(movimentos)], TaskStatus.OPEN, prazo, nome_tipo, descricao,
                               solicitantes[i % len(solicitantes)], None)
            delegate_child_task(pai, office2, pai.type_task, pai.amount_delegated)
            filha = Task.objects.filter(parent=pai).order_by('-pk').first()
            if filha is None:
                continue
            campos_filha = {'task_status': status_filha.value, 'description': '{} {}'.format(descricao, DEMO_MARK),
                            'person_executed_by': executor2 if status_filha is not TaskStatus.REQUESTED else None}
            campos_pai = {}
            if status_filha is TaskStatus.ACCEPTED:
                campos_filha.update(acceptance_date=agora - timedelta(days=1))
                campos_pai = {'task_status': TaskStatus.ACCEPTED.value, 'acceptance_date': agora - timedelta(days=1)}
            elif status_filha is TaskStatus.DONE:
                campos_filha.update(acceptance_date=agora - timedelta(days=6), execution_date=prazo - timedelta(hours=2))
                campos_pai = {'task_status': TaskStatus.DONE.value, 'acceptance_date': agora - timedelta(days=6),
                              'execution_date': prazo - timedelta(hours=2)}
            Task.objects.filter(pk=filha.pk).update(**campos_filha)
            if campos_pai:
                Task.objects.filter(pk=pai.pk).update(**campos_pai)
            criadas += 2
        return criadas

    @staticmethod
    def datas_por_status(task, status, agora, prazo):
        base = min(agora, prazo) - timedelta(days=random.randint(2, 5))
        if status in (TaskStatus.OPEN, TaskStatus.ACCEPTED, TaskStatus.RETURN, TaskStatus.DONE,
                      TaskStatus.FINISHED, TaskStatus.REFUSED, TaskStatus.BLOCKEDPAYMENT):
            task.delegation_date = base
        if status in (TaskStatus.ACCEPTED, TaskStatus.RETURN, TaskStatus.DONE, TaskStatus.FINISHED, TaskStatus.BLOCKEDPAYMENT):
            task.acceptance_date = base + timedelta(hours=6)
        if status in (TaskStatus.DONE, TaskStatus.FINISHED, TaskStatus.BLOCKEDPAYMENT):
            task.execution_date = prazo - timedelta(hours=2)
        if status is TaskStatus.RETURN:
            task.return_date = base + timedelta(days=1)
        if status is TaskStatus.REFUSED:
            task.refused_date = base + timedelta(hours=3)
        if status is TaskStatus.FINISHED:
            task.finished_date = prazo + timedelta(days=1)
        if status is TaskStatus.BLOCKEDPAYMENT:
            task.blocked_payment_date = prazo + timedelta(days=2)
