from enum import Enum
from django.db.models import Q
from django.apps import apps
from django.forms.models import model_to_dict
import logging
from openpyxl import load_workbook
import os
from functools import wraps
from localflavor.br.forms import BRCPFField, BRCNPJField
import re
from decimal import Decimal

EZL_LOGGER = logging.getLogger('ezl')


# enumerador usado para integracao entre sistemas
class LegacySystem(Enum):
    ADVWIN = "Advwin"
    AUTOJUR = "Autojur"
    ELAW = "eLaw"


def get_admin_setting(model, setting_name):
    # busca o valor da configuracao do sistema de um campo específico passado como parametro
    # obs.: o model deve ser passado como parametro pq o django nao permite importar model nesse arquivo utils
    admin_settings = model.objects.first()
    if admin_settings:
        setting_content = getattr(admin_settings, setting_name)

    return setting_content

def login_log(f):
    """
    Metodo decorator para gerar log mostrando o usuario e o momento que foi realizado o login
    :param f:
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        res = f(*args, **kwargs)
        try:
            username = args[1].data.get('login')
            msg = 'LOGIN realizado por: {user}'.format(user=username)
            EZL_LOGGER.info(msg)
        except Exception as e:
            EZL_LOGGER.error(str(e))
        return res

    return wrapper


def logout_log(f):
    """
    Metodo decorator para gerar log mostrando o usuario e o momento que foi realizado o logout
    :param f:
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            request = args[0]
            username = request.user.username
            msg = 'LOGOUT realizado por: {user}'.format(user=username)
            EZL_LOGGER.info(msg)
        except Exception as e:
            EZL_LOGGER.error(str(e))
        return f(*args, **kwargs)

    return wrapper


def get_office_field(request, profile=None):
    """
    Método para montar o campo de office, de acordo com a variável de sessão custom_session_user
    :param request:
    :param profile:
    :return: forms.ModelChoiceField
    """
    from core.models import Office, DefaultOffice
    from django import forms
    try:
        if profile:
            queryset = profile.person.offices.active_offices()
            initial = DefaultOffice.objects.filter(auth_user=profile).first().office if \
                DefaultOffice.objects.filter(auth_user=profile).first() else None
        elif request.session.get('custom_session_user'):
            initial = get_office_session(request)
            queryset = Office.objects.filter(
                pk=initial.pk)
        else:
            queryset = request.user.person.offices.active_offices()
            initial = None
    except Exception as e:
        queryset = Office.objects.none()
        initial = None

    return forms.ModelChoiceField(
        queryset=queryset,
        empty_label='',
        required=True,
        label=u'Escritório',
        initial=initial)


def get_office_related_office_field(request):
    from core.models import Office
    from django import forms
    queryset = Office.objects.none()
    initial = None
    office = get_office_session(request)
    if office:
        if office.public_office:
            queryset = office.offices.all().order_by(
                'legal_name') | Office.objects.filter(public_office=True)
        else:
            queryset = office.offices.all().order_by('legal_name')
            queryset |= Office.objects.filter(pk=office.pk)
            queryset = queryset.distinct()

    return forms.ModelChoiceField(
        queryset=queryset,
        empty_label='Selecione',
        required=True,
        label=u'Escritório',
        initial=initial)


def get_office_api(request):
    return request.auth.application.office


def get_office_session(request):
    """
    Retorna o objeto Office de acordo com a sessão atual do usuário; Ou False caso não tenha selecionado escritório
    :param request:
    :return: Office object or False
    """
    from core.models import Office
    office = Office.objects.none()
    if request:
        if request.session.get('custom_session_user'):
            custom_session_user = list(
                request.session.get('custom_session_user').values())
            office = Office.objects.filter(
                pk=custom_session_user[0]['current_office']).first()
        else:
            office = False

    return office


def get_office_by_id(office_id):
    from core.models import Office
    if office_id:
        return Office.objects.filter(pk=office_id).first()
    return None


def get_domain(request):
    try:
        if request.META.get('HTTP_X_FORWARDED_HOST') or request.META.get(
                'HTTP_HOST'):
            return '{}://{}'.format(
                request.scheme,
                request.META.get('HTTP_X_FORWARDED_HOST',
                                 request.META.get('HTTP_HOST')))
        return request.META.get('HTTP_REFERER')[:-1]
    except:
        return '{}://{}'.format(request.scheme, request.get_host())


