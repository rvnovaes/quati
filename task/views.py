import json
import pickle
import io
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zipfile import ZipFile
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from core.views import CustomLoginRequiredView, set_office_session
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.db import IntegrityError, OperationalError
from django.db.models import Q, Case, When, CharField, Count, TextField, Max, Subquery, OuterRef, Prefetch, F
from django.db.models.functions import Cast, Coalesce
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse, Http404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.generic import CreateView, UpdateView, TemplateView, View
from django.views.static import serve as static_serve_view
from django.core.exceptions import ValidationError
from django_tables2 import SingleTableView, RequestConfig
from djmoney.money import Money
from core.messages import CREATE_SUCCESS_MESSAGE, UPDATE_SUCCESS_MESSAGE, DELETE_SUCCESS_MESSAGE, \
    operational_error_create, ioerror_create, exception_create, integrity_error_delete, DELETE_EXCEPTION_MESSAGE, \
    success_sent, success_delete, NO_PERMISSIONS_DEFINED
from core.models import Person, CorePermissions, CustomSettings
from core.permissions import CustomPermissionRequiredMixin
from core.views import AuditFormMixin, MultiDeleteViewMixin, SingleTableViewMixin
from core.xlsx import XLSXWriter
from lawsuit.forms import LawSuitForm
from lawsuit.models import Movement, LawSuit, Folder, TypeMovement
from task.delegate import DelegateTask
from task.filters import TaskFilter, TaskToPayFilter, TaskToReceiveFilter, OFFICE, BatchChangTaskFilter, \
    TaskCheckinReportFilter
from task.forms import TaskForm, TaskDetailForm, TaskCreateForm, TaskToAssignForm, FilterForm, TypeTaskForm, \
    ImportTaskListForm, TaskBulkCreateForm, TaskChangeAskedBy, TaskChangeRepresentativeBy
from task.models import Task, Ecm, TaskStatus, TypeTask, TaskHistory, TaskFilterViewModel, Filter, TaskFeedback, \
    TaskGeolocation, TypeTaskMain, TaskSurveyAnswer
from .report import TaskToPayXlsx, ExportFilterTask
from task.queries import *
from task.signals import send_notes_execution_date
from task.tables import TaskTable, DashboardStatusTable, FilterTable, TypeTaskTable
from task.tasks import import_xls_task_list
from task.rules import RuleViewTask
from task.workflow import CorrespondentsTable, CorrespondentsTablePostPaid
from task.serializers import TaskCheckinSerializer
from financial.models import ServicePriceTable
from financial.serializers import ServicePriceDelegationTableSerializer
from core.utils import get_office_session, get_domain
from task.utils import get_task_attachment, get_dashboard_tasks, get_task_ecms, delegate_child_task, get_last_parent, \
    has_task_parent, get_delegate_amounts, get_status_to_filter, get_default_customer, recalculate_amounts
from decimal import Decimal
from guardian.core import ObjectPermissionChecker
from functools import reduce
from django.shortcuts import render
import os
from django.conf import settings
from urllib.parse import urljoin
from babel.numbers import format_currency
from task import signals
from django.db.models.signals import pre_save, post_save
from dal import autocomplete
import logging
import operator
from manager.template_values import ListTemplateValues
from manager.enums import TemplateKeys
from manager.utils import get_template_value_value

logger = logging.getLogger(__name__)

mapOrder = {'asc': '', 'desc': '-'}


class TaskListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = Task
    table_class = TaskTable


class TaskBulkCreateView(AuditFormMixin, CreateView):
    model = Task
    form_class = TaskBulkCreateForm
    success_url = reverse_lazy('task_list')
    success_message = CREATE_SUCCESS_MESSAGE
    template_name_suffix = '_bulk_create_form'

    def __init__(self):
        super().__init__()
        self.folder = None
        self.law_suit = None
        self.movement = None

    def get_folder(self, validation_data):
        folder_number = validation_data.get('folder_number', False)
        if folder_number:
            folder = Folder.objects.filter(id=folder_number).first()
        else:
            folder = Folder.objects.filter(person_customer_id=validation_data.get('person_customer_id'),
                                           is_default=True,
                                           office=validation_data.get('office'),
                                           is_active=True).first()
            if not folder:
                folder, created = Folder.objects.get_or_create(
                    person_customer_id=validation_data.get('person_customer_id'),
                    is_default=True,
                    office=validation_data.get('office'),
                    is_active=True,
                    defaults={'create_user': validation_data.get('create_user')})
        self.folder = folder

    def get_law_suit(self, validation_data):
        law_suit_number = validation_data.get('law_suit_number', False)
        if law_suit_number:
            law_suit = LawSuit.objects.filter(id=law_suit_number).first()
            if law_suit.folder != self.folder and not self.folder.is_default:
                law_suit.folder = self.folder
                law_suit.save()
            else:
                folder = law_suit.folder
        else:
            law_suit, created = LawSuit.objects.get_or_create(folder=self.folder,
                                                              law_suit_number='Processo avulso',
                                                              office=validation_data.get('office'),
                                                              defaults={
                                                                  'create_user': validation_data.get('create_user'),
                                                                  'is_active': True})
        self.law_suit = law_suit

    def get_movement(self, validation_data):
        movement_id = validation_data.get('movement_id', False)
        if movement_id:
            movement = Movement.objects.filter(id=movement_id).first()
            movement.law_suit = self.law_suit
            movement.save()
        else:
            default_type_movement, created = TypeMovement.objects.get_or_create(is_default=True,
                                                                                office=validation_data.get('office'),
                                                                                defaults={
                                                                                    'name': 'OS Avulsa',
                                                                                    'create_user': validation_data.get(
                                                                                        'create_user')})
            movement_filter = {
                'folder': self.folder,
                'law_suit': self.law_suit,
                'type_movement': default_type_movement,
                'office': validation_data.get('office'),
            }
            movement = Movement.objects.filter(**movement_filter).first()
            if not movement:
                movement_filter['create_user'] = validation_data.get('create_user')
                movement_filter['is_active'] = True
                movement = Movement.objects.create(**movement_filter)
        self.movement = movement

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        office = get_office_session(self.request)
        context['min_hour_os'] = get_template_value_value(office, TemplateKeys.MIN_HOUR_OS.name)
        context['default_customer'] = None
        context['lawsuit_form'] = LawSuitForm(request=self.request)

        default_customer = get_default_customer(office)
        if default_customer:
            context['default_customer'] = {'id': default_customer.id,
                                           'text': default_customer.legal_name}
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        form.fields['person_customer_swal'].required = False
        form.fields['person_asked_by'].queryset = Person.objects.all()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        try:
            validation_data = {
                'create_user': self.request.user,
                'office': form.instance.office,
                'movement_id': self.request.POST['movement'],
                'law_suit_number': self.request.POST['task_law_suit_number'],
                'folder_number': self.request.POST['folder_number'],
                'person_customer_id': self.request.POST['person_customer']
            }
            form.instance.create_user = validation_data['create_user']
            form.instance.create_date = timezone.now()
            form.instance.is_active = True

            self.get_folder(validation_data)
            self.get_law_suit(validation_data)
            if self.request.POST.get('court_district', None) \
                    and self.law_suit.court_district_id != int(self.request.POST['court_district']):
                self.law_suit.court_district_id = int(self.request.POST['court_district'])
                self.law_suit.save()
            if self.request.POST.get('court_district_complement', None) and \
                    self.law_suit.court_district_complement_id != int(self.request.POST['court_district_complement']):
                self.law_suit.court_district_complement_id = int(self.request.POST['court_district_complement'])
                self.law_suit.save()
            if self.request.POST.get('city', None) and self.law_suit.city_id != int(self.request.POST['city']):
                self.law_suit.city_id = int(self.request.POST['city'])
                self.law_suit.save()
            self.get_movement(validation_data)

            form.instance.movement = self.movement
            form.instance.__server = get_domain(self.request)
            task = form.save()

            documents = form.cleaned_data['documents'] if form.fields.get('documents') else []
            if documents:
                for document in documents:
                    file_name = document.name.replace(' ', '_')
                    task.ecm_set.create(
                        path=document,
                        exhibition_name=file_name,
                        create_user=task.create_user)

            form.delete_temporary_files()

            status = 201
            ret = {'status': 'Ok', 'task_id': task.id, 'task_number': task.task_number}
            return JsonResponse(ret, status=status)
        except Exception as e:
            logger.exception('Erro ao criar OS')
            status = 500
            ret = {'status': 'error', 'error': getattr(e, 'messages', [str(e)])}
            return JsonResponse(ret, status=status)

    def form_invalid(self, form):
        status = 500
        ret = {'status': 'false', 'errors': form.errors}
        return JsonResponse(ret, status=status)


class TaskCreateView(AuditFormMixin, CreateView):
    model = Task
    form_class = TaskCreateForm
    success_message = CREATE_SUCCESS_MESSAGE
    template_name_suffix = '_persist_form'

    def get_initial(self):
        if self.kwargs.get('movement'):
            lawsuit_id = Movement.objects.get(
                id=self.kwargs.get('movement')).law_suit_id
            self.kwargs['lawsuit'] = lawsuit_id

        if isinstance(self, CreateView):
            self.form_class.declared_fields['is_active'].initial = True
            self.form_class.declared_fields['is_active'].disabled = True

        elif isinstance(self, UpdateView):
            self.form_class.declared_fields['is_active'].disabled = False

        return self.initial.copy()

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        task = form.instance
        form.instance.movement_id = self.kwargs.get('movement')
        self.kwargs.update({'lawsuit': form.instance.movement.law_suit_id})
        form.instance.__server = get_domain(self.request)
        response = super().form_valid(form)

        documents = self.request.FILES.getlist('file')
        if documents:
            for document in documents:
                file_name = document.name.replace(' ', '_')
                task.ecm_set.create(
                    path=document,
                    exhibition_name=file_name,
                    create_user=task.create_user)

        form.delete_temporary_files()

        return response

    def get_success_url(self):
        return reverse(
            'movement_update',
            kwargs={
                'lawsuit': self.kwargs['lawsuit'],
                'pk': self.kwargs['movement']
            })


class TaskToAssignView(CustomLoginRequiredView, UpdateView):
    model = Task
    form_class = TaskToAssignForm
    success_url = reverse_lazy('dashboard')
    template_name_suffix = '_to_assign'

    def form_valid(self, form):
        form.instance.person_distributed_by = self.request.user.person
        form.instance.task_status = TaskStatus.OPEN
        # TODO: rever processo de anexo, quando for trocar para o ECM Generico
        get_task_attachment(self, form)
        super().form_valid(form)
        return HttpResponseRedirect(self.success_url + str(form.instance.id))

    def form_invalid(self, form):
        super().form_invalid(form)
        return HttpResponseRedirect(self.success_url + str(form.instance.id))


