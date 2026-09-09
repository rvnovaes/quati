import os
import json
from enum import Enum
from django.db import router, transaction
import uuid
import pickle
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.urls.base import reverse
from django.utils import timezone
from sequences import get_next_value
from core.models import Person, Audit, AuditCreate, LegacyCode, OfficeMixin, OfficeManager, Office, CustomSettings, \
    EmailTemplate, State
from lawsuit.models import Movement, Folder, CourtDistrict, CourtDivision
from chat.models import Chat
from billing.models import Charge
from decimal import Decimal
from .schemas import *
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField
from django.forms import MultipleChoiceField
from .mail import TaskCompanyRepresentativeChangeMail
from simple_history.models import HistoricalRecords
from core.models import BaseHistoricalModel, NotesMixin
from financial.enums import CategoryPrice, RateType


class ChoiceArrayField(ArrayField):
    """
    A field that allows us to store an array of choices.
    Uses Django's Postgres ArrayField
    and a MultipleChoiceField for its formfield.
    """

    def formfield(self, **kwargs):
        defaults = {
            'form_class': MultipleChoiceField,
            'choices': self.base_field.choices,
        }
        defaults.update(kwargs)
        # Skip our parent's formfield implementation completely as we don't
        # care for it.
        # pylint:disable=bad-super-call
        return super(ArrayField, self).formfield(**defaults)


class Permissions(Enum):
    can_access_settings = 'Can access custom settings'
    view_delegated_tasks = 'Can view tasks delegated to the user'
    view_all_tasks = 'Can view all tasks'
    return_all_tasks = 'Can return tasks'
    validate_all_tasks = 'Can validade tasks'
    view_requested_tasks = 'Can view tasks requested by the user'
    block_payment_tasks = 'Can block tasks payment'
    can_access_general_data = 'Can access general data screens'
    view_distributed_tasks = 'Can view tasks distributed by the user'
    can_distribute_tasks = 'Can distribute tasks to another user'
    can_see_tasks_from_team_members = 'Can see tasks from your team members'
    can_see_tasks_company_representative = 'Can see tasks your company representative'
    view_checkin_report = 'Can view checkin report'


# Dicionário para retornar o icone referente ao status da providencia
icon_dict = {
    'ACCEPTED': 'mdi mdi-calendar-clock',
    'OPEN': 'mdi mdi-account-location',
    'RETURN': 'mdi mdi-backburger',
    'DONE': 'mdi mdi-checkbox-marked-circle-outline',
    'REFUSED': 'mdi mdi-clipboard-alert',
    'INVALID': 'mdi mdi-exclamation',
    'FINISHED': 'mdi mdi-gavel',
    'BLOCKEDPAYMENT': 'mdi mdi-currency-usd-off',
    'ERROR': 'mdi mdi-close-circle-outline',
    'REQUESTED': 'mdi mdi-playlist-play',
    'ACCEPTED_SERVICE': 'mdi mdi-thumb-up-outline',
    'REFUSED_SERVICE': 'mdi mdi-thumb-down-outline',
}

color_dict = {
    'ACCEPTED': 'success',
    'OPEN': 'primary',
    'RETURN': 'warning',
    'DONE': 'info',
    'REFUSED': 'warning',
    'INVALID': 'muted',
    'FINISHED': 'success',
    'BLOCKEDPAYMENT': 'muted',
    'ERROR': 'danger',
    'REQUESTED': 'danger',
    'ACCEPTED_SERVICE': 'danger',
    'REFUSED_SERVICE': 'danger',
}

status_order_dict = {
    'ACCEPTED': 6,
    'OPEN': 5,
    'RETURN': 4,
    'DONE': 7,
    'REFUSED': 9,
    'INVALID': 11,
    'FINISHED': 8,
    'BLOCKEDPAYMENT': 10,
    'ERROR': 0,
    'REQUESTED': 1,
    'ACCEPTED_SERVICE': 2,
    'REFUSED_SERVICE': 3,
}


class TypeTaskTypes(Enum):
    LICENSE = "Alvará"
    AUDIENCE = "Audiência"
    DILIGENCE = "Diligência"
    PROTOCOL = "Protocolo"

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.value, x.name) for x in cls]


