import os
import importlib
import json
from abc import abstractproperty
from urllib.parse import urljoin
from django import forms
from django.forms.utils import ErrorList
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, password_validation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from core.serializers import OfficeSerializer, AddressSerializer, ContactMechanismSerializer, CustomMessageSerializer
from django.urls import reverse_lazy, reverse
from django.db.models import ProtectedError, Q, F, Sum, Case, When, IntegerField
from django.db import transaction, IntegrityError
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.generic.edit import CreateView, UpdateView, DeleteView, FormView
from django.views.static import serve as static_serve_view
from django.views import View
from django.views.generic import ListView, TemplateView
from allauth.account.views import LoginView, PasswordResetView
from django.contrib.auth import authenticate, login as auth_login
from dal import autocomplete
from django_tables2 import SingleTableView, RequestConfig
from core.forms import PersonForm, AddressForm, UserUpdateForm, UserCreateForm, ResetPasswordFormMixin, OfficeForm, \
    InviteForm, InviteOfficeForm, ContactMechanismForm, TeamForm, ImportCityListForm, OfficeProfileForm
from core.generic_search import GenericSearchForeignKey, GenericSearchFormat, \
    set_search_model_attrs
from core.messages import CREATE_SUCCESS_MESSAGE, UPDATE_SUCCESS_MESSAGE, delete_error_protected, \
    DELETE_SUCCESS_MESSAGE, ADDRESS_UPDATE_ERROR_MESSAGE, ADDRESS_UPDATE_SUCCESS_MESSAGE, \
    USER_CREATE_SUCCESS_MESSAGE, person_cpf_cnpj_already_exists
from core.models import Person, Address, City, State, Country, AddressType, Office, Invite, DefaultOffice, \
    OfficeMixin, InviteOffice, OfficeMembership, ContactMechanism, Team, ControlFirstAccessUser, OfficeOffices, \
    AreaOfExpertise, CustomMessage
from core.signals import create_person
from core.tables import PersonTable, UserTable, AddressTable, AddressOfficeTable, OfficeTable, InviteTable, \
    InviteOfficeTable, OfficeMembershipTable, ContactMechanismTable, ContactMechanismOfficeTable, TeamTable
from core.utils import login_log, logout_log, get_office_session, get_domain, \
    check_cpf_cnpj_exist, get_office_by_id, set_user_default_office
from core.view_validators import create_person_office_relation, person_exists
from core.mail import send_mail_sign_up
from financial.models import ServicePriceTable
from lawsuit.models import Folder, Movement, LawSuit, Organ
from task.models import Task, TaskStatus
from task.metrics import get_correspondent_metrics
from task.utils import create_default_type_tasks
from ecm.forms import AttachmentForm
from ecm.utils import attachment_form_valid, attachments_multi_delete
from django.core.validators import validate_email
from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import get_groups_with_perms
from billing.models import Plan, PlanOffice
from django.contrib.auth.mixins import PermissionRequiredMixin
from core.tasks import import_xls_city_list
from allauth.socialaccount.providers.oauth2.views import *
from allauth.socialaccount.providers.google.views import *
from billing.tables import BillingDetailsTable
from billing.forms import BillingDetailsForm, BillingAddressCombinedForm
from core.utils import cpf_is_valid, cnpj_is_valid, post_create_new_user


class AutoCompleteView(autocomplete.Select2QuerySetView):
    model = abstractproperty()
    lookups = abstractproperty()
    select_related = None

    @classmethod
    def get_part_queryset(cls, part, queryset):
        q = Q()
        for lookup in cls.lookups:
            q |= Q(**{lookup: part})

        return queryset.filter(q)

    def get_queryset(self):
        if self.select_related:
            qs = self.model.objects.select_related(*self.select_related)

        if self.q:
            parts = self.q.split(' ')

            for part in parts:
                qs = self.get_part_queryset(part, qs)
                if not qs.exists():
                    return self.model.objects.none()

            return qs

        else:
            qs = qs[:10]

        return qs

    def get_create_option(self, context, q):
        """This method is required just to translate the creation message."""
        create_option = []
        display_create_option = False
        if self.create_field and q:
            page_obj = context.get('page_obj', None)
            if page_obj is None or page_obj.number == 1:
                display_create_option = True

        if display_create_option and self.has_add_permission(self.request):
            create_option = [{
                'id': q,
                'text': 'Criar "%(new_value)s"' % {'new_value': q},
                'create_id': True,
            }]
        return create_option


def login(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse_lazy('dashboard'))
    else:
        return render(request, 'account/login.html')


@login_required
def inicial(request):
    if request.user.is_authenticated and getattr(request.user, 'person'):
        person = request.user.person
        if person.offices.active_offices().exists() or person.invites.filter(status='N').first():
            set_office_session(request)
            if not get_office_session(request):
                return HttpResponseRedirect(reverse_lazy('office_instance'))
            return HttpResponseRedirect(reverse_lazy('dashboard'))        
        return HttpResponseRedirect(reverse_lazy('social_register'))
    else:
        return HttpResponseRedirect('/')


class StartUserView(TemplateView):
    template_name = 'core/start_user.html'

    def get_context_data(self):
        context = super().get_context_data()

        if self.request.user.person.is_correspondent:
            metrics = get_correspondent_metrics(self.request.user.person)
            context['rating'] = metrics['rating']
            context['returned_os'] = metrics['returned_os_rate']

        office_pks = self.request.user.person.offices.active_offices(
        ).values_list(
            'pk', flat=True)
        context['person_invites'] = Invite.objects.filter(
            invite_from='P', office_id__in=office_pks, status='N').all()

        return context


class OfficeInstanceView(View):
    template_name = 'core/office_instance.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)


@logout_log
def logout_user(request):
    # Faz o logout do usuário contido na requisição, limpando todos os dados da sessão corrente;
    logout(request)
    # Redireciona para a página de login
    return HttpResponseRedirect('/')


def _form_accepts_request(form_class):
    """Só repassa request= para forms que o aceitam (BaseModelForm ou __init__ com parâmetro request)."""
    import inspect
    from core.forms import BaseModelForm
    if issubclass(form_class, BaseModelForm):
        return True
    try:
        params = inspect.signature(form_class.__init__).parameters
    except (TypeError, ValueError):
        return False
    return 'request' in params


class MultiDeleteViewMixin(DeleteView):
    success_message = None

    def post(self, request, *args, **kwargs):
        # Django >= 4 chama get_object() no post padrão; aqui a exclusão é em lote (sem pk na URL).
        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        if request.method == 'POST':
            pks = request.POST.getlist('selection')

            try:
                self.model.objects.filter(pk__in=pks).delete()
                attachments_multi_delete(self.model, pks=pks)
                messages.success(self.request, self.success_message)
            except ProtectedError as e:
                qs = e.protected_objects.first()
                messages.error(
                    self.request,
                    delete_error_protected(
                        str(self.model._meta.verbose_name), qs.__str__()))

        # http://django-tables2.readthedocs.io/en/latest/pages/generic-mixins.html
        if self.success_url:
            return HttpResponseRedirect(self.success_url)
        else:
            return HttpResponseRedirect(self.get_success_url())


class MultiDeleteView(DeleteView):
    success_message = None
    error_message = 'Não é possível fazer exclusão do(s) registro(s) selecionado(s) porque existe(m) ' \
                    +'informações associadas na tabela %s para o registro %s.'

    def post(self, request, *args, **kwargs):
        # Django >= 4 chama get_object() no post padrão; aqui a exclusão é em lote (sem pk na URL).
        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        if request.method == 'POST':
            pks = request.POST.getlist('selection')
            with transaction.atomic():
                try:
                    for item in self.model.objects.filter(pk__in=pks):
                        item.delete()
                    attachments_multi_delete(self.model, pks=pks)
                    messages.success(self.request, self.success_message)
                except ProtectedError as e:
                    qs = e.protected_objects.first()
                    if self.error_message:
                        msg_error = self.error_message % (qs._meta.object_name,
                                                          item)
                    else:
                        delete_error_protected(
                            str(self.model._meta.verbose_name), qs.__str__())
                    messages.error(self.request, msg_error)

        # http://django-tables2.readthedocs.io/en/latest/pages/generic-mixins.html
        if self.success_url:
            return HttpResponseRedirect(self.success_url)
        else:
            return HttpResponseRedirect(self.get_success_url())