class BatchTaskToAssignView(AuditFormMixin, UpdateView):
    def post(self, request, *args, **kwargs):
        try:
            task_id = kwargs.get('pk')
            task = Task.objects.get(pk=task_id)
            form = TaskToAssignForm(request.POST, instance=task)
            if form.is_valid():
                form.instance.person_executed_by_id = request.POST.get('person_executed_by')
                form.instance.person_distributed_by = self.request.user.person
                form.instance.task_status = TaskStatus.OPEN
                get_task_attachment(self, form)
                form.save()
                return JsonResponse({'status': 'ok'})
            return JsonResponse({'status': 'error', 'errors': form})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})


class BatchTaskChangeAskedByView(AuditFormMixin, UpdateView):
    def post(self, request, *args, **kwargs):
        try:
            task_id = kwargs.get('pk')
            task = Task.objects.get(pk=task_id)
            form = TaskChangeAskedBy(request.POST, instance=task)
            if form.is_valid():
                form.save()
                return JsonResponse({'status': 'ok'})
            return JsonResponse({'status': 'error', 'errors': form})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})


class BatchTaskChangeRepresentativeByView(AuditFormMixin, UpdateView):
    def post(self, request, *args, **kwargs):
        try:
            task_id = kwargs.get('pk')
            task = Task.objects.get(pk=task_id)
            form = TaskChangeRepresentativeBy(request.POST, instance=task)
            if form.is_valid():
                form.save()
                return JsonResponse({'status': 'ok'})
            return JsonResponse({'status': 'error', 'errors': form})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

class BatchTaskToDelegateView(AuditFormMixin, UpdateView):
    def post(self, request, *args, **kwargs):
        try:
            task = Task.objects.get(pk=kwargs.get('pk'))
            form = TaskDetailForm(request.POST, instance=task)
            if form.is_valid():
                form.instance.task_status = TaskStatus.OPEN
                form = DelegateTask(self.request, form).delegate()

                form.save()
                return JsonResponse({'status': 'ok'})
            return JsonResponse({'status': 'error', 'errors': form})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})


class BatchTaskToRefuseView(AuditFormMixin, UpdateView):
    def post(self, request, *args, **kwargs):
        task = Task.objects.get(pk=kwargs.get('pk'))
        task.task_status = TaskStatus.REFUSED
        send_notes_execution_date.send(
            sender=self.__class__,
            notes=request.POST.get('notes'),
            instance=task,
            execution_date=task.execution_date,
            survey_result=task.survey_result)
        task.save()
        return JsonResponse({'status': 'ok'})


class TaskUpdateView(AuditFormMixin, UpdateView):
    model = Task
    form_class = TaskForm
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_persist_form'

    def get_initial(self):
        if self.kwargs.get('movement'):
            lawsuit_id = Movement.objects.get(
                id=self.kwargs.get('movement')).law_suit_id
            self.kwargs['lawsuit'] = lawsuit_id
            self.success_url = reverse(
                'movement_update',
                kwargs={
                    'lawsuit': self.kwargs['lawsuit'],
                    'pk': self.kwargs['movement']
                })
        if isinstance(self, CreateView):
            self.form_class.declared_fields['is_active'].initial = True
            self.form_class.declared_fields['is_active'].disabled = True

        elif isinstance(self, UpdateView):
            self.form_class.declared_fields['is_active'].disabled = False
        return self.initial.copy()

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        task = form.instance
        self.kwargs.update({'lawsuit': form.instance.movement.law_suit_id})
        form.instance.__server = get_domain(self.request)
        super(TaskUpdateView, self).form_valid(form)

        if form.cleaned_data['documents']:
            for document in form.cleaned_data['documents']:
                file_name = document.name.replace(' ', '_')
                task.ecm_set.create(
                    path=document,
                    exhibition_name=file_name,
                    create_user=task.create_user)

        form.delete_temporary_files()
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super(TaskUpdateView, self).get_context_data(**kwargs)
        context['ecms'] = Ecm.objects.filter(task_id=self.object.id)

        return context


class TaskDeleteView(SuccessMessageMixin, CustomLoginRequiredView,
                     MultiDeleteViewMixin):
    model = Task
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)

    def post(self, request, *args, **kwargs):
        self.success_url = urlparse(request.META.get('HTTP_REFERER')).path
        return super(TaskDeleteView, self).post(request, *args, **kwargs)


class TaskReportBase(PermissionRequiredMixin, CustomLoginRequiredView,
                     TemplateView):
    permission_required = ('core.view_financial_report',)
    template_name = None
    filter_class = None
    datetime_field = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.task_filter = self.filter_class(
            data=self.request.GET, request=self.request)
        context['filter'] = self.task_filter
        try:
            if self.request.GET['group_by_tasks'] == OFFICE:
                office_list, total, total_to_receive, amount_total = self.get_os_grouped_by_office()
            else:
                office_list, total, total_to_receive, amount_total = self.get_os_grouped_by_client()
        except:
            office_list, total, total_to_pay, amount_total = self.get_os_grouped_by_office()
        context['offices_report'] = office_list
        context['total'] = total
        context['amount_total'] = amount_total
        return context

    def get_queryset(self):
        office = get_office_session(self.request)
        queryset = Task.objects.filter(
            office=office,
            task_status=TaskStatus.FINISHED,
            child__isnull=False)
        queryset = self.filter_queryset(queryset)
        return queryset.order_by('child__office__name')

    def filter_queryset(self, queryset):
        if self._validate_form():
            query, finished_query = self._base_filter_queryset()

            if query or finished_query:
                query.add(Q(finished_query), Q.AND)
                queryset = queryset.filter(query)
            else:
                queryset = Task.objects.none()
        else:
            queryset = Task.objects.none()
        return queryset

    def get_os_grouped_by_office(self):
        offices = []
        offices_map = {}
        tasks = self.get_queryset()
        total = 0
        total_to_receive = 0
        amount_total = 0
        for task in tasks:
            correspondent = self._get_related_office(task)
            if correspondent not in offices_map:
                offices_map[correspondent] = {}
            client = self._get_related_client(task)
            if client not in offices_map[correspondent]:
                offices_map[correspondent][client] = []
            offices_map[correspondent][client].append(task)

        offices_map_total = {}
        for office, clients in offices_map.items():
            office_total = 0
            office_total_to_receive = 0
            office_amount_total = 0
            for client, tasks in clients.items():
                client_total = sum(map(lambda x: x.amount_to_receive, tasks))
                client_total_to_receive = sum(map(lambda x: x.amount_to_receive, tasks))
                client_amount_total = sum(map(lambda x: x.amount, tasks))
                office_total = office_total + client_total
                office_amount_total += client_amount_total
                office_total_to_receive += client_total_to_receive
                offices.append({
                    'office_name': office.name,
                    'client_name': client.name,
                    'client_refunds': client.refunds_correspondent_service,
                    'tasks': tasks,
                    "client_total": client_total,
                    "client_total_to_receive": client_total_to_receive,
                    "office_total": 0,
                })
            offices_map_total[office.name] = {'total': office_total, 'total_to_receive': office_total_to_receive, 'amount_total': office_amount_total}
            total = total + office_total
            total_to_receive += office_total_to_receive
            amount_total = office_amount_total

        for item in offices:
            item['office_total'] = offices_map_total[item['office_name']]

        return offices, total, total_to_receive, amount_total

    def get_os_grouped_by_client(self):
        clients = []
        clients_map = {}
        tasks = self.get_queryset()
        total = 0
        total_to_receive = 0
        for task in tasks:
            client = self._get_related_client(task)
            if client not in clients_map:
                clients_map[client] = {}
            correspondent = self._get_related_office(task)
            if correspondent not in clients_map[client]:
                clients_map[client][correspondent] = []
            clients_map[client][correspondent].append(task)

        clients_map_total = {}
        for client, offices in clients_map.items():
            client_total = 0
            client_total_to_receive = 0
            for office, tasks in offices.items():
                office_total = sum(map(lambda x: x.amount_to_receive, tasks))
                office_total_to_receive = sum(map(lambda x: x.amount_to_receive, tasks))
                client_total = client_total + office_total
                client_total_to_receive += office_total_to_receive
                # necessário manter a mesma estrutura do get_os_grouped_by_office para não mexer no template.
                clients.append({
                    'office_name': client.name,
                    'client_name': office.name,
                    'tasks': tasks,
                    "client_total": office_total,
                    "client_total_to_receive": office_total_to_receive,
                    "office_total": 0,
                })
            clients_map_total[client.name] = {'total': client_total, 'total_to_receive': client_total_to_receive}
            total = total + client_total
            total_to_receive += client_total_to_receive

        for item in clients:
            item['office_total'] = clients_map_total[item['office_name']]

        return clients, total, total_to_receive

    def _get_related_client(self, task):
        return task.client

    def _validate_form(self):
        if not self.task_filter.form.is_valid():
            messages.add_message(self.request, messages.ERROR,
                                 'Formulário inválido.')
            return False
        return True

    def _base_filter_queryset(self):
        data = self.task_filter.form.cleaned_data
        query = Q()
        finished_query = Q()

        if data['status']:
            key = "{}__isnull".format(self.datetime_field)
            query.add(Q(**{key: data['status'] != 'true'}), Q.AND)

        if data['client']:
            query.add(
                Q(movement__law_suit__folder__person_customer__legal_name__unaccent__icontains
                  =data['client']), Q.AND)

        if data['office']:
            if isinstance(self, ToReceiveTaskReportView):
                query.add(
                    Q(parent__office__name__unaccent__icontains=data[
                        'office']), Q.AND)
            else:
                query.add(
                    Q(office__name__unaccent__icontains=data['office']),
                    Q.AND)

        if data['finished_in']:
            if data['finished_in'].start:
                finished_query.add(
                    Q(finished_date__gte=data['finished_in'].start.replace(
                        hour=0, minute=0)), Q.AND)
            if data['finished_in'].stop:
                finished_query.add(
                    Q(finished_date__lte=data['finished_in'].stop.replace(
                        hour=23, minute=59)), Q.AND)

        if 'refunds_correspondent_service' in data and data['refunds_correspondent_service']:
            refunds = (data['refunds_correspondent_service'] == 'True')
            query.add(
                Q(movement__law_suit__folder__person_customer__refunds_correspondent_service=refunds),
                Q.AND)
        return query, finished_query


