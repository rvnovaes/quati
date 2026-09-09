from functools import wraps
from itertools import groupby
from datetime import datetime
from django.contrib.auth.models import User
from core.models import Office
from financial.utils import remove_special_char
from core.utils import get_office_session
from decimal import Decimal


def field_to_html_input(field):
    html_map = {
        'CharField': 'text',
        'BooleanField': 'checkbox',
        'AutoField': 'number',
        'DateField': 'date',
        # 'DateTimeField': 'datetime-local',
        'DateTimeField': 'date',
        'ForeignKey': 'foreignkey',
        'OneToOneField': 'foreignkey',
        'old': 'text'
    }
    return html_map.get(field)


def group_by(fields):
    data = sorted(fields, key=lambda i: i.get('type') or 'old')
    new_data = {}
    for k, g in groupby(data, lambda i: i.get('type') or 'old'):
        new_data[k] = list(g)
    return new_data


def set_search_model_attrs(f):
    """
    Embrulha metodo get_context_data para atribuir campos do model para a pesquisa global
    :param f:
    :return:
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        res = f(*args, **kwargs)
        res['search_model_fields'] = list(
            map(lambda i: {'name': i.name, 'verbose_name': i.verbose_name,
                           'type': field_to_html_input(i.get_internal_type()),
                           'choices': i.choices,
                           'default': i._get_default() if i.get_internal_type() == 'BooleanField'
                           else False},
                res.get('table')._meta.model._meta.fields))
        res['search_model_fields'] = group_by(res['search_model_fields'])
        return res

    return wrapper


class GenericSearchFormat(object):
    # Classe responsavel por formatar o filtro global
    def __init__(self,
                 request,
                 model,
                 fields,
                 related_id=False,
                 field_name_related=False):
        self.model = model
        self.related_id = related_id
        self.field_name_related = field_name_related
        self.request = request
        self.params = self.format_params()
        self.model_type_fields = list(map(lambda i: {'name': i.name, 'type': i.get_internal_type()},
                                          list(filter(lambda x: x.name in self.params.keys(), fields))))
        self.model_type_fields.extend(list(map(lambda i: {'name': i.name, 'type': i.get_internal_type()},
                                               list(filter(lambda x: x.name + '_ini' in self.params.keys(), fields)))))
        self.model_type_fields.extend(list(map(lambda i: {'name': i.name, 'type': i.get_internal_type()},
                                               list(filter(lambda x: x.name + '_fim' in self.params.keys(), fields)))))
        self.search = {
            'CharField': GenericSearchString(),
            'Integer': GenericSearchInteger(),
            'AutoField': GenericSearchInteger(),
            'DateField': GenericSearchDate(),
            'DateTimeField': GenericSearchDate(),
            'ForeignKey': GenericSearchForeignKey(self.model),
            'OneToOneField': GenericSearchForeignKey(self.model),
            'BooleanField': GenericSearchBooleanField(),
            'DecimalField': GenericSearchDecimal()
        }

    def despatch(self, office=False):
        params = []
        if not any([self.params, params]):
            return False

        if self.params.get('is_active') == 'T':
            self.params.pop('is_active')
            self.model_type_fields.remove({
                'type': 'BooleanField',
                'name': 'is_active'
            })

        try:
            office_field = self.model._meta.get_field('office')
            if self.model in [User, Office]:
                search = "self.model.objects.get_queryset().filter({params})"
            else:
                if not office:
                    office = [get_office_session(self.request).id]
                if not type(office) is list:
                    office = [office]
                search = "self.model.objects.get_queryset(office={office}).filter({params})".format(
                    office=office, params='{params}')
        except:
            search = "self.model.objects.get_queryset().filter({params})"
        table_string = "self.table_class({queryset})"
        search = table_string.format(queryset=search)
        for field in self.model_type_fields:
            if field.get('type') in ['DateField', 'DateTimeField']:
                value = self.params.get(field.get('name') +
                                        '_ini'), self.params.get(
                                            field.get('name') + '_fim')
                params.append(
                    self.search.get(field.get('type'),
                                    GenericSearch()).dict_to_filter(
                                        field.get('name'), value))
            else:
                params.append(
                    self.search.get(field.get('type'),
                                    GenericSearch()).dict_to_filter(
                                        field.get('name'),
                                        self.params.get(field.get('name'))))

        if self.related_id:
            params.append('{0}__id={1}'.format(self.field_name_related,
                                               self.related_id))

        if not params:
            return False      
        return search.format(params=','.join(list(set(params))))        

    def format_params(self):
        return dict(
            list(
                filter(lambda x: x[1],
                       list(map(lambda i: i, self.request.GET.items())))))


class GenericSearch(object):
    """
    Classe responsavel por gerar a pesquisa generica de acordo com o tipo de campo
    """

    def __init__(self, *args, **kwargs):
        pass

    def dict_to_filter(self, param, value):
        return "Q({}__icontains='{}')".format(param, value)


class GenericSearchString(GenericSearch):
    def dict_to_filter(self, param, value):
        return "{}__unaccent__icontains=\"{}\"".format(param,
                                                       value.replace('"', "'"))


class GenericSearchInteger(GenericSearch):
    def dict_to_filter(self, param, value):
        return "{}='{}'".format(param, value)


class GenericSearchDecimal(GenericSearch):
    def dict_to_filter(self, param, value):
        value = value.replace('.', '')
        value = value.replace(',', '.')
        return "{}='{}'".format(param, Decimal(value))


class GenericSearchBooleanField(GenericSearch):
    def dict_to_filter(self, param, value):
        if param == 'is_active':
            return self.dict_to_filter_is_active(param, value)
        value = True if value == 'on' else False
        return "{}={}".format(param, value)

    def dict_to_filter_is_active(self, param, value):
        options = {'A': True, 'I': False}
        return "{0}={1}".format(param, options.get(value))


class GenericSearchDate(GenericSearch):
    def dict_to_filter(self, param, value):
        filter_date = []
        if value[0]:
            data = datetime.strptime(
                value[0] + ' 00:00:00',
                "%d/%m/%Y %H:%M:%S").strftime('%Y-%m-%d %H:%M:%S')
            filter_date.append("{0}__gte='{1}'".format(param, data))
        if value[1]:
            data = datetime.strptime(
                value[1] + ' 23:59:59',
                "%d/%m/%Y %H:%M:%S").strftime('%Y-%m-%d %H:%M:%S')
            filter_date.append("{0}__lte='{1}'".format(param, data))
        return ",".join(filter_date)


class GenericSearchForeignKey(GenericSearch):
    def __init__(self, model):
        super(GenericSearchForeignKey, self).__init__()
        self.model = model

    def dict_to_filter(self, param, value):
        ids = self.get_related_values(value, param)
        return "{}__in={}".format(param, ids)

    def get_related_values(self, value, param):
        if value:
            model_query_set = 'self.model.{0}.get_queryset()'.format(param)
            return list(map(lambda x: x.id,
                            list(filter(lambda i: remove_special_char(value.lower()) in
                                                  remove_special_char(i.__str__().lower()),
                                        eval(model_query_set)))))
        return []
