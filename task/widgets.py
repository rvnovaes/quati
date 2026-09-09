import datetime
from core.models import Person, Office
from django import forms
from django_filters.fields import RangeField
from django.utils.timezone import make_aware
from import_export.widgets import ForeignKeyWidget, Widget, DateTimeWidget
from task.models import TaskStatus
from task.messages import wrong_task_status
from core.widgets import CodeMirrorTextarea

code_mirror_schema = CodeMirrorTextarea(
    mode="javascript",
    theme="material",
    config={
        'fixedGutter': True,
        'indentUnit': 4
    })


class UnaccentForeignKeyWidget(ForeignKeyWidget):
    """
    Widget to find foreginkey records based on unaccent text.
    """

    def clean(self, value, row=None, *args, **kwargs):
        val = super(ForeignKeyWidget, self).clean(value)
        if val:
            ret = self.get_queryset(value, row, *args, **kwargs).filter(**{'{}'.format(self.field): val}).first()
            return ret if ret else self.get_queryset(
                value, row, *args, **kwargs).filter(
                    **{
                        '{}__unaccent__iexact'.format(self.field): val
                    }).first()
        else:
            return None

    def get_queryset(self, value, row, *args, **kwargs):
        try:
            office_field = self.model._meta.get_field('office')
            return self.model.objects.get_queryset(office=row['office'])
        except:
            return super().get_queryset(value, row, *args, **kwargs)


class TypeTaskByWidget(UnaccentForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        val = super(ForeignKeyWidget, self).clean(value)
        if val:
            ret = self.get_queryset(
                value, row, *args,
                **kwargs).filter(**{
                    '{}'.format(self.field): val,
                    'office_id': row['office']
                }).first()
            return ret if ret else self.get_queryset(
                value, row, *args, **kwargs).filter(
                    **{
                        '{}__unaccent__iexact'.format(self.field): val
                    }).first()
        else:
            return None


class PersonAskedByWidget(UnaccentForeignKeyWidget):
    """
    Widget to find the person_asked_by.
    """

    def clean(self, value, row=None, *args, **kwargs):
        queryset = Person.objects.requesters(office_id=row['office'])
        ret = None
        if value:
            ret = queryset.filter(**{'{}'.format(self.field): value}).first()
            if not ret:
                ret = queryset.filter(
                    **{
                        '{}__unaccent__iexact'.format(self.field): value
                    }).first()
        if ret:
            return ret
        elif not (ret or value):
            return None
        else:
            raise ValueError(
                "Não foi encontrado solicitante para este escritório com o nome {}."
                .format(value))


class PersonCompanyRepresentative(UnaccentForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        office = Office.objects.get(pk=row['office'])
        person_company_representative = office.persons.filter(legal_name__unaccent__icontains=value,
                                                              legal_type='F').first()
        if value and person_company_representative:
            return person_company_representative
        elif not value:
            return None
        else:
            raise ValueError(
                "Não foi encontrado preposto para este escritório com o nome {}."
                .format(value))


class TaskStatusWidget(Widget):
    """
    Widget to get task_status from TaskStatus enum
    """

    def clean(self, value, row=None, *args, **kwargs):
        ret = TaskStatus.REQUESTED.value
        if value:
            if not row['id']:
                values = {item.value.title(): item.value for item in [TaskStatus.REQUESTED,
                                                                      TaskStatus.ACCEPTED_SERVICE]}
                ret = values.get(value.title(), None)
                if not ret:
                    raise ValueError(wrong_task_status(value.title(), values.values()))
            else:
                ret = value
        return ret


class DateTimeWidgetMixin(DateTimeWidget):
    """
    Widget to convert from excell double to string datetime
    """

    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return None
        if isinstance(value, float):
            seconds = int(round((value - 25569) * 86400.0))
            value = make_aware(datetime.datetime.utcfromtimestamp(seconds))
        return super().clean(value, row, *args, **kwargs)


class ApiDatetimeRangeField(RangeField):
    def __init__(self, *args, **kwargs):
        fields = (
            forms.DateTimeField(),
            forms.DateTimeField())
        super(ApiDatetimeRangeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            start_datetime, stop_datetime = data_list
            if start_datetime:
                start_datetime = datetime.datetime.combine(start_datetime, datetime.time.min)
            if stop_datetime:
                stop_datetime = datetime.datetime.combine(stop_datetime, datetime.time.max)
            return slice(start_datetime, stop_datetime)
        return None