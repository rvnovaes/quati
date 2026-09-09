import json
from core.views import CustomLoginRequiredView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import render, redirect
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic import View
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django_tables2 import RequestConfig
from core.messages import (CREATE_SUCCESS_MESSAGE, UPDATE_SUCCESS_MESSAGE,
                           DELETE_SUCCESS_MESSAGE)
from core.models import Office, ContactMechanismType, EMAIL
from core.views import (AuditFormMixin, MultiDeleteViewMixin,
                        SingleTableViewMixin)
from task.models import Task
from task.workflow import CorrespondentsTable
from .forms import CostCenterForm, ServicePriceTableForm, ImportServicePriceTableForm, PolicyPriceForm
from .serializers import ServicePriceDelegationTableSerializer
from .models import CostCenter, ServicePriceTable, ImportServicePriceTable, PolicyPrice
from .tables import CostCenterTable, ServicePriceTableTable, PolicyPriceTable
from .tasks import import_xls_service_price_table, IMPORTED_IMPORT_SERVICE_PRICE_TABLE, \
PROCESS_PERCENT_IMPORT_SERVICE_PRICE_TABLE, WORKSHEET_IN_PROCESS, IMPORTED_WORKSHEET,\
ERROR_PROCESS
from core.views import TypeaHeadGenericSearch
from core.utils import get_office_session
from .utils import clearCache
from dal import autocomplete


class CostCenterListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = CostCenter
    table_class = CostCenterTable
    ordering = ('name', )


class CostCenterCreateView(AuditFormMixin, CreateView):
    model = CostCenter
    form_class = CostCenterForm
    success_url = reverse_lazy('costcenter_list')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'costcenter_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class CostCenterUpdateView(AuditFormMixin, UpdateView):
    model = CostCenter
    form_class = CostCenterForm
    success_url = reverse_lazy('costcenter_list')
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_update_form'
    object_list_url = 'costcenter_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class CostCenterDeleteView(AuditFormMixin, MultiDeleteViewMixin):
    model = CostCenter
    success_url = reverse_lazy('costcenter_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'costcenter_list'

    def post(self, request, *args, **kwargs):
        ret = super().post(request, *args, **kwargs)
        return ret


class CostCenterAutocomplete(TypeaHeadGenericSearch):

    @staticmethod
    def get_data(module, model, field, q, office, forward_params, extra_params, *args, **kwargs):
        data = []
        for cost_center in CostCenter.objects.filter(Q(name__unaccent__icontains=q),
                                                     Q(is_active=True),
                                                     Q(office=office)):
            data.append({'id': cost_center.id, 'data-value-txt': cost_center.__str__()})
        return list(data)


class CostCenterFilterAutocompleteSelect2(autocomplete.Select2QuerySetView):
    @property
    def base_queryset(self):
        return CostCenter.objects.filter(office=get_office_session(self.request))

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return CostCenter.objects.none()
        qs = self.base_queryset
        if self.q:
            qs = qs.filter(name__unaccent__icontains=self.q)
        return qs


class ServicePriceTableListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = ServicePriceTable
    table_class = ServicePriceTableTable
    ordering = ('office', )
    paginate_by = 30

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.request.user.is_superuser:
            qs = context['table'].data.data.exclude(policy_price__category='NETWORK')
            table = self.table_class(qs)
            total_colums = len(table.columns.items())
            RequestConfig(
                self.request, paginate={
                    'per_page': self.paginate_by
                }).configure(table)
            context['table'] = table
            context['total_columns'] = total_colums
        return context


class ServicePriceTableCreateView(AuditFormMixin, CreateView):
    model = ServicePriceTable
    form_class = ServicePriceTableForm
    success_url = reverse_lazy('servicepricetable_list')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'servicepricetable_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['office_session'] = get_office_session(self.request)
        context['policy_prices_categories'] = json.dumps(
            {policy_price.id: {'category': policy_price.category,
                               'billing_moment': policy_price.billing_moment} for
             policy_price in context['form'].fields['policy_price'].queryset})
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if request.POST['office_network'] and not request.POST['office_correspondent']:
            form.fields['office_correspondent'].required = False
        if request.POST['office_correspondent'] and not request.POST['office_network']:
            form.fields['office_network'].required = False
        if form.is_valid():
            return self.form_valid(form)
        else:
            self.object = form.instance
            return self.form_invalid(form)

    def form_valid(self, form):
        if not form.instance.office_correspondent:
            form.instance.office_correspondent = get_office_session(self.request)
        return super().form_valid(form)


class ServicePriceTableUpdateView(AuditFormMixin, UpdateView):
    model = ServicePriceTable
    form_class = ServicePriceTableForm
    success_url = reverse_lazy('servicepricetable_list')
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_update_form'
    object_list_url = 'servicepricetable_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['policy_prices_categories'] = json.dumps(
            {policy_price.id: {'category': policy_price.category,
                               'billing_moment': policy_price.billing_moment} for
             policy_price in context['form'].fields['policy_price'].queryset})
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if request.POST['office_network'] and not request.POST['office_correspondent']:
            form.fields['office_correspondent'].required = False
        if request.POST['office_correspondent'] and not request.POST['office_network']:
            form.fields['office_network'].required = False
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        if not form.instance.office_correspondent:
            form.instance.office_correspondent = get_office_session(self.request)
        return super().form_valid(form)


