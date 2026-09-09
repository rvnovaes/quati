from django.core.mail import send_mail, EmailMultiAlternatives
from django.templatetags.tz import localtime
from django.template.loader import render_to_string
from django.contrib.auth.tokens import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.urls.base import reverse
from django.conf import settings
from datetime import datetime
from core.models import EMAIL, PHONE, CustomSettings
from task import models as task_models
import traceback
import logging
from django.utils import timezone
from manager.template_values import GetTemplateValue
from manager.enums import TemplateKeys

logger = logging.getLogger(__name__)


def to_localtime(date_time=None, format_str='%d/%m/%Y %H:%M'):
    if date_time:
        return localtime(date_time).strftime(format_str)
    else:
        return ''


def get_str_or_blank(obj=None):
    return str(obj) if obj else ''


def get_project_link(task):
    if hasattr(task, '_TaskCreateView__server'):
        project_link = task._TaskCreateView__server

    elif hasattr(task, '_TaskUpdateView__server'):
        project_link = task._TaskUpdateView__server

    elif hasattr(task, '_TaskDetailView__server'):
        project_link = task._TaskDetailView__server

    else:
        project_link = settings.PROJECT_LINK

    return project_link


class SendMail:
    subject = None
    message = None
    from_mail = settings.DEFAULT_FROM_EMAIL
    to_mail = [None]

    class Meta:
        abstract = True

    def send(self):
        msg = EmailMultiAlternatives(self.subject, 'teste', self.from_mail,
                                     self.to_mail)
        msg.attach_alternative(self.message, "text/html")
        msg.send()


class BaseTemplateEmail(object):
    def __init__(self, task, **kwargs):
        self.task = task


class TaskFinishedEmail(BaseTemplateEmail):
    def __init__(self, task, **kwargs):
        super().__init__(task, **kwargs)
        self.default_user = GetTemplateValue(office=self.task.office,
                                             template_key=TemplateKeys.DEFAULT_USER.name).value

    def get_url_change_password(self):
        token_generator = default_token_generator
        temp_key = token_generator.make_token(self.default_user)
        path = reverse(
            "account_reset_password_from_key",
            kwargs=dict(
                uidb36=user_pk_to_url_str(self.default_user),
                key=temp_key))
        return '{}{}'.format(settings.WORKFLOW_URL_EMAIL, path)

    def get_dynamic_template_data(self):
        if not self.default_user.last_login:
            return {
                "task_number": self.task.task_number,
                "type_task": self.task.type_task.name,
                "title_type_service": "OS {task_number} - {type_task} ".format(task_number=self.task.task_number,
                                                                               type_task=self.task.type_task.name),
                "office_name": self.task.parent.office.legal_name,
                "office_correspondent_name": self.task.parent.office.legal_name,
                "username": self.default_user.username,
                "btn_finished": self.get_url_change_password(),
            }
        return False


class TaskOpenMailTemplate(BaseTemplateEmail):

    def get_dynamic_template_data(self):
        task = self.task if self.task.parent else self.task.get_latest_child_not_refused
        office = self.task.parent.office if self.task.parent else self.task.office
        project_link = '{}{}'.format(get_project_link(self.task), reverse('task_detail', kwargs={'pk': task.pk}))
        return {
            "task_number": task.task_number,
            "title_type_service": "OS {task_number} - {type_task} ".format(task_number=task.task_number,
                                                                           type_task=task.type_task.name),
            "type_task": task.type_task.name,
            "description": get_str_or_blank(task.description),
            "final_deadline_date": to_localtime(task.final_deadline_date, '%d/%m/%Y %H:%M'),
            "opposing_party": get_str_or_blank(task.opposing_party),
            "delegation_date": to_localtime(task.delegation_date, '%d/%m/%Y %H:%M'),
            "court_division": get_str_or_blank(task.court_division),
            "organ": get_str_or_blank(task.movement.law_suit.organ),
            "address": get_str_or_blank(task.address),
            "lawsuit_number": get_str_or_blank(task.lawsuit_number),
            "client": get_str_or_blank(task.client),
            "state": get_str_or_blank(task.movement.law_suit.court_district.state
                                      ) if task.movement.law_suit.court_district else '',
            "court_district": get_str_or_blank(task.movement.law_suit.court_district),
            "city": get_str_or_blank(task.city),
            "court_district_complement": get_str_or_blank(task.court_district_complement),
            "performance_place": get_str_or_blank(task.performance_place),
            "office_name": get_str_or_blank(office.legal_name),
            "office_phone": get_str_or_blank(office.contactmechanism_set.filter(contact_mechanism_type=PHONE).first()),
            "office_email": get_str_or_blank(office.contactmechanism_set.filter(contact_mechanism_type=EMAIL).first()),
            "office_address": get_str_or_blank(office.address_set.first()),
            "office_correspondent_name": task.office.legal_name,
            "office_correspondent_phone": get_str_or_blank(task.office.contactmechanism_set.filter(
                contact_mechanism_type=PHONE).first()),
            "office_correspondent_email": get_str_or_blank(task.office.contactmechanism_set.filter(
                contact_mechanism_type=EMAIL).first()),
            "office_correspondent_address": get_str_or_blank(task.office.address_set.first()),
            "external_task_url": "{}/providencias/external-task-detail/{}/".format(
                settings.WORKFLOW_URL_EMAIL, self.task.task_hash.hex),
            "task_url": project_link,
            "btn_accpeted": "{}/providencias/external-task/ACCEPTED/{}/".format(
                settings.WORKFLOW_URL_EMAIL, self.task.task_hash.hex),
            "btn_refused": "{}/providencias/external-task/REFUSED/{}/".format(
                settings.WORKFLOW_URL_EMAIL, self.task.task_hash.hex)
        }