class TaskStatus(Enum):
    REQUESTED = 'Solicitada'
    ACCEPTED_SERVICE = 'Aceita pelo Service'
    OPEN = 'Em Aberto'
    ACCEPTED = 'A Cumprir'
    DONE = 'Cumprida'
    RETURN = 'Retorno'
    FINISHED = 'Finalizada'
    REFUSED_SERVICE = 'Recusada pelo Service'
    REFUSED = 'Recusada'
    BLOCKEDPAYMENT = 'Glosada'
    INVALID = 'Inválida'
    ERROR = 'Erro no sistema de origem'

    @property
    def get_icon(self):
        return icon_dict[self.name]

    @property
    def get_status_order(self):
        return status_order_dict[self.name]

    def get_color(self):
        return color_dict[self.name]

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.value, x.name) for x in cls]

    @classmethod
    def choices_icons(cls):
        return [(x.get_icon, x.value) for x in cls]


class SurveyType(Enum):
    BLANK = ''
    OPERATIONLICENSE = 'Cumprimento de Ordem de Serviço do tipo Alvará'
    COURTHEARING = 'Cumprimento de Ordem de Serviço do tipo Audiência'
    DILIGENCE = 'Cumprimento de Ordem de Serviço do tipo Diligência'
    PROTOCOL = 'Cumprimento de Ordem de Serviço do tipo Protocolo'

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.value, x.name) for x in cls]


class CheckPointType(Enum):
    CHECKIN = 'Checkin'
    CHECKOUT = 'Checkout'

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.value, x.name) for x in cls]


class MailRecipients(Enum):
    NONE = 'Nenhum'
    OFFICE = 'Escritório'
    PERSON_ASKED_BY = 'Solicitante'
    PERSON_EXECUTED_BY = 'Correspondente'
    PERSON_DISTRIBUTED_BY = 'Service'
    PARENT__OFFICE = 'Escritório contratante'
    PARENT__PERSON_ASKED_BY = 'Solicitante do contratante'
    PARENT__PERSON_EXECUTED_BY = 'Correspondente do contratante'
    PARENT__PERSON_DISTRIBUTED_BY = 'Service do contratante'
    GET_CHILD__OFFICE = 'Escritório correspondente'
    GET_CHILD__PERSON_ASKED_BY = 'Solicitante do correspondente'
    GET_CHILD__PERSON_EXECUTED_BY = 'Correspondente do correspondente'
    GET_CHILD__PERSON_DISTRIBUTED_BY = 'Service do correspondente'

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.name, x.value) for x in cls]


def default_characteristics():
    return json.dumps(CHARACTERISTICS, indent=4)


class TypeTaskMain(models.Model):
    is_hearing = models.BooleanField(verbose_name='É audiência', default=False)
    name = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        unique=True,
        verbose_name='Tipo de Serviço')
    characteristics = JSONField(
        null=True,
        blank=True,
        verbose_name='Características disponíveis',
        default=default_characteristics)

    class Meta:
        ordering = ('name',)
        verbose_name = 'Tipo de Serviço Principal'
        verbose_name_plural = 'Tipos de Serviço Principais'

    def __str__(self):
        return self.name


class TypeTask(Audit, LegacyCode, OfficeMixin):
    type_task_main = models.ManyToManyField(
        TypeTaskMain,
        verbose_name='Tipo de Serviço Principal',
        related_name='type_tasks')
    name = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        verbose_name='Tipo de Serviço')
    survey = models.ForeignKey(
        'survey.Survey',
        null=True,
        blank=True,
        verbose_name='Formulário do correspondente', on_delete=models.PROTECT)

    survey_company_representative = models.ForeignKey(
        'survey.Survey',
        null=True,
        blank=True,
        related_name='type_tasks_person_company_representative',
        verbose_name='Formulário do preposto', on_delete=models.PROTECT)

    office = models.ForeignKey(
        Office,
        on_delete=models.CASCADE,
        blank=False,
        null=False,
        related_name='%(class)s_office',
        verbose_name='Escritório')

    objects = OfficeManager()

    class Meta:
        db_table = 'type_task'
        ordering = ('name',)
        verbose_name = 'Tipo de Serviço'
        verbose_name_plural = 'Tipos de Serviço'

    @property
    def use_upload(self):
        return False

    @property
    def main_tasks(self):
        return list(self.type_task_main.all())

    @property
    def suvey_dict(self):
        return {
            'survey': self.survey if self.survey else None,
            'survey_company_representative': self.survey_company_representative if self.survey_company_representative
            else None
        }

    def __str__(self):
        return self.name