class ServicePriceTableDeleteView(AuditFormMixin, MultiDeleteViewMixin):
    model = ServicePriceTable
    success_url = reverse_lazy('servicepricetable_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'servicepricetable_list'


@login_required
def import_service_price_table(request):   
    context = {}
    if request.method == 'POST':
        form = ImportServicePriceTableForm(request.POST, request.FILES)        
        if form.is_valid():
            file_xls = form.save(commit=False)
            file_xls.office = get_office_session(request)
            file_xls.create_user = request.user 
            file_xls.start = timezone.now()               
            file_xls.save()

            import_xls_service_price_table.delay(file_xls.pk)
            context['show_modal_progress'] = True
            context['file_xls'] = file_xls
            context['file_name'] = request.FILES['file_xls'].name           
        else:
            messages.error(request, form.errors)
        context['form'] = form
        return render(request, 'financial/import_service_price_table.html', context)         
    else:
        form = ImportServicePriceTableForm()

    have_type_contact_mechanism_email = ContactMechanismType.objects.filter(type_contact_mechanism_type=EMAIL).first()
    context['type_contact_mechanism_type_EMAIL_is_empty'] = have_type_contact_mechanism_email is None        
    context['form'] = form
    return render(request, 'financial/import_service_price_table.html', context)


class ImportServicePriceTableStatus(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):                
        imported = False
        percent_imported = 0
        worksheet_in_process = ""
        imported_worksheet = False
        error_process = False
        process_have_log = False
        
        imported_cache_key = IMPORTED_IMPORT_SERVICE_PRICE_TABLE + str(pk)        
        if cache.get(imported_cache_key):
            imported = cache.get(imported_cache_key)
        
        worksheet_in_process_key = WORKSHEET_IN_PROCESS + str(pk)
        if cache.get(worksheet_in_process_key):
            worksheet_in_process = cache.get(worksheet_in_process_key)
        
        imported_worksheet_key = IMPORTED_WORKSHEET + str(pk)
        if cache.get(imported_worksheet_key):
            imported_worksheet = cache.get(imported_worksheet_key)

        error_process_key = ERROR_PROCESS + str(pk)
        if cache.get(error_process_key):
            error_process = cache.get(error_process_key)
                
        percent_imported_cache_key = PROCESS_PERCENT_IMPORT_SERVICE_PRICE_TABLE + str(pk)
        if cache.get(percent_imported_cache_key):
            percent_imported = cache.get(percent_imported_cache_key)            
        
        if imported or error_process:
            if imported:
                percent_imported = 100
            else:
                percent_imported = 0
            process_have_log = ImportServicePriceTable.objects.get(pk=pk).log != " "
            clearCache([imported_cache_key,
                worksheet_in_process_key,
                imported_worksheet_key,
                percent_imported_cache_key,
                error_process_key])

        return JsonResponse({
            'imported': imported, 
            'percent': percent_imported,
            'worksheet_in_process': worksheet_in_process,
            'imported_worksheet': imported_worksheet,
            'error_process': error_process,
            'process_have_log': process_have_log            
        })


@login_required
def ajax_get_log_import_service_price_table_data_table(request):    
    pk = request.GET.get('pk')        
    file_xls = ImportServicePriceTable.objects.get(pk=pk)    
    log = file_xls.log.split(";")
    log_list = []

    for item in log:
        if item != " ":
            log_list.append(item)
          
    data = {
        "data": log_list
    }        
    return JsonResponse(data)


class ServicePriceTableDetailView(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):
        instance = ServicePriceTable.objects.get(pk=pk)
        return JsonResponse(ServicePriceDelegationTableSerializer(instance=instance).data)


class PolicyPriceView(CustomLoginRequiredView, SingleTableViewMixin):
    model = PolicyPrice
    table_class = PolicyPriceTable


class PolicyPriceCreateView(AuditFormMixin, CreateView):
    model = PolicyPrice
    form_class = PolicyPriceForm
    success_url = reverse_lazy('policyprice_list')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'policyprice_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class PolicyPriceUpdateView(AuditFormMixin, UpdateView):
    model = PolicyPrice
    form_class = PolicyPriceForm
    success_url = reverse_lazy('policyprice_list')
    success_message = UPDATE_SUCCESS_MESSAGE
    object_list_url = 'policyprice_list'

    def get_form_kwags(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class PolicyPriceDeleteView(AuditFormMixin, MultiDeleteViewMixin):
    model = PolicyPrice
    success_url = reverse_lazy('policyprice_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'policyprice_list'