class TaskAcceptedMailTemplate(BaseTemplateEmail):

    def get_dynamic_template_data(self):
        return {
            "task_number": self.task.task_number,
            "type_task": self.task.type_task.name,
            "title_type_service": "OS {task_number} - {type_task} ".format(task_number=self.task.task_number,
                                                                           type_task=self.task.type_task.name),
            "office_name": self.task.parent.office.legal_name,
            "btn_done": "{}/providencias/external-task/FINISHED/{}/".format(
                settings.WORKFLOW_URL_EMAIL, self.task.task_hash.hex),
            "task_url": "{}/providencias/external-task-detail/{}/".format(
                settings.WORKFLOW_URL_EMAIL, self.task.task_hash.hex),
        }


class TaskRefusedServiceMailTemplate(BaseTemplateEmail):
    def __init__(self, task, **kwargs):
        super().__init__(task, **kwargs)
        self.by_person = kwargs.get('by_person')

    def get_dynamic_template_data(self):
        task_pk = self.task.pk if not self.task.parent else self.task.parent.pk
        project_link = '{}{}'.format(
            get_project_link(self.task),
            reverse('task_detail', kwargs={'pk': task_pk}))
        task_number = self.task.task_number if not self.task.parent else self.task.parent.task_number
        return {
            "task_number":
                task_number,
            "type_task":
                self.task.type_task.name,
            "title_type_service":
                "OS {task_number} - {type_task} ".format(
                    task_number=task_number,
                    type_task=self.task.type_task.name),
            "person_distributed_by":
                str(self.task.person_distributed_by).title(),
            "task_url": project_link,
            "final_deadline_date": timezone.localtime(self.task.final_deadline_date).strftime('%d/%m/%Y %H:%M'),
            "by_person": self.by_person
        }


class TaskRefusedMailTemplate(BaseTemplateEmail):
    def __init__(self, task, **kwargs):
        super().__init__(task, **kwargs)
        self.by_person = kwargs.get('by_person')
        self.task_number = kwargs.get('task_number')

    def get_dynamic_template_data(self):
        project_link = '{}{}'.format(
            get_project_link(self.task),
            reverse('task_detail', kwargs={'pk': self.task.pk}))
        # task_number = self.task.task_number if not self.task.parent else self.task.parent.task_number
        return {
            "task_number":
                self.task_number,
            "type_task":
                self.task.type_task.name,
            "title_type_service":
                "OS {task_number} - {type_task} ".format(
                    task_number=self.task_number,
                    type_task=self.task.type_task.name),
            "person_executed_by":
                str(self.task.person_executed_by).title(),
            "task_url": project_link,
            "final_deadline_date": timezone.localtime(self.task.final_deadline_date).strftime('%d/%m/%Y %H:%M'),
            "by_person": self.by_person
        }


class TaskReturnMailTemplate(BaseTemplateEmail):
    def __init__(self, task, **kwargs):
        super().__init__(task, **kwargs)
        self.by_person = kwargs.get('by_person')

    def get_dynamic_template_data(self):
        project_link = '{}{}'.format(
            get_project_link(self.task),
            reverse('task_detail', kwargs={'pk': self.task.pk}))
        return {
            "task_number":
                self.task.task_number,
            "type_task":
                self.task.type_task.name,
            "title_type_service":
                "OS {task_number} - {type_task} ".format(
                    task_number=self.task.task_number,
                    type_task=self.task.type_task.name),
            "person_distributed_by":
                str(self.task.person_distributed_by).title(),
            "task_url": project_link,
            "final_deadline_date": timezone.localtime(self.task.final_deadline_date).strftime('%d/%m/%Y %H:%M'),
            "by_person": self.by_person
        }



def _apply_default_recipient(recipients):
    """
    Em homologação (DEFAULT_TO_EMAIL definido) todo e-mail vai para o endereço configurado.
    Retorna (lista_destinatarios, destinatarios_originais_ou_None).
    """
    recipients = list(dict.fromkeys(r for r in recipients if r))
    if settings.DEFAULT_TO_EMAIL:
        return [settings.DEFAULT_TO_EMAIL], recipients
    return recipients, None