class TaskBase(Audit, LegacyCode, OfficeMixin):
    task_hash = models.UUIDField(default=uuid.uuid4, editable=False)
    amount = models.DecimalField(
        null=False,
        blank=False,
        verbose_name='Valor',
        max_digits=9,
        decimal_places=2,
        default=Decimal('0.00'))
    # Responsável por armanezar a categoria do preço. Recebe o valor do campo PolicyPrice.category, ao ser delegado
    price_category = models.CharField(verbose_name='Categoria do preço', max_length=255,
                                      choices=CategoryPrice.choices(), null=True, blank=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='child')
    task_number = models.PositiveIntegerField(
        verbose_name='Número da Providência', unique=False)
    movement = models.ForeignKey(
        Movement,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='Movimentação')
    person_asked_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        blank=False,
        null=True,
        related_name='%(class)s_asked_by',
        verbose_name='Solicitante')
    person_executed_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='%(class)s_executed_by',
        verbose_name='Correspondente')
    person_distributed_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        blank=False,
        null=True,
        verbose_name='Contratante')
    type_task = models.ForeignKey(
        TypeTask,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        verbose_name='Tipo de Serviço')
    delegation_date = models.DateTimeField(
        null=True, blank=True, verbose_name='Data de Delegação')
    acceptance_date = models.DateTimeField(
        null=True, verbose_name='Data de Aceitação')
    final_deadline_date = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name='Prazo Fatal')
    execution_date = models.DateTimeField(
        null=True, verbose_name='Data de Cumprimento')

    requested_date = models.DateTimeField(
        null=False,
        blank=False,
        default=timezone.now,
        verbose_name='Data de Solicitação')
    acceptance_service_date = models.DateTimeField(
        null=True, verbose_name='Data de Aceitação pelo Contratante')
    refused_service_date = models.DateTimeField(
        null=True, verbose_name='Data de Recusa pelo Contratante')
    return_date = models.DateTimeField(
        null=True, verbose_name='Data de Retorno')
    refused_date = models.DateTimeField(
        null=True, verbose_name='Data de Recusa')

    blocked_payment_date = models.DateTimeField(
        null=True, verbose_name='Data da Glosa')
    finished_date = models.DateTimeField(
        null=True, verbose_name='Data de Finalização')

    description = models.TextField(
        null=True, blank=True, verbose_name=u'Descrição do serviço')
    task_status = models.CharField(
        null=False,
        verbose_name='Status da OS',
        max_length=30,
        choices=((x.value, x.name.title()) for x in TaskStatus),
        default=TaskStatus.REQUESTED)
    person_company_representative = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name='Preposto', related_name='%(class)s_to_person_representative')

    __previous_status = None  # atributo transient

    objects = OfficeManager()

    class Meta:
        abstract = True

    # TODO fazer composição para buscar no endereço completo
    # TODO Modifiquei pois quando não há orgão cadastrado em lawsuit lança erro de
    # variável nula / Martins
    @property
    def address(self):
        address = ''
        organ = self.movement.law_suit.organ
        if organ:
            address = organ.address_set.first()
        return address

    @property
    def court(self):
        return self.movement.law_suit.organ

    @property
    def status(self):
        return TaskStatus(self.task_status)

    @property
    def get_latest_child_not_refused(self):
        if not self.pk:
            return None
        if self.child.exists() and self.child.latest('pk').task_status not in [
            TaskStatus.REFUSED.__str__(),
            TaskStatus.REFUSED_SERVICE.__str__()
        ]:
            return self.child.latest('pk')
        return None


