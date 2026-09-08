import json
from django.shortcuts import render
from django.views import View
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse, Http404
from billing.models import *
from core.models import AddressType, Address
from core.views import CustomLoginRequiredView
from core.utils import get_office_session
from .forms import BillingAddressCombinedForm
from .serializers import BillingDetailSerializer


class BillingDetailDataView(CustomLoginRequiredView, View):
    def get(self, request, pk, *args, **kwargs):
        billing_detail = BillingDetails.objects.get(pk=pk)
        billing_serializer = BillingDetailSerializer(billing_detail)
        return JsonResponse(billing_serializer.data)


class BillingDetailByOffice(CustomLoginRequiredView, View):
    def get(self, request, *args, **kwargs):
        office = get_office_session(request)
        billing_detail = BillingDetails.objects.filter(office=office).first()
        billing_serializer = BillingDetailSerializer(billing_detail)
        return JsonResponse(billing_serializer.data)


class BillingDetailBaseView(object):
    def __init__(self):
        self.office = None
        self.address = None

    def create_update_address(self, address, form):
        address.address_type = form.cleaned_data['address_type']
        address.street = form.cleaned_data['street']
        address.number = form.cleaned_data['number']
        address.complement = form.cleaned_data['complement']
        address.city_region = form.cleaned_data['city_region']
        address.zip_code = form.cleaned_data['zip_code']
        address.city = form.cleaned_data['city']
        address.state = address.city.state
        address.country = address.state.country
        address.create_user = self.request.user
        address.save()
        self.address = address

    def create_update_billing_detail(self, billing_detail, form):
        billing_detail.card_name = form.cleaned_data['card_name']
        billing_detail.full_name = form.cleaned_data['full_name']
        billing_detail.email = form.cleaned_data['email']
        billing_detail.cpf_cnpj = form.cleaned_data['cpf_cnpj']
        billing_detail.cpf = form.cleaned_data['cpf']
        billing_detail.birth_date = form.cleaned_data['birth_date']
        billing_detail.phone_number = form.cleaned_data['phone_number']
        billing_detail.billing_address = self.address
        billing_detail.office = self.office
        billing_detail.create_user = self.request.user
        billing_detail.save()


class BillingDetailAjaxUpdate(CustomLoginRequiredView, View, BillingDetailBaseView):
    def post(self, request, *args, **kwargs):
        self.office = get_office_session(request)
        data = {k: v for k, v in request.POST.items()}
        data['address_type'] = AddressType.objects.filter(name='Comercial').first().id
        form = BillingAddressCombinedForm(data)
        instance = BillingDetails.objects.filter(pk=kwargs.get('pk')).first()
        if form.is_valid() and instance:
            # salva o endereço
            address = instance.billing_address
            self.create_update_address(address, form)

            # salva o billing detail usando o endereço informado
            billing_detail = instance
            self.create_update_billing_detail(billing_detail, form)

            return JsonResponse({'billing_detail_id': billing_detail.id,
                                 'action': 'atualizado'}, status=200)
        else:
            return JsonResponse({'errors': form.errors}, status=500)


class BillingDetailAjaxCreate(CustomLoginRequiredView, View, BillingDetailBaseView):
    def post(self, request, *args, **kwargs):
        self.office = get_office_session(request)
        data = {k: v for k, v in request.POST.items()}
        data['address_type'] = AddressType.objects.filter(name='Comercial').first().id
        form = BillingAddressCombinedForm(data)
        if form.is_valid():
            # salva o endereço
            address = Address()
            self.create_update_address(address, form)

            # salva o billing detail usando o endereço informado
            billing_detail = BillingDetails()
            self.create_update_billing_detail(billing_detail, form)

            return JsonResponse({'billing_detail_id': billing_detail.id,
                                 'action': 'criado'}, status=200)
        else:
            return JsonResponse({'errors': form.errors}, status=500)


class BillingDetailAjaxDelete(View):
    def post(self, request, *args, **kwargs):
        ids = request.POST.getlist('ids[]')
        BillingDetails.objects.filter(pk__in=ids).delete()
        return JsonResponse({'status': 'ok'})
