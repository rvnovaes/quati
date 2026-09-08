import copy
import uuid
from decimal import Decimal
from django.template.loader import render_to_string
from django.utils import timezone
from ecm.models import DefaultAttachmentRule, Attachment
from financial.utils import recalculate_values
from task.workflow import get_child_recipients
from task.models import *
from task.mail import SendMail
from task.rules import RuleViewTask
from core.utils import get_office_session
from core.tasks import send_mail
from django.db.models import Q
from django.core.files.base import ContentFile
from django.conf import settings
import logging
from manager.enums import TemplateKeys
from manager.utils import get_template_value_value

logger = logging.getLogger(__name__)


def get_task_attachment(self, form):
    state = form.instance.court_district.state if form.instance.court_district else None
    attachmentrules = DefaultAttachmentRule.objects.filter(
        Q(office=get_office_session(self.request)),
        Q(Q(type_task=form.instance.type_task) | Q(type_task=None)),
        Q(Q(person_customer=form.instance.client) | Q(person_customer=None)),
        Q(Q(state=state) | Q(state=None)),
        Q(
            Q(court_district=form.instance.court_district)
            | Q(court_district=None)),
        Q(
            Q(
                city=(form.instance.movement.law_suit.organ.address_set.
                      first().city if form.instance.movement and form.instance.
                      movement.law_suit and form.instance.movement.law_suit.
                      organ and form.instance.movement.law_suit.organ.
                      address_set.first() else None)) | Q(city=None)))

    for rule in attachmentrules:
        attachments = Attachment.objects.filter(
            model_name='ecm.defaultattachmentrule').filter(object_id=rule.id)
        for attachment in attachments:
            new_file = get_file_content_copy(attachment.file)
            if new_file:
                file_name = os.path.basename(attachment.file.name)
                new_file.name = file_name
                if not Ecm.objects.filter(
                        exhibition_name=file_name, task_id=form.instance.id):
                    obj = Ecm(
                        path=new_file,
                        task=Task.objects.get(id=form.instance.id),
                        create_user_id=self.request.user.id,
                        create_date=timezone.now(),
                        exhibition_name=file_name)
                    obj.save()


def get_file_content_copy(filefield):
    local_file_path = os.path.join(settings.MEDIA_ROOT, filefield.name)
    if os.path.exists(local_file_path):
        with open(local_file_path, 'rb') as local_file:
            content = ContentFile(local_file.read())
    else:
        try:
            content = ContentFile(filefield.read())
        except:
            content = None
    return content


def task_send_mail(instance, number, project_link, short_message, custom_text,
                   mail_list):
    mail = SendMail()
    mail.subject = 'Quati - OS {} - {} - Prazo: {} - {}'.format(
        number,
        str(instance.type_task).title(),
        instance.final_deadline_date.strftime('%d/%m/%Y'),
        instance.task_status)
    mail.message = render_to_string(
        'mail/base.html', {
            'server': project_link,
            'pk': instance.pk,
            'project_name': settings.PROJECT_NAME,
            'number': str(number),
            'short_message': short_message,
            'custom_text': custom_text,
            'task': instance
        })
    mail.to_mail = list(set(mail_list))
    try:
        mail.send()
    except Exception as e:
        print(e)
        print('Você tentou mandar um e-mail')


def get_dashboard_tasks(request, office_session, checker, person):
    rule_view = RuleViewTask(request=request)
    dynamic_query = rule_view.get_dynamic_query(person, checker)
    data = Task.objects.none()
    exclude_status = []

    if not office_session:
        return data, office_session
    # NOTE: Quando o usuário é superusuário ou não possui permissão é retornado um objeto Q vazio
    if dynamic_query or checker.has_perm('group_admin', office_session):
        # filtra as OS de acordo com a pessoa (correspondente, solicitante e contratante) preenchido na OS
        if office_session:
            if not office_session.use_service:
                exclude_status.append(TaskStatus.ACCEPTED_SERVICE.value)
                exclude_status.append(TaskStatus.REFUSED_SERVICE.value)
            if not office_session.use_etl:
                exclude_status.append(TaskStatus.ERROR.value)
            data = Task.objects.filter(dynamic_query).filter(
                is_active=True, office_id=office_session.id).filter(~Q(
                    task_status__in=exclude_status))

    return data, exclude_status


