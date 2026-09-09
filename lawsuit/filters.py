from .models import CourtDistrict, State, Movement, LawSuit, Instance
import django_filters
from django_filters import rest_framework as filters


class CourtDistrictFilter(filters.FilterSet):
    state = filters.CharFilter(field_name="state__initials", lookup_expr='iexact')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')

    class Meta:
        model = CourtDistrict
        fields = ['state', 'name']


class InstanceFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    legacy_code = filters.CharFilter(field_name='legacy_code', lookup_expr='exact')

    class Meta:
        model = Instance
        fields = ['legacy_code', 'name']


class MovementFilter(filters.FilterSet):
    legacy_code = filters.CharFilter(field_name='legacy_code', lookup_expr='iexact')
    law_suit_number = filters.CharFilter(field_name='law_suit__law_suit_number', lookup_expr='iexact')
    type_movement_legacy_code = filters.CharFilter(field_name='type_movement__legacy_code', lookup_expr='iexact')

    class Meta:
        model = Movement
        fields = ['legacy_code', 'law_suit_number', 'type_movement_legacy_code']


class LawsuitFilter(filters.FilterSet):
    company_id = filters.CharFilter(field_name='folder__person_customer__company_id')
    class Meta:
        model = LawSuit
        fields = ['company_id']