def validate_xlsx_header(xls_file, headers):
    header_is_valid = False
    if headers:
        wb = load_workbook(xls_file, data_only=True)
        headers_in_file = list(
            map(lambda header: header.value,
                [list(sheet.rows)[0] for sheet in wb.worksheets][0]))
        header_is_valid = set(headers).issubset(set(headers_in_file))
    return header_is_valid


def clear_history_amount(history):
    if getattr(history, 'amount'):
        history.amount = Decimal("{:0.2f}".format(float(history.amount)))
    if getattr(history, 'amount_delegated'):
        history.amount_delegated = Decimal("{:0.2f}".format(float(history.amount_delegated)))
    return history


def field_has_changed(history, field_to_check):
    if history.prev_record:
        history = clear_history_amount(history)
        delta = history.diff_against(history.prev_record)
        for change in delta.changes:
            if change.field == field_to_check:
                return True
    return False


def get_history_changes(history):
    changes = {}
    if history.prev_record:
        history = clear_history_amount(history)
        delta = history.diff_against(history.prev_record)
        for change in delta.changes:
            changes[change.field] = change
    return changes


def cpf_is_valid(cpf):
    try:
        BRCPFField().clean(cpf)
        return True
    except:
        return False


def cnpj_is_valid(cnpj):
    try:
        BRCNPJField().clean(cnpj)
        return True
    except:
        return False


def clear_cpf_cnpj(cpf_cnpj):
    return re.sub(r'[^0-9]', '', cpf_cnpj)


def check_cpf_cnpj_exist(model, cpf_cnpj):
    model = apps.get_model('core', model)
    instances = model.objects.filter(cpf_cnpj=clear_cpf_cnpj(cpf_cnpj))
    data = {'exist': False}
    if instances.exists():
        instance = instances.latest('pk')
        data.update(model_to_dict(instance, fields=['legal_name', 'name', 'cpf_cnpj', 'id']))
        data['exist'] = True
    return data


def get_person_field(request, user=None):
    """
    Método para montar o campo de person, de acordo com a sessao do usuario logado
    :param request:
    :param user: um objeto User para selecionar o valor inicial do campo
    :return: forms.ModelChoiceField
    """
    from core.models import Person
    from django import forms

    initial = None
    empty_label = ''
    user_query = Q(auth_user__isnull=True)
    try:
        office = get_office_session(request)
        if user:
            initial = user.person.id
            empty_label = None
            user_query = Q(Q(auth_user__isnull=True) | Q(auth_user=user))
        queryset = office.persons.filter(is_active=True).filter(user_query)
    except Exception:
        queryset = Person.objects.none()
        initial = None
        empty_label = ''

    return forms.ModelChoiceField(
        queryset=queryset,
        empty_label=empty_label,
        required=False,
        label=u'Pessoa',
        initial=initial)


def set_user_default_office(default_office, user, alter_user=None):
    from core.models import DefaultOffice
    if not alter_user:
        alter_user = user
    obj = DefaultOffice.objects.filter(auth_user=user).first()
    if obj:
        obj.office = default_office
        obj.alter_user = alter_user
        obj.save()
    else:
        obj = DefaultOffice.objects.create(
            auth_user=user,
            office=default_office,
            create_user=alter_user
        )
    return obj


def create_office_template_value(office):
    from manager.models import Template
    from manager.utils import create_template_value
    for template in Template.objects.filter(is_active=True):
        create_template_value(template, office, str(template.default_value))


def add_create_user_to_admin_group(office):
    from guardian.shortcuts import get_groups_with_perms

    if not office.create_user.is_superuser:
        for group in {
            group
            for group, perms in get_groups_with_perms(
            office, attach_perms=True).items()
            if 'group_admin' in perms
        }:
            office.create_user.groups.add(group)


def post_create_new_user(request_invite, office_name, user, office_cpf_cnpj=None, office_pk=None):
    from core.models import Office, DefaultOffice, Invite
    if not request_invite:
        office = Office.objects.create(name=office_name,
                                       legal_name=office_name,
                                       create_user=user,
                                       cpf_cnpj=office_cpf_cnpj)
        DefaultOffice.objects.create(
            auth_user=user,
            office=office,
            create_user=user)
        return 'dashboard'
    else:
        office = Office.objects.get(pk=office_pk)
        Invite.objects.create(
            office=office,
            person=user.person,
            status='N',
            create_user=user,
            invite_from='P',
            is_active=True)
        return 'office_instance'