class LoginCustomView(LoginView):
    """
    Esta classe herda da view que e responsavel por realizar o login no django-allauth
    """

    @login_log
    def form_valid(self, form):
        """
        Este metodo valida o formulario de login e faz a chamada da funcao que
        efetuar a autenticacao
        Esta sendo sobrescrito para gerar o log de autenticacao de usuario atraves
        do decorator log
        :param form:
        """
        return super(LoginCustomView, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        res = super().dispatch(request, *args, **kwargs)
        set_first_login_user(request)
        return res


def set_first_login_user(request):
    created = False
    if request.user.is_authenticated and request.user.person.offices.active_offices().exists():
        obj, created = ControlFirstAccessUser.objects.get_or_create(
            auth_user=request.user)
    request.session['first_login_user'] = created


def set_office_session(request):
    if not get_office_session(request=request):
        if not hasattr(request.user, 'defaultoffice'):
            return HttpResponseRedirect(reverse('office_instance'))
        request.session['custom_session_user'] = {
            request.user.pk: {
                'current_office': request.user.defaultoffice.office.pk
            }
        }


class CustomLoginRequiredView(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        """
        A view que herdar desta classe ira identificar se existe um escritorio na sessao, se nao tentar buscar os
        escritorio default do usuario se nenhuma das opcoes estiverem setadas ira redirecionar para tela de escolha de
        um escritorio
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        set_office_session(request)
        res = super().dispatch(request, *args, **kwargs)
        return res


class AuditFormMixin(CustomLoginRequiredView, SuccessMessageMixin):
    """
    Implementa a alteração da data e usuários para operação de update e new
    Lógica que verifica se a requisição é para Create ou Update.
    Se Create, o botão 'ativar' é desabilitar e valor padrão True
    Se Update, o botão 'ativar é habilitado para edição e o valor, carregado do banco
    """

    object_list_url = None

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        form_class = self.get_form_class()
        if _form_accepts_request(form_class):
            kw['request'] = self.request
        return kw

    def get_context_data(self, **kwargs):
        kwargs.update({'form_attachment': AttachmentForm})
        return super().get_context_data(
            object_list_url=self.get_object_list_url(), **kwargs)

    def get_object_list_url(self):
        if self.object_list_url:
            return reverse(self.object_list_url)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if 'is_active' in form.fields and not form.instance.pk:
            form.data = form.data.copy()
            form.data['is_active'] = True
            form.fields['is_active'].initial = True
            form.fields['is_active'].required = False
            form.fields['is_active'].widget.attrs['disabled'] = 'disabled'
        return form

    @attachment_form_valid
    def form_valid(self, form):
        instance = form.save(commit=False)

        if 'is_active' in form.fields and not instance.pk:
            instance.is_active = True

        if form.instance.id is None:
            form.instance.create_date = timezone.now()
            form.instance.create_user = self.request.user
        else:
            form.instance.alter_date = timezone.now()
            form.instance.alter_user = self.request.user
            form.save()

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, form.errors)
        return super().form_invalid(form)


class ViewRelatedMixin(AuditFormMixin):
    """
        Este mixin procura abstrair funcionalidades pertinentes a models que são editados
        como detail em outro model permitindo salvar model detalhe vinculado ao model mestre.
        Exemplo: Cadastro de pessoa com os cadastros de endereço e mecanismo de contato.
    """

    def __init__(self,
                 related_model=None,
                 related_field_pk=False,
                 related_model_name=''):
        self.related_model = related_model
        self.related_model_name = related_model_name
        self.related_field_pk = related_field_pk
        self.object_related = None

    def dispatch(self, *args, **kwargs):
        self.object_related = self.related_model.objects.get(
            pk=kwargs['{}_pk'.format(self.related_field_pk)])
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(person=self.object_related, **kwargs)

    def form_valid(self, form):
        form.save(commit=False)
        setattr(form.instance, self.related_model_name, self.object_related)
        try:
            # TODO - Verificar se é a melhor forma de tratar duplicidades
            return super().form_valid(form)
        except IntegrityError as e:
            messages.add_message(self.request, messages.ERROR,
                                 'Registro já existente.')
            return self.form_invalid(form)

    def get_object_list_url(self):
        # TODO: Este método parece ser inútil, success_url pode ser usado.
        return reverse(
            '{}_update'.format(self.related_model_name),
            args=(self.object_related.pk, ))


class AddressCreateView(ViewRelatedMixin, CreateView):
    model = Address
    form_class = AddressForm
    success_message = CREATE_SUCCESS_MESSAGE

    def __init__(self):
        super().__init__(
            related_model=Person,
            related_model_name='person',
            related_field_pk='person')

    def get_success_url(self):
        return reverse('person_update', args=(self.kwargs.get('person_pk'), ))


class AddressOfficeCreateView(ViewRelatedMixin, CreateView):
    model = Address
    form_class = AddressForm
    success_message = CREATE_SUCCESS_MESSAGE

    def __init__(self):
        super().__init__(
            related_model=Office,
            related_model_name='office',
            related_field_pk='office')

    def get_success_url(self):
        return reverse('office_update', args=(self.kwargs.get('office_pk'), ))


class AddressUpdateView(UpdateView):
    model = Address
    form_class = AddressForm
    success_message = UPDATE_SUCCESS_MESSAGE

    def get_success_url(self):
        return reverse('person_update', args=(self.kwargs.get('person_pk'), ))

    def get_object_list_url(self):
        # TODO: Este método parece ser inútil, success_url pode ser usado.
        return reverse('person_update', args=(self.kwargs.get('person_pk'), ))


class AddressOfficeUpdateView(AddressUpdateView):
    def get_success_url(self):
        return reverse('office_update', args=(self.kwargs.get('office_pk'), ))


class AddressDeleteView(MultiDeleteViewMixin):
    model = Address
    form_class = AddressForm
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)

    def get_success_url(self):
        return reverse(
            'person_update', kwargs={'pk': self.kwargs['person_pk']})


class AddressOfficeDeleteView(AddressDeleteView):
    model = Address
    form_class = AddressForm
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)

    def get_success_url(self):
        return reverse(
            'office_update', kwargs={'pk': self.kwargs['office_pk']})


class SingleTableViewMixin(SingleTableView):
    ordering = None
    paginate_by = 10

    @classmethod
    def filter_queryset(cls, queryset):
        if cls.ordering:
            return queryset.order_by(*cls.ordering)
        else:
            return queryset

    @set_search_model_attrs
    def get_context_data(self, **kwargs):
        context = super(SingleTableViewMixin, self).get_context_data(**kwargs)
        context['module'] = self.model.__module__
        context['model'] = self.model.__name__
        try:
            context['nav_' + str(self.model._meta.verbose_name)] = True
        except:
            pass
        context['form_name'] = self.model._meta.verbose_name
        context['form_name_plural'] = self.model._meta.verbose_name_plural
        context['page_title'] = self.model._meta.verbose_name_plural

        custom_session_user = self.request.session.get('custom_session_user')
        office = False
        if custom_session_user and custom_session_user.get(
                str(self.request.user.pk)):
            current_office_session = custom_session_user.get(
                str(self.request.user.pk))
            office = Office.objects.filter(
                pk=int(current_office_session.get(
                    'current_office'))).values_list(
                        'id', flat=True).first()
        if not office:
            office = self.request.user.person.offices.active_offices(
            ).values_list(
                'id', flat=True).first()

        generic_search = GenericSearchFormat(self.request, self.model,
                                             self.model._meta.fields)
        args = generic_search.despatch(office=office)
        if args:
            table = eval(args)
        else:
            qs = self.model.objects.get_queryset()
            try:
                office_field = self.model._meta.get_field('office')
                if office:
                    qs = self.model.objects.get_queryset(office=office)
            except:
                pass
            qs = self.filter_queryset(qs)
            table = self.table_class(qs)
        total_colums = len(table.columns.items())
        RequestConfig(
            self.request, paginate={
                'per_page': self.paginate_by
            }).configure(table)
        context['table'] = table
        context['total_columns'] = total_colums
        return context


def address_update(request, pk):
    instance = get_object_or_404(Address, id=pk)
    form = AddressForm(request.POST or None, instance=instance)

    # Todo: Trocar o codigo de data por serialize()
    data = {
        'result': False,
        'message': ADDRESS_UPDATE_ERROR_MESSAGE,
        'city': str(form.instance.city),
        'state': str(form.instance.state),
        'country': str(form.instance.country),
        'address_type': str(form.instance.address_type)
    }

    if form.is_valid():
        form.save()
        data = {'result': True, 'message': ADDRESS_UPDATE_SUCCESS_MESSAGE}

    return JsonResponse(data)


class PersonListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = Person
    table_class = PersonTable
    ordering = (
        'legal_name',
        'name',
    )

    def get_context_data(self, **kwargs):
        context = super(PersonListView, self).get_context_data(**kwargs)
        office_session = get_office_session(request=self.request)
        only_linked_person = True if self.request.GET.get(
            "only_linked_person") else False
        if only_linked_person:
            table = self.table_class(context['table'].data.data.filter(
                offices=office_session,
                officemembership__is_active=True).exclude(
                    pk__in=Organ.objects.all()).order_by('-pk'))
        else:
            table = self.table_class(context['table'].data.data.filter(
                offices=office_session).exclude(
                    pk__in=Organ.objects.all()).order_by('-pk'))
        context['table'] = table
        RequestConfig(self.request, paginate={'per_page': 10}).configure(table)
        return context


class PersonCreateView(AuditFormMixin, CreateView):
    model = Person
    form_class = PersonForm
    success_url = reverse_lazy('person_list')

    def get_success_url(self):
        return reverse('person_update', kwargs={'pk': self.object.pk})

    def form_valid(self, form):

        # if AuditFormMixin.form_valid(self, form):
        instance = form.save(commit=False)

        if 'is_active' in form.fields and not instance.pk:
            instance.is_active = True

        if form.instance.id is None:
            form.instance.create_date = timezone.now()
            form.instance.create_user = self.request.user
        else:
            form.instance.alter_date = timezone.now()
            form.instance.alter_user = self.request.user
            form.save()

        context = self.get_context_data()
        with transaction.atomic():
            self.object = form.save(commit=False)
            office_session = get_office_session(self.request)
            if person_exists(self.object.cpf_cnpj, office_session):
                form._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList(
                    [person_cpf_cnpj_already_exists()])
                return self.form_invalid(form)

            self.object = form.save()
            create_person_office_relation(self.object, self.request.user,
                                          office_session)
        return super().form_valid(form)


class PersonUpdateView(AuditFormMixin, UpdateView):
    model = Person
    form_class = PersonForm
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_update_form'
    object_list_url = 'person_list'

    def get_context_data(self, **kwargs):
        kwargs.update({
            'table':
            AddressTable(self.object.address_set.all()),
            'table_contact_mechanism':
            ContactMechanismTable(self.object.contactmechanism_set.all()),
        })
        return super().get_context_data(**kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        user = User.objects.get(id=self.request.user.id)
        checker = ObjectPermissionChecker(user)
        kw['is_admin'] = checker.has_perm('group_admin',
                                          get_office_session(self.request))
        return kw

    def get_success_url(self):
        return reverse('person_update', args=(self.object.id, ))


class PersonDeleteView(AuditFormMixin, MultiDeleteView):
    model = Person
    success_url = reverse_lazy('person_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'person_list'


class GenericAutocompleteForeignKey(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        try:
            module = importlib.import_module(self.request.GET.get('module'))
            model = getattr(module, self.request.GET.get('model'))
            field_name = self.request.GET.get('name')
            qs = model.objects.none()
            if self.q:
                generic_search = GenericSearchForeignKey(model)
                ids = generic_search.get_related_values(self.q, field_name)
                qs = list(
                    filter(lambda i: i.id in ids,
                           eval(
                               'model.{0}.get_queryset()'.format(field_name))))
            return qs
        except:
            return []


@login_required
def person_address_search_country(request):
    countries = Country.objects.filter(id__gt=1).values('name',
                                                        'id').order_by('name')
    countries_json = json.dumps({
        'number': len(countries),
        'countries': list(countries)
    },
                                cls=DjangoJSONEncoder)
    return JsonResponse(countries_json, safe=False)


@login_required
def person_address_search_state(request, pk):
    states = State.objects.filter(country_id=pk).values('name',
                                                        'id').order_by('name')
    states_json = json.dumps({
        'number': len(states),
        'states': list(states)
    },
                             cls=DjangoJSONEncoder)
    return JsonResponse(states_json, safe=False)


@login_required
def person_address_search_city(request, pk):
    cities = City.objects.filter(state_id=pk).values('name',
                                                     'id').order_by('name')
    cities_json = json.dumps({
        'number': len(cities),
        'cities': list(cities)
    },
                             cls=DjangoJSONEncoder)
    return JsonResponse(cities_json, safe=False)


@login_required
def person_address_information(request, pk):
    try:
        address = Address.objects.get(id=pk)
        data = {
            'result': True,
            'street': address.street,
            'number': address.number,
            'complement': address.complement,
            'city_region': address.city_region,
            'state_id': str(address.state_id),
            'state': str(address.state),
            'city': str(address.city),
            'city_id': str(address.city_id),
            'address_type': str(address.address_type),
            'address_type_id': str(address.address_type_id),
            'zip_code': address.zip_code,
            'notes': address.notes,
            'home_address': address.home_address,
            'business_address': address.business_address,
            'country': str(address.country),
            'country_id': str(address.country_id),
            'person': str(address.person_id),
            'is_active': address.is_active
        }
    except:
        data = {'result': False}

    return JsonResponse(data)


@login_required
def person_address_search_address_type(request):
    addresses_types = AddressType.objects.all().values('name', 'id')
    addresses_types_json = json.dumps({
        'number': len(addresses_types),
        'addresses_types': list(addresses_types)
    },
                                      cls=DjangoJSONEncoder)
    return JsonResponse(addresses_types_json, safe=False)


class GenericFormOneToMany(FormView, SingleTableView):
    related_ordering = None

    def get_initial(self):
        if self.kwargs.get('lawsuit'):
            folder_id = LawSuit.objects.get(
                id=self.kwargs.get('lawsuit')).folder.id
            self.kwargs['folder'] = folder_id
        if isinstance(self, CreateView):
            self.form_class.declared_fields['is_active'].initial = True
            self.form_class.declared_fields['is_active'].disabled = True

        elif isinstance(self, UpdateView):
            self.form_class.declared_fields['is_active'].disabled = False
        return self.initial.copy()

    def form_valid(self, form):
        user = User.objects.get(id=self.request.user.id)
        folder = self.kwargs.get('folder') or None
        lawsuit = self.kwargs.get('lawsuit') or None
        movement = self.kwargs.get('movement') or None
        pk = self.kwargs.get('pk')
        if form.instance.id is None:
            if folder:
                form.instance.folder = Folder.objects.get(id=folder)
                if isinstance(self, UpdateView):
                    form.instance.law_suit = LawSuit.objects.get(id=pk)
            if lawsuit:
                form.instance.law_suit = LawSuit.objects.get(id=lawsuit)
                if isinstance(self, UpdateView):
                    form.instance.movement = Movement.objects.get(id=pk)
            if movement:
                form.instance.movement = Movement.objects.get(id=movement)
                if isinstance(self, UpdateView):
                    form.instance.task = Task.objects.get(id=pk)

        if form.instance.id is None:
            # TODO: nao precisa salvar o create_date e o alter_date pq o model já faz isso. tirar
            # de todos os lugares
            form.instance.create_date = timezone.now()
            form.instance.create_user = user
        else:

            form.instance.alter_date = timezone.now()
            form.instance.alter_user = user
        form.save()
        super(GenericFormOneToMany, self).form_valid(form)
        return HttpResponseRedirect(self.success_url)

    @set_search_model_attrs
    def get_context_data(self, **kwargs):
        context = super(GenericFormOneToMany, self).get_context_data(**kwargs)
        related_model_id = self.kwargs.get('pk')
        context['module'] = self.related_model.__module__
        context['model'] = self.related_model.__name__
        context['nav_' + self.related_model._meta.verbose_name] = True
        context['form_name'] = self.related_model._meta.verbose_name
        context[
            'form_name_plural'] = self.related_model._meta.verbose_name_plural
        fields_related = list(
            filter(lambda i: i.get_internal_type() == 'ForeignKey',
                   self.related_model._meta.fields))
        field_related = list(
            filter(lambda i: i.related_model == self.model, fields_related))[0]
        generic_search = GenericSearchFormat(
            request=self.request,
            model=self.related_model,
            fields=self.related_model._meta.fields,
            related_id=related_model_id,
            field_name_related=field_related.name)
        generic_search_args = generic_search.despatch()
        if generic_search_args:
            table = eval(
                generic_search_args.replace('.model.', '.related_model.'))
        else:
            table = self.table_class(self.related_model.objects.none())
            if related_model_id:
                lookups = {
                    '{}__id'.format(field_related.name): related_model_id,
                    'office__id': get_office_session(self.request).id
                }
                qs = self.related_model.objects.filter(**lookups)

                if self.related_ordering:
                    qs = qs.order_by(*self.related_ordering)

                table = self.table_class(qs)

        RequestConfig(self.request, paginate={'per_page': 10}).configure(table)
        context['table'] = table
        return context

    success_message = None


def recover_database(request):
    return render(
        request, 'core/recover_database.html', {
            'request': False,
            'host': settings.LINK_TO_RESTORE_DB_DEMO,
            'timeout': 45000
        })


class UserListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = User
    table_class = UserTable
    template_name = 'auth/user_list.html'
    ordering = (
        'first_name',
        'last_name',
        'username',
        'email',
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        table_data = context['table'].data.data
        context['table'] = self.table_class(
            list(
                map(
                    lambda i: i.auth_user,
                    get_office_session(self.request).persons.filter(
                        auth_user__in=table_data,
                        auth_user__is_superuser=False))))
        RequestConfig(
            self.request, paginate={
                'per_page': 10
            }).configure(context['table'])
        return context


class UserView(FormView):
    model = User
    form_class = UserCreateForm
    success_url = reverse_lazy('user_list')
    template_name = 'auth/user_create.html'
    success_message = CREATE_SUCCESS_MESSAGE

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        if not form.instance.id:
            form.save()
        default_office = set_user_default_office(
            form.cleaned_data['office'],
            form.instance,
            self.request.user
        )
        super().form_valid(form)
        return HttpResponseRedirect(self.success_url)

    def clean_groups(self, office):
        groups = self.request.POST.getlist('office_' + str(office.id), '')
        if not groups:
            messages.error(
                self.request,
                "O usuário deve pertencer a pelo menos um grupo. Verifique as permissões do escritório %s"
                % office)
            return []
        return groups

    def get_create_office_membership(self, office, user):
        member, created = OfficeMembership.objects.get_or_create(
            person=user.person,
            office=office,
            defaults={
                'create_user': self.request.user,
                'is_active': True
            })
        if not created:
            # Caso o relacionamento exista mas esta inativo
            member.is_active = True
            member.save()

    def manage_user_groups(self, office, groups, user):
        for group_office in office.office_groups.all():
            if str(group_office.group.id) in groups:
                self.get_create_office_membership(office, user)
                group_office.group.user_set.add(user)
            else:
                group_office.group.user_set.remove(user)
        if not user.groups.all():
            messages.error(
                self.request,
                "O usuário deve pertencer a pelo menos um grupo")
            return self.form_invalid(self.get_form())
        return user.groups.all()

    def update_user_person(self, form):
        person = form.cleaned_data.get('person')
        if person:
            old_person = form.instance.person if form.instance.id else None
            if old_person:
                old_person.auth_user = None
                old_person.save()
            form.instance.person = person


class UserCreateView(UserView, AuditFormMixin, CreateView):

    def get_success_url(self):
        return reverse_lazy('user_list')

    def form_valid(self, form):
        form.save(commit=False)
        try:
            with transaction.atomic():
                self.update_user_person(form)
                office = get_office_session(self.request)
                groups = self.clean_groups(office)
                if not groups:
                    raise Exception()
                form.save()
                self.manage_user_groups(office, groups, form.instance)
        except Exception:
            return self.form_invalid(form)

        super().form_valid(form)
        return HttpResponseRedirect(self.success_url)


class UserUpdateView(UserView, AuditFormMixin, UpdateView):
    form_class = UserUpdateForm
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name = 'auth/user_form.html'

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse_lazy('user_list'))

    def get_initial(self):
        self.form_class.declared_fields['password'].disabled = True
        self.form_class.declared_fields['username'].disabled = True
        return self.initial.copy()

    def form_valid(self, form):
        form.save(commit=False)
        checker = ObjectPermissionChecker(self.request.user)
        try:
            with transaction.atomic():
                self.update_user_person(form)
                for office in form.instance.person.offices.active_offices():
                    if checker.has_perm('group_admin', office):
                        groups = self.clean_groups(office)
                        if not groups:
                            raise Exception()
                        self.manage_user_groups(office, groups, form.instance)
                form.save()
        except Exception:
            return self.form_invalid(form)

        super(UserView, self).form_valid(form)
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        """
        Sobrescreve o metodo get_context_data e seta a ultima url acessada no cache
        Isso e necessario para que ao salvar uma alteracao, o metodo post consiga verificar
        a pagina da paginacao onde o usuario fez a alteracao
        :param kwargs:
        :return: super
        """
        context = super(UserUpdateView, self).get_context_data(**kwargs)
        cache.set('user_page', self.request.META.get('HTTP_REFERER'))
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
        if cache.get('user_page'):
            self.success_url = cache.get('user_page')
        return super(UserUpdateView, self).post(request, *args, **kwargs)


class UserDeleteView(CustomLoginRequiredView, MultiDeleteView):
    model = User
    success_url = reverse_lazy('user_list')
    success_message = DELETE_SUCCESS_MESSAGE.format('usuários')

    def get_success_url(self):
        return reverse_lazy('user_list')


class PasswordResetViewMixin(PasswordResetView, FormView):
    form_class = ResetPasswordFormMixin

    def form_valid(self, form):
        context = form.save(self.request)
        return render(self.request, 'account/password_reset_done.html',
                      context)

    def form_invalid(self, form):
        return render(self.request, 'account/password_reset_done_error.html',
                      {})


class OfficeListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = Office
    table_class = OfficeTable

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pks = []
        for office in self.request.user.person.offices.active_offices():
            if self.request.user.has_perm('can_access_general_data', office):
                pks.append(office.pk)
        context['table'] = self.table_class(
            context['table'].data.data.filter(pk__in=pks))
        RequestConfig(
            self.request, paginate={
                'per_page': 10
            }).configure(context['table'])
        return context


class OfficeCreateView(AuditFormMixin, CreateView):
    model = Office
    form_class = OfficeForm
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'office_list'

    def form_valid(self, form):
        form.instance.create_user = self.request.user
        try:
            form.instance.save()
        except IntegrityError as e:
            error_msg = 'Já existe um escritório com o CPF/CNPJ informado.'
            messages.add_message(self.request, messages.ERROR,
                                 error_msg)
            form.add_error('cpf_cnpj', ValidationError(error_msg))
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('office_update', kwargs={'pk': self.object.pk})


class OfficeUpdateView(AuditFormMixin, UpdateView):
    model = Office
    form_class = OfficeForm
    template_name_suffix = '_update_form'
    success_message = UPDATE_SUCCESS_MESSAGE
    object_list_url = 'office_list'

    def get_context_data(self, **kwargs):
        kwargs.update({
            'table':
            AddressOfficeTable(self.object.get_address()),
            'table_members':
            OfficeMembershipTable(
                self.object.officemembership_set.filter(
                    is_active=True,
                    person__auth_user__isnull=False,
                    person__auth_user__is_superuser=False).exclude(
                        person__auth_user=self.request.user)),
            'table_offices':
            OfficeTable(
                Office.objects.get(pk=self.kwargs.get('pk')).offices.all().
                order_by('legal_name')),
            'table_contact_mechanism':
            ContactMechanismOfficeTable(
                self.object.contactmechanism_set.all()),
        })
        data = super().get_context_data(**kwargs)
        data['inviteofficeform'] = InviteForm(self.request.POST) \
            if InviteForm(self.request.POST).is_valid() else InviteForm()
        RequestConfig(
            self.request, paginate=False).configure(
                kwargs.get('table_members'))
        RequestConfig(
            self.request, paginate=False).configure(
                kwargs.get('table_offices'))
        return data

    def dispatch(self, request, *args, **kwargs):
        office_instance = Office.objects.filter(
            pk=int(kwargs.get('pk', None))).first()
        if not self.request.user.has_perm('can_access_general_data',
                                          office_instance):
            messages.error(
                self.request,
                "Você não possui permissão para editar o escritório selecionado."
                " Favor selecionar o escritório correto")
            del self.request.session['custom_session_user']
            self.request.session.modified = True
            return HttpResponseRedirect(reverse('office_instance'))
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('office_update', kwargs={'pk': self.kwargs['pk']})


class OfficeDeleteView(CustomLoginRequiredView, MultiDeleteViewMixin):
    model = Office
    form_class = OfficeForm
    success_url = reverse_lazy('office_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'office_list'


class CustomSession(View):
    def post(self, request, *args, **kwargs):
        """
        Cria uma sessao customizada do usuario para armazenar o escritorio atual
        do usuario. O Valor e armazenando na sessao atravez da chave
        custom_session_user, que ira possuir um dicionario contendo como chave
        o id do usuario e como valor um dicionario contendo o current_office.
        """
        data = {}
        if request.POST.get('current_office'):
            custom_session_user = self.request.session.get(
                'custom_session_user')
            if not custom_session_user:
                data['modified'] = True            
            elif custom_session_user.get(str(self.request.user.pk), {}).get('current_office') \
                    != request.POST.get('current_office'):
                data['modified'] = True
            current_office = request.POST.get('current_office')
            request.session['custom_session_user'] = {
                self.request.user.pk: {
                    'current_office': current_office
                }
            }
            office = Office.objects.filter(pk=int(current_office)).first()
            if office:
                data['current_office_pk'] = office.pk
                data['current_office_name'] = office.legal_name
            else:
                request.session.modified = True
                del request.session['custom_session_user']
                data['modified'] = True

        return JsonResponse(data)

    def get(self, request, *args, **kwargs):
        """
        Busca a sessao customizada pra do usuario que retorna informacoes
        do escritorio atual do usuario
        """
        data = {}
        custom_session_user = request.session.get('custom_session_user')
        if custom_session_user and custom_session_user.get(
                str(request.user.pk)):
            current_office_session = custom_session_user.get(
                str(request.user.pk))
            office = Office.objects.filter(
                pk=int(current_office_session.get('current_office'))).first()
            if office:
                data['current_office_pk'] = office.pk
                data['current_office_name'] = office.legal_name
        else:
            default_office = DefaultOffice.objects.filter(
                auth_user=request.user).first()
            if default_office:
                data['current_office_pk'] = default_office.office.pk
                data['current_office_name'] = default_office.office.legal_name
        return JsonResponse(data)


class InviteCreateView(AuditFormMixin, CreateView):
    model = Invite
    form_class = InviteForm
    success_url = reverse_lazy('start_user')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'start_user'

    def post(self, request, *args, **kwargs):
        form = InviteForm(request.POST)
        form.instance.create_user = self.request.user
        person = request.POST.get('person')
        office = request.POST.get('office')
        try:
            validate_email(person)
            external_user = True
            email = person
            if Person.objects.filter(auth_user__email=email):
                person = Person.objects.filter(
                    auth_user__email=email).first().pk
            else:
                person = None
                form.instance.status = 'E'
        except:
            external_user = False
            email = None
        if not Invite.objects.filter(person__pk=person, office__pk=office, email=email, status='N') and \
                not Invite.objects.filter(person__pk=person, office__pk=office, email=email, status='E'):
            form.instance.person = Person.objects.filter(
                pk=person).first() if person else None
            form.instance.office = Office.objects.get(pk=office)
            form.instance.email = email
            form.instance.__host = get_domain(request)
            form.instance.save()
        return JsonResponse({'status': 'ok'})


class InviteOfficeCreateView(AuditFormMixin, CreateView):
    model = InviteOffice
    form_class = InviteOfficeForm
    success_url = reverse_lazy('start_user')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'start_user'

    def post(self, request, *args, **kwargs):
        form = InviteOfficeForm(request.POST)
        form.instance.create_user = self.request.user
        office_invite = request.POST.get('office_invite')
        office = request.POST.get('office')
        if office == office_invite:
            return JsonResponse({
                'error':
                'Não é possível convidar o mesmo escritório!'
            })
        if not InviteOffice.objects.filter(
                office_invite__pk=office_invite, office__pk=office,
                status='N'):
            form.instance.office = Office.objects.get(
                pk=request.POST.get('office'))
            form.instance.office_invite = Office.objects.get(
                pk=request.POST.get('office_invite'))
            form.instance.save()
        return JsonResponse({'status': 'ok'})


class InviteUpdateView(UpdateView):
    def post(self, request, *args, **kargs):
        invite = Invite.objects.get(pk=int(request.POST.get('invite_pk')))
        invite.status = request.POST.get('status')
        if invite.status == 'A':
            OfficeMembership.objects.update_or_create(
                person=invite.person,
                office=invite.office,
                defaults={
                    'create_user': self.request.user,
                    'is_active': True
                })
            if not DefaultOffice.objects.filter(auth_user=invite.person.auth_user, is_active=True).first():
                DefaultOffice.objects.create(auth_user=invite.person.auth_user,
                                             office=invite.office,
                                             is_active=True,
                                             create_user=self.request.user)
            groups_list = {
                group
                for group, perms in get_groups_with_perms(
                    invite.office, attach_perms=True).items()
                if 'view_delegated_tasks' in perms
            }
            for group in groups_list:
                if group not in invite.person.auth_user.groups.all() and \
                        group.name.startswith(invite.office.CORRESPONDENT_GROUP):
                    invite.person.auth_user.groups.add(group)

        invite.save()
        return HttpResponse('ok')


class InviteOfficeUpdateView(UpdateView):
    def post(self, request, *args, **kargs):
        invite = InviteOffice.objects.get(
            pk=int(request.POST.get('invite_pk')))
        invite.status = request.POST.get('status')
        if invite.status == 'A':
            OfficeOffices(from_office=invite.office,
                          to_office=invite.office_invite,
                          create_user=self.request.user).save()
            service_price_table = ServicePriceTable.objects.filter(
                office=invite.office,
                office_correspondent=invite.office_invite)
            if service_price_table:
                service_price_table.update(is_active=True)
        invite.save()
        return HttpResponse('ok')


class InviteTableView(CustomLoginRequiredView, ListView):
    model = Invite
    template_name = 'core/invite_table.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        table = InviteTable(
            Invite.objects.filter(
                office__id=self.kwargs.get('office_pk'),
                invite_from='O').order_by('-pk'))
        RequestConfig(self.request).configure(table)
        context['table'] = table
        return context


class InviteOfficeTableView(CustomLoginRequiredView, ListView):
    model = InviteOffice
    template_name = 'core/invite_table.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        table = InviteOfficeTable(
            InviteOffice.objects.filter(
                office__id=self.kwargs.get('office_pk')).order_by('-pk'))
        RequestConfig(self.request).configure(table)
        context['table'] = table
        return context


class InviteVerify(View):
    def get(self, request):
        user = request.user
        person = user.person
        office_pks = person.offices.active_offices().values_list(
            'pk', flat=True)

        data = []

        for invite in Invite.objects.filter(
                Q(status='N'),
                Q(
                    Q(Q(office_id__in=office_pks), Q(invite_from='P'))
                    | Q(Q(person=person), Q(invite_from='O')))):
            data.append({
                'id': invite.pk,
                'office': invite.office.legal_name,
                'person': invite.person.legal_name,
                'invite_from': invite.invite_from
            })

        return JsonResponse(data, safe=False)


class EditableListSave(CustomLoginRequiredView, View):
    """
    O nome da classe ficou generico pelo fato desta view poder ser utilizada
    em outras classes.
    """

    models = {"ServicePriceTable": ServicePriceTable}

    def post(self, request):
        items = json.loads(request.POST['items'])
        for item in items:
            model_class = self.models.get(item['model'])
            if model_class is None:
                continue
            instance = model_class.objects.get(id=item['id'])
            for field_item in item['fields']:
                setattr(instance, field_item['field'], field_item['value'])
            instance.save()

        return JsonResponse({"ok": True})


class PopupSuccessView(LoginRequiredMixin, TemplateView):
    template_name = "core/popup_success.html"


class PopupMixin:
    @property
    def is_popup(self):
        return self.request.GET.get('popup', False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_popup"] = self.is_popup
        return context


class ListUsersToInviteView(CustomLoginRequiredView, View):
    def get(self, request, *args, **kwargs):
        users = User.objects.all().values('pk', 'username', 'email',
                                          'person__name', 'person__pk')
        return JsonResponse({'data': list(users)})


class InviteMultipleUsersView(CustomLoginRequiredView, CreateView):
    form_class = InviteForm

    def post(self, request, *args, **kwargs):
        if self.request.POST.get('persons') and self.request.POST.get(
                'office'):
            persons = self.request.POST.getlist('persons')
            office_pk = self.request.POST.get('office')
            for person_pk in persons:
                person = Person.objects.get(pk=person_pk)
                office = Office.objects.get(pk=office_pk)
                Invite.objects.create(
                    create_user=request.user,
                    person=person,
                    office=office,
                    status='N',
                    invite_from='O')
            return HttpResponseRedirect(
                reverse_lazy('office_update', kwargs={'pk': office_pk}))
        return reverse_lazy('office_list')


class TypeaHeadGenericSearch(View):
    """
    Responsavel por gerar os filtros do campo typeahead
    """

    def get(self, request, *args, **kwargs):
        module = importlib.import_module(self.request.GET.get('module'))
        model = getattr(module, self.request.GET.get('model'))
        field = request.GET.get('field')
        q = request.GET.get('q')
        extra_params = json.loads(self.request.GET.get('extra_params', {}))
        office = get_office_session(self.request)
        forward = request.GET.get(
            'forward') if request.GET.get('forward') != 'undefined' else None
        forward_value = request.GET.get('forwardValue')
        forward_params = ''
        if forward:
            if model._meta.get_field(
                    forward).get_internal_type() == 'ForeignKey':
                forward = '{}__id'.format(forward)
                extra_params['forward_field'] = forward
        if forward and int(forward_value):
            forward_params = {
                '{}'.format(forward): forward_value,
            }
        data = self.get_data(module, model, field, q, office, forward_params,
                             extra_params, *args, **kwargs)
        return JsonResponse(data, safe=False)

    @staticmethod
    def get_data(module, model, field, q, office, forward_params, extra_params,
                 *args, **kwargs):
        params = {
            '{}__unaccent__icontains'.format(field): q,
        }
        data = model.objects.filter(**params).annotate(value=F(field)).values(
            'id', 'value').order_by(field)
        if issubclass(model, OfficeMixin) or hasattr(model, 'offices'):
            data.filter(office=office)
        return list(data)


class TypeaHeadInviteUserSearch(TypeaHeadGenericSearch):
    @staticmethod
    def get_data(module, model, field, q, office, forward_params, extra_params,
                 *args, **kwargs):
        data = []        
        users = User.objects.filter(
            Q(person__legal_name__unaccent__icontains=q) 
            | Q(username__unaccent__icontains=q) | Q(email__unaccent__icontains=q))
        for user in users:            
            if hasattr(user, 'person'):
                data.append(
                    {
                        'id': user.person.id,
                        'value': user.person.legal_name + ' ({})'.format(user.username),
                        'data-value-txt': user.person.legal_name + ' ({} - {})'.format(
                            user.username, user.email)
                    }
                )
        return list(data)


class CityAutoCompleteView(TypeaHeadGenericSearch):
    @staticmethod
    def get_data(module, model, field, q, office, forward_params, extra_params,
                 *args, **kwargs):
        data = []
        cities = City.objects.filter(**forward_params) if forward_params else City.objects.all()
        forward_field = extra_params.get('forward_field', None)
        if forward_field:
            forward_field = forward_field.replace('__', '.')
        for city in cities.filter(Q(name__unaccent__icontains=q) |
                                  Q(state__initials__exact=q)|
                                  Q(state__country__name__unaccent__contains=q)):
            data.append({'id': city.id,
                         'data-value-txt': city.__str__(),
                         'data-forward-id': eval('city.{}'.format(forward_field)) if forward_field else 0
                         })
        return list(data)


class CitySelect2Autocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = City.objects.filter(is_active=True)
        court_district = self.forwarded.get('court_district', None)
        if court_district:
            qs = qs.filter(court_district_id=court_district)
        if self.q:
            filters = Q(name__unaccent__icontains=self.q)
            filters |= Q(state__initials__unaccent__icontains=self.q)
            qs = qs.filter(filters)
        return qs.order_by('name')

    def get_result_label(self, result):
        return "{}".format(result.__str__())


class ZipCodeCitySelect2Autocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = City.objects.none()
        if self.q:
            q_list = self.q.split('|')
            if q_list and len(q_list) == 2:
                qs = City.objects.filter(is_active=True)
                filters = Q(name__unaccent__icontains=q_list[0])
                filters &= Q(state__initials__unaccent__icontains=q_list[1])
                qs = qs.filter(filters)
        return qs.order_by('name')

    def get_result_label(self, result):
        return "{}".format(result.__str__())


class ClientAutocomplete(TypeaHeadGenericSearch):
    @staticmethod
    def get_data(module, model, field, q, office, forward_params, extra_params,
                 *args, **kwargs):
        data = []
        for client in Person.objects.filter(
                Q(legal_name__unaccent__icontains=q), Q(is_customer=True, ),
                Q(offices=office)):
            data.append({'id': client.id, 'data-value-txt': client.__str__()})
        return list(data)


class ClientSelect2Autocomplete(autocomplete.Select2QuerySetView):
    @property
    def base_queryset(self):
        return Person.objects.all().filter(offices=get_office_session(self.request), is_customer=True, is_active=True)

    def get_queryset(self):
        qs = self.base_queryset

        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.legal_name


class ClientFilterSelect2Autocomplete(ClientSelect2Autocomplete):
    @property
    def base_queryset(self):
        return Person.objects.all().filter(offices=get_office_session(self.request), is_customer=True)


class PersonCompanyRepresentativeSelect2Autocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Person.objects.all().filter(offices=get_office_session(self.request), legal_type='F', is_active=True)

        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs

    def get_result_label(self, result):
        return result.legal_name


class OfficeAutocomplete(TypeaHeadGenericSearch):
    @staticmethod
    def get_data(module, model, field, q, office, forward_params):
        data = []
        for item in Office.objects.filter(
                Q(name__unaccent__icontains=q), Q(offices=office)):
            data.append({'id': item.id, 'data-value-txt': item.__str__()})
        return list(data)


class CorrespondentAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Person.objects.none()
        office = get_office_session(self.request)
        qs = Person.objects.correspondents(office_id=office.id)
        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs


class OfficeCorrespondentAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Office.objects.none()
        office = get_office_session(self.request)
        qs = office.related_offices
        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs


class RequesterAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Person.objects.none()
        qs = Person.objects.requesters().filter(offices=get_office_session(self.request))
        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs


class OriginRequesterAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Office.objects.none()
        office = get_office_session(self.request)
        qs = office.related_offices
        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs


class ServiceAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Person.objects.none()
        qs = Person.objects.services().filter(offices=get_office_session(self.request))
        if self.q:
            qs = qs.filter(legal_name__unaccent__icontains=self.q)
        return qs


class TypeaHeadInviteOfficeSearch(TypeaHeadGenericSearch):
    @staticmethod
    def get_data(module, model, field, q, office, forward_params, extra_params,
                 *args, **kwargs):
        data = []
        for office in Office.objects.filter(
                Q(legal_name__unaccent__icontains=q)):
            data.append({'id': office.id, 'data-value-txt': office.legal_name})
        return list(data)


class OfficeMembershipInactiveView(UpdateView):
    model = OfficeMembership
    success_message = "Usuário desvinculado com sucesso!"

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            pks = request.POST.getlist('selection')

            try:
                for record in self.model.objects.filter(pk__in=pks):
                    if not Task.objects.filter(
                            ~Q(
                                Q(task_status=TaskStatus.FINISHED)
                                | Q(task_status=TaskStatus.REFUSED)
                                | Q(task_status=TaskStatus.REFUSED_SERVICE)
                                | Q(task_status=TaskStatus.BLOCKEDPAYMENT)),
                            Q(
                                Q(person_asked_by=record.person)
                                | Q(person_executed_by=record.person)
                                | Q(person_distributed_by=record.person))):
                        record.is_active = False
                        record.save()
                        messages.success(self.request, self.success_message)
                        try:
                            DefaultOffice.objects.filter(
                                auth_user=record.person.auth_user,
                                office=record.office).delete()
                        except:
                            pass
                    else:
                        messages.error(
                            self.request,
                            "O usuário {} não pode ser desvinculado do escritório, uma vez que"
                            " ainda existem OS a serem cumpridas por ele".
                            format(record.person))
            except ProtectedError as e:
                qs = e.protected_objects.first()
                messages.error(
                    self.request,
                    delete_error_protected(
                        str(self.model._meta.verbose_name), qs.__str__()))

        # http://django-tables2.readthedocs.io/en/latest/pages/generic-mixins.html
        if self.success_url:
            return HttpResponseRedirect(self.success_url)
        else:
            return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        if self.request.META.get('HTTP_REFERER'):
            return self.request.META.get('HTTP_REFERER')
        return reverse(
            'office_update', kwargs={'pk': self.kwargs['office_pk']})


class OfficeOfficesInactiveView(UpdateView):
    model = Office
    success_message = "Escritório {} desvinculado com sucesso!"

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            pks = request.POST.getlist('selection')
            try:
                for record in self.model.objects.filter(pk__in=pks):
                    if not Task.objects.filter(
                        (Q(
                            Q(task_status=TaskStatus.REQUESTED)
                            | Q(task_status=TaskStatus.ACCEPTED_SERVICE)
                            | Q(task_status=TaskStatus.RETURN)
                            | Q(task_status=TaskStatus.OPEN)
                            | Q(task_status=TaskStatus.ACCEPTED)
                            | Q(task_status=TaskStatus.DONE))
                         | Q(
                             Q(parent__task_status=TaskStatus.OPEN)
                             | Q(parent__task_status=TaskStatus.ACCEPTED)
                             | Q(parent__task_status=TaskStatus.DONE))),
                            parent__office=self.kwargs['office_pk'],
                            office=record.pk):
                        current_office = Office.objects.get(
                            pk=self.kwargs['office_pk'])
                        OfficeOffices.objects.filter(from_office=current_office,
                                                     to_office=record).delete()

                        service_price_table = ServicePriceTable.objects.filter(
                            office=self.kwargs['office_pk'],
                            office_correspondent=record.pk)
                        if service_price_table:
                            service_price_table.update(is_active=False)

                        messages.success(self.request,
                                         self.success_message.format(record))
                    else:
                        messages.error(
                            self.request,
                            "O escritório {} não pode ser desvinculado, uma vez que"
                            " ainda existem OS a serem cumpridas por ele".
                            format(record))
            except ProtectedError as e:
                qs = e.protected_objects.first()
                messages.error(
                    self.request,
                    delete_error_protected(
                        str(self.model._meta.verbose_name), qs.__str__()))

        if self.success_url:
            return HttpResponseRedirect(self.success_url)
        else:
            return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse(
            'office_update', kwargs={'pk': self.kwargs['office_pk']}))


class TagsInputPermissionsView(View):
    def get(self, request, office_pk, *args, **kwargs):
        groups = Office.objects.get(pk=office_pk).office_groups.all()
        data = []
        for group in groups:
            data.append({'value': group.group.pk, 'text': group.label_group})
        return JsonResponse(data, safe=False)


class OfficeSessionSearch(View):
    def get(self, request, *args, **kwargs):
        q = request.GET.get('office_legal_name', '')
        if hasattr(request.user, 'person'):
            offices = request.user.person.offices.all()
        else:
            offices = Office.objects.all()
        selected_offices = list(
            offices.filter(legal_name__icontains=q).values_list(
                'id', flat=True))
        data = []
        for office in offices:
            show = True if office.pk in selected_offices else False
            data.append({'id': office.pk, 'show': show})
        return JsonResponse(data, safe=False)


class OfficeSearch(View):
    def get(self, request, *args, **kwargs):
        q_string = request.GET.get('office_legal_name', '')
        offices = Office.objects.all()
        if q_string != '':
            selected_offices = list(
                offices.filter(legal_name__icontains=q_string).values_list(
                    'id', flat=True))
        else:
            selected_offices = []
        data = []
        for office in offices:
            show = True if office.pk in selected_offices else False
            data.append({'id': office.pk, 'show': show})
        return JsonResponse(data, safe=False)


class ValidatePassword(View):
    def post(self, request, *args, **kwargs):
        password = request.POST.get('password')
        data = {}
        try:
            password_validation.validate_password(password)
            data['valid'] = True
        except ValidationError as error:
            data['valid'] = False
            message = error.messages
            message = [x + '<br>' for x in message]
            data['message'] = message

        return JsonResponse(data, safe=False)


class ValidateUsername(View):
    def post(self, request, *args, **kwargs):
        username = request.POST.get('username')
        data = {'valid': True}
        if User.objects.filter(username=username).first():
            data['valid'] = False

        return JsonResponse(data, safe=False)


class ValidateEmail(View):
    def post(self, request, *args, **kwargs):
        email = request.POST.get('email')
        data = {'valid': True}
        if User.objects.filter(email=email).first():
            data['valid'] = False
        if User.objects.filter(username=email).first():
            data['valid'] = False
        return JsonResponse(data, safe=False)


class ValidateCpfCnpj(View):
    def post(self, request, *args, **kwargs):
        cpf_cnpj = request.POST.get('cpf_cnpj')
        data = {'valid': False}
        if cpf_is_valid(cpf_cnpj) or cnpj_is_valid(cpf_cnpj):
            data = {'valid': True}
        return JsonResponse(data, safe=False)


class CheckCpfCnpjExist(View):
    def post(self, request, *args, **kwargs):
        model_name = request.POST.get('model')
        cpf_cnpj = request.POST.get('cpf_cnpj')
        data = check_cpf_cnpj_exist(model_name, cpf_cnpj)
        return JsonResponse(data, safe=False)


class ContactMechanismCreateView(ViewRelatedMixin, CreateView):
    model = ContactMechanism
    form_class = ContactMechanismForm
    success_message = CREATE_SUCCESS_MESSAGE

    def __init__(self):
        super().__init__(
            related_model=Person,
            related_model_name='person',
            related_field_pk='person')

    def get_success_url(self):
        return reverse('person_update', args=(self.kwargs.get('person_pk'), ))

    def form_valid(self, form):
        # Se tipo do mecanismo de contato for e-mail validar se é válido
        if form.instance.contact_mechanism_type.is_email():
            try:
                validate_email(form.instance.description)
            except ValidationError as e:
                messages.add_message(self.request, messages.ERROR,
                                     'Informe um endereço de e-mail válido.')
                return self.form_invalid(form)
        return super().form_valid(form)


class ContactMechanismUpdateView(UpdateView):
    model = ContactMechanism
    form_class = ContactMechanismForm
    success_message = UPDATE_SUCCESS_MESSAGE

    def get_success_url(self):
        return reverse('person_update', args=(self.kwargs.get('person_pk'), ))

    def form_valid(self, form):
        if form.instance.contact_mechanism_type.is_email():
            try:
                validate_email(form.instance.description)
            except ValidationError as e:
                messages.add_message(self.request, messages.ERROR,
                                     'Informe um endereço de e-mail válido.')
                return self.form_invalid(form)
        try:
            # TODO - Verificar se é a melhor forma de tratar duplicidades
            return super().form_valid(form)
        except IntegrityError as e:
            messages.add_message(self.request, messages.ERROR,
                                 'Registro já existente.')
            return self.form_invalid(form)


class ContactMechanismDeleteView(MultiDeleteViewMixin):
    model = ContactMechanism
    form_class = ContactMechanismForm
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)

    def get_success_url(self):
        return reverse(
            'person_update', kwargs={'pk': self.kwargs['person_pk']})


class ContactMechanismOfficeCreateView(ViewRelatedMixin, CreateView):
    model = ContactMechanism
    form_class = ContactMechanismForm
    success_message = CREATE_SUCCESS_MESSAGE

    def __init__(self):
        super().__init__(
            related_model=Office,
            related_model_name='office',
            related_field_pk='office')

    def get_success_url(self):
        return reverse('office_update', args=(self.kwargs.get('office_pk'), ))

    def form_valid(self, form):
        # Se tipo do mecanismo de contato for e-mail validar se é válido
        if form.instance.contact_mechanism_type.is_email():
            try:
                validate_email(form.instance.description)
            except ValidationError as e:
                messages.add_message(self.request, messages.ERROR,
                                     'Informe um endereço de e-mail válido.')
                return self.form_invalid(form)
        return super().form_valid(form)


class ContactMechanismOfficeUpdateView(ContactMechanismUpdateView):
    def get_success_url(self):
        return reverse('office_update', args=(self.kwargs.get('office_pk'), ))


class ContactMechanismOfficeDeleteView(ContactMechanismDeleteView):
    model = ContactMechanism
    form_class = ContactMechanismForm
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)

    def get_success_url(self):
        return reverse(
            'office_update', kwargs={'pk': self.kwargs['office_pk']})


class TeamListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = Team
    table_class = TeamTable


class TeamCreateView(AuditFormMixin, CreateView):
    model = Team
    form_class = TeamForm
    success_url = reverse_lazy('team_list')
    success_message = CREATE_SUCCESS_MESSAGE

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class TeamUpdateView(CustomLoginRequiredView, UpdateView):
    model = Team
    form_class = TeamForm
    success_url = reverse_lazy('team_list')
    success_message = UPDATE_SUCCESS_MESSAGE

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class TeamDeleteView(CustomLoginRequiredView, MultiDeleteViewMixin):
    model = Team
    success_url = reverse_lazy('team_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)


class MediaFileView(LoginRequiredMixin, View):
    def get(self, request, path):
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, path)):
            return static_serve_view(
                self.request, path, document_root=settings.MEDIA_ROOT)
        raise Http404('Arquivo não existe')


class OfficePermissionRequiredMixin(PermissionRequiredMixin):
    def has_permission(self):
        guardian = ObjectPermissionChecker(self.request.user)
        office_session = get_office_session(self.request)
        perms = self.get_permission_required()
        for perm in perms:
            if not guardian.has_perm(perm.name, office_session):
                return False
        return True


class PersonCustomerCreateTaskBulkCreate(View):
    form = PersonForm

    def post(self, *args, **kwargs):
        create_user = self.request.user
        office_session = get_office_session(self.request)
        form = self.form(self.request.POST)
        status = 200
        if form.is_valid():
            form.instance.create_user = create_user
            form.instance.is_active = True
            instance = form.save()
            create_person_office_relation(instance, self.request.user, office_session)
            data = {'id': instance.id, 'text': instance.legal_name}
        else:
            status = 500
            data = {'error': True, 'errors': []}
            for error in form.errors:
                data['errors'].append(error)

        return JsonResponse(json.loads(json.dumps(data)), status=status)


class ImportCityList(PermissionRequiredMixin, CustomLoginRequiredView,
                     TemplateView):
    permission_required = ('superuser', )
    template_name = 'core/import_city_list.html'
    form_class = ImportCityListForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_name_plural'] = 'Importação de Cidades'
        context['page_title'] = 'Importação de Cidade'
        return context

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(*args, **kwargs)
        form = self.form_class(request.POST, request.FILES)
        status = 200
        if form.is_valid():
            file_xls = form.save(commit=False)
            file_xls.office = get_office_session(request)
            file_xls.create_user = request.user
            file_xls.start = timezone.now()
            file_xls.log_file = "{\"status\": \"Em andamento\" , \"current_line\": 0, \"total_lines\": 0}"
            file_xls.save()

            import_xls_city_list.delay(file_xls.pk)

            context['show_modal_progress'] = True
            context['file_xls_id'] = file_xls.id
            context['file_name'] = request.FILES['file_xls'].name
        else:
            status = 500
            ret = {'status': 'false', 'message': form.errors}
            messages.error(request, form.errors)
            return JsonResponse(ret, status=status)
        context.pop('view')
        return JsonResponse(json.loads(json.dumps(context)), status=status)

    def get(self, request, *args, **kwargs):

        context = self.get_context_data(**kwargs)
        if request.GET.get('file_xls_id'):
            context.pop('view')
            file_xls_id = request.GET.get('file_xls_id')
            file_xls = self.form_class._meta.model.objects.filter(pk=file_xls_id).first()
            context['file_xls_id'] = file_xls.id
            context['log_file'] = json.loads(file_xls.log_file) if file_xls.log_file else ''
            return JsonResponse(json.loads(json.dumps(context)), status=200)
        else:
            return super().get(request, *args, **kwargs)


class NewRegister(TemplateView):
    template_name = 'account/register.html'

    def get_context_data(self):
        context = super().get_context_data()
        return context

    def post(self, request, *args, **kwargs):
        try:
            username = email = request.POST.get('email')
            password = request.POST.get('password')
            first_name = request.POST.get('name').split(' ')[0]
            last_name = ' '.join(request.POST.get('name').split(' ')[1:])
            office_name = request.POST.get('office')
            office_cpf_cnpj = request.POST.get('cpf_cnpj')
            user = User.objects.create(username=username, last_name=last_name[0:30], first_name=first_name, email=email)
            user.set_password(password)
            user.save()
            authenticate(username=username, password=password)
            auth_login(request, user, backend='allauth.account.auth_backends.AuthenticationBackend')
            request_invite = request.POST.get('request_invite')
            office_pk = request.POST.get('office_pk')

            send_mail_sign_up(first_name, email)
            url_return = post_create_new_user(request_invite, office_name, user, office_cpf_cnpj, office_pk)
            return JsonResponse({'redirect': reverse_lazy(url_return)})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})


class SocialRegister(TemplateView):
    template_name = 'account/social_register.html'

    def post(self, request, *args, **kwargs):
        try:
            office_name = request.POST.get('office')
            office_cpf_cnpj = request.POST.get('cpf_cnpj')
            user = request.user
            office_pk = request.POST.get('office_pk')
            request_invite = request.POST.get('request_invite')
            url_return = post_create_new_user(request_invite, office_name, user, office_cpf_cnpj, office_pk)
            if not request_invite:
                send_mail_sign_up(user.first_name, user.email)

            return JsonResponse({'redirect': reverse_lazy(url_return)})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})


class TermsView(TemplateView):
    template_name = 'account/terms/terms_and_conditions.html'


class OfficeProfileDataView(View):
    def get(self, request, *args, **kwargs):
        office_id = kwargs.get('pk', None)
        office = get_office_by_id(office_id) if office_id else get_office_session(request)
        return JsonResponse(OfficeSerializer(office).data)

    def post(self, request, *args, **kwargs):
        office_session = get_office_session(request)
        office_id = kwargs.get('pk', None)
        if office_id and office_session != get_office_by_id(office_id):
            return JsonResponse({'error': 'Só é possível alterar o escritório da sessão'})
        office_serializer = OfficeSerializer(data=request.POST, instance=get_office_session(request))
        if office_serializer.is_valid():
            office_serializer.save()
            return JsonResponse(office_serializer.data)
        return JsonResponse({'error': office_serializer.errors})


class OfficeProfileView(TemplateView):
    template_name = 'core/office_profile.html'

    model = Office
    form_class = OfficeProfileForm    
    success_message = UPDATE_SUCCESS_MESSAGE
    object_list_url = 'office_list'

    def get_context_data(self, **kwargs):
        office_id = kwargs.get('pk', None)
        office_session = get_office_session(self.request)
        office_profile = get_office_by_id(office_id)
        self.object = office_profile or office_session

        kwargs.update({
            'table':
                AddressOfficeTable(self.object.get_address()),
            'table_members':
                OfficeMembershipTable(
                    self.object.officemembership_set.filter(
                        is_active=True,
                        person__auth_user__isnull=False,
                        person__auth_user__is_superuser=False
                    ).exclude(
                        person__auth_user=self.request.user)),
            'table_offices':
                OfficeTable(self.object.offices.all().order_by('legal_name')),
            'table_contact_mechanism':
                ContactMechanismOfficeTable(self.object.contactmechanism_set.all()),
            'table_billing_details':
                BillingDetailsTable(self.object.billingdetails_office.all()),
        })
        data = super().get_context_data(**kwargs)
        data['office'] = self.object
        data['is_session_office'] = False
        if self.object == office_session:
            data['is_session_office'] = True
            data['inviteofficeform'] = InviteForm(self.request.POST) \
                if InviteForm(self.request.POST).is_valid() else InviteForm()
            RequestConfig(
                self.request, paginate=False).configure(
                    kwargs.get('table_members'))
            RequestConfig(
                self.request, paginate=False).configure(
                    kwargs.get('table_offices'))
            data['form_office'] = self.form_class(instance=data['office'])
            data['form_address'] = AddressForm()
            data['form_contact_mechanism'] = ContactMechanismForm()
            data['form_billing_details'] = BillingAddressCombinedForm
            data['areas_expertise'] = AreaOfExpertise.objects.annotate(
                total_office=Sum(
                    Case(
                        When(offices=self.object, then=1),
                        default=0, output_field=IntegerField()
                    ))).values('id', 'area', 'total_office')
        return data


class OfficeAreasOfExpertiseUpdateView(View):

    def post(self, request, *args, **kwargs):
        office = get_office_session(request)
        areas_of_expoertise = AreaOfExpertise.objects.all()
        list_areas = []
        for area in areas_of_expoertise:
            if int(request.POST.get('area_{}'.format(area.id), 0)) == 0:
                area.offices.remove(office)
            else:
                list_areas.append(area.area)
                area.offices.add(office)
        return JsonResponse({'status': 'ok',
                             'areas': list_areas}, status=200)


class OfficeProfileUpdateView(UpdateView):
    model = Office
    form_class = OfficeProfileForm

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST, request.FILES, instance=get_office_session(request))
        if form.is_valid():
            try:
                form.save()
                return HttpResponseRedirect(reverse('office_profile'))
            except IntegrityError as e:
                if 'cpf_cnpj' in e.args[0]:
                    error = {'errors': {'cpf_cnpj': ['Já existe um escritório com o CPF ou CNPJ informado']}}
                else:
                    error = {'errors': {'__all__': [e.__str__()]}}
                return JsonResponse(error, status=500)
            except Exception as e:
                return JsonResponse({'errors': {'__all__': [e.__str__()]}}, status=500)
        else:
            return JsonResponse({'errors': form.errors}, status=400)

    def form_invalid(self, form):
        return JsonResponse({'errors': form.errors}, status=400)

    def get_success_url(self):
        return reverse('office_profile')    


class OfficeProfileAddressCreateView(ViewRelatedMixin, CreateView):
    model = Address
    form_class = AddressForm
    success_message = CREATE_SUCCESS_MESSAGE

    def __init__(self):
        super().__init__(
            related_model=Office,
            related_model_name='office',
            related_field_pk='office')       

    def form_valid(self, form):
        form.instance.create_user = self.request.user
        form.instance.office = get_office_session(self.request)
        self.object = form.save()        
        return JsonResponse(AddressSerializer(form.instance).data)        

    def get_success_url(self):
        return reverse('office_profile')    


class OfficeProfileAddressUpdateView(CustomLoginRequiredView, UpdateView):
    model = Address
    form_class = AddressForm

    def form_invalid(self, form):
        return JsonResponse({'errors': form.errors}, status=400)

    def form_valid(self, form):
        form.instance.create_user = self.request.user
        form.instance.office = get_office_session(self.request)
        self.object = form.save()        
        return JsonResponse(AddressSerializer(form.instance).data)        

    def get_success_url(self):
        return reverse('office_profile')


class OfficeProfileAddressDeleteView(CustomLoginRequiredView, View):
    def post(self, request, *args, **kwargs):
        address_ids = request.POST.getlist('ids[]')
        Address.objects.filter(pk__in=address_ids).delete()
        return JsonResponse({'status': 'ok'})


class OfficeProfileAddressDataView(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):        
        address = Address.objects.get(pk=pk)
        address_serializer = AddressSerializer(address)
        return JsonResponse(address_serializer.data)


class OfficeProfileContactMechanismDataView(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):        
        contact_mechanism = ContactMechanism.objects.get(pk=pk)
        contact_mechanism_serializer = ContactMechanismSerializer(contact_mechanism)
        return JsonResponse(contact_mechanism_serializer.data)


class OfficeProfileContactMechanismCreateView(ViewRelatedMixin, CreateView):
    model = ContactMechanism
    form_class = ContactMechanismForm
    success_message = CREATE_SUCCESS_MESSAGE

    def __init__(self):
        super().__init__(related_model=Office, related_model_name='office', related_field_pk='office')

    def form_valid(self, form):
        form.instance.create_user = self.request.user
        form.instance.office = get_office_session(self.request)
        self.object = form.save()
        return JsonResponse(ContactMechanismSerializer(self.object).data)        

    def get_success_url(self):
        return reverse('office_profile')


class OfficeProfileContactMechanismUpdateView(CustomLoginRequiredView, UpdateView):
    model = ContactMechanism
    form_class = ContactMechanismForm

    def form_invalid(self, form):
        return JsonResponse({'errors': form.errors}, status=400)

    def form_valid(self, form):
        form.instance.create_user = self.request.user
        form.instance.office = get_office_session(self.request)
        self.object = form.save()        
        return JsonResponse(ContactMechanismSerializer(form.instance).data)

    def get_success_url(self):
        return reverse('office_profile')        


class OfficeProfileContactMechanismDeleteView(CustomLoginRequiredView, View):
    def post(self, request, *args, **kwargs):
        contact_ids = request.POST.getlist('ids[]')
        ContactMechanism.objects.filter(pk__in=contact_ids).delete()
        return JsonResponse({'status': 'ok'})    


class CustomGoogleOAuth2Adapter(GoogleOAuth2Adapter):
    def get_callback_url(self, request, app):
        callback_url = reverse(self.provider_id + "_callback")
        protocol = self.redirect_uri_protocol
        return build_absolute_uri(None, callback_url, protocol)            


oauth2_login = OAuth2LoginView.adapter_view(CustomGoogleOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(CustomGoogleOAuth2Adapter)


class StateAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return State.objects.none()
        qs = State.objects.all()
        if self.q:
            qs = qs.filter(name__unaccent__icontains=self.q)
        return qs


class CustomMessagesView(View):
    def get(self, request, *args, **kwargs):
        messages = CustomMessage.objects.filter(
            initial_date__lte=timezone.now(),
            finish_date__gte=timezone.now())
        return JsonResponse(
            CustomMessageSerializer(messages, many=True).data, safe=False)


class TeamFilterSelect2Autocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Team.objects.filter(office=get_office_session(self.request))
        if self.q:
            filters = Q(name__unaccent__icontains=self.q)
            qs = qs.filter(filters)
        return qs.order_by('name')

    def get_result_label(self, result):
        return "{}".format(result.__str__())
