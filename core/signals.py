from django.contrib.auth.models import User
from django.conf import settings
from django.db import models
from django.db.models.signals import post_init, pre_save, post_save, post_delete

from core.models import Person, Invite, Office, OfficeMembership, CustomSettings, EmailTemplate
from django.dispatch import receiver, Signal
from task.mail import SendMail
from task.utils import create_default_type_tasks
from django.template.loader import render_to_string
from core.permissions import create_permission
from core.utils import create_office_custom_settings
from guardian.shortcuts import get_groups_with_perms
from core.utils import create_office_template_value, add_create_user_to_admin_group
from manager.utils import get_template_by_key, create_template_value, exist_template_value, update_template_value
from manager.enums import TemplateKeys


def create_office_setting_email_notification(office):
    template_key = TemplateKeys.EMAIL_NOTIFICATION.name
    value = office.create_user.email
    if not exist_template_value(office, template_key):
        template = get_template_by_key(template_key)
        create_template_value(template, office, value)
    else:
        template_obj = office.get_template_value_obj(template_key)
        update_template_value(template_obj, value)


def create_office_setting_default_user(office):
    template_key = TemplateKeys.DEFAULT_USER.name
    value = office.create_user_id
    if not exist_template_value(office, template_key):
        template = get_template_by_key(template_key)
        create_template_value(template, office, value)
    else:
        template_obj = office.get_template_value_obj(template_key)
        update_template_value(template_obj, value)


def create_office_setting_i_work_alone(office):
    template_key = TemplateKeys.I_WORK_ALONE.name
    template = get_template_by_key(template_key)
    i_work_alone = getattr(office, '_i_work_alone', template.default_value if template else False)
    office.i_work_alone = i_work_alone


def create_office_setting_use_service(office):
    template_key = TemplateKeys.USE_SERVICE.name
    template = get_template_by_key(template_key)
    use_service = getattr(office, '_use_servie', template.default_value if template else False)
    office.use_service = use_service


def create_office_setting_use_etl(office):
    template_key = TemplateKeys.USE_ETL.name
    template = get_template_by_key(template_key)
    use_etl = getattr(office, '_use_etl', template.default_value if template else False)
    office.use_etl = use_etl


def create_office_setting_default_customer(office):
    template_key = TemplateKeys.DEFAULT_CUSTOMER.name
    default_customer = Person.objects.filter(legal_name=office.legal_name,
                                             name=office.legal_name,
                                             is_customer=True).first()
    if not default_customer:
        default_customer, created = Person.objects.get_or_create(legal_name=office.legal_name,
                                                                 name=office.legal_name,
                                                                 is_customer=True,
                                                                 defaults={"create_user_id": office.create_user.id,
                                                                           "is_active": True})
        if created:
            OfficeMembership.objects.create(person=default_customer,
                                            office_id=office.id,
                                            create_user_id=office.create_user.id,
                                            is_active=True)

    if not exist_template_value(office, template_key):
        template = get_template_by_key(template_key)
        if template is None:
            # Fixture 'template' (app manager) ainda não carregada (ex.: testes). Nada a configurar.
            return
        create_template_value(template, office, default_customer.id)
    else:
        template_obj = office.get_template_value_obj(template_key)
        update_template_value(template_obj, default_customer.id)


def create_membership_and_groups(office):
    member, created = OfficeMembership.objects.get_or_create(
        person=office.create_user.person,
        office=office,
        defaults={
            'create_user': office.create_user,
            'is_active': True
        })
    if not created:
        # Caso o relacionamento esteja apenas inativo
        member.is_active = True
        member.save()
    else:
        for super_user in User.objects.filter(is_superuser=True).all():
            member, created = OfficeMembership.objects.update_or_create(
                person=super_user.person,
                office=office,
                defaults={
                    'create_user': office.create_user,
                    'is_active': True
                })
    add_create_user_to_admin_group(office)
    create_default_type_tasks(office)


def create_person(instance, sender, **kwargs):
    if not getattr(instance, 'person', None):
        Person.objects.create(
            legal_name=instance.first_name + ' ' + instance.last_name,
            name=instance.first_name + ' ' + instance.last_name,
            is_lawyer=False,
            legal_type='F',
            alter_user=instance,
            auth_user=instance,
            create_user=instance,
            is_active=True,
            is_customer=False,
            is_supplier=False,
            import_from_legacy=False,
            legacy_code='')
    else:
        person = instance.person
        person.auth_user = instance
        person.save()


@receiver(post_save, sender=Invite)
def send_invite_email(instance, sender, **kwargs):
    project_link = settings.PROJECT_LINK
    if hasattr(instance, '_InviteCreateView__host'):
        project_link = instance._InviteCreateView__host
    mail = SendMail()
    mail.subject = 'Easy Lawyer - Convite para cadastro'
    mail.message = render_to_string(
        'core/mail/base.html', {
            'server': project_link,
            'pk': instance.pk,
            'project_name': settings.PROJECT_NAME,
            'invite': instance
        })
    mail.to_mail = [instance.email]

    # TODO: tratar corretamente a excecao

    try:
        mail.send()
    except Exception as e:
        print(e)
        print('Você tentou mandar um e-mail')


models.signals.post_save.connect(
    create_person, sender=User, dispatch_uid='create_person')


@receiver(post_save, sender=Office)
def office_post_save(sender, instance, created, **kwargs):
    create_permission(instance)
    if created:
        create_membership_and_groups(instance)
        create_office_template_value(instance)
        create_office_setting_default_customer(instance)
        create_office_setting_i_work_alone(instance)
        create_office_setting_use_etl(instance)
        create_office_setting_use_service(instance)
        create_office_setting_default_user(instance)
        create_office_setting_email_notification(instance)
        add_create_user_to_admin_group(instance)

        # TODO: Retirar metodo a seguir depois de eliminar a relacao entre CustomSettings e TaskWorkflow e
        #  TaskStatusToShow
        CustomSettings.objects.update_or_create(
            office=instance,
            create_user_id=instance.create_user_id,
            is_active=True,
            defaults={
                'alter_user_id': instance.create_user.id
            }
        )


@receiver(post_delete, sender=Office)
def office_post_delete(sender, instance, **kwargs):
    for group in get_groups_with_perms(instance):
        group.delete()


@receiver(post_save, sender=CustomSettings)
def custom_settings_post_save(sender, instance, created, **kwargs):
    if created:
        create_office_custom_settings(instance.office)