def create_work_alone_status_to_show(office, work_alone):
    from task.models import TaskShowStatus, TaskStatus, EmailTemplate
    instance = office.customsettings
    work_alone_status_dict = {
        True: [
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.OPEN,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-a9f3606fb333406c9b907fee244e30a4').first(), mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.RETURN, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.REFUSED, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.ACCEPTED,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-ae35cc53722345eaa4a4adf521c3bd81').first(), mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.FINISHED,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-7af22ba0396943729cdcb87e2e9f787c').first(), mail_recipients=['NONE']),
        ],
        False: [
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.REQUESTED, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.ACCEPTED_SERVICE, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.OPEN,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-9233ece106b743c08074d1eb5efac1f3').first(),
                           mail_recipients=['PERSON_EXECUTED_BY', 'GET_CHILD__OFFICE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.ACCEPTED, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.DONE, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.RETURN,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-5c0f201b780a4b7ea6d3adfc7eae4e49').first(),
                           mail_recipients=['PERSON_EXECUTED_BY', 'PERSON_DISTRIBUTED_BY', 'GET_CHILD__OFFICE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.FINISHED, mail_recipients=['NONE']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.REFUSED_SERVICE,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-a0687119152c4396894274fcf33c94bc').first(),
                           mail_recipients=['PERSON_ASKED_BY', 'PARENT__PERSON_DISTRIBUTED_BY']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.REFUSED,
                           send_mail_template=EmailTemplate.objects.filter(
                               template_id='d-f6188c1006af4193aa66f99af71d070b').first(),
                           mail_recipients=['PERSON_DISTRIBUTED_BY', 'PARENT__PERSON_DISTRIBUTED_BY']),
            TaskShowStatus(custtom_settings_id=instance.id, create_user=instance.create_user,
                           status_to_show=TaskStatus.BLOCKEDPAYMENT, mail_recipients=['NONE']),
        ]
    }
    instance.task_status_show.exclude(custtom_settings_id=instance.id,
                                      status_to_show=TaskStatus.ERROR).delete()
    instance.task_status_show.bulk_create(work_alone_status_dict.get(work_alone))


def create_work_alone_workflows(office, work_alone):
    from manager.enums import TemplateKeys
    from django.contrib.auth.models import Group
    from task.models import TaskWorkflow, TaskStatus
    instance = office.customsettings
    task_workflows = []
    if work_alone:
        office.use_etl = False
        office.use_service = False
        default_user = office.get_template_value(TemplateKeys.DEFAULT_USER.name)
        if not default_user:
            admin_person = office.persons.filter(auth_user__isnull=False,
                                                 auth_user__is_superuser=False,
                                                 auth_user__groups__name__startswith='{}-{}'.format(
                                                     office.persons.model.ADMINISTRATOR_GROUP, office.id)).first()
            default_user = getattr(admin_person, 'auth_user', None)
        default_user.groups.add(
            Group.objects.filter(
                name='Correspondente-{}'.format(office.pk)).first())
        task_workflows.extend([
            TaskWorkflow(
                custtom_settings_id=instance.id,
                create_user=instance.create_user,
                task_from=TaskStatus.REQUESTED,
                task_to=TaskStatus.ACCEPTED_SERVICE,
                responsible_user=default_user),
            TaskWorkflow(
                custtom_settings_id=instance.id,
                create_user=instance.create_user,
                task_from=TaskStatus.ACCEPTED_SERVICE,
                task_to=TaskStatus.OPEN,
                responsible_user=default_user),
        ])
    instance.task_workflows.all().delete()
    instance.task_workflows.bulk_create(task_workflows)


def create_use_etl_status_to_show(office, use_etl):
    from task.models import TaskShowStatus, TaskStatus
    instance = office.customsettings
    if use_etl:
        status_to_show, nil = TaskShowStatus.objects.get_or_create(custtom_settings_id=instance.id,
                                                                   status_to_show=TaskStatus.ERROR,
                                                                   defaults={'create_user': instance.create_user})
    else:
        TaskShowStatus.objects.filter(custtom_settings_id=instance.id,
                                      status_to_show=TaskStatus.ERROR).delete()


def create_office_custom_settings(office):

    instance = office.customsettings
    i_work_alone = instance.office.i_work_alone
    use_etl = instance.office.use_etl

    create_work_alone_status_to_show(office, i_work_alone)
    create_work_alone_workflows(office, i_work_alone)
    create_use_etl_status_to_show(office, use_etl)
