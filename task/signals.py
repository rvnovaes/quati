from django.db import transaction
from django.db.models.signals import post_init, pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver, Signal
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import MultipleObjectsReturned
from task.models import Task, Ecm, EcmTask, TaskStatus, TaskHistory, TaskGeolocation
from task.utils import create_ecm_task
from task.workflow import get_parent_status, get_child_status, get_parent_fields, get_child_recipients, \
    get_parent_recipients
from chat.models import Chat, UserByChat
from chat.utils import create_users_company_by_chat
from lawsuit.models import CourtDistrict
from core.utils import get_office_session, field_has_changed, get_history_changes
from core.models import CustomSettings
from task.mail import TaskMail
import logging
from simple_history.models import HistoricalRecords
from simple_history.signals import (
    pre_create_historical_record,
    post_create_historical_record
)
import sys
import traceback
from babel.numbers import format_currency
from manager.template_values import ListTemplateValues
from manager.enums import TemplateKeys


logger = logging.getLogger(__name__)

send_notes_execution_date = Signal()  # args: notes, instance, execution_date, survey_result


def create_or_update_user_by_chat(task, task_to_fields, fields):
    for field in fields:
        user = None
        if getattr(task_to_fields, field, False):
            user = getattr(getattr(task_to_fields, field), 'auth_user', False)
        if user:
            try:
                user, created = UserByChat.objects.get_or_create(
                    user_by_chat=user,
                    chat=task.chat,
                    defaults={
                        'create_user': user,
                        'user_by_chat': user,
                        'chat': task.chat
                    })
            except MultipleObjectsReturned:
                # Tratamento específico para cenário da tarefa EZL-904
                user = UserByChat.objects.filter(
                    user_by_chat=user, chat=task.chat).first()
            user = user.user_by_chat


def create_company_chat(sender, instance, created, **kwargs):
    if not instance.parent and instance.client.company:
        label = 'company-task-{}'.format(instance.pk)
        title = """{lawsuit_number}""".format(
            lawsuit_number=instance.lawsuit_number)
        description = "Processo: {}".format(instance.lawsuit_number)
        chat, chat_created = Chat.objects.update_or_create(
            label=label,
            defaults={
                'company': instance.client.company,
                'create_user': instance.create_user,
                'description': description,
                'title': title,
                'back_url': '/dashboard/{}'.format(instance.pk),
            })
        instance.company_chat = chat
        if chat_created:
            instance.company_chat.offices.add(instance.office)
            create_users_company_by_chat(instance.client.company, chat)
        instance.save(**{
            'skip_signal': True,
            'skip_mail': True,
            'from_parent': True
        })


def create_or_update_chat(sender, instance, created, **kwargs):
    try:
        opposing_party = ''
        if instance.movement and instance.movement.law_suit:
            opposing_party = instance.movement.law_suit.opposing_party
        state = ''
        if isinstance(instance.court_district, CourtDistrict):
            state = instance.court_district.state
        description = """
        Parte adversa: {opposing_party}, Cliente: {client},
        {court_district} - {state}, Prazo: {final_deadline_date}
        """.format(
            opposing_party=opposing_party,
            client=instance.client,
            court_district=instance.court_district,
            state=state,
            final_deadline_date=instance.final_deadline_date.strftime(
                '%d/%m/%Y %H:%M'))
        label = 'task-{}'.format(instance.pk)
        title = """#{task_number} - {type_task}""".format(
            task_number=instance.task_number, type_task=instance.type_task)
        chat, chat_created = Chat.objects.update_or_create(
            label=label,
            defaults={
                'create_user': instance.create_user,
                'description': description,
                'title': title,
                'back_url': '/dashboard/{}'.format(instance.pk),
            })
        chat.task_set.add(instance)
        chat.offices.add(instance.office)
        create_or_update_user_by_chat(
            instance, instance,
            ['person_asked_by', 'person_executed_by', 'person_distributed_by'])
        if instance.parent:
            instance.chat.offices.add(instance.parent.office)
            create_or_update_user_by_chat(instance, instance.parent, [
                'person_asked_by', 'person_executed_by',
                'person_distributed_by'
            ])
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error('ERRO AO CHAMAR O METODO create_or_update_chat')
        logger.error(traceback.print_exception(exc_type, exc_value, exc_traceback,
                                               limit=2, file=sys.stdout))