class Task(TaskBase):
    TASK_NUMBER_SEQUENCE = 'task_task_task_number'

    survey_result = models.JSONField(
        verbose_name=u'Respotas do Formulário', blank=True, null=True)
    amount_delegated = models.DecimalField(
        null=False,
        blank=False,
        verbose_name='Valor delegado',
        max_digits=9,
        decimal_places=2,
        default=Decimal('0.00'))
    amount_to_receive = models.DecimalField(
        null=False,
        blank=False,
        verbose_name='Valor a receber',
        max_digits=9,
        decimal_places=2,
        default=Decimal('0.00'))
    amount_to_pay = models.DecimalField(
        null=False,
        blank=False,
        verbose_name='Valor a pagar',
        max_digits=9,
        decimal_places=2,
        default=Decimal('0.00'))
    rate_type_receive = models.CharField(verbose_name='Tipo de taxa a receber', max_length=10,
                                         choices=RateType.choices(), default=RateType.PERCENT)
    rate_type_pay = models.CharField(verbose_name='Tipo de taxa a pagar', max_length=10,
                                     choices=RateType.choices(), default=RateType.PERCENT)
    chat = models.ForeignKey(
        Chat,
        verbose_name='Chat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True)
    company_chat = models.ForeignKey(
        Chat,
        verbose_name='Chat Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks_company_chat')
    billing_date = models.DateTimeField(null=True, blank=True)
    receipt_date = models.DateTimeField(null=True, blank=True)
    performance_place = models.CharField(
        null=False,
        blank=False,
        max_length=255,
        verbose_name='Local de cumprimento')
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, blank=True, null=True)

    """
    Os campos a seguir armazenam o checkin dos atores da OS, independente de terem sido feitos 
    pela OS pai, ou por outra OS da cadeia.
    """
    executed_by_checkin = models.ForeignKey('task.TaskGeolocation',
                                            on_delete=models.PROTECT,
                                            blank=True,
                                            null=True,
                                            related_name='task_executed_by')
    company_representative_checkin = models.ForeignKey('task.TaskGeolocation',
                                                       on_delete=models.PROTECT,
                                                       blank=True,
                                                       null=True,
                                                       related_name='task_company_representative')
    history = HistoricalRecords(bases=[BaseHistoricalModel],
                                cascade_delete_history=True,
                                excluded_fields=['task_hash', 'parent', 'task_number', 'movement', 'person_asked_by',
                                                 'person_executed_by', 'person_distributed_by', 'delegation_date',
                                                 'acceptance_date', 'final_deadline_date', 'execution_date',
                                                 'requested_date', 'acceptance_service_date', 'refused_service_date',
                                                 'return_date', 'refused_date', 'blocked_payment_date', 'finished_date',
                                                 'description', 'survey_result', 'chat', 'company_chat',
                                                 'billing_date', 'receipt_date', 'performance_place',
                                                 'person_company_representative', 'executed_by_checkin',
                                                 'company_representative_checkin', 'create_date', 'alter_date',
                                                 'legacy_code', 'system_prefix', 'is_active', 'charge',
                                                 'price_category', 'rate_type_pay', 'rate_type_receive'])

    __notes = None  # atributo transient
    _mail_attrs = None  # atributo transiente

    class Meta:
        db_table = 'task'
        ordering = ['-alter_date']
        verbose_name = 'Providência'
        verbose_name_plural = 'Providências'
        permissions = [(i.name, i.value) for i in Permissions]
        unique_together = ('task_number', 'office')

    @property
    def client(self):
        folder = Folder.objects.get(folders__law_suits__task__exact=self)
        return folder.person_customer

    def __str__(self):
        # Feito desta forma para controlar problema no django-simple-history
        try:
            return self.type_task.name
        except Exception:
            return Task.objects.get(pk=self.pk).type_task.name

    @property
    def court_division(self):
        return self.movement.law_suit.court_division

    @property
    def court_district(self):
        return self.movement.law_suit.court_district

    @property
    def court_district_complement(self):
        return self.movement.law_suit.court_district_complement

    @property
    def city(self):
        return self.movement.law_suit.city

    def get_absolute_url(self):
        return reverse("task_detail", kwargs={"pk": self.id})

    @property
    def opposing_party(self):
        return self.movement.law_suit.opposing_party

    @property
    def lawsuit_number(self):
        return self.movement.law_suit.law_suit_number

    def serialize(self):
        """JSON representation of object"""
        data = {
            "id":
                self.id,
            "url":
                self.get_absolute_url(),
            "task_number":
                self.task_number,
            "lawsuit_number":
                self.lawsuit_number,
            "client":
                self.client.simple_serialize(),
            "opposing_party":
                self.opposing_party,
            "status":
                str(self.status),
            "type_task": {
                "name": self.type_task.name,
                "id": self.type_task.id
            },
            "final_deadline_date":
                self.final_deadline_date.strftime(settings.DATETIME_FORMAT)
                if self.final_deadline_date else "",
            "delegation_date":
                self.delegation_date.strftime(settings.DATETIME_FORMAT)
                if self.delegation_date else ""
        }
        return data

    # TODO Remover Property após modificação do ECM da Task para o ECM genérico
    @property
    def use_upload(self):
        return False

    @staticmethod
    def person_company_representative_has_change(old_instance, new_instance):
        if old_instance.person_company_representative != new_instance.person_company_representative:
            return True
        return False

    @staticmethod
    def send_mail_new_company_representative(instance):
        if instance.person_company_representative and instance.person_company_representative.get_emails():
            email = TaskCompanyRepresentativeChangeMail(
                instance.person_company_representative.get_emails(), instance, 'mail/task_company_representative_new.html')
            email.send_mail()

    @staticmethod
    def send_mail_old_company_representative(instance):
        if instance.person_company_representative and instance.person_company_representative.get_emails():
            email = TaskCompanyRepresentativeChangeMail(
                instance.person_company_representative.get_emails(), instance, 'mail/task_company_representative_old.html')
            email.send_mail()

    def on_change_person_company_representative(self):
        if self.pk:
            old_instance = Task.objects.get(pk=self.pk)
            if self.person_company_representative_has_change(old_instance=old_instance, new_instance=self):
                self.send_mail_old_company_representative(old_instance)
                self.send_mail_new_company_representative(self)

    def save(self, *args, **kwargs):
        self._skip_signal = kwargs.pop('skip_signal', False)
        self._skip_mail = kwargs.pop('skip_mail', False)
        self._from_parent = kwargs.pop('from_parent', False)
        if not self.task_number:
            self.task_number = self.get_task_number()
        if not self.pk and self.person_company_representative:
            res = super().save(*args, **kwargs)
            self.send_mail_new_company_representative(self)
            return res
        self.on_change_person_company_representative()
        return super().save(*args, **kwargs)

    @transaction.atomic
    def get_task_number(self):
        return get_next_value('office_{office_pk}_{name}'.format(
            office_pk=self.office.pk, name=self.TASK_NUMBER_SEQUENCE))

    @property
    def allow_attachment(self):
        return not (self.status == TaskStatus.REFUSED
                    or self.status == TaskStatus.BLOCKEDPAYMENT
                    or self.status == TaskStatus.FINISHED)

    @property
    def origin_code(self):
        if self.parent:
            return self.parent.task_number
        else:
            return self.legacy_code

    @property
    def get_survey_dict(self):
        return self.type_task.suvey_dict

    @property
    def have_pending_surveys(self):
        survey_dict = self.get_survey_dict
        if survey_dict:
            task_id_list = [self.pk]
            if self.get_latest_child_not_refused:
                task_id_list.append(self.get_latest_child_not_refused.pk)
            pending_survey_company_representative = pending_survey = False
            if survey_dict.get('survey', None):
                pending_survey = not TaskSurveyAnswer.objects.filter(tasks__in=task_id_list,
                                                                     survey=survey_dict.get('survey')).first()
            if self.person_company_representative and survey_dict.get('survey_company_representative', None):
                pending_survey_company_representative = not TaskSurveyAnswer.objects.filter(
                    tasks=self, survey=survey_dict.get('survey_company_representative'),
                    create_user=self.person_company_representative.auth_user).first()
            return {'survey_company_representative': pending_survey_company_representative,
                    'survey_executed_by': pending_survey}


