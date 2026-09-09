from django.urls import reverse_lazy
import django_tables2 as tables
from django_tables2.utils import A

from core.tables import CheckBoxMaterial
from .models import CostCenter, ServicePriceTable, PolicyPrice


class CostCenterTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequence = ('selection', 'name', 'is_active', 'legacy_code')
        model = CostCenter
        fields = ['selection', 'name', 'is_active', 'legacy_code']
        attrs = {"class": "table stable-striped table-bordered"}
        empty_text = "Não existem centros de custo cadastrados"
        row_attrs = {
            'data_href': lambda record: '/financeiro/centros-de-custos/' + str(record.pk) + '/'
        }
        order_by = 'name'


class ServicePriceTableTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)
    value = tables.Column(attrs={"editable": True, "mask": "money"})

    class Meta:
        sequence = ('selection', 'office', 'office_correspondent', 'office_network', 'type_task', 'state',
                    'court_district', 'court_district_complement', 'city', 'client', 'policy_price', 'value',
                    'is_active')
        model = ServicePriceTable
        fields = ('selection', 'office', 'office_correspondent', 'office_network', 'type_task', 'court_district',
                  'state', 'client', 'policy_price', 'value', 'is_active', 'court_district_complement', 'city')
        attrs = {"class": "table stable-striped table-bordered"}
        empty_text = "Não existe tabela de preços cadastrada."
        row_attrs = {
            'data_href': lambda record: reverse_lazy('servicepricetable_update', args=(record.pk,))
        }
        order_by = ('office', 'office_correspondent', 'office_network')


class ServicePriceTableTaskTable(tables.Table):
    office_correspondent = tables.LinkColumn('office_profile', args=[A('office_correspondent_id')], orderable=False,
                                             verbose_name='Escritório correspondente',
                                             attrs={
                                                 'a': {'target': '_blank'}
                                             })
    type_task = tables.Column(orderable=False, verbose_name='Tipo de serviço')
    office_network = tables.Column(orderable=False, verbose_name='Rede')
    court_district = tables.Column(orderable=False, verbose_name='Comarca')
    court_district_complement = tables.Column(orderable=False, verbose_name='Complemento da comarca')
    city = tables.Column(orderable=False, verbose_name='Cidade')
    state = tables.Column(orderable=False, verbose_name='UF')
    client = tables.Column(orderable=False, verbose_name='Cliente')    
    value = tables.Column(orderable=False, verbose_name='Valor*')
    office_rating = tables.Column(orderable=False, verbose_name='Avaliação*')
    office_return_rating = tables.Column(orderable=False, verbose_name='OS Retornadas')
    finished_by_rate = tables.Column(orderable=False, verbose_name='OS Finalizadas')

    class Meta:
        sequence = ('office_correspondent', 'type_task', 'office_network', 'state', 'court_district',
                    'court_district_complement', 'city', 'client', 'value', 'office_rating',
                    'finished_by_rate', 'office_return_rating')
        model = ServicePriceTable
        fields = ('office_correspondent', 'type_task', 'office_network', 'court_district', 'state', 'client', 'value',
                  'court_district_complement', 'office_rating', 'finished_by_rate', 'office_return_rating', 'city')
        attrs = {"class": "table stable-striped table-bordered correspondents-table", "id": "correspondents-table"}
        empty_text = "Não existe tabela de preços cadastrada para o tipo de serviço selecionado."
        order_by = ("value", "office_rating", "office_return_rating", "office_correspondent__legal_name")
        row_attrs = {
            'id': lambda record: 'office-{}'.format(record.pk),
            'data-id': lambda record: record.pk,
            'data-value': lambda record: record.value,
            'data-price-category': lambda record: record.policy_price.category,
            'data-formated-value': lambda record: record.value.__str__(),
            'data-office-public': lambda record: record.office_correspondent.public_office if record.office_correspondent else False,
            'data-office-txt': lambda record: record.office.__str__(),
            'class': 'tr_select'
        }


class PolicyPriceTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta: 
        model = PolicyPrice
        fields = ('selection', 'name', 'category', 'billing_moment', 'is_active')
        empty_text = "Não existe tipo de preço cadastrado."
        row_attrs = {
            'data_href': lambda record: reverse_lazy('policyprice_update', args=(record.pk,))
        }