def set_status_by_workflow(instance, custom_settings):
    workflow_status = custom_settings.task_workflows.filter(
        task_from=instance.task_status).first()
    if workflow_status:
        instance.task_status = workflow_status.task_to
        instance.person_executed_by = workflow_status.responsible_user.person
        instance.person_distributed_by = workflow_status.responsible_user.person
        instance.save(**{'skip_signal': True, 'skip_mail': True})
        return set_status_by_workflow(instance, custom_settings)
    return True


def workflow_task(sender, instance, created, **kwargs):
    try:
        custom_settings = CustomSettings.objects.filter(
            office=instance.office).first()
        if custom_settings:
            set_status_by_workflow(instance, custom_settings)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error('ERRO AO CHAMAR O METODO workflow_task')
        logger.error(traceback.print_exception(exc_type, exc_value, exc_traceback,
                                               limit=2, file=sys.stdout))


def get_task_number(task, recipient_str_list):
    task_number = task.task_number
    if recipient_str_list.__len__() > 1:
        related_task = getattr(task, recipient_str_list[0], None)
        if related_task:
            task_number = related_task.task_number
    return task_number


def get_mail_recipients_from_status_to_show(task, status_to_show):
    mail_list = []
    person_recipient_list = status_to_show.mail_recipients
    for person in person_recipient_list:
        recipient_str_list = person.lower().split('__')
        obj = task
        task_number = get_task_number(task, recipient_str_list)
        for recipient_str in recipient_str_list:
            obj = getattr(obj, recipient_str, None)
            if not obj:
                break
        if obj:
            mail_list.append({
                'recipient': list(filter(None, obj.emails.split(' | '))),
                'task_number': task_number
            })

    return mail_list


def workflow_send_mail(instance, by_person):
    custom_settings = instance.office.customsettings
    mail_list = []
    status_to_show = None
    if custom_settings:
        status_to_show = custom_settings.task_status_show.filter(
            status_to_show=instance.task_status).first()
        if status_to_show and status_to_show.send_mail_template:
            if instance.office.i_work_alone:
                mail_list = {
                    'recipient': list(instance.office.get_template_value(TemplateKeys.EMAIL_NOTIFICATION.name)),
                    'task_number': instance.task_number
                }
            else:
                mail_list = get_mail_recipients_from_status_to_show(instance, status_to_show)

    if mail_list and status_to_show:
        for mail in mail_list:
            recipients = mail.get('recipient', '')
            task_number = mail.get('task_number', '')
            email = TaskMail(recipients,
                             instance,
                             status_to_show.send_mail_template.template_id,
                             by_person,
                             task_number)
            if email:
                email.send_mail()


@receiver(post_save, sender=Task)
def post_save_task(sender, instance, created, **kwargs):
    post_save.disconnect(post_save_task, sender=sender)
    """
    A ordem das chamadas a seguir e importante uma vez que ao dar o save na instancia em alguns métodos, alteramos as
    propriedades skip_mail ou skip_signal da instancia. Esta alteracao acaba por influenciar o comportamento dos metodos 
    seguintes.
    """
    try:
        workflow_task(sender, instance, created, **kwargs)
        instance.__previous_status = TaskStatus(instance.task_status)
        create_or_update_chat(sender, instance, created, **kwargs)
        create_company_chat(sender, instance, created, **kwargs)
    except Exception as e:
        raise e
    finally:
        post_save.connect(post_save_task, sender=sender)


@receiver(post_save, sender=EcmTask)
def ecm_task_post_save(sender, instance, created, **kwargs):
    if not created:
        return

    # Copia o EcmTask para todos os pais e filhos recursivamente
    if instance.task.parent:
        create_ecm_task(instance.ecm, instance.task.parent)
    if instance.task.get_latest_child_not_refused:
        create_ecm_task(instance.ecm, instance.task.get_latest_child_not_refused)


@receiver(post_save, sender=Ecm)
def create_ecm_task_for_ecm(sender, instance, created, **kwargs):
    """Cria o EcmTask para o Ecm assim que o Ecm for criado"""
    if created and instance.path:
        create_ecm_task(instance, instance.task)


