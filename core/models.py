import os
from enum import Enum
import hashlib
import time

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User, Group
from django.db.models import JSONField

from core.managers import PersonManager
from core.utils import LegacySystem, clear_cpf_cnpj
from guardian.shortcuts import get_perms
from oauth2_provider.models import Application, AbstractApplication


INVITE_STATUS = (('A', 'ACCEPTED'), ('R', 'REFUSED'), ('N', 'NOT REVIEWED'),
                 ('E', 'EXTERNAL'))
INVITE_FROM = (('P', 'PERSON'), ('O', 'OFFICE'))
INVALIDO = 1
PHONE = 2
EMAIL = 3
SKYPE = 4
WHATSAPP = 5
FACEBOOK = 6
SITE = 7
LINKEDIN = 8
INSTAGRAM = 9
SNAPCHAT = 10
CONTACT_MECHANISM_TYPE = ((INVALIDO, 'INVÁLIDO'), (PHONE, 'TELEFONE'),
                          (EMAIL, 'E-MAIL'), (SKYPE, 'SKYPE'), (WHATSAPP,
                                                                'WHATSAPP'),
                          (FACEBOOK, 'FACEBOOK'), (SITE, 'SITE'), (LINKEDIN,
                                                                   'LINKEDIN'),
                          (INSTAGRAM, 'INSTAGRAM'), (SNAPCHAT, 'SNAPCHAT'))


class CorePermissions(Enum):
    group_admin = 'Group Administrator'
    view_reports = 'View Reports menu'


class LegalType(Enum):
    FISICA = 'F'
    JURIDICA = 'J'

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.value, x.name) for x in cls]

    @staticmethod
    def format(value):
        """
        Mostra os tipos de pessoa de forma correta, com acento

        :param value: Valor selecionado sendo F ou J
        :type value: str
        :return: Retorna o valor a ser mostrado na tela para o usuario final
        :rtype: str
        """
        label = {'F': 'Física', 'J': 'Jurídica'}
        return label.get(value)


def _create_hash(size=False):
    hash = hashlib.sha1()
    hash_str = str(time.time()).encode('utf-8')
    hash.update(hash_str)
    return hash.hexdigest()[:size] if size else hash.hexdigest()


class AuditCreate(models.Model):
    # auto_now_add - toda vez que for criado
    create_date = models.DateTimeField('Criado em', auto_now_add=True)
    create_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='%(class)s_create_user',
        verbose_name='Criado por')

    class Meta:
        abstract = True


class OfficeManager(models.Manager):
    def get_queryset(self, office=False):
        res = super().get_queryset()
        if office:
            office_list = []
            if type(office) is list:
                office_list.extend(office)
            else:
                office_list.append(office)
            res = super().get_queryset().filter(office__id__in=office_list)
        return res


class AuditAlter(models.Model):
    # auto_now - toda vez que for salvo
    alter_date = models.DateTimeField(
        'Atualizado em', auto_now=True, blank=True, null=True)
    alter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='%(class)s_alter_user',
        verbose_name='Alterado por')

    class Meta:
        abstract = True


class LegacyCode(models.Model):
    legacy_code = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Código legado')
    system_prefix = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Prefixo do sistema',
        choices=((x.value, x.name.title()) for x in LegacySystem))

    class Meta:
        abstract = True
        unique_together = (('legacy_code', 'system_prefix'), )


class AdminSettings(models.Model):
    rate_commission_requestor = models.FloatField(default=0.025, verbose_name='Taxa de comissão do solicitante')
    rate_commission_correspondent = models.FloatField(default=0.1, verbose_name='Taxa de comissão do correspondente')

    def __str__(self):
        return 'Solicitante={0}, Correspondente={1}'.format(self.rate_commission_requestor, self.rate_commission_correspondent)

class Audit(AuditCreate, AuditAlter):
    is_active = models.BooleanField(
        null=False, default=True, verbose_name='Ativo')

    class Meta:
        abstract = True

    def activate(self):
        self.is_active = True
        self.save()

    def deactivate(self):
        self.is_active = False
        self.save()

    @property
    def use_upload(self):
        return True

    @property
    def upload_required(self):
        return False


class AddressType(Audit):
    name = models.CharField(max_length=255, null=False, unique=True)

    class Meta:
        db_table = 'address_type'
        ordering = ['name']

    def __str__(self):
        return self.name


