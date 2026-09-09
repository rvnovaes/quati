import logging
import traceback

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

MANUAL_URL = 'https://ezlawyer.atlassian.net/wiki/spaces/PUB/pages/101597/Manual+do+sistema'


def send_template_mail(subject, template_name, context, recipients, attachments=None):
    """Renderiza um template HTML e envia via SMTP. Respeita DEFAULT_TO_EMAIL (homologação)."""
    recipients = list(dict.fromkeys(r for r in recipients if r))
    if not recipients:
        return False
    context = dict(context)
    context.setdefault('project_name', settings.PROJECT_NAME)
    context.setdefault('project_link', settings.PROJECT_LINK)
    context.setdefault('server', settings.WORKFLOW_URL_EMAIL)
    if settings.DEFAULT_TO_EMAIL:
        context['original_recipients'] = ', '.join(recipients)
        recipients = [settings.DEFAULT_TO_EMAIL]
    try:
        html = render_to_string(template_name, context)
        msg = EmailMultiAlternatives(subject, 'Este e-mail requer um cliente com suporte a HTML.',
                                     settings.DEFAULT_FROM_EMAIL, recipients)
        msg.attach_alternative(html, 'text/html')
        for filename, content, mimetype in attachments or []:
            msg.attach(filename, content, mimetype)
        return bool(msg.send())
    except Exception:
        logger.error(traceback.format_exc())
        return False


def send_mail_sign_up(name, to_email):
    return send_template_mail(
        'Bem-vindo ao {}'.format(settings.PROJECT_NAME),
        'mail/sign_up.html',
        {'name': name, 'url': MANUAL_URL},
        [to_email])