@receiver(post_delete, sender=Ecm)
def delete_related_ecm(sender, instance, **kwargs):
    ecm_related = instance.ecm_related_id
    if not ecm_related:
        ecm_related = instance.pk
    if ecm_related:
        transaction.on_commit(lambda: Ecm.objects.filter(Q(pk=ecm_related)
                                                         | Q(ecm_related_id=ecm_related)).delete())


@receiver(post_init, sender=Task)
def load_previous_status(sender, instance, **kwargs):
    instance.__previous_status = \
        TaskStatus(
            instance.task_status) if instance.task_status else TaskStatus.INVALID
    instance._mail_attrs = None


@receiver(send_notes_execution_date)
def receive_notes_execution_date(notes, instance, execution_date,
                                 survey_result, **kwargs):
    setattr(instance, '__notes', notes if notes else '')
    setattr(instance, '__external_task', kwargs.get('external_task'))
    logger.info('HISTORY {}', kwargs)
    if execution_date and not instance.execution_date:
        instance.execution_date = execution_date
    instance.survey_result = survey_result if survey_result else None


@receiver(pre_save, sender=Task)
def change_status(sender, instance, **kwargs):
    now_date = timezone.now()
    new_status = TaskStatus(instance.task_status) or TaskStatus.INVALID
    previous_status = TaskStatus(
        instance.__previous_status) or TaskStatus.INVALID

    if new_status is not previous_status:
        if new_status is TaskStatus.REQUESTED and not instance.requested_date:
            instance.requested_date = now_date
        if new_status is TaskStatus.ACCEPTED_SERVICE:
            instance.acceptance_service_date = now_date
        if new_status is TaskStatus.REFUSED_SERVICE:
            instance.refused_service_date = now_date
        if new_status is TaskStatus.OPEN:
            instance.delegation_date = now_date
        if new_status is TaskStatus.ACCEPTED:
            instance.acceptance_date = now_date
        elif new_status is TaskStatus.REFUSED:
            instance.refused_date = now_date
        elif new_status is TaskStatus.DONE:
            instance.return_date = None
        elif new_status is TaskStatus.RETURN:
            instance.execution_date = None
            instance.return_date = now_date
        elif new_status is TaskStatus.BLOCKEDPAYMENT:
            instance.blocked_payment_date = now_date
        elif new_status is TaskStatus.FINISHED:
            instance.finished_date = now_date

        if new_status is TaskStatus.DONE and previous_status is TaskStatus.OPEN and instance.get_latest_child_not_refused:
            instance.execution_date = now_date

        instance.alter_date = now_date


def update_status_parent_task(sender, instance, **kwargs):
    """
    Responsavel por alterar o status da OS pai, quando o status da OS filha e modificado
    :param sender:
    :param instance:
    :param kwargs:
    :return:
    """
    if instance.parent and instance.task_status != instance.__previous_status:
        if not get_parent_status(instance.status) == TaskStatus(instance.parent.__previous_status) \
                and not getattr(instance, '_from_parent'):
            instance.parent.task_status = get_parent_status(instance.status)
            if instance.parent.task_status == TaskStatus.REQUESTED:
                setattr(
                    instance.parent, '__notes',
                    'O escritório {} recusou a OS {}. Motivo: {}'.format(
                        instance.office.legal_name,
                        instance.parent.task_number,
                        getattr(instance, '__notes', '')))
            fields = get_parent_fields(instance.status)
            for field in fields:
                setattr(instance.parent, field, getattr(instance, field)),
            instance.parent._mail_attrs = get_parent_recipients(
                instance.status)
            setattr(instance.parent, '_TaskDetailView__server',
                    getattr(instance, '_TaskDetailView__server', None))
            instance.parent.save(**{
                'skip_signal': instance._skip_signal,
                'skip_mail': True
            })


def update_status_child_task(sender, instance, **kwargs):
    """
    Responsavel por atualizar o status da os filha se a o estatus da OS pai e modificado
    :param sender:
    :param instance:
    :param kwargs:
    :return:
    """
    status = get_child_status(instance.status)
    if TaskStatus(instance.task_status) == TaskStatus(instance.__previous_status):
        setattr(instance, '_skip_signal', True)
    child = instance.get_latest_child_not_refused
    while child and status:
        child.task_status = status
        child._mail_attrs = get_child_recipients(instance.task_status)
        setattr(child, '_TaskDetailView__server',
                getattr(instance, '_TaskDetailView__server', None))
        child.save(
            **{
                'skip_signal': instance._skip_signal,
                'skip_mail': False,
                'from_parent': True
            })
        status = get_child_status(child.status)
        child = child.get_latest_child_not_refused