class TemplateMail(object):
    """
    Renderiza um template Django de e-mail e envia via SMTP (Postfix).
    Substitui o envio por templates dinâmicos do SendGrid.
    """
    template_name = None
    subject = None
    from_email = None

    def __init__(self, recipients, template_name=None, subject=None):
        self.recipients, self.original_recipients = _apply_default_recipient(recipients)
        if template_name:
            self.template_name = template_name
        if subject:
            self.subject = subject
        self.from_email = self.from_email or settings.DEFAULT_FROM_EMAIL
        self.attachments = []

    def get_context(self):
        return {}

    def get_subject(self, context):
        return self.subject or context.get('title_type_service') or settings.PROJECT_NAME

    def build_message(self):
        context = self.get_context()
        if not context:
            return None
        context.setdefault('project_name', settings.PROJECT_NAME)
        context.setdefault('project_link', settings.PROJECT_LINK)
        context.setdefault('server', settings.WORKFLOW_URL_EMAIL)
        if self.original_recipients:
            context['original_recipients'] = ', '.join(self.original_recipients)
        html = render_to_string(self.template_name, context)
        msg = EmailMultiAlternatives(self.get_subject(context), 'Este e-mail requer um cliente com suporte a HTML.',
                                     self.from_email, self.recipients)
        msg.attach_alternative(html, 'text/html')
        for filename, content, mimetype in self.attachments:
            msg.attach(filename, content, mimetype)
        return msg

    def send_mail(self):
        if not self.recipients:
            return False
        try:
            msg = self.build_message()
            if msg is None:
                return False
            sent = msg.send()
            logger.info('E-mail "%s" enviado para %s (%s)', msg.subject, self.recipients, sent)
            return bool(sent)
        except Exception:
            logger.error(traceback.format_exc())
            return False


class TaskMail(TemplateMail):
    """
    E-mail de mudança de status da OS. O template é escolhido pelo status atual da OS;
    o parâmetro template_id (nome do template cadastrado em EmailTemplate) só sobrescreve
    quando termina em ".html".
    """
    @staticmethod
    def email_status():
        # Import tardio: task.models importa este módulo.
        TaskStatus = task_models.TaskStatus
        return {
            TaskStatus.REQUESTED: (TaskOpenMailTemplate, 'mail/task_open.html'),
            TaskStatus.REFUSED_SERVICE: (TaskRefusedServiceMailTemplate, 'mail/task_refused_service.html'),
            TaskStatus.REFUSED: (TaskRefusedMailTemplate, 'mail/task_refused.html'),
            TaskStatus.RETURN: (TaskReturnMailTemplate, 'mail/task_return.html'),
            TaskStatus.ACCEPTED: (TaskAcceptedMailTemplate, 'mail/task_accepted.html'),
            TaskStatus.OPEN: (TaskOpenMailTemplate, 'mail/task_open.html'),
            TaskStatus.FINISHED: (TaskFinishedEmail, 'mail/task_finished.html'),
        }

    def __init__(self, email, task, template_id=None, by_person=None, task_number=''):
        super().__init__(email)
        self.task = task
        self.by_person = by_person
        self.task_number = task_number
        template_class, template_name = self.email_status().get(self.task.status, (None, None))
        if template_id and str(template_id).endswith('.html'):
            template_name = template_id
        self.template_name = template_name
        self.template_class = template_class(task, by_person=by_person, task_number=task_number) \
            if template_class else None
        self.attachments = self.get_task_attachments()

    def get_context(self):
        if not self.template_class:
            return {}
        data = self.template_class.get_dynamic_template_data()
        if not data:
            return {}
        data['task'] = self.task
        return data

    def get_task_attachments(self):
        task = self.task.parent if self.task.parent else self.task
        attachments = []
        for ecm in task.ecm_set.all():
            try:
                attachments.append((ecm.filename, ecm.path.read(), 'application/octet-stream'))
            except Exception:
                logger.warning('Não foi possível anexar o ECM %s ao e-mail', ecm.pk)
        return attachments


class TaskCompanyRepresentativeChangeMail(TemplateMail):
    """E-mail para o preposto quando ele é vinculado/desvinculado de uma OS."""

    def __init__(self, email, task, template_name):
        super().__init__(email, template_name=template_name)
        self.task = task

    def get_context(self):
        project_link = '{}{}'.format(
            get_project_link(self.task),
            reverse('task_detail', kwargs={'pk': self.task.pk}))
        return {
            "task": self.task,
            "task_title": "{task_number} - {type_task} ".format(
                task_number=self.task.task_number,
                type_task=self.task.type_task.name),
            "task_url": project_link,
            "name": self.task.person_company_representative.legal_name
        }

    def get_subject(self, context):
        return 'OS {}'.format(context['task_title'])