class ToReceiveTaskReportView(TaskReportBase):
    template_name = 'task/reports/to_receive.html'
    filter_class = TaskToReceiveFilter
    datetime_field = 'receipt_date'

    def get_queryset(self):
        office = get_office_session(self.request)
        queryset = Task.objects.filter(
            office=office,
            task_status=TaskStatus.FINISHED,
            parent__isnull=False)
        queryset = self.filter_queryset(queryset)
        return queryset.order_by('parent__office__legal_name')

    def _get_related_office(self, task):
        return task.parent.office

    def filter_queryset(self, queryset):
        if self._validate_form():
            query, finished_query = self._base_filter_queryset()
            data = self.task_filter.form.cleaned_data
            parent_finished_query = Q()
            if data['parent_finished_in']:
                if data['parent_finished_in'].start:
                    parent_finished_query.add(
                        Q(parent__finished_date__gte=data['parent_finished_in'].start.replace(
                            hour=0, minute=0)), Q.AND)
                if data['parent_finished_in'].stop:
                    parent_finished_query.add(
                        Q(parent__finished_date__lte=data['parent_finished_in'].stop.replace(
                            hour=23, minute=59)), Q.AND)

            if query or finished_query or parent_finished_query:
                query.add(Q(finished_query), Q.AND).add(Q(parent_finished_query), Q.AND)
                queryset = queryset.filter(query).annotate(fee=F('amount') - F('amount_to_receive'))
            else:
                queryset = Task.objects.none()
        else:
            queryset = Task.objects.none()
        return queryset

    def post(self, request):
        office = get_office_session(self.request)
        tasks_payload = request.POST.get('tasks')
        if not tasks_payload:
            return JsonResponse({"error": "tasks is required"}, status=400)

        # Todo: Ajustar signals e dar um unico update  
        for task_id in json.loads(tasks_payload):
            try:
                pre_save.disconnect(signals.change_status, sender=Task)
                pre_save.disconnect(signals.pre_save_task, sender=Task)
                post_save.disconnect(signals.post_save_task, sender=Task)
                task = Task.objects.get(id=task_id, office=office)
                setattr(task, self.datetime_field, timezone.now())
                task.save_without_historical_record()
            except:
                pass
            finally:
                pre_save.connect(signals.change_status, sender=Task)
                pre_save.connect(signals.pre_save_task, sender=Task)
                post_save.connect(signals.post_save_task, sender=Task)

        messages.add_message(self.request, messages.SUCCESS,
                             "OS's marcadas como recebidas com sucesso.")
        return JsonResponse({"status": "ok"})


class ToPayTaskReportView(View):
    filter_class = TaskToPayFilter
    datetime_field = 'billing_date'

    def get(self, request, *args, **kwargs):
        self.task_filter = self.filter_class(
            data=self.request.GET, request=self.request)
        tasks = self.get_queryset()
        data = json.dumps([])
        if request.GET.get("group_by_tasks") == 'E':
            order = 'office_name, client_name, finished_date'
        else:
            order = 'client_name, office_name, finished_date'
        if tasks:
            data = json.dumps(get_tasks_to_pay(task_ids=list(tasks.values_list('pk', flat=True)), order=order),
                              cls=DjangoJSONEncoder)
        return JsonResponse(data, safe=False)

    def filter_queryset(self, queryset):
        if not self.task_filter.form.is_valid():
            messages.add_message(self.request, messages.ERROR,
                                 'Formulário inválido.')
        else:
            data = self.task_filter.form.cleaned_data
            query = Q()
            finished_query = Q()

            if data['status']:
                key = "parent__{}__isnull".format(self.datetime_field)
                query.add(Q(**{key: int(data['status'])}), Q.AND)

            if data['client']:
                query.add(
                    Q(movement__law_suit__folder__person_customer__legal_name__unaccent__icontains
                      =data['client']), Q.AND)

            if data['office']:
                if isinstance(self, ToReceiveTaskReportView):
                    query.add(
                        Q(parent__office__legal_name__unaccent__icontains=data[
                            'office']), Q.AND)
                else:
                    query.add(
                        Q(office__legal_name__unaccent__icontains=data['office']),
                        Q.AND)

            if data['finished_in']:
                if data['finished_in'].start:
                    finished_query.add(
                        Q(parent__finished_date__gte=data['finished_in'].start.replace(
                            hour=0, minute=0)), Q.AND)
                if data['finished_in'].stop:
                    finished_query.add(
                        Q(parent__finished_date__lte=data['finished_in'].stop.replace(
                            hour=23, minute=59)), Q.AND)

            if 'refunds_correspondent_service' in data and data['refunds_correspondent_service']:
                refunds = (data['refunds_correspondent_service'] == 'True')
                query.add(
                    Q(movement__law_suit__folder__person_customer__refunds_correspondent_service=refunds),
                    Q.AND)

            if query or finished_query:
                query.add(Q(finished_query), Q.AND)
                queryset = queryset.filter(query)
            else:
                queryset = Task.objects.none()

        return queryset

    def get_queryset(self):
        office = get_office_session(self.request)
        queryset = Task.objects \
            .select_related('office') \
            .select_related('type_task') \
            .select_related('movement__type_movement') \
            .select_related('movement__folder') \
            .select_related('movement__folder__person_customer') \
            .select_related('movement__law_suit__court_district') \
            .select_related('movement__law_suit__court_district__state') \
            .select_related('parent__type_task') \
            .filter(parent__office=office, parent__task_status=TaskStatus.FINISHED, parent__isnull=False)
        queryset = self.filter_queryset(queryset)
        return queryset

    def post(self, request):
        office = get_office_session(self.request)
        tasks_payload = request.POST.getlist('tasks[]')
        if not tasks_payload:
            return JsonResponse({"error": "tasks is required"}, status=400)

        for task_id in tasks_payload:
            # Todo: Ajustar signals e dar um unico update
            try:
                pre_save.disconnect(signals.change_status, sender=Task)
                pre_save.disconnect(signals.pre_save_task, sender=Task)
                post_save.disconnect(signals.post_save_task, sender=Task)
                task = Task.objects.get(id=task_id, office=office)
                setattr(task, self.datetime_field, timezone.now())
                task.save_without_historical_record()
            except:
                pass
            finally:
                pre_save.connect(signals.change_status, sender=Task)
                pre_save.connect(signals.pre_save_task, sender=Task)
                post_save.connect(signals.post_save_task, sender=Task)

        messages.add_message(self.request, messages.SUCCESS,
                             "OS's faturadas com sucesso.")
        return JsonResponse({"status": "ok"})


class ToPayTaskReportXlsxView(ToPayTaskReportView):
    def get(self, request, *args, **kwargs):
        self.task_filter = self.filter_class(
            data=self.request.GET, request=self.request)
        tasks = self.get_queryset()
        data = []
        if request.GET.get("group_by_tasks") == 'E':
            order = 'office_name, client_name, finished_date'
        else:
            order = 'client_name, office_name, finished_date'
        if tasks:
            data = get_tasks_to_pay(task_ids=list(tasks.values_list('pk', flat=True)), order=order)
        report = TaskToPayXlsx(data)
        output = report.get_report()
        filename = 'os_pagar.xlsx'
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=%s' % filename
        return response


class ToPayTaskReportTemplateView(TemplateView):
    template_name = 'task/reports/to_pay.html'
    filter_class = TaskToPayFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.task_filter = self.filter_class(
            data=self.request.GET, request=self.request)
        context['filter'] = self.task_filter
        return context


