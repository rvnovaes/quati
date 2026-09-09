from django.core.cache import cache
from lawsuit.models import CourtDistrict
from django.db.models import Q
from decimal import Decimal
from .models import ServicePriceTable


def clearCache(key_list):
    for key in key_list:
        cache.delete(key)


def remove_special_char(text):
    d = {'À': 'A', 'Á': 'A', 'Ä': 'A', 'Â': 'A', 'Ã': 'A',
         'È': 'E', 'É': 'E', 'Ë': 'E', 'Ê': 'E',
         'Ì': 'I', 'Í': 'I', 'Ï': 'I', 'Î': 'I',
         'Ò': 'O', 'Ó': 'O', 'Ö': 'O', 'Ô': 'O', 'Õ': 'O',
         'Ù': 'U', 'Ú': 'U', 'Ü': 'U', 'Û': 'U',
         'à': 'a', 'á': 'a', 'ä': 'a', 'â': 'a', 'ã': 'a', 'ª': 'a',
         'è': 'e', 'é': 'e', 'ë': 'e', 'ê': 'e',
         'ì': 'i', 'í': 'i', 'ï': 'i', 'î': 'i',
         'ò': 'o', 'ó': 'o', 'ö': 'o', 'ô': 'o', 'õ': 'o', 'º': 'o', '°': 'o',
         'ù': 'u', 'ú': 'u', 'ü': 'u', 'û': 'u',
         'Ç': 'C', 'ç': 'c'}
    new_text = ''

    for c in range(0, len(text)):
        new_char = text[c]
        try:
            new_char = d[text[c]]
        except KeyError:
            pass

        new_text = new_text + new_char

    return new_text


def valid_court_district(court_district, state):
    if court_district.state != state:
        return False
    return True


def check_service_price_table_unique(pk, office, office_correspondent, state, court_district, type_task, client,
                                     court_district_complement):
    office_q = Q(office=office)
    office_correspondent_q = Q(office_correspondent=office_correspondent) if office_correspondent \
        else Q(office_correspondent__isnull=True)
    state_q = Q(state=state) if state else Q(state__isnull=True)
    court_district_q = Q(court_district=court_district) if court_district else Q(court_district__isnull=True)
    court_district_complement_q = Q(court_district_complement=court_district_complement) if court_district_complement \
        else Q(court_district_complement__isnull=True)
    type_task_q = Q(type_task=type_task) if type_task else Q(type_task__isnull=True)
    client_q = Q(client=client) if client else Q(client__isnull=True)
    if ServicePriceTable.objects.filter(~Q(pk=pk), office_q, office_correspondent_q, state_q, court_district_q,
                                        type_task_q, client_q, court_district_complement_q):
        return False
    return True


def check_office_correspondent_relation(office, office_correspondent):
    return office_correspondent in office.offices.active_offices()


def recalculate_values(old_value, value_to_pay, value_to_receive, new_value, rate_type_pay, rate_type_receive):
    """
    Calcula os novos valores a pagar e a receber para a tabela de preços, de acordo com os dados antigos
    :param old_value: Valor autal da tabela de preços
    :param value_to_pay: Valor atual a pagar (valor que será pago ao correspondente que executar o serviço)
    :param value_to_receive: Valor atual a receber (valor que será pago ao contratante pela execução do serviço)
    :param new_value: Novo valor para a tabela de preços
    :param rate_type_pay: tipo de correção a ser feita para o valor a pagar (PERCENT ou VALUE)
    :param rate_type_receive: tipo de correção a ser feita para o valor a receber (PERCENT ou VALUE)
    :return value_to_pay, value_to_receive: novos valores a pagar e a receber pela tabela de peços
    """
    if hasattr(value_to_pay, 'amount'):
        value_to_pay = value_to_pay.amount
    if hasattr(value_to_receive, 'amount'):
        value_to_receive = value_to_receive.amount
    if old_value == 0.00:
        value_to_receive = Decimal(value_to_receive)
        value_to_pay = Decimal(value_to_pay)
    else:
        diff_to_pay = abs(value_to_pay - old_value)
        diff_to_receive = abs(value_to_receive - old_value)
        new_value = Decimal(new_value)
        if rate_type_pay == 'PERCENT':
            diff_to_pay = round(1 - (diff_to_pay / old_value), 2)
            value_to_pay = round(new_value * diff_to_pay, 2)
        else:
            value_to_pay = round(new_value - diff_to_pay, 2)
        value_to_pay = Decimal(value_to_pay)
        if rate_type_receive == 'PERCENT':
            diff_to_receive = round(1 + (diff_to_receive / old_value), 2)
            value_to_receive = round(new_value * diff_to_receive, 2)
        else:
            value_to_receive = round(new_value + diff_to_receive, 2)
        value_to_receive = Decimal(value_to_receive)
    return value_to_pay, value_to_receive