class Country(Audit):
    name = models.CharField(max_length=255, null=False, unique=True)

    class Meta:
        db_table = 'country'
        verbose_name = 'País'
        verbose_name_plural = 'Paises'

    def __str__(self):
        return self.name


class State(Audit):
    name = models.CharField(max_length=255, null=False, unique=True)
    initials = models.CharField(max_length=10, null=False, unique=True)
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, blank=False, null=False)

    class Meta:
        db_table = 'state'
        verbose_name = 'Estado'
        ordering = ['name']

    def __str__(self):
        return self.name


class City(Audit):
    name = models.CharField(max_length=255, null=False)
    state = models.ForeignKey(
        State, on_delete=models.PROTECT, blank=False, null=False)

    court_district = models.ForeignKey(
        'lawsuit.CourtDistrict',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name='Comarca')

    class Meta:
        db_table = 'city'
        verbose_name = 'Cidade'
        unique_together = (('name', 'state'), )

    def __str__(self):
        return '{} - {}'.format(self.name, self.state.initials)


class AbstractPerson(Audit, LegacyCode):
    ADMINISTRATOR_GROUP = 'Administrador'
    CORRESPONDENT_GROUP = 'Correspondente'
    REQUESTER_GROUP = 'Solicitante'
    SERVICE_GROUP = 'Service'
    SUPERVISOR_GROUP = 'Supervisor'
    COMPANY_REPRESENTATIVE = 'Preposto'
    FINANCE_GROUP = 'Financeiro'
    legal_name = models.CharField(
        max_length=255, blank=False, verbose_name='Razão social/Nome completo')
    name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Nome Fantasia/Apelido')
    is_lawyer = models.BooleanField(
        null=False, default=False, verbose_name='É Advogado?')
    legal_type = models.CharField(
        null=False,
        verbose_name='Tipo',
        max_length=1,
        choices=((x.value, x.format(x.value)) for x in LegalType),
        default=LegalType.JURIDICA)
    cpf_cnpj = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        verbose_name='CPF/CNPJ')
    auth_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name='Usuário do sistema')
    is_customer = models.BooleanField(
        null=False, default=False, verbose_name='É Cliente?')
    is_supplier = models.BooleanField(
        null=False, default=False, verbose_name='É Fornecedor?')
    import_from_legacy = models.BooleanField(
        null=False,
        default=False,
        verbose_name='Importar OSs do sistema de origem para esse cliente',
    )

    @property
    def cpf(self):
        return self.cpf_cnpj

    @cpf.setter
    def cpf(self, value):
        self.cpf = value

    @property
    def cnpj(self):
        return self.cpf_cnpj

    @cnpj.setter
    def cnpj(self, value):
        self.cnpj = value

    def contact_mechanism_by_type(self, mechanism_type, formated=True):
        mechanism_type = ContactMechanismType.objects.filter(
            name__iexact=mechanism_type).first()
        contacts = self.contactmechanism_set.filter(
            contact_mechanism_type=mechanism_type)
        items = [contact.description for contact in contacts]
        if formated:
            return ' | '.join(items) if items else ''
        return items

    @property
    def emails(self):
        emails = self.get_emails()
        return ' | '.join(emails) if emails else ''

    @property
    def phones(self):
        return self.contact_mechanism_by_type('telefone')

    def get_emails(self):
        emails = self.contact_mechanism_by_type('e-mail', formated=False)
        emails = set(emails)
        if (self.auth_user and self.auth_user.email
                and self.auth_user.email.strip()):
            emails.add(self.auth_user.email.strip())
        return list(emails)

    def get_phones(self):
        return self.contact_mechanism_by_type('telefone', formated=False)

    def get_address(self):
        return self.address_set.exclude(id=1)

    @property
    def is_admin(self):
        return True if self.auth_user.groups.filter(name__startswith=self.ADMINISTRATOR_GROUP).first() \
            else False

    @property
    def is_correspondent(self):
        return True if self.auth_user.groups.filter(name__startswith=self.CORRESPONDENT_GROUP).first() \
            else False

    @property
    def is_requester(self):
        return True if self.auth_user.groups.filter(name__startswith=self.REQUESTER_GROUP).first() \
            else False

    @property
    def is_service(self):
        return True if self.auth_user.groups.filter(name__startswith=self.SERVICE_GROUP).first() \
            else False

    @property
    def is_supervisor(self):
        return True if self.auth_user.groups.filter(name__startswith=self.SUPERVISOR_GROUP).first() \
            else False

    @property
    def is_company_representative(self):
        return True if self.auth_user.groups.filter(name__startswith=self.COMPANY_REPRESENTATIVE).first() \
            else False

    class Meta:
        abstract = True

    def __str__(self):
        return self.legal_name or ''