class TaskFeedback(models.Model):
    feedback_date = models.DateTimeField(auto_now_add=True)
    task = models.ForeignKey('Task', verbose_name='OS', on_delete=models.PROTECT)
    rating = models.SmallIntegerField(
        verbose_name='Nota', choices=[(x, x) for x in range(1, 6)])
    comment = models.TextField(null=True, verbose_name='Comentário')
    create_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='%(class)s_create_user',
        verbose_name='Criado por')


def get_dir_name(instance, filename):
    return 'ECM/{0}/{1}'.format(instance.task.pk, filename)


class EcmQuerySet(models.QuerySet):
    def delete(self):
        # Não podemos apagar os ECMs que possuam legacy_code
        queryset = self.exclude(legacy_code__isnull=False)
        return super(EcmQuerySet, queryset).delete()


class EcmManager(models.Manager):
    def get_queryset(self):
        return EcmQuerySet(self.model, using=self._db)


class EcmTask(models.Model):
    """
    Model utilizado para relacionar um Ecm com mais de uma task.
    NOTE: Ainda mantemos a FK de Ecm para task para não termos
    que fazer uma migração gigante que demande a exclusão de
    ECMs duplicados.
    """
    task = models.ForeignKey('Task', on_delete=models.PROTECT)
    ecm = models.ForeignKey('Ecm', on_delete=models.PROTECT)