class DashboardView(CustomLoginRequiredView, TemplateView):
    template_name = 'task/task_dashboard.html'
    table_pagination = {'per_page': 5}
    ret_status_dict = {}

    def get(self, request, *args, **kwargs):
        office_session = get_office_session(request)
        checker = ObjectPermissionChecker(request.user)
        company_representative = checker.has_perm('can_see_tasks_company_representative', office_session)
        view_all_tasks = checker.has_perm('view_all_tasks', office_session)
        if company_representative and not view_all_tasks:
            return HttpResponseRedirect(reverse_lazy('task_to_company_representative'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        office_session = get_office_session(self.request)
        context = super().get_context_data(**kwargs)
        custom_settings = CustomSettings.objects.filter(
            office=office_session).first()
        context['cards_to_show'] = []
        if custom_settings and custom_settings.task_status_show:
            context['cards_to_show'] = list(
                custom_settings.task_status_show.values_list(
                    'status_to_show', flat=True))
        person = Person.objects.get(auth_user=self.request.user)
        checker = ObjectPermissionChecker(person.auth_user)
        ret_status_dict, office_session = self.get_data(person, checker)
        context['ret_status_dict'] = ret_status_dict
        context.update(self.get_flow_context(ret_status_dict, context['cards_to_show']))
        context.update(self.get_deadlines_context(person, checker))

        if not self.request.user.get_all_permissions():
            context['messages'] = [{
                'tags': 'error',
                'message': NO_PERMISSIONS_DEFINED
            }]
        return context

    # Etapas do fluxo principal da OS, na ordem em que aparecem na faixa do dashboard.
    FLOW_STATUSES = (TaskStatus.REQUESTED, TaskStatus.ACCEPTED_SERVICE, TaskStatus.OPEN,
                     TaskStatus.ACCEPTED, TaskStatus.DONE, TaskStatus.FINISHED)
    FLOW_HINTS = {
        TaskStatus.REQUESTED: 'aguardando delegação',
        TaskStatus.ACCEPTED_SERVICE: 'aceita pelo service',
        TaskStatus.OPEN: 'delegada, sem resposta',
        TaskStatus.ACCEPTED: 'aceita pelo correspondente',
        TaskStatus.DONE: 'aguardando conferência',
        TaskStatus.FINISHED: 'conferida e paga',
    }
    SIDE_CHIP_CLASS = {
        TaskStatus.ERROR: 'q-chip-bad', TaskStatus.REFUSED_SERVICE: 'q-chip-bad', TaskStatus.REFUSED: 'q-chip-bad',
        TaskStatus.RETURN: 'q-chip-warn', TaskStatus.BLOCKEDPAYMENT: 'q-chip-muted',
    }

    def get_flow_context(self, ret_status_dict, cards_to_show):
        """Separa os status em etapas do fluxo (faixa) e estados fora do fluxo (chips)."""
        by_name = {}
        for key, item in ret_status_dict.items():
            if isinstance(item, dict) and item.get('name'):
                by_name[item['name']] = item
        flow, side = [], []
        for status in self.FLOW_STATUSES:
            item = by_name.get(status.name)
            if not item or (cards_to_show and status.value not in cards_to_show):
                continue
            flow.append(dict(item, hint=self.FLOW_HINTS[status],
                             css='q-done' if status is TaskStatus.FINISHED else 'q-s{}'.format(min(len(flow), 3)),
                             dom_id=item['status'].replace(' ', '').lower()))
        for status, css in self.SIDE_CHIP_CLASS.items():
            item = by_name.get(status.name)
            if not item or (cards_to_show and status.value not in cards_to_show):
                continue
            side.append(dict(item, css=css, dom_id=item['status'].replace(' ', '').lower()))
        return {'flow_statuses': flow, 'side_statuses': side}

    def get_deadlines_context(self, person, checker):
        """OS ativas com prazo fatal nos próximos 7 dias, para a tabela de prazos."""
        office_session = get_office_session(self.request)
        data, _ = get_dashboard_tasks(self.request, office_session, checker, person)
        now = timezone.now()
        active = [TaskStatus.REQUESTED.value, TaskStatus.ACCEPTED_SERVICE.value, TaskStatus.OPEN.value,
                  TaskStatus.ACCEPTED.value, TaskStatus.RETURN.value]
        queryset = data.filter(task_status__in=active, final_deadline_date__lte=now + timezone.timedelta(days=7)) \
            .select_related('type_task', 'person_executed_by', 'movement__law_suit__court_district') \
            .order_by('final_deadline_date')
        chip_for = {
            TaskStatus.REQUESTED.value: 'q-chip-muted', TaskStatus.ACCEPTED_SERVICE.value: 'q-chip-info',
            TaskStatus.OPEN.value: 'q-chip-bad', TaskStatus.ACCEPTED.value: 'q-chip-warn', TaskStatus.RETURN.value: 'q-chip-warn',
        }
        deadlines = []
        for task in queryset[:8]:
            deadline = timezone.localtime(task.final_deadline_date) if task.final_deadline_date else None
            child = task.get_latest_child_not_refused
            executed_by = task.person_executed_by or (child.office if child else None)
            if deadline is None:
                urgency = ''
            elif deadline < now:
                urgency = 'q-due-hot'
            elif (deadline - now).total_seconds() < 48 * 3600:
                urgency = 'q-due-hot'
            elif (deadline - now).total_seconds() < 4 * 86400:
                urgency = 'q-due-soon'
            else:
                urgency = ''
            deadlines.append({
                'pk': task.pk, 'task_number': task.task_number, 'type_task': task.type_task,
                'executed_by': executed_by, 'court_district': task.court_district,
                'deadline': deadline, 'overdue': bool(deadline and deadline < now), 'urgency': urgency,
                'status': task.task_status, 'chip': chip_for.get(task.task_status, 'q-chip-muted'),
            })
        return {'deadlines': deadlines, 'deadlines_total': queryset.count(), 'today': timezone.localtime(now)}

    def get_data(self, person, checker):
        office_session = get_office_session(self.request)
        data, exclude_status = get_dashboard_tasks(
            self.request, office_session, checker, person)
        ret_status_dict = self.get_ret_status_dict(data, exclude_status)

        return ret_status_dict, office_session

    @staticmethod
    def get_ret_status_dict(data, exclude_status):
        status_totals = data.values('task_status').annotate(
            total=Count('task_status')).order_by('task_status')
        total = 0
        status_dict = {}
        for task_status in TaskStatus:
            if task_status.value not in exclude_status:
                status = status_totals.filter(task_status=task_status).first()
                task_status_value = task_status.value
                task_status_total = status['total'] if status else 0
                status_dict[task_status.get_status_order] = {
                    'status': task_status_value,
                    'total': task_status_total,
                    'name': task_status.name,
                    'title': task_status_value,
                    'task_icon': task_status.get_icon
                }
                total += task_status_total

        ret_status_dict = {}
        for status_key in sorted(status_dict.keys()):
            ret_status_dict[str(status_key)] = status_dict[status_key]
        ret_status_dict['total'] = total
        ret_status_dict['total_requested_month'] = data.filter(
            requested_date__year=datetime.today().year,
            requested_date__month=datetime.today().month).count()

        return ret_status_dict


class TaskDetailView(SuccessMessageMixin, CustomLoginRequiredView, UpdateView):
    model = Task
    form_class = TaskDetailForm
    success_url = reverse_lazy('dashboard')
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name = 'task/task_detail.html'

    def form_valid(self, form):
        if TaskStatus[self.request.POST['action']] == TaskStatus.OPEN \
                and not form.cleaned_data['servicepricetable_id']:
            form.is_valid = False
            messages.error(self.request, "Favor Selecionar um correspondente")
            return self.form_invalid(form)
        form.instance.task_status = TaskStatus[
                                        self.request.POST['action']] or TaskStatus.INVALID
        form.instance.alter_user = User.objects.get(id=self.request.user.id)
        notes = form.cleaned_data['notes'] if form.cleaned_data[
            'notes'] else None
        execution_date = (form.cleaned_data['execution_date']
                          if form.cleaned_data['execution_date'] else
                          form.initial['execution_date'])
        survey_result = (form.cleaned_data['survey_result']
                         if form.cleaned_data['survey_result'] else
                         form.initial['survey_result'])

        if survey_result and not form.initial['survey_result']:
            if isinstance(survey_result, str):
                survey_result = json.loads(survey_result)
            survey = TaskSurveyAnswer()
            survey.survey = form.instance.type_task.survey
            survey.create_user = self.request.user
            survey.survey_result = survey_result
            survey.save()
            survey.tasks.add(form.instance)
            task_to_check_parent = form.instance
            while has_task_parent(task_to_check_parent):
                survey.tasks.add(task_to_check_parent.parent)
                task_to_check_parent = task_to_check_parent.parent
        send_notes_execution_date.send(
            sender=self.__class__,
            notes=notes,
            instance=form.instance,
            execution_date=execution_date,
            survey_result=survey_result,
            **{'external_task': False})
        form.instance.__server = get_domain(self.request)
        if form.instance.task_status == TaskStatus.ACCEPTED_SERVICE:
            form.instance.person_distributed_by = self.request.user.person
        if form.instance.task_status == TaskStatus.REFUSED_SERVICE:
            form.instance.person_distributed_by = self.request.user.person
        if form.instance.task_status == TaskStatus.REFUSED and not form.instance.person_distributed_by:
            form.instance.person_distributed_by = self.request.user.person
        if form.instance.task_status == TaskStatus.OPEN:
            form = DelegateTask(self.request, form).delegate()

        feedback_rating = form.cleaned_data.get('feedback_rating')
        feedback_comment = form.cleaned_data.get('feedback_comment')
        if feedback_rating and not form.instance.taskfeedback_set.exists():
            TaskFeedback.objects.create(
                task=form.instance,
                rating=feedback_rating,
                comment=feedback_comment,
                create_user=form.instance.alter_user)

        super(TaskDetailView, self).form_valid(form)
        return HttpResponseRedirect(self.success_url + str(form.instance.id))

    def get_context_data(self, **kwargs):
        context = super(TaskDetailView, self).get_context_data(**kwargs)
        # pega o office da sessao
        office_session = get_office_session(self.request)

        # pega as configuracoes personalizadas do escritorio
        context['custom_settings'] = office_session.customsettings
        manager = ListTemplateValues(self.object.office)
        context['i_work_alone']: office_session.i_work_alone

        context['ecms'] = Ecm.objects.filter(task_id=self.object.id)
        context['task_history'] = \
            TaskHistory.objects.filter(
                task_id=self.object.id).order_by('-create_date')

        # monta lista de surveys a serem respondidos pela OS
        pending_surveys = self.object.have_pending_surveys
        pending_list = []
        if pending_surveys.get('survey_company_representative'):
            pending_list.append('Preposto')
        if pending_surveys.get('survey_executed_by'):
            pending_list.append('Correspondente')
        context['pending_surveys'] = {'status': True if pending_list else False,
                                      'pending_list': pending_list}
        # Pega o ultimo parent, se nao tiver parent retorna o proprio objeto
        last_parent = get_last_parent(self.object)
        context['survey_data'] = (last_parent.type_task.survey.data
                                  if last_parent.type_task.survey else None)

        # Pega tabela de correspondentes
        get_correspondents_table = CorrespondentsTable(self.object,
                                                       office_session)
        context['correspondents_table'] = get_correspondents_table.get_correspondents_table()

        # Verifica se todos os Surveys foram preenchidos
        checker = ObjectPermissionChecker(self.request.user)
        if checker.has_perm('can_see_tasks_company_representative', office_session):
            if not TaskSurveyAnswer.objects.filter(tasks=self.object, create_user=self.request.user):
                if (last_parent.type_task.survey_company_representative):
                    context['not_answer_questionnarie'] = True
                    if last_parent.type_task.survey_company_representative:
                        context['survey_company_representative'] = last_parent.type_task.survey_company_representative.data
                    else:
                        context['survey_company_representative'] = ''
        context['show_company_representative_in_tab'] = self.show_company_representative_in_tab(checker, office_session)
        context['show_person_executed_by_in_tab'] = self.show_person_executed_by_in_tab(checker, office_session)        
        context['ENV'] = os.environ.get('ENV')
        return context

    def show_company_representative_in_tab(self, checker, office_session):
        """
        Caso a pessoa logada seja o correspondente da ordem de servico
        Nao mostra os dados do preposto na aba Participantes
        """
        show_in_tab = True
        is_person_executed_by = checker.has_perm('view_delegated_tasks', office_session)
        if is_person_executed_by:
            if self.object.person_executed_by == self.request.user.person:
                show_in_tab = False
        return show_in_tab

    def show_person_executed_by_in_tab(self, checker, office_session):
        """
        Caso a pessoa logada seja o preposto da ordem de servico
        Nao mostra os dados do correspondente na aba Participantes
        """
        show_in_tab = True
        is_company_representative = checker.has_perm('can_see_tasks_company_representative', office_session)
        if is_company_representative:
            if self.object.person_company_representative == self.request.user.person:
                show_in_tab = False
        return show_in_tab

    def dispatch(self, request, *args, **kwargs):
        res = super().dispatch(request, *args, **kwargs)
        office_session = get_office_session(request)
        if office_session != Task.objects.filter(
                pk=kwargs.get('pk')).first().office:
            messages.error(
                self.request,
                "A OS que está tentando acessar, não pertence ao escritório selecionado."
                " Favor selecionar o escritório correto")
            if request.session.get('custom_session_user'):
                del request.session['custom_session_user']
                request.session.modified = True
            return HttpResponseRedirect(reverse('office_instance'))
        return res


class EcmCreateView(CustomLoginRequiredView, CreateView):
    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist('path')
        task = kwargs['pk']
        data = {'success': False, 'message': exception_create()}
        for file in files:
            file_name = file._name.replace(' ', '_')
            obj_task = Task.objects.get(id=task)
            ecm = Ecm(
                path=file,
                task=obj_task,
                exhibition_name=file_name,
                create_user_id=str(request.user.id),
                create_date=timezone.now())

            try:
                ecm.save()
                data = {'success': True,
                        'id': ecm.id,
                        'name': str(file),
                        'user': str(self.request.user),
                        'username': str(self.request.user.first_name + ' ' +
                                        self.request.user.last_name),
                        'filename': str(ecm.exhibition_name),
                        'task_id': str(task),
                        'message': success_sent()
                        }
            except OperationalError:
                data = {
                    'success': False,
                    'message': operational_error_create()
                }
            except IOError:
                data = {'is_deleted': False, 'message': ioerror_create()}
            except Exception:
                data = {'success': False, 'message': exception_create()}

        return JsonResponse(data)


def delete_ecm(request, pk):
    try:
        ecm = Ecm.objects.get(id=pk)
        task_id = ecm.task.pk
        ecm.delete()
        num_ged = Ecm.objects.filter(task_id=task_id).count()
        data = {
            'is_deleted': True,
            'num_ged': num_ged,
            'message': success_delete()
        }
    except IntegrityError:
        data = {
            'is_deleted': False,
            'num_ged': 1,
            'message': integrity_error_delete()
        }
    except Ecm.DoesNotExist:
        data = {
            'is_deleted': False,
            'num_ged': 1,
            'message': "Anexo já foi excluído ou não existe.",
        }
    except ValidationError as error:
        data = {
            'is_deleted': False,
            'num_ged': 1,
            'message': error.args[0],
        }
    except Exception as ex:
        data = {
            'is_deleted': False,
            'num_ged': 1,
            'message': DELETE_EXCEPTION_MESSAGE + '\n' + ex.args[0],
        }

    return JsonResponse(data)


@login_required
def delete_internal_ecm(request, pk):
    return delete_ecm(request, pk)


def delete_external_ecm(request, task_hash, pk):
    # Para usuario que apenas acessam a task por hash, sem autenticar
    ecm = Ecm.objects.get(pk=pk)
    if ecm.task.task_hash.hex == task_hash:
        return delete_ecm(request, pk)
    return JsonResponse({'message': 'Hash inválido'})


class DashboardSearchView(CustomLoginRequiredView, SingleTableView):
    model = TaskFilterViewModel
    filter_class = TaskFilter
    template_name = 'task/task_filter.html'
    context_object_name = 'task_filter'
    context_filter_name = 'filter'
    ordering = ['-final_deadline_date']
    table_class = DashboardStatusTable

    def query_builder(self):
        query_set = self.model.objects.none()
        person_dynamic_query = Q()
        person = Person.objects.get(auth_user=self.request.user)
        office_session = get_office_session(self.request)
        checker = ObjectPermissionChecker(person.auth_user)

        filters = self.request.GET
        task_filter = self.filter_class(data=filters, request=self.request)
        task_form = task_filter.form

        if task_form.is_valid():
            data = task_form.cleaned_data

            if data['custom_filter']:
                q = pickle.loads(data['custom_filter'].query)
                query_set = TaskFilterViewModel.objects.filter(q, office=get_office_session(self.request))
            else:
                task_dynamic_query = Q()
                client_query = Q()
                requested_dynamic_query = Q()
                accepted_service_dynamic_query = Q()
                refused_service_query = Q()
                open_dynamic_query = Q()
                accepted_dynamic_query = Q()
                refused_dynamic_query = Q()
                return_dynamic_query = Q()
                done_dynamic_query = Q()
                blocked_payment_dynamic_query = Q()
                finished_dynamic_query = Q()
                team_dynamic_query = Q()

                if not checker.has_perm('can_distribute_tasks',
                                        office_session):
                    if checker.has_perm('view_delegated_tasks',
                                        office_session):
                        person_dynamic_query.add(
                            Q(person_executed_by=person.id), Q.OR)
                    if checker.has_perm('view_requested_tasks',
                                        office_session):
                        person_dynamic_query.add(
                            Q(person_asked_by=person.id), Q.OR)
                    if checker.has_perm('can_see_tasks_company_representative', office_session):
                        person_dynamic_query.add(Q(person_company_representative=person.id), Q.OR)
                if data['office_executed_by']:
                    task_dynamic_query.add(
                        Q(
                            Q(child__office_id=data['office_executed_by']),
                            ~Q(child__task_status__in=[TaskStatus.REFUSED_SERVICE.__str__(),
                                                       TaskStatus.REFUSED.__str__()])
                        ), Q.AND)
                if data['state']:
                    task_dynamic_query.add(
                        Q(state__in=data['state']), Q.AND)
                if data['court_district']:
                    if self.request.GET.get('court_district_option') == 'EXCEPT':
                        task_dynamic_query.add(
                            ~Q(court_district__in=data['court_district']), Q.AND)
                    else:
                        task_dynamic_query.add(
                            Q(court_district__in=data['court_district']), Q.AND)
                if data['court_district_complement']:
                    task_dynamic_query.add(
                        Q(court_district_complement=data['court_district_complement']), Q.AND)
                if data.get('task_status'):
                    status = [
                        getattr(TaskStatus, s) for s in data['task_status']
                    ]
                    task_dynamic_query.add(Q(task_status__in=status), Q.AND)
                if data['type_task']:
                    task_dynamic_query.add(Q(type_task__in=data['type_task']), Q.AND)
                if data['type_task_main']:
                    task_dynamic_query.add(Q(type_task__type_task_main__in=data['type_task_main']), Q.AND)
                if data['court']:
                    task_dynamic_query.add(
                        Q(movement__law_suit__organ=data['court']), Q.AND)
                if data['cost_center']:
                    task_dynamic_query.add(
                        Q(movement__law_suit__folder__cost_center=data[
                            'cost_center']), Q.AND)
                if data['folder_number']:
                    task_dynamic_query.add(
                        Q(movement__law_suit__folder__folder_number=data[
                            'folder_number']), Q.AND)
                if data['folder_legacy_code']:
                    task_dynamic_query.add(
                        Q(movement__law_suit__folder__legacy_code=data[
                            'folder_legacy_code']), Q.AND)
                if data['client']:
                    if self.request.GET.get('client_option') == 'EXCEPT':
                        task_dynamic_query.add(
                            ~Q(movement__law_suit__folder__person_customer__id__in=data[
                                'client']), Q.AND)
                    else:
                        task_dynamic_query.add(
                            Q(movement__law_suit__folder__person_customer__id__in=data[
                                'client']), Q.AND)
                if data['law_suit_number']:
                    task_dynamic_query.add(
                        Q(law_suit_number__unaccent__icontains=data[
                            'law_suit_number']), Q.AND)
                if data['task_number']:
                    task_dynamic_query.add(
                        Q(task_number=data['task_number']), Q.AND)
                if data['task_origin_code']:
                    task_dynamic_query.add(
                        Q(
                            Q(legacy_code=data['task_origin_code'])
                            | Q(parent_task_number=data['task_origin_code'])),
                        Q.AND)
                if data['person_executed_by']:
                    task_dynamic_query.add(
                        Q(person_executed_by=data['person_executed_by']),
                        Q.AND)
                if data['person_asked_by']:
                    task_dynamic_query.add(
                        Q(person_asked_by=data['person_asked_by']), Q.AND)
                if data['origin_office_asked_by']:
                    task_dynamic_query.add(
                        Q(office=office_session, parent__office_id=data['origin_office_asked_by']), Q.AND)
                if data['person_distributed_by']:
                    task_dynamic_query.add(
                        Q(person_distributed_by=data['person_distributed_by']),
                        Q.AND)
                if data['team']:
                    rule_view = RuleViewTask(self.request)
                    team_dynamic_query.add(
                        rule_view.get_query_team_tasks([data['team']]), Q.AND)
                if data['requested_in']:
                    if data['requested_in'].start:
                        requested_dynamic_query.add(
                            Q(requested_date__gte=data['requested_in'].start.
                              replace(hour=0, minute=0)), Q.AND)
                    if data['requested_in'].stop:
                        requested_dynamic_query.add(
                            Q(requested_date__lte=data['requested_in'].stop.
                              replace(hour=23, minute=59)), Q.AND)
                if data['accepted_service_in']:
                    if data['accepted_service_in'].start:
                        accepted_service_dynamic_query.add(
                            Q(acceptance_service_date__gte=data[
                                'accepted_service_in'].start.replace(
                                hour=0, minute=0)), Q.AND)
                    if data['accepted_service_in'].stop:
                        accepted_service_dynamic_query.add(
                            Q(acceptance_service_date__lte=data[
                                'accepted_service_in'].stop.replace(
                                hour=23, minute=59)), Q.AND)
                if data['refused_service_in']:
                    if data['refused_service_in'].start:
                        refused_service_query.add(
                            Q(refused_service_date__gte=data[
                                'refused_service_in'].start.replace(
                                hour=0, minute=0)), Q.AND)
                    if data['refused_service_in'].stop:
                        refused_service_query.add(
                            Q(refused_service_date__lte=data[
                                'refused_service_in'].stop.replace(
                                hour=23, minute=59)), Q.AND)
                if data['open_in']:
                    if data['open_in'].start:
                        open_dynamic_query.add(
                            Q(delegation_date__gte=data['open_in'].start.
                              replace(hour=0, minute=0)), Q.AND)
                    if data['open_in'].stop:
                        open_dynamic_query.add(
                            Q(delegation_date__lte=data['open_in'].stop.
                              replace(hour=23, minute=59)), Q.AND)
                if data['accepted_in']:
                    if data['accepted_in'].start:
                        accepted_dynamic_query.add(
                            Q(acceptance_date__gte=data['accepted_in'].start.
                              replace(hour=0, minute=0)), Q.AND)
                    if data['accepted_in'].stop:
                        accepted_dynamic_query.add(
                            Q(acceptance_date__lte=data['accepted_in'].stop.
                              replace(hour=23, minute=59)), Q.AND)
                if data['refused_in']:
                    if data['refused_in'].start:
                        refused_dynamic_query.add(
                            Q(refused_date__gte=data['refused_in'].start.
                              replace(hour=0, minute=0)), Q.AND)
                    if data['refused_in'].stop:
                        refused_dynamic_query.add(
                            Q(refused_date__lte=data['refused_in'].stop.
                              replace(hour=23, minute=59)), Q.AND)
                if data['return_in']:
                    if data['return_in'].start:
                        return_dynamic_query.add(
                            Q(return_date__gte=data['return_in'].start.replace(
                                hour=0, minute=0)), Q.AND)
                    if data['return_in'].stop:
                        return_dynamic_query.add(
                            Q(return_date__lte=data['return_in'].stop.replace(
                                hour=23, minute=59)), Q.AND)
                if data['done_in']:
                    if data['done_in'].start:
                        done_dynamic_query.add(
                            Q(execution_date__gte=data['done_in'].start.
                              replace(hour=0, minute=0)), Q.AND)
                    if data['done_in'].stop:
                        done_dynamic_query.add(
                            Q(execution_date__lte=data['done_in'].stop.replace(
                                hour=23, minute=59)), Q.AND)
                if data['blocked_payment_in']:
                    if data['blocked_payment_in'].start:
                        blocked_payment_dynamic_query.add(
                            Q(blocked_payment_date__gte=data[
                                'blocked_payment_in'].start.replace(
                                hour=0, minute=0)), Q.AND)
                    if data['blocked_payment_in'].stop:
                        blocked_payment_dynamic_query.add(
                            Q(blocked_payment_date__lte=data[
                                'blocked_payment_in'].stop.replace(
                                hour=23, minute=59)), Q.AND)
                if data['finished_in']:
                    if data['finished_in'].start:
                        finished_dynamic_query.add(
                            Q(finished_date__gte=data['finished_in'].start.
                              replace(hour=0, minute=0)), Q.AND)
                    if data['finished_in'].stop:
                        finished_dynamic_query.add(
                            Q(finished_date__lte=data['finished_in'].stop.
                              replace(hour=23, minute=59)), Q.AND)
                if data['final_deadline_date_in']:
                    if data['final_deadline_date_in'].start:
                        finished_dynamic_query.add(
                            Q(final_deadline_date__gte=data[
                                'final_deadline_date_in'].start.replace(
                                hour=0, minute=0)), Q.AND)
                    if data['final_deadline_date_in'].stop:
                        finished_dynamic_query.add(
                            Q(final_deadline_date__lte=data[
                                'final_deadline_date_in'].stop.replace(
                                hour=23, minute=59)), Q.AND)

                person_dynamic_query.add(Q(client_query), Q.AND) \
                    .add(Q(task_dynamic_query), Q.AND) \
                    .add(Q(team_dynamic_query), Q.AND) \
                    .add(Q(requested_dynamic_query), Q.AND) \
                    .add(Q(accepted_service_dynamic_query), Q.AND) \
                    .add(Q(refused_service_query), Q.AND) \
                    .add(Q(open_dynamic_query), Q.AND) \
                    .add(Q(accepted_dynamic_query), Q.AND) \
                    .add(Q(refused_dynamic_query), Q.AND) \
                    .add(Q(return_dynamic_query), Q.AND) \
                    .add(Q(done_dynamic_query), Q.AND) \
                    .add(Q(blocked_payment_dynamic_query), Q.AND) \
                    .add(Q(finished_dynamic_query), Q.AND)

                office_id = (get_office_session(self.request).id
                             if get_office_session(self.request) else 0)
                query_set = TaskFilterViewModel.objects.filter(
                    office_id=office_id).filter(person_dynamic_query)

            try:
                if filters.get('save_filter', None) is not None:
                    filter_name = data['custom_filter_name']
                    filter_description = data['custom_filter_description']
                    q = pickle.dumps(person_dynamic_query)
                    new_filter = Filter(
                        name=filter_name,
                        query=q,
                        description=filter_description,
                        create_user=self.request.user,
                        create_date=timezone.now())
                    new_filter.save()
            except IntegrityError:
                messages.add_message(self.request, messages.ERROR,
                                     'Já existe filtro com este nome.')
        else:
            messages.add_message(self.request, messages.ERROR,
                                 'Formulário inválido.')
        return query_set, task_filter

    def get_queryset(self, **kwargs):

        task_list, task_filter = self.query_builder()
        self.filter = task_filter

        if not self.request.GET.get('export_answers'):
            task_list = task_list.distinct()

        return task_list

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context[self.context_filter_name] = self.filter
        table = self.table_class(self.object_list)
        RequestConfig(self.request, paginate={'per_page': 10}).configure(table)
        context['table'] = table
        return context

    def get(self, request, *args, **kwargs):
        checker = ObjectPermissionChecker(self.request.user)
        if (self.request.GET.get('export_answers') and checker.has_perm(
                'can_view_survey_results', get_office_session(request))):
            return self._export_answers(request)

        if self.request.GET.get('export_result'):
            return self._export_result(request)

        return super().get(request)

    def _export_result(self, request):
        from task.queries import get_filter_tasks
        self.object_list = self.get_queryset()
        tasks = list(self.object_list.values_list('id', flat=True))
        data = {}
        if tasks:
            data = get_filter_tasks(tasks)
        report = ExportFilterTask(data)
        output = report.get_report()
        filename = 'resultados_da_pesquisa.xlsx'
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=%s' % filename
        return response

    def _export_answers(self, request):
        tasks = self.get_queryset()
        task_ids = tasks.values_list('id', flat=True)
        office_list = list(set(tasks.values_list('office', flat=True)))
        answers = TaskSurveyAnswer.objects.filter(tasks__id__in=task_ids).prefetch_related(
            Prefetch('tasks', queryset=Task.objects.filter(office__in=office_list), to_attr='answers_office'))

        columns = self._get_answers_columns(answers)
        all_columns = [
                          'N° da OS',
                          'N° da OS no sistema de origem',
                          'Tipo de Serviço',
                          'Usuário',
                      ] + columns
        xlsx = XLSXWriter("respostas_dos_formularios.xlsx", all_columns)

        for answer in answers:
            self._export_answers_write_task(xlsx, answer, columns)

        xlsx.close()
        return xlsx.get_http_response()

    def _export_answers_write_task(self, xlsx, answer, columns):
        task = answer.answers_office[0]
        base_fields = [task.task_number, task.legacy_code, str(task.type_task), answer.create_user.username]
        answers = ['' for x in range(len(columns))]
        survey_result = answer.survey_result
        if isinstance(survey_result, str):
            survey_result = json.loads(answer.survey_result)
        if getattr(survey_result, 'items', None):
            for question, value in survey_result.items():
                question_index = columns.index(question)
                # Check if is a datetime value
                try:
                    if len(value) == 24:
                        time = datetime.strptime(value.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                        value = time.strftime("%d/%m/%Y %H:%M")
                except (TypeError, ValueError):
                    # Not a datetime value
                    pass
                answers[question_index] = value

        xlsx.write_row(base_fields + answers)

    def _get_answers_columns(self, answers):
        columns = []
        i = 0
        for answer in answers:
            if getattr(answer.survey_result, 'items', None):
                for question, answer in answer.survey_result.items():
                    if question not in columns:
                        columns.append(question)
        return columns


class DashboardStatusCheckView(CustomLoginRequiredView, View):
    def get(self, request, *args, **kwargs):
        checker = ObjectPermissionChecker(request.user)
        office_session = get_office_session(request)
        data, exclude_status = get_dashboard_tasks(
            request, office_session, checker, request.user.person)

        status_totals = data.values('task_status').annotate(
            total=Count('task_status')).order_by('task_status')

        ret = {'office': office_session.legal_name}
        total = 0
        for status in status_totals:
            ret[status['task_status'].replace(' ',
                                              '_').lower()] = status['total']
            total += status['total']

        ret['total'] = total
        ret['total_requested_month'] = data.filter(
            requested_date__year=datetime.today().year,
            requested_date__month=datetime.today().month).count()

        return JsonResponse(ret)


@login_required
def ajax_get_task_data_table(request):
    status = request.GET.get('status')
    data_dict = json.loads(request.GET.get('data', '{}'))
    draw = int(data_dict.get('draw', 0))
    start = int(data_dict.get('start', 0))
    length = int(data_dict.get('length', 5))
    search_dict = data_dict.get('search', {})
    columns = data_dict.get('columns', [])
    order_dict = data_dict.get('order', {})
    checker = ObjectPermissionChecker(request.user)
    dash = DashboardView()
    dash.request = request
    rule_view = RuleViewTask(request=request)
    dynamic_query = rule_view.get_dynamic_query(request.user.person, checker)
    values_list = [
        'pk', 'task_number', 'final_deadline_date', 'type_task__name',
        'movement__law_suit__law_suit_number',
        'movement__law_suit__court_district__name',
        'movement__law_suit__court_district__state__initials',
        'movement__law_suit__folder__person_customer__legal_name',
        'movement__law_suit__opposing_party', 'movement__law_suit__court_district_complement__name',
        'task_original'
    ]
    if status == 'Erro no sistema de origem':
        values_list.extend(
            ['inconsistencyetl__inconsistency', 'inconsistencyetl__solution'])
    query = Task.objects.filter(dynamic_query).filter(
        is_active=True, task_status=status,
        office=get_office_session(request)).select_related(
        'type_task', 'movement__law_suit',
        'movement__law_suit__court_district',
        'movement__law_suit__court_district__state',
        'movement__law_suit__folder__person_customer', 'movement__law_suit__court_district_complement__name',
        'parent').annotate(
        task_original=Case(
            When(
                parent_id__isnull=False,
                then=Cast('parent__task_number',
                          CharField(max_length=255))),
            default=Cast('legacy_code', CharField(max_length=255)),
            output_field=CharField(max_length=255),
        ), ).values(*values_list)

    # criando o filtro de busca a partir do valor enviado no campo de pesquisa
    search_value = search_dict.get('value', None)
    reduced_filter = None
    if search_value:
        search_dict_query = {}
        for column in columns:
            if column.get('searchable'):
                key = '{}__icontains'.format(column.get('data'))
                search_dict_query[key] = search_value
        reduced_filter = reduce(
            operator.or_,
            (Q(**d) for d in [dict([i]) for i in search_dict_query.items()]))

    # criando lista de ordered
    ordered_list = list(map(lambda i: '{}{}'.format(
        mapOrder.get(i.get('dir')), i.get('column')), order_dict))

    records_total = query.count()
    if not ordered_list:
        ordered_list = ['final_deadline_date']
    if reduced_filter:
        query = query.filter(reduced_filter).order_by(*ordered_list)
    else:
        query = query.order_by(*ordered_list)

    records_filtered = query.count()
    xdata = [x for x in query[start:start + length]]
    data = {
        "draw": draw,
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": xdata
    }
    return JsonResponse(data)


def get_ecm_url(ecm, external=False):
    if external:
        return '{path}/{task_hash}/'.format(path=ecm.path.name, task_hash=ecm.task.task_hash.hex)
    return ecm.path.name


def get_ecms(task_id, external=False):
    data_list = []
    ecms = get_task_ecms(task_id)
    for ecm in ecms:
        data_list.append({
            'task_id': ecm.task_id,
            'pk': ecm.pk,
            'url': get_ecm_url(ecm, external=external),
            'base_external_url': '/providencias' if external else '',
            'filename': ecm.filename,
            'exhibition_name': ecm.exhibition_name if ecm.exhibition_name else ecm.filename,
            'user': ecm.create_user.username,
            'data': timezone.localtime(ecm.create_date).strftime('%d/%m/%Y %H:%M'),
            'state': ecm.task.get_task_status_display(),
        })
    data = {'task_id': task_id, 'total_ecms': ecms.count(), 'ecms': data_list}
    return JsonResponse(data)


def ajax_get_ecms(request):
    task_id = request.GET.get('task_id')
    return get_ecms(task_id)


def get_external_ecms(request):
    task = Task.objects.filter(task_hash=request.GET.get('task_hash')).first()
    return get_ecms(task.pk, external=True)


class ExternalMediaFileView(View):
    def get(self, request, path, task_hash):
        if Ecm.objects.filter(task__task_hash=task_hash, path=path).exists():
            if os.path.exists(os.path.join(settings.MEDIA_ROOT, path)):
                return static_serve_view(
                    self.request, path, document_root=settings.MEDIA_ROOT)
        raise Http404('Arquivo não existe')
        raise Http404('Arquivo não existe')


class FilterListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = Filter
    table_class = FilterTable

    def get_context_data(self, **kwargs):
        """
        Sobrescreve o metodo get_context_data para retornar apenas filtros criados pelo usuário logado
        :param kwargs:
        :return: Retorna o contexto contendo a listatem
        :rtype: dict
        """
        context = super(FilterListView, self).get_context_data(**kwargs)
        checker = ObjectPermissionChecker(self.request.user)
        if not checker.has_perm('group_admin', get_office_session(
                self.request)):
            context['table'] = self.table_class(
                context['table'].data.data.filter(
                    create_user=self.request.user))
        RequestConfig(
            self.request, paginate={
                'per_page': 10
            }).configure(context['table'])
        return context


class FilterUpdateView(AuditFormMixin, UpdateView):
    model = Filter
    form_class = FilterForm
    success_url = reverse_lazy('filter_list')
    success_message = UPDATE_SUCCESS_MESSAGE

    def get_context_data(self, **kwargs):
        """
        Sobrescreve o metodo get_context_data e seta a ultima url acessada no cache
        Isso e necessario para que ao salvar uma alteracao, o metodo post consiga verificar
        a pagina da paginacao onde o usuario fez a alteracao
        :param kwargs:
        :return: super
        """
        context = super().get_context_data(**kwargs)
        cache.set('filter_page', self.request.META.get('HTTP_REFERER'))
        return context

    def post(self, request, *args, **kwargs):
        """
        Sobrescreve o metodo post e verifica se existe cache da ultima url
        Isso e necessario pelo fato da necessidade de retornar pra mesma paginacao
        Que o usuario se encontrava ao fazer a alteracao
        :param request:
        :param args:
        :param kwargs:
        :return: super
        """
        if cache.get('filter_page'):
            self.success_url = cache.get('filter_page')

        return super().post(request, *args, **kwargs)


class FilterDeleteView(AuditFormMixin, MultiDeleteViewMixin):
    model = Filter
    success_url = reverse_lazy('filter_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)


class GeolocationTaskCreate(CustomLoginRequiredView, View):
    def post(self, request):
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        checkpointtype = request.POST.get('checkpointtype')
        task_id = request.POST.get('task_id')
        check_date = timezone.now()
        task = Task.objects.filter(pk=task_id).first()
        if task and latitude and longitude:
            taskgeolocation = TaskGeolocation.objects.filter(
                task=task, checkpointtype=checkpointtype, create_user=request.user).first()
            if taskgeolocation:
                taskgeolocation.latitude = Decimal(latitude)
                taskgeolocation.longitude = Decimal(longitude)
                taskgeolocation.date = check_date
                taskgeolocation.alter_user = request.user
                taskgeolocation.save()
            else:
                TaskGeolocation.objects.create(
                    latitude=Decimal(latitude),
                    longitude=Decimal(longitude),
                    create_user=request.user,
                    date=check_date,
                    checkpointtype=checkpointtype,
                    task=task)
            return JsonResponse({
                "ok":
                    True,
                "latitude":
                    latitude,
                "longitude":
                    longitude,
                "check_date":
                    date_format(timezone.localtime(check_date), 'DATETIME_FORMAT')
            })
        return JsonResponse({"ok": False})


class GeolocationTaskFinish(CustomLoginRequiredView, View):
    def post(self, request):
        finished_date = timezone.now()
        task_id = request.POST.get('task_id')
        task = Task.objects.filter(pk=task_id).first()
        if task:
            taskgeolocation = TaskGeolocation.objects.filter(task=task).first()
            if taskgeolocation:
                taskgeolocation.finished_date = finished_date
                taskgeolocation.alter_user = request.user
                taskgeolocation.save()
            return JsonResponse({
                "ok":
                    True,
                "finished_date":
                    date_format(
                        timezone.localtime(finished_date), 'DATETIME_FORMAT')
            })
        return JsonResponse({"ok": False})


@login_required
def ecm_batch_download(request, pk):
    # https://stackoverflow.com/questions/12881294/django-create-a-zip-of-multiple-files-and-make-it-downloadable
    # http://mypythondjango.blogspot.com/2018/01/how-to-zip-files-in-filefield-and.html
    task = Task.objects.get(pk=pk)
    try:
        buff = io.BytesIO()
        zf = ZipFile(buff, mode='a')
        zip_filename = 'Anexos_OS_{}.zip'.format(task.task_number)
        for ecm in get_task_ecms(pk):
            output = io.BytesIO(ecm.get_file_content())
            output.seek(0)
            zf.writestr(ecm.path.name, output.getvalue())
        zf.close()
        buff.seek(0)
        data = buff.read()
        resp = HttpResponse(data, content_type="application/x-zip-compressed")
        resp['Content-Disposition'] = 'attachment; filename=%s' % zip_filename
        return resp
    except Exception as e:
        messages.error(request, 'Erro ao baixar todos arquivos.' + str(e))
        return HttpResponseRedirect(ecm.task.get_absolute_url())


class TypeTaskListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = TypeTask
    table_class = TypeTaskTable
    ordering = ('id',)


class TypeTaskCreateView(AuditFormMixin, CreateView):
    model = TypeTask
    form_class = TypeTaskForm
    success_url = reverse_lazy('typetask_list')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'typetask_list'
    permission_required = (CorePermissions.group_admin,)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class TypeTaskUpdateView(AuditFormMixin, UpdateView):
    model = TypeTask
    form_class = TypeTaskForm
    success_url = reverse_lazy('typetask_list')
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_update_form'
    object_list_url = 'typetask_list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class TypeTaskDeleteView(AuditFormMixin, MultiDeleteViewMixin):
    model = TypeTask
    success_url = reverse_lazy('typetask_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'typetask_list'


class GetTypeTaskMainCharacteristics(CustomLoginRequiredView, View):
    def get(self, request, pk):
        type_task_main = TypeTaskMain.objects.filter(pk=pk).first()
        characteristics = type_task_main.characteristics if type_task_main else None
        return JsonResponse({"characteristics": characteristics})


class ExternalTaskView(UpdateView):
    """
    Permite que o um usuario execute acoes em uma determinado 
    OS sem estar logado
    """
    model = Task
    template_name = 'task/external_task.html'
    form_class = TaskDetailForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)

    def get(self, request, status=False, task_hash=False, *args, **kwargs):
        self.object = Task.objects.filter(task_hash=task_hash).first()
        custom_settings = CustomSettings.objects.filter(
            office=self.object.office).first()
        manager = ListTemplateValues(self.object.office)
        request.user = manager.get_value_by_key(TemplateKeys.DEFAULT_USER.name)
        set_office_session(request)
        ecms = Ecm.objects.filter(task_id=self.object.id)
        task_history = self.object.history.all()
        survey_data = (self.object.type_task.survey.data
                       if self.object.type_task.survey else None)
        self.execution_date = timezone.now()
        # monta lista de surveys a serem respondidos pela OS
        pending_surveys = self.object.have_pending_surveys
        pending_list = []
        if pending_surveys.get('survey_company_representative'):
            pending_list.append('Preposto')
        if pending_surveys.get('survey_executed_by'):
            pending_list.append('Correspondente')
        return render(
            request, self.template_name, {
                'object': self.object,
                'show_person_executed_by_in_tab': True,
                'task': self.object,
                'form': TaskDetailForm(instance=self.object),
                'user': request.user,
                'ecms': ecms,
                'task_history': task_history,
                'survey_data': survey_data,
                'custom_settings': custom_settings,
                'i_work_alone': self.object.office.i_work_alone,
                'pending_surveys': {'status': True if pending_list else False,
                                    'pending_list': pending_list}
            })

    def post(self, request, task_hash, *args, **kwargs):
        task = Task.objects.filter(task_hash=task_hash).first()
        default_user = get_template_value_value(office=task.office,
                                                template_key=TemplateKeys.DEFAULT_USER.name)
        form = self.form_class(request.POST, instance=task)
        if default_user:
            form.instance.alter_user = default_user
        form.instance.task_status = TaskStatus[
                                        self.request.POST['action']] or TaskStatus.INVALID
        if form.is_valid():
            notes = form.cleaned_data['notes'] if form.cleaned_data[
                'notes'] else None
            logger.info('*send_notes_execution_date*: {}'.format(notes))
            execution_date = (form.cleaned_data['execution_date']
                              if form.cleaned_data['execution_date'] else
                              form.initial['execution_date'])
            survey_result = (form.cleaned_data['survey_result']
                             if form.cleaned_data['survey_result'] else
                             form.initial['survey_result'])
            send_notes_execution_date.send(
                sender=self.__class__,
                notes=notes,
                instance=form.instance,
                execution_date=execution_date,
                survey_result=survey_result,
                **{'external_task': True})
            form.instance.__external_task = True
            form.save()
        return HttpResponseRedirect(
            reverse(
                'external-task-detail', args=[form.instance.task_hash.hex]))


class EcmExternalCreateView(CreateView):
    def post(self, request, task_hash, *args, **kwargs):
        files = request.FILES.getlist('path')
        task = Task.objects.filter(task_hash=task_hash).first()
        default_user = get_template_value_value(office=task.office,
                                                template_key=TemplateKeys.DEFAULT_USER.name)
        request.user = default_user
        data = {'success': False, 'message': exception_create()}

        for file in files:
            file_name = file._name.replace(' ', '_')
            ecm = Ecm(
                path=file,
                task=task,
                exhibition_name=file_name,
                create_user_id=str(request.user.id),
                create_date=timezone.now())

            try:
                ecm.save()
                data = {
                    'success':
                        True,
                    'id':
                        ecm.id,
                    'task_hash':
                        ecm.task.task_hash.hex,
                    'name':
                        str(file),
                    'user':
                        str(self.request.user),
                    'username':
                        str(self.request.user.first_name + ' ' +
                            self.request.user.last_name),
                    'filename':
                        str(ecm.exhibition_name),
                    'task_id':
                        str(task.pk),
                    'message':
                        success_sent()
                }

            except OperationalError:
                data = {
                    'success': False,
                    'message': operational_error_create()
                }

            except IOError:

                data = {'is_deleted': False, 'message': ioerror_create()}

            except Exception:
                data = {'success': False, 'message': exception_create()}

        return JsonResponse(data)


class ImportTaskList(PermissionRequiredMixin, CustomLoginRequiredView,
                     TemplateView):
    permission_required = ('core.group_admin',)
    template_name = 'task/import_task_list.html'
    form_class = ImportTaskListForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_name_plural'] = 'Importação de OS'
        context['page_title'] = 'Importação de OS'
        return context

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        form = self.form_class(request.POST, request.FILES)
        status = 200
        if form.is_valid():
            file_xls = form.save(commit=False)
            file_xls.office = get_office_session(request)
            file_xls.create_user = request.user
            file_xls.start = timezone.now()
            file_xls.save()

            ret = import_xls_task_list(file_xls.pk)
            file_xls.end = timezone.now()
            file_xls.save()
            file_xls.delete()
        else:
            status = 500
            ret = {'status': 'false', 'message': form.errors}
            messages.error(request, form.errors)
            return JsonResponse(ret, status=status)
        return JsonResponse(json.loads(json.dumps(ret)), status=status)


class BatchChangeTasksView(CustomPermissionRequiredMixin, DashboardSearchView):
    filter_class = BatchChangTaskFilter
    template_name = 'task/batch-change-tasks.html'
    option = ''
    table_class = DashboardStatusTable
    permission_required = ('can_distribute_tasks', 'group_admin', )

    def get_permission_required(self):
        if self.request.resolver_match.kwargs.get('option') == 'CA':
            self.permission_required = ('can_see_tasks_from_team_members', 'group_admin', )
        return super().get_permission_required()

    def get(self, request, option, *args, **kwargs):
        self.option = option
        request.option = option
        return super().get(self, request, *args, **kwargs)

    def get_queryset(self):
        task_list, task_filter = self.query_builder()
        self.filter = task_filter
        status_to_filter = get_status_to_filter(self.option)
        filter_args = {'task_status__in': status_to_filter}
        if self.option not in ['A', 'D']:
            office_session = get_office_session(self.request)
            filter_args['office'] = office_session

        return task_list.filter(**filter_args)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context[self.context_filter_name] = self.filter
        table = self.table_class(self.object_list)
        if self.option == 'P':
            geo_list = []
            for p in self.object_list:
                if TaskGeolocation.objects.filter(task_id=p.id):
                    geo_list.append(p.id)
            table = self.table_class(self.object_list.exclude(id__in=geo_list))
        RequestConfig(self.request, paginate={'per_page': 30}).configure(table)
        context['table'] = table
        context['option'] = self.option
        context['office'] = get_office_session(self.request)
        return context


class BatchCheapestCorrespondent(CustomLoginRequiredView, View):
    def get(self, request, *args, **kwargs):
        task = Task.objects.get(pk=request.GET.get('task_id'))
        price_table = CorrespondentsTable(task, task.office)
        cheapest_correspondent = price_table.get_cheapest_correspondent()
        if cheapest_correspondent:
            return JsonResponse({
                'count': len(cheapest_correspondent),
                'id': cheapest_correspondent[0].pk,
                'office_correspondent': cheapest_correspondent[0].office_correspondent.legal_name,
                'value': cheapest_correspondent[0].value
            })
        return JsonResponse({})


class ViewTaskToPersonCompanyRepresentative(DashboardSearchView):
    template_name = 'task/task_to_person_company_representative.html'

    def get_queryset(self):
        task_list, task_filter = self.query_builder()
        self.filter = task_filter
        return task_list.filter(
            person_company_representative=self.request.user.person).exclude(
            pk__in=self.request.user.tasksurveyanswer_create_user.values_list('tasks__id', flat=True))

    def get_context_data(self):
        context = super().get_context_data()
        context['surveys_company_representative'] = [
            {'task_id': task.pk, 'survey': task.type_task.survey_company_representative} for task in self.object_list
            if task.task_status in [str(TaskStatus.RETURN), str(TaskStatus.OPEN), str(TaskStatus.ACCEPTED),
                                    str(TaskStatus.DONE)]
        ]
        return context

    def post(self, request, *args, **kwargs):
        try:
            task = Task.objects.get(pk=request.POST.get('task_id'))
            survey_result = json.loads(request.POST.get('survey'))
            survey = TaskSurveyAnswer(create_user=request.user,
                                      survey=task.type_task.survey_company_representative, survey_result=survey_result)
            survey.save()
            survey.tasks.add(task)
            if task.parent:
                survey.tasks.add(task.parent)
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'error': e})


class TaskUpdateAmountView(CustomLoginRequiredView, View):
    def post(self, request, *args, **kwargs):
        task = Task.objects.get(pk=request.POST.get('task_id'))
        child_task = task.get_latest_child_not_refused
        current_amount = task.amount_delegated
        new_amount = request.POST.get('amount_delegated')
        child_task.amount = task.amount_delegated = Decimal(new_amount)
        if current_amount == task.amount_to_pay:
            amount_to_pay = amount_to_receive = new_amount
        else:
            amount_to_pay, amount_to_receive = recalculate_amounts(
                current_amount,
                task.amount_to_pay,
                child_task.amount_to_receive,
                new_amount,
                task.rate_type_pay,
                task.rate_type_receive
            )
        task.amount_to_pay = amount_to_pay
        child_task.amount_to_receive = amount_to_receive

        pre_save.disconnect(signals.change_status, sender=Task)
        pre_save.disconnect(signals.pre_save_task, sender=Task)
        post_save.disconnect(signals.post_save_task, sender=Task)

        task.save()
        child_task.save()

        pre_save.connect(signals.change_status, sender=Task)
        pre_save.connect(signals.pre_save_task, sender=Task)
        post_save.connect(signals.post_save_task, sender=Task)
        data = {
            'amount_delegated': new_amount,
            'message': 'Registro atualizado com sucesso'
        }
        return JsonResponse(data, status=200)


@login_required
def ajax_bulk_create_update_status(request):
    task_id = request.POST.get('task_id', 0)
    status = 200
    data = {
        "updated": False,
    }
    if task_id:
        task = Task.objects.filter(pk=task_id).first()
        if task and task.task_status == 'Solicitada':
            task.task_status = TaskStatus.ACCEPTED_SERVICE
            task.save()
            data = {
                "updated": True,
            }
        else:
            status = 500
    else:
        status = 400
    return JsonResponse(data, status=status)


class TypeTaskAutocomplete(autocomplete.Select2QuerySetView):
    @property
    def base_queryset(self):
        return TypeTask.objects.filter(is_active=True, office=get_office_session(self.request))

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return TypeTask.objects.none()
        qs = self.base_queryset
        if self.q:
            qs = qs.filter(name__unaccent__icontains=self.q)
        return qs


class TypeTaskFilterAutocomplete(TypeTaskAutocomplete):
    @property
    def base_queryset(self):
        return TypeTask.objects.filter(office=get_office_session(self.request))


class TypeTaskMainAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return TypeTaskMain.objects.none()
        qs = TypeTaskMain.objects.all()
        if self.q:
            qs = qs.filter(name__unaccent__icontains=self.q)
        return qs


class TaskCheckinReportView(CustomLoginRequiredView, TemplateView):
    template_name = 'task/reports/checkin.html'
    filter_class = TaskCheckinReportFilter
    model = Task

    def get(self, request, *args, **kwargs):
        if not request.GET:
            return super().get(request, *args, **kwargs)
        tasks = self.filter_class(request.GET, queryset=self.get_queryset())
        tasks_serializer = TaskCheckinSerializer(tasks.qs, many=True)
        return JsonResponse(tasks_serializer.data, safe=False)

    def get_queryset(self):
        office = get_office_session(self.request)
        office_corresp = Task.objects.filter(id=OuterRef('child')).order_by('-id')
        return self.model.objects.select_related('movement__law_suit')\
            .select_related('movement__law_suit__folder__person_customer') \
            .select_related('type_task') \
            .filter(Q(office=office),
                    Q(task_status__in=[TaskStatus.DONE, TaskStatus.FINISHED,
                                       TaskStatus.BLOCKEDPAYMENT]),)\
            .annotate(filho=Max('child'))\
            .annotate(office_exec=Subquery(office_corresp.values('office__legal_name')[:1]))\
            .annotate(os_executor=Coalesce('person_executed_by__legal_name', 'office_exec'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter_class
        return context


class ServicePriceTableOfTaskView(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):
        task = Task.objects.get(pk=pk)
        if request.GET.get('billing_moment') == 'POST_PAID':
            price_table = CorrespondentsTablePostPaid(task, task.office)
        else:
            price_table = CorrespondentsTable(task, task.office)
        data = ServicePriceDelegationTableSerializer(price_table.correspondents_qs, many=True).data
        return JsonResponse(data, safe=False)


class ServicePriceTableCheapestOfTaskView(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):
        task = Task.objects.get(pk=pk)
        if request.GET.get('billing_moment') == 'POST_PAID':
            price_table = CorrespondentsTablePostPaid(task, task.office)
        else:
            price_table = CorrespondentsTable(task, task.office)
        data = ServicePriceDelegationTableSerializer(price_table.get_cheapest_correspondent()).data
        return JsonResponse(data)