class Company(models.Model):
    logo = models.ImageField(verbose_name='Logo', null=True, blank=True)
    name = models.CharField(verbose_name='Empresa', max_length=255)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'

    def __str__(self):
        return self.name


class CompanyUser(models.Model):
    user = models.ForeignKey(
        User, verbose_name='Usuário', related_name='companys', on_delete=models.PROTECT)
    company = models.ForeignKey(
        Company, verbose_name='Empresa', related_name='users', on_delete=models.PROTECT)
    show_administrative_menus = models.BooleanField(
        verbose_name="Mostrar menus administrativos", default=False)

    class Meta:
        verbose_name = 'Usuario da empresa'
        verbose_name_plural = 'Usuário das empresas'

    def __str__(self):
        return self.user.username


class Person(AbstractPerson):
    objects = PersonManager()

    cpf_cnpj = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=False,
        verbose_name='CPF/CNPJ')
    create_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='%(class)s_create_user',
        verbose_name='Criado por')
    alter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='%(class)s_alter_user',
        verbose_name='Alterado por')

    company = models.ForeignKey(
        Company,
        verbose_name='Compartilhar com empresa',
        null=True,
        blank=True, on_delete=models.PROTECT)

    refunds_correspondent_service = models.BooleanField(
        null=False, default=False, verbose_name='Cliente reembolsa valor gasto com serviço de correspondência')

    class Meta:
        db_table = 'person'
        ordering = ['legal_name', 'name']
        verbose_name = 'Pessoa'
        verbose_name_plural = 'Pessoas'

    def simple_serialize(self):
        """Simple JSON representation of instance"""
        return {
            "id": self.id,
            "legal_name": self.legal_name,
            "name": self.name
        }

    @property
    def get_person_permissions(self):
        permissions = dict()
        for group in self.auth_user.groups.all():
            if hasattr(group, 'officerelgroup'):
                if group.officerelgroup.office not in permissions:
                    permissions[group.officerelgroup.office] = []
                permissions[group.officerelgroup.office].extend(
                    get_perms(group, group.officerelgroup.office))
        return permissions