class Ecm(Audit, LegacyCode):
    path = models.FileField(upload_to=get_dir_name, max_length=255, null=False)
    size = models.PositiveIntegerField(null=True, blank=True)
    task = models.ForeignKey(
        Task, blank=False, null=False, on_delete=models.PROTECT)
    tasks = models.ManyToManyField('Task', through='EcmTask', related_name='+')
    updated = models.BooleanField(default=True, null=False)
    exhibition_name = models.CharField(
        verbose_name="Nome de Exibição",
        max_length=255,
        null=False,
        blank=False)
    ecm_related = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='child')

    objects = EcmManager()

    def save(self, *args, **kwargs):
        if not self.size:
            try:
                self.size = self.path.size
            except:
                # Skip errors when file does not exists
                pass
        return super().save(*args, **kwargs)

    # Retorna o nome do arquivo no Path, para renderizar no tamplate
    @property
    def filename(self):
        return os.path.basename(self.path.name) if self.path else None

    @property
    def user(self):
        return User.objects.get(username=self.path.instance.create_user)

    @property
    def local_file_path(self):
        return os.path.join(settings.MEDIA_ROOT, self.path.name)

    def local_file_exists(self):
        return os.path.exists(self.local_file_path)

    def get_file_content(self):
        try:
            return self.path.read()
        except OSError:
            with open(self.local_file_path, 'rb') as pfile:
                contents = pfile.read()
            return contents

    def delete(self, using=None, keep_parents=False):
        using = using or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            # Lock before checking links; uploads always create an own-task link.
            current = type(self).objects.using(using).select_for_update().get(pk=self.pk)
            if current.legacy_code:
                raise ValidationError(
                    "Não é possível apagar um arquivo que foi vinculado a outro sistema.")
            copies = type(self).objects.using(using).exclude(pk=self.pk)
            if (current.ecm_related_id or copies.filter(ecm_related_id=self.pk).exists()
                    or copies.filter(path=current.path.name).exists()):
                raise ValidationError(
                    "Não é possível excluir um anexo que possui cópias vinculadas.")

            EcmTask.objects.using(using).filter(ecm_id=self.pk, task_id=current.task_id).delete()
            # Other-task links remain protected. A failure restores the own-task
            # links too; django-cleanup removes the file only after commit.
            return super().delete(using=using, keep_parents=keep_parents)

    def download(self):
        """Baixamos o arquivo do S3 caso ele não exista localmente"""
        if not self.local_file_exists():
            path = os.path.join('media', 'ECM', str(self.task_id))
            os.makedirs(path, exist_ok=True)
            with open(self.local_file_path, 'wb') as local_file:
                local_file.write(self.path.read())
        return self.local_file_path


class TaskHistory(AuditCreate, NotesMixin):
    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, blank=False, null=False)
    status = models.CharField(max_length=30, choices=TaskStatus.choices())

    class Meta:
        verbose_name = 'Histórico da Providência'
        verbose_name_plural = 'Histórico das Providências'

    def save(self, *args, **kwargs):
        self._skip_signal = kwargs.pop('skip_signal', False)
        return super(TaskHistory, self).save(*args, **kwargs)


class TaskGeolocation(Audit):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        blank=False,
        null=False,
        related_name='geolocation')
    date = models.DateTimeField(null=True, verbose_name='Data de Início')
    checkpointtype = models.CharField(
        null=True,
        verbose_name='Tipo de Marcação',
        max_length=10,
        choices=((x.value, x.name.title()) for x in CheckPointType),
        default=CheckPointType.CHECKIN)
    latitude = models.DecimalField(
        null=True,
        blank=True,
        verbose_name='Latitude',
        max_digits=9,
        decimal_places=6)
    longitude = models.DecimalField(
        null=True,
        blank=True,
        verbose_name='Longitude',
        max_digits=9,
        decimal_places=6)

    class Meta:
        verbose_name = 'Geolocalização da Providência'
        verbose_name_plural = 'Geolocalização das Providências'
        ordering = (
            'task',
            'date',
        )

    @property
    def position(self):
        return "{},{}".format(self.latitude, self.longitude)