def create_default_type_tasks(office, create_user=None):
    if not create_user:
        create_user = office.create_user
    main_type_tasks = TypeTaskMain.objects.all()
    TypeTask.objects.filter(office=office).delete()
    for main_type_task in main_type_tasks:
        type_task = TypeTask()
        type_task.name = main_type_task.name
        type_task.create_user = create_user
        type_task.office = office
        type_task.save()
        type_task.type_task_main.add(main_type_task)
        type_task.save()


def get_task_ecms(task_id):
    return Ecm.objects.filter(Q(tasks__id=task_id) | Q(task_id=task_id)).distinct('id')


def create_ecm_task(ecm, task):
    EcmTask.objects.get_or_create(ecm=ecm, task=task)


def clone_task_ecms(task_from, task_to):
    for ecm in get_task_ecms(task_from.id):
        create_ecm_task(ecm, task_to)


def self_or_none(obj):
    return obj if obj else None


def delegate_child_task(object_parent, office_correspondent, type_task=None, amount_to_receive=None):
    """
    Este metodo e chamado quando um escritorio delega uma OS para outro escritorio
    Ao realizar este processo a nova OS criada devera ficar com o status de Solicitada
    enquanto a OS pai devera ficar com o status de Delegada/Em Aberti
    :param object_parent: Task que sera copiada para gerar a nova task
    :param office_correspondent: Escritorio responsavel pela nova task
    :param type_task: Tipo de servico a considerado para a criacao da OS filha
    :return:
    """
    if object_parent.get_latest_child_not_refused:
        if TaskStatus(object_parent.get_latest_child_not_refused.task_status) not in [
                TaskStatus.REFUSED, TaskStatus.REFUSED_SERVICE,
                TaskStatus.FINISHED
        ]:
            return False
    new_task = copy.copy(object_parent)
    new_task.type_task = type_task or object_parent.type_task
    new_task.task_hash = uuid.uuid4()
    new_task.legacy_code = None
    new_task.system_prefix = None
    new_task.pk = new_task.task_number = None
    new_task.person_asked_by = None
    new_task.person_executed_by = None
    new_task.person_distributed_by = None
    new_task.delegation_date = None
    new_task.person_company_representative = None
    new_task.charge = None
    new_task.office = office_correspondent
    new_task.task_status = TaskStatus.REQUESTED
    new_task.parent = object_parent
    new_task.amount = object_parent.amount_delegated
    new_task.amount_to_pay = Decimal('0.00')
    new_task.amount_delegated = Decimal('0.00')
    new_task.amount_to_receive = amount_to_receive
    new_task._mail_attrs = get_child_recipients(TaskStatus.OPEN)
    new_task.save(**{'from_parent': True})
    clone_task_ecms(object_parent, new_task)


def get_offices_to_pay(tasks):
    from task.serializers import OfficeToPaySerializer
    return [OfficeToPaySerializer(task.office).data for task in tasks]


def get_last_parent(task):
    if task.parent:
        return get_last_parent(task.parent)
    return task


def has_task_parent(task):
    if task.parent:
        return True
    return False


def get_delegate_amounts(task, service_price_table):
    if task.amount_delegated != service_price_table.value:
        return recalculate_amounts(service_price_table.value,
                                   task.amount_to_pay,
                                   task.amount_to_receive,
                                   task.amount_delegated,
                                   task.rate_type_pay,
                                   task.rate_type_receive)

    return Decimal(service_price_table.value_to_receive.amount), Decimal(service_price_table.value_to_pay.amount)