class Office(AbstractPerson):
    objects = PersonManager()
    logo = models.ImageField(verbose_name='Logo', null=True, blank=True)
    persons = models.ManyToManyField(
        Person, blank=True, related_name='offices', through='OfficeMembership')
    offices = models.ManyToManyField(
        'self', blank=True, through='OfficeOffices', symmetrical=False)
    public_office = models.BooleanField(
        default=False, verbose_name='Escritório público')
    use_service_old = models.BooleanField(
        default=True,
        verbose_name='Possuo equipe de conferência de dados na delegação e validação da OS')
    use_etl_old = models.BooleanField(
        default=True,
        verbose_name='Possuo processo de importação de dados de outros sistemas'
    )
    cpf_cnpj = models.CharField(max_length=255, blank=False, null=True,
                                unique=True, verbose_name='CPF/CNPJ')

    class Meta:
        verbose_name = 'Escritório'

    def __str__(self):
        return self.legal_name

    @property
    def ordered_groups(self):
        return self.office_groups.order_by('group__name')

    @property
    def states_of_practice(self):
        return self.office_correspondent.filter(state__isnull=False).order_by('state').distinct('state__name').values_list('state__name', flat=True)

    @property
    def type_of_service(self):
        return self.office_correspondent.filter(type_task__type_task_main__isnull=False).order_by(
            'type_task__type_task_main').distinct('type_task__type_task_main__name').values_list(
            'type_task__type_task_main__name', flat=True)

    def save(self, *args, **kwargs):
        self._i_work_alone = kwargs.pop('i_work_alone', False)
        self._use_service = kwargs.pop('use_service', True)
        self._use_etl = kwargs.pop('use_etl', True)
        if self.cpf_cnpj:
            self.cpf_cnpj = clear_cpf_cnpj(self.cpf_cnpj)
        return super().save(*args, **kwargs)

    def get_template(self, template_key):
        from manager.template_values import GetTemplateValue
        return GetTemplateValue(self, template_key)

    def get_template_value(self, template_key):
        return self.get_template(template_key).value

    def get_template_value_obj(self, template_key):
        return self.get_template(template_key).get_template_value_obj

    @property
    def use_service(self):
        from manager.enums import TemplateKeys
        return self.get_template_value(TemplateKeys.USE_SERVICE.name)

    @use_service.setter
    def use_service(self, value):
        from manager.enums import TemplateKeys
        from manager.utils import update_template_value
        new_value = 'on' if value else ''
        template_obj = self.get_template_value_obj(TemplateKeys.USE_SERVICE.name)
        update_template_value(template_obj, new_value)

    @property
    def use_etl(self):
        from manager.enums import TemplateKeys
        return self.get_template_value(TemplateKeys.USE_ETL.name)

    @use_etl.setter
    def use_etl(self, value):
        from manager.enums import TemplateKeys
        from manager.utils import update_template_value
        new_value = 'on' if value else ''
        template_obj = self.get_template_value_obj(TemplateKeys.USE_ETL.name)
        update_template_value(template_obj, new_value)

    @property
    def i_work_alone(self):
        from manager.enums import TemplateKeys
        return self.get_template_value(TemplateKeys.I_WORK_ALONE.name)

    @i_work_alone.setter
    def i_work_alone(self, value):
        from manager.enums import TemplateKeys
        from manager.utils import update_template_value
        new_value = 'on' if value else ''
        template_obj = self.get_template_value_obj(TemplateKeys.USE_SERVICE.name)
        update_template_value(template_obj, new_value)

    @property
    def duplicate_process(self):
        from manager.enums import TemplateKeys
        return self.get_template_value(TemplateKeys.DUPLICATE_PROCESS.name)

    @duplicate_process.setter
    def duplicate_process(self, value):
        from manager.enums import TemplateKeys
        from manager.utils import update_template_value
        template_obj = self.get_template_value_obj(TemplateKeys.DUPLICATE_PROCESS.name)
        update_template_value(template_obj, str(value))

    @property
    def related_offices(self):
        from django.db.models import Q
        qs = self._meta.model.objects.filter(Q(
            Q(id__in=self.to_offices.values_list('from_office', flat=True)) |
            Q(id__in=self.from_offices.values_list('to_office', flat=True)))
        )
        return qs


class OfficeMixin(models.Model):
    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        related_name='%(class)s_office',
        verbose_name='Escritório')

    class Meta:
        abstract = True


class NotesMixin(models.Model):
    notes = models.TextField(
        null=True, blank=True, verbose_name=u'Observações')

    class Meta:
        abstract = True


class OfficeOffices(Audit):
    from_office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name='from_offices',
                                    verbose_name='Escritório de Origem')
    to_office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name='to_offices',
                                  verbose_name='Escritório Relacionado')
    person_reference = models.ForeignKey(Person, on_delete=models.CASCADE, blank=True, null=True,
                                         verbose_name='Pessoa de Referência')

    class Meta:
        verbose_name = 'Relacionamento entre Escritórios'
        verbose_name_plural = 'Relacionamentos entre Escritórios'
        ordering = ('from_office__legal_name', 'to_office__legal_name')

    def __str__(self):
        return '{} - {}'.format(self.from_office, self.to_office)


class OfficeMembership(Audit):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    office = models.ForeignKey(Office, on_delete=models.CASCADE)


class OfficeRelGroup(models.Model):
    office = models.ForeignKey(
        Office, on_delete=models.CASCADE, related_name='office_groups')
    group = models.OneToOneField(Group, on_delete=models.CASCADE)

    @property
    def label_group(self):
        try:
            return self.group.name.split('-')[0]
        except:
            return self.group.name

    class Meta:
        verbose_name = 'Grupo por escritório'
        verbose_name_plural = 'Grupos por escritório'

    def __str__(self):
        return self.group.name


class DefaultOffice(OfficeMixin, Audit):
    auth_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=False,
        null=False,
        verbose_name='Usuário do sistema')

    objects = OfficeManager()

    class Meta:
        verbose_name = 'Escritório Padrão'
        verbose_name_plural = 'Escritórios Padrão'


class OfficeNetwork(Audit):
    name = models.CharField(verbose_name='Nome do grupo', max_length=255)
    members = models.ManyToManyField(
        Office, related_name='network_members', verbose_name='Membros')

    class Meta:
        verbose_name = 'Rede de escritórios'
        verbose_name_plural = 'Redes de escritórios'

    def __str__(self):
        return self.name

    @property
    def list_members(self):
        list_members = [x.__str__() for x in self.members.all().order_by('legal_name')]
        return list_members
    list_members.fget.short_description = 'Membros'