class TaskFilterViewModel(TaskBase):
    asked_by_legal_name = models.TextField(
        verbose_name='Nome', blank=True, null=True, max_length=255)
    client = models.CharField(
        null=True, verbose_name='Cliente', max_length=255)
    court_district = models.ForeignKey(
        CourtDistrict,
        on_delete=models.PROTECT,
        verbose_name='Comarca')
    court_district_name = models.TextField(
        verbose_name='Nome da comarca', null=True, blank=True, max_length=255)
    court_division = models.ForeignKey(
        CourtDivision,
        on_delete=models.PROTECT,
        verbose_name='Vara')
    court_division_name = models.TextField(
        verbose_name='Nome da vara', null=True, blank=True, max_length=255)
    executed_by_id = models.PositiveIntegerField()
    executed_by_legal_name = models.TextField(
        verbose_name='Nome', blank=True, null=True, max_length=255)
    law_suit_number = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Número do Processo')
    opposing_party = models.TextField(
        blank=True, null=True, verbose_name='Parte adversa')
    office_legal_name = models.TextField(
        blank=True, null=True, verbose_name='Escritório/Empresa')
    origin_code = models.TextField(
        verbose_name='Nome', blank=True, null=True, max_length=255)
    parent_task_number = models.PositiveIntegerField(
        default=0, verbose_name='OS Original')
    state = models.ForeignKey(
        State,
        on_delete=models.PROTECT,
        verbose_name='UF')
    state_initials = models.TextField(
        verbose_name='Sigla UF', max_length=10)
    type_task_name = models.TextField(
        verbose_name='Nome Tipo de Serviço', max_length=255)

    class Meta:
        db_table = 'task_filter_view'
        managed = False
        verbose_name = 'Filtro de providência'
        verbose_name_plural = 'Filtros de providência'

    def __str__(self):
        return self.type_task_name

    @property
    def cost_center(self):
        folder = Folder.objects.get(folders__law_suits__task__exact=self)
        return folder.cost_center

    @property
    def folder_number(self):
        folder = Folder.objects.get(folders__law_suits__task__exact=self)
        return folder.folder_number


class Filter(Audit):
    name = models.TextField(
        verbose_name='Nome', blank=False, null=False, max_length=255)
    description = models.TextField(
        verbose_name='Descrição', blank=True, null=True)
    query = models.BinaryField(verbose_name='query', blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def query_sql(self):
        return str(
            DashboardViewModel.objects.filter(pickle.loads(self.query)).query)

    class Meta:
        verbose_name = 'Filtro'
        verbose_name_plural = 'Filtros'
        unique_together = (('create_user', 'name'),)


class TaskWorkflow(Audit):
    custtom_settings = models.ForeignKey(
        CustomSettings, related_name='task_workflows', on_delete=models.PROTECT)
    task_from = models.CharField(
        verbose_name='Do status',
        null=False,
        max_length=30,
        choices=((x.value, x.name.title()) for x in TaskStatus),
        default=TaskStatus.REQUESTED)
    task_to = models.CharField(
        verbose_name='Para o status',
        null=False,
        max_length=30,
        choices=((x.value, x.name.title()) for x in TaskStatus),
        default=TaskStatus.REQUESTED)

    responsible_user = models.ForeignKey(User, on_delete=models.PROTECT)


class TaskShowStatus(Audit):
    custtom_settings = models.ForeignKey(
        CustomSettings, related_name='task_status_show', on_delete=models.PROTECT)
    status_to_show = models.CharField(
        verbose_name='Mostrar status',
        null=False,
        max_length=30,
        choices=((x.value, x.name.title()) for x in TaskStatus),
        default=TaskStatus.REQUESTED)
    send_mail_template = models.ForeignKey(
        EmailTemplate, verbose_name='Template a enviar', blank=True, null=True, on_delete=models.PROTECT)
    mail_recipients = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            verbose_name='Destinatários do e-mail',
            max_length=256,
            choices=((x.name, x.value) for x in MailRecipients)),
        default=list)

    class Meta:
        unique_together = ('status_to_show', 'custtom_settings')


class TaskSurveyAnswer(Audit):
    tasks = models.ManyToManyField(Task, blank=True)
    survey = models.ForeignKey('survey.Survey', on_delete=models.CASCADE, null=True, blank=True)
    survey_result = models.JSONField(verbose_name=u'Respotas do Formulário', blank=True, null=True)