def get_status_to_filter(option):
    default_status = [TaskStatus.ACCEPTED_SERVICE, TaskStatus.REQUESTED, TaskStatus.OPEN,
                      TaskStatus.DONE, TaskStatus.ERROR]
    status_dict = {
        'A': [TaskStatus.ACCEPTED_SERVICE, TaskStatus.REQUESTED],
        'D': [TaskStatus.ACCEPTED_SERVICE, TaskStatus.REQUESTED],
        'CA': [TaskStatus.REQUESTED, TaskStatus.ACCEPTED_SERVICE, TaskStatus.OPEN, TaskStatus.ACCEPTED,
               TaskStatus.DONE, TaskStatus.RETURN, TaskStatus.REFUSED_SERVICE, TaskStatus.ERROR],
        'P': [TaskStatus.ACCEPTED,TaskStatus.ACCEPTED_SERVICE,TaskStatus.OPEN,TaskStatus.ERROR,TaskStatus.REQUESTED]
    }

    return sorted(list(status.value for status in status_dict.get(option.upper(), default_status)))


def set_performance_place(movement):
    list_places = []
    if movement.law_suit.court_district:
        list_places = [movement.law_suit.court_district.state.initials,
                       movement.law_suit.court_district.name]
    if movement.law_suit.court_district_complement:
        list_places.append(movement.law_suit.court_district_complement.name)
    elif movement.law_suit.city:
        list_places.append(movement.law_suit.city.name)
        
    performance_place = ' - '.join(list_places) if list_places else 'Não definido'

    return performance_place


def get_default_customer(office):
    key = TemplateKeys.DEFAULT_CUSTOMER.name
    return get_template_value_value(office, key)


def validate_final_deadline_date(final_deadline_date, office):
    min_hour_os = float(get_template_value_value(office, TemplateKeys.MIN_HOUR_OS.name))
    return not (min_hour_os > 0
                and timezone.localtime() + timezone.timedelta(hours=min_hour_os) > final_deadline_date)


def recalculate_amounts(old_amount, amount_to_pay, amount_to_receive, new_amount, rate_type_pay, rate_type_receive):
    """
    Calcula os novos valores a pagar e a receber para a ordem de serviço, de acordo com os dados antigos.
    Este método recebe os dados da OS, e chama o método utilizado para recalcular os valor da tabela de preços,
    invertendo os valores a pagar e a receber, já que o concieto deles é invertido para a OS
    :param old_amount: Valor autal de delegação da OS
    :param amount_to_pay: Valor atual a pagar (valor que será pago ao MTA pela execução do serviço)
    :param amount_to_receive: Valor atual a receber (valor que será pago ao correspondente que executar o serviço)
    :param new_amount: Novo valor de delegação da OS
    :param rate_type_pay: tipo de correção a ser feita para o valor a pagar (PERCENT ou VALUE)
    :param rate_type_receive: tipo de correção a ser feita para o valor a receber (PERCENT ou VALUE)
    :return amount_to_pay, amount_to_receive: novos valores a pagar e a receber pela execução do serviço
    """
    amount_to_receive, amount_to_pay = recalculate_values(old_amount,
                                                          amount_to_receive,
                                                          amount_to_pay,
                                                          new_amount,
                                                          rate_type_pay, rate_type_receive)
    return amount_to_pay, amount_to_receive


def filter_api_queryset_by_params(queryset, params):
    if params.getlist('office_id[]'):
        queryset = queryset.filter(office_id__in=params.getlist('office_id[]'))

    if params.get('correspondent'):
        queryset = queryset.filter(office_id=params.get('correspondent'), parent__office_id=params.get('office_id'))

    if params.get('person_executed_by_id[]'):
        queryset = queryset.filter(person_executed_by_id__in=params.getlist('person_executed_by_id[]'))
    if params.getlist('task_status[]'):
        status_to_filter = params.getlist('task_status[]')
        queryset = queryset.filter(task_status__in=[getattr(TaskStatus, status) for status in status_to_filter])

    return queryset