class Invite(Audit):
    person = models.ForeignKey(
        Person,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name='invites',
        verbose_name='Pessoa')
    office = models.ForeignKey(
        Office,
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name='invites',
        verbose_name='Escritório')
    status = models.CharField(
        choices=INVITE_STATUS,
        default='N',
        max_length=1,
        verbose_name='Status')
    email = models.EmailField(
        verbose_name='E-mail',
        blank=True,
        null=True,
        max_length=255,
    )
    invite_code = models.CharField(
        blank=True,
        null=True,
        verbose_name='Código do convite',
        max_length=50,
        default=_create_hash,
        unique=True)
    invite_from = models.CharField(
        choices=INVITE_FROM,
        default='O',
        max_length=1,
        verbose_name='Origem do convite')

    class Meta:
        verbose_name = 'Convite'

    def __str__(self):
        return self.person.legal_name if self.person else self.email


class InviteOffice(Audit, OfficeMixin):
    office_invite = models.ForeignKey(
        Office,
        blank=False,
        null=False,
        related_name='invites_offices',
        verbose_name='Escritório convidado', on_delete=models.PROTECT)
    status = models.CharField(
        choices=INVITE_STATUS,
        default='N',
        max_length=1,
        verbose_name='Status')

    def __str__(self):
        return self.office_invite.legal_name

    class Meta:
        verbose_name = 'Convite para escritório'
        verbose_name_plural = 'Convites para escritórios'


class Address(Audit, NotesMixin):
    address_type = models.ForeignKey(
        AddressType,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='Tipo')
    street = models.CharField(max_length=255, verbose_name='Logradouro')
    number = models.CharField(max_length=255, verbose_name='Número')
    complement = models.CharField(
        max_length=255, blank=True, verbose_name='Complemento')
    city_region = models.CharField(max_length=255, verbose_name='Bairro')
    zip_code = models.CharField(max_length=255, verbose_name='CEP')
    home_address = models.BooleanField(default=False, blank=True)
    business_address = models.BooleanField(default=False, blank=True)
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='Cidade')
    state = models.ForeignKey(
        State,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='Estado')
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='País')
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, blank=True, null=True)
    office = models.ForeignKey(
        Office, on_delete=models.PROTECT, blank=True, null=True)

    class Meta:
        db_table = 'address'
        verbose_name = 'Endereço'
        verbose_name_plural = 'Endereços'

    def __str__(self):
        tpl = '{street}, {number}{complement} - {city_region} - {city} - {state} - CEP {zip_code}'
        return tpl.format(
            number=self.number,
            street=self.street,
            city_region=self.city_region,
            city=self.city.name,
            state=self.state.name,
            zip_code=self.zip_code,
            complement='/' + self.complement if self.complement else '')


class ContactMechanismType(Audit):
    type_contact_mechanism_type = models.IntegerField(
        choices=CONTACT_MECHANISM_TYPE,
        verbose_name='Tipo',
        default=PHONE,
        null=False)
    name = models.CharField(max_length=255, null=False, unique=True)

    def is_email(self):
        return self.type_contact_mechanism_type == EMAIL

    class Meta:
        db_table = 'contact_mechanism_type'

    def __str__(self):
        return self.name


class ContactMechanism(Audit):
    contact_mechanism_type = models.ForeignKey(
        ContactMechanismType,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name="Tipo")
    description = models.CharField(
        max_length=255, null=False, verbose_name="Descrição")
    notes = models.CharField(
        max_length=400, blank=True, verbose_name="Observações")
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, blank=True, null=True)
    office = models.ForeignKey(
        Office, on_delete=models.PROTECT, blank=True, null=True)

    class Meta:
        db_table = 'contact_mechanism'
        verbose_name = 'Mecanismo de contato'
        verbose_name_plural = 'Mecanismos de contato'
        unique_together = (('description', 'person'), ('description',
                                                       'office'))

    def __str__(self):
        return self.description


class ContactUs(Audit):
    name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=255)
    message = models.TextField()

    class Meta:
        db_table = 'contact_us'

    def __str__(self):
        return self.name


class ModelExportHistory(models.Model):
    model = models.CharField(max_length=255, unique=True, null=False)