@receiver(pre_save, sender=Task)
def pre_save_task(sender, instance, **kwargs):
    pre_save.disconnect(pre_save_task, sender=sender)
    """
    A ordem das chamadas a seguir e importante uma vez que ao dar o save na instancia em alguns métodos, alteramos as
    propriedades skip_mail ou skip_signal da instancia. Esta alteracao acaba por influenciar o comportamento dos metodos 
    seguintes.
    """
    try:
        update_status_parent_task(sender, instance, **kwargs)
        update_status_child_task(sender, instance, **kwargs)
    except Exception as e:
        raise e
    finally:
        pre_save.connect(pre_save_task, sender=sender)


@receiver(post_save, sender=TaskGeolocation)
def post_save_geolocation(sender, instance, **kwargs):
    pre_save.disconnect(pre_save_task, sender=Task)
    post_save.disconnect(post_save_task, sender=Task)
    task = instance.task
    create_user = instance.create_user
    checkin_type = 'executed_by_checkin'
    if task.person_company_representative and create_user == task.person_company_representative.auth_user:
        checkin_type = 'company_representative_checkin'
    # atualiza na task o id do checkin
    if instance.checkpointtype == 'Checkin':
        setattr(task, checkin_type, instance)
    task.save()
    while task.parent:
        task = task.parent
        # atualiza na task o id do checkin
        if instance.checkpointtype == 'Checkin':
            setattr(task, checkin_type, instance)
        task.save()
    pre_save.connect(pre_save_task, sender=Task)
    post_save.connect(post_save_task, sender=Task)


@receiver(pre_create_historical_record)
def pre_create_historical_record_callback(sender, **kwargs):
    history_instance = kwargs.get('history_instance')
    try:
        history_instance.history_office = get_office_session(HistoricalRecords.thread.request)
    except:
        history_instance.history_office = getattr(kwargs.get('instance'), 'office', None)
    instance = kwargs.get('instance')
    if instance.history.exists():
        if not get_history_changes(history_instance):
            history_instance.pk = instance.history.latest('pk').pk


@receiver(post_create_historical_record)
def post_create_historical_record_callback(sender, **kwargs):
    history_instance = kwargs.get('history_instance')
    instance = kwargs.get('instance')
    status = get_child_status(instance.status) if instance.get_latest_child_not_refused else None
    try:
        request = HistoricalRecords.thread.request
        msg = request.POST.get('notes', '')
    except:
        msg = ''
    task_number = None
    if status == TaskStatus.REFUSED and instance.task_status == TaskStatus.REQUESTED:
        task_number = instance.get_latest_child_not_refused.task_number
    if instance.task_status == TaskStatus.REFUSED and instance.parent:
        task_number = instance.task_number
    if task_number:
        msg = """
        A OS {} foi recusada pelo escritório pelo motivo: {}
        """.format(task_number, msg)
    if field_has_changed(history_instance, 'amount'):
        change = get_history_changes(history_instance).get('amount')
        msg += "Valor alterado de {} para {}".format(
            format_currency(change.old, 'R$', locale='pt_BR'),
            format_currency(change.new, 'R$', locale='pt_BR'))
    if field_has_changed(history_instance, 'amount_delegated'):
        change = get_history_changes(history_instance).get('amount_delegated')
        msg += "Valor de delegação alterado de {} para {}".format(
            format_currency(change.old, 'R$', locale='pt_BR'),
            format_currency(change.new, 'R$', locale='pt_BR'))

    history_instance.history_notes = msg
    history_instance.save()
    try:
        if history_instance.history_office == instance.office:
            by_person = "pelo(a) contratante {}".format(str(history_instance.history_user.person).title())
        else:
            by_person = "pelo(a) escritório {}".format(str(history_instance.history_office).title())
        if not getattr(instance, '_skip_mail', False):
            workflow_send_mail(instance, by_person)
    except:
        pass