class Team(Audit, OfficeMixin):
    name = models.CharField(max_length=255, verbose_name='Nome')
    members = models.ManyToManyField(
        User, related_name='team_members', verbose_name='Membros')
    supervisors = models.ManyToManyField(
        User, related_name='team_supervisors', verbose_name='Supervisores')
    objects = OfficeManager()
    use_upload = False

    class Meta:
        verbose_name = 'Equipe'
        verbose_name_plural = 'Equipes'
        unique_together = (('office', 'name'), )

    def __str__(self):
        return self.name

    @staticmethod
    def get_members(user):
        users = []
        if user.person.is_supervisor:
            users.extend(list(
                Team.objects.filter(
                    supervisors=user).values_list('members', flat=True)))
        return users


def get_dir_name(instance, filename):
    path = os.path.join('media', 'service_price_table')
    if not os.path.exists(path):
        os.makedirs(path)
    return 'service_price_table/{0}'.format(filename)


class ImportXlsFile(Audit, OfficeMixin):
    file_xls = models.FileField('Arquivo', upload_to=get_dir_name)
    start = models.DateTimeField('Início processo')
    end = models.DateTimeField('Fim processo', null=True)
    log_file = JSONField(
        null=True,
        blank=True,
        verbose_name='Log do processo')

    def __str__(self):
        return self.file_xls.file.name + ' - ' + 'Início: ' + str(
            self.start) + ' - ' + 'Fim: ' + str(self.end)

    class Meta:
        verbose_name = 'Arquivos Importados para inserção em lote'


class ExternalApplication(AbstractApplication):
    office = models.ForeignKey(
        Office, verbose_name='Escritório', blank=True, null=True, on_delete=models.PROTECT)
    company = models.ForeignKey(
        Company, verbose_name='Empresa', blank=True, null=True, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Aplicação externa'
        verbose_name_plural = 'Aplicações externas'

    def __str__(self):
        return self.name


class ControlFirstAccessUser(models.Model):
    auth_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='Usuário do sistema')
    first_login = models.DateTimeField(
        "Data do primeiro acesso.", auto_now_add=True)

    def __str__(self):
        return self.auth_user.username

    class Meta:
        verbose_name = 'Controle de primeiro acesso'
        verbose_name_plural = 'Controle de primeiro acesso'


class CustomSettings(Audit):
    office = models.OneToOneField(Office, verbose_name='Escritório', on_delete=models.PROTECT)
    default_user = models.ForeignKey(User, verbose_name='Usuário default', blank=True, null=True, on_delete=models.PROTECT)
    email_to_notification = models.EmailField(verbose_name='E-mail para receber notificações',
                                              null=True, blank=True)
    i_work_alone = models.BooleanField(default=True)
    default_customer = models.ForeignKey(Person, verbose_name='Cliente padrão',
                                         blank=True, null=True,
                                         limit_choices_to={"is_customer": True}, on_delete=models.PROTECT)
    show_task_in_admin_dash = models.BooleanField(default=True, verbose_name='Mostrar as OSs deste escritório no Dash')

    class Meta:
        verbose_name = 'Configurações por escritório'

    def __str__(self):
        return self.office.legal_name


class EmailTemplate(models.Model):
    name = models.CharField(verbose_name='Nome do template', max_length=255)
    template_id = models.CharField(
        verbose_name='Template (caminho do arquivo .html)', max_length=255)

    class Meta:
        verbose_name = 'E-mail templates'

    def __str__(self):
        return self.name


class AreaOfExpertise(models.Model):
    area = models.CharField(verbose_name='Área de atuação', max_length=2555)
    offices = models.ManyToManyField(Office, blank=True)

    class Meta:
        verbose_name = 'Área de atuação'
        verbose_name_plural = 'Áreas de atuação'
        ordering = ['area']

    def __str__(self):
        return self.area


class BaseHistoricalModel(models.Model):
    history_office = models.ForeignKey(Office, null=True, blank=True, on_delete=models.PROTECT)
    history_notes = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True


class CustomMessage(models.Model):
    initial_date = models.DateTimeField(verbose_name='Data inicial')
    finish_date = models.DateTimeField(verbose_name='Data final')
    title = models.CharField(verbose_name="Título", max_length=255)
    message = models.TextField(verbose_name='Mensagem')
    link = models.URLField(verbose_name='Link', null=True, blank=True)

    class Meta:
        verbose_name = "Mensagens Customizadas"
        verbose_name_plural = "Mensagens Customizadas"

    def __str__(self):
        return self.title