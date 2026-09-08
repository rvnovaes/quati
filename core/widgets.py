import datetime
from dal.widgets import QuerySetSelectMixin
from django import forms
from django.forms.widgets import boolean_check, Input, DateTimeBaseInput, ChoiceWidget
from django.utils import translation
from django.utils import timezone
from django.utils.encoding import force_str
from django_filters import RangeFilter
from django.forms.widgets import Widget
from django.template import loader
from django.utils.safestring import mark_safe
from dal.autocomplete import ModelSelect2

from django.conf import settings


class MDDateTimepicker(DateTimeBaseInput):
    format_key = 'DATETIME_INPUT_FORMATS'
    template_name = 'core/widgets/md_datetimepicker.html'

    def get_context(self, name, value, attrs):
        context = super(Input, self).get_context(name, value, attrs)
        context['widget']['type'] = self.input_type
        if self.min_date:
            context['widget']['min_date'] = timezone.localtime(
                self.min_date).strftime('%d/%m/%Y %H:%M')
        if self.max_date:
            context['widget']['max_date'] = True
        if value and not isinstance(value, str):
            context['widget']['value'] = value.strftime('%d/%m/%Y %H:%M')
        context['widget']['format'] = self.format
        return context

    def __init__(self, attrs=None, format=None, min_date=None, max_date=False):
        super(MDDateTimepicker, self).__init__(attrs)
        self.format = format if format else 'DD/MM/YYYY'
        self.min_date = min_date if min_date else None
        self.max_date = max_date


class MDDatePicker(DateTimeBaseInput):
    format_key = 'DATETIME_INPUT_FORMATS'
    template_name = 'core/widgets/md_datepicker.html'

    def get_context(self, name, value, attrs):
        context = super(Input, self).get_context(name, value, attrs)
        context['widget']['type'] = self.input_type
        context['widget']['format'] = self.format
        if self.min_date:
            context['widget']['min_date'] = timezone.localtime(
                self.min_date).strftime('%d/%m/%Y')

        if value and not isinstance(value, str):
            context['widget']['value'] = value.strftime('%d/%m/%Y')
            # self.value = value.strftime('%d/%m/%Y %H:%M')
        return context

    def __init__(self, attrs=None, format=None, min_date=None):
        super(MDDatePicker, self).__init__(attrs)
        self.format = format if format else 'DD/MM/YYYY'
        self.min_date = min_date if min_date else None


class MDCheckboxInput(Input):
    input_type = 'checkbox'
    template_name = 'core/widgets/md_checkbox.html'

    def __init__(self, attrs=None, check_test=None):
        super(MDCheckboxInput, self).__init__(attrs)
        # check_test is a callable that takes a value and returns True
        # if the checkbox should be checked for that value.
        self.check_test = boolean_check if check_test is None else check_test

    def format_value(self, value):
        """Only return the 'value' attribute if value isn't empty."""
        if value is True or value is False or value is None or value == '':
            return
        return force_str(value)

    def get_context(self, name, value, attrs):
        if self.check_test(value):
            if attrs is None:
                attrs = {}
            attrs['checked'] = True

        return super(MDCheckboxInput, self).get_context(name, value, attrs)

    def value_from_datadict(self, data, files, name):
        if name not in data:
            # A missing value means False because HTML form submission does not
            # send results for unselected checkboxes.
            return False
        value = data.get(name)
        # Translate true and false strings to boolean values.
        values = {'true': True, 'false': False}
        if isinstance(value, str):
            value = values.get(value.lower(), value)
        return bool(value)

    def value_omitted_from_data(self, data, files, name):
        # HTML checkboxes don't appear in POST data if not checked, so it's
        # never known if the value is actually omitted.
        return False


class MDRangeWidget(forms.MultiWidget):
    template_name = 'core/widgets/md_range_datetimepicker.html'
    format = 'DD/MM/YYYY'

    def __init__(self, format=None, attrs=None):
        self.format = format if format else 'DD/MM/YYYY'
        widgets = (MDDateTimepicker(), MDDateTimepicker())
        super(MDRangeWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return [value.start, value.stop]
        return [None, None]

    def get_context(self, name, value, attrs):
        context = super(MDRangeWidget, self).get_context(name, value, attrs)
        if self.is_localized:
            for widget in self.widgets:
                widget.is_localized = self.is_localized
        # value is a list of values, each corresponding to a widget
        # in self.widgets.
        if not isinstance(value, list):
            value = self.decompress(value)

        final_attrs = context['widget']['attrs']
        input_type = final_attrs.pop('type', None)
        id_ = final_attrs.get('id')
        subwidgets = []
        for i, widget in enumerate(self.widgets):
            if input_type is not None:
                widget.input_type = input_type
            widget_name = '%s_%s' % (name, i)
            try:
                widget_value = value[i]
            except IndexError:
                widget_value = None
            if id_:
                widget_attrs = final_attrs.copy()
                widget_attrs['id'] = '%s_%s' % (id_, i)
            else:
                widget_attrs = final_attrs
            subwidgets.append(
                widget.get_context(widget_name, widget_value,
                                   widget_attrs)['widget'])
        context['widget']['subwidgets'] = subwidgets
        context['widget']['format'] = self.format
        return context


class DateTimeRangeField(forms.MultiValueField):
    widget = MDRangeWidget

    def __init__(self, fields=None, format=None, label=None, *args, **kwargs):

        if fields is None:
            fields = (forms.DateTimeField(
                widget=MDDateTimepicker(attrs={'class': 'form-control'})),
                      forms.DateTimeField(
                          widget=MDDateTimepicker(
                              attrs={'class': 'form-control'})))
            super(DateTimeRangeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            return slice(*data_list)
        return None


class MDDateTimeRangeFilter(RangeFilter):
    field_class = DateTimeRangeField
    format = None

    def __init__(self, name=None, label=None, format=None, *args, **kwargs):
        self.name = name
        self.format = format if format else 'DD/MM/YYYY'
        # self.field.widget = MDRangeWidget(format=self.format)
        kwargs['format'] = self.format
        super(MDDateTimeRangeFilter, self).__init__(*args, **kwargs)

    def filter(self, qs, value):
        if self.format != 'DD/MM/YYYY':
            return super().filter(qs, value)
        if value:
            if value.start is not None and value.stop is not None:
                lookup = '%s__range' % self.name
                return self.get_method(qs)(**{lookup: (
                    datetime.datetime.combine(value.start, datetime.time.min),
                    datetime.datetime.combine(value.stop, datetime.time.max)
                )})
            else:
                return super().filter(qs, value)
        return qs


class MDSelect(ModelSelect2):

    class Media:
        # Assets do django-autocomplete-light >= 3.9 (select2 vem do admin do Django)
        extend = False
        css = {
            'all': (
                'admin/css/vendor/select2/select2.css',
                'autocomplete_light/select2.css',
            )
        }
        js = ('admin/js/vendor/select2/select2.full.js',
              'autocomplete_light/autocomplete_light.js',
              'autocomplete_light/select2.js',
              'autocomplete_light/i18n/pt-BR.js',
              )

    def build_attrs(self, *args, **kwargs):
        attrs = super().build_attrs(*args, **kwargs)
        attrs.setdefault('data-language', 'pt-BR')
        attrs.setdefault('data-placeholder', 'Procurar...')
        return attrs

    def get_context(self, name, value, attrs):
        context = super(MDSelect, self).get_context(name, value, attrs)
        if self.allow_multiple_selected:
            context['widget']['attrs']['multiple'] = 'multiple'
        return context

    @staticmethod
    def _choice_has_empty_value(choice):
        """Return True if the choice's value is empty string or None."""
        value, _ = choice
        return ((isinstance(value, str) and not bool(value))
                or value is None)

    def use_required_attribute(self, initial):
        """
        Don't render 'required' if the first <option> has a value, as that's
        invalid HTML.
        """
        use_required_attribute = super(MDSelect,
                                       self).use_required_attribute(initial)
        # 'required' is always okay for <select multiple>.
        if self.allow_multiple_selected:
            return use_required_attribute

        first_choice = next(iter(self.choices), None)
        return (use_required_attribute and first_choice is not None
                and self._choice_has_empty_value(first_choice))


class TypeaHeadWidget(Widget):
    template_name = 'skeleton/componentes/fields/typeahead.html'

    def __init__(self,
                 model,
                 url=False,
                 name=False,
                 forward=None,
                 *args,
                 **kwargs):
        self.model = model
        self.url = url if url else '/typeahead/search'
        self.name = name
        self.forward = forward or ''
        super().__init__(*args, **kwargs)

    class Media:
        js = (
            'skeleton/plugins/bower_components/typeahead.js-master/dist/typeahead.bundle.min.js',
            'core/js/typeahead.js')

    def get_context_data(self, name, value, attrs=None):
        return {
            'widget': {
                'name': self.name or name,
                'value': value,
                'url': self.url,
                'module': self.model.__module__,
                'model': self.model.__name__,
                'forward': self.forward
            }
        }

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context_data(name, value, attrs)
        template = loader.get_template(self.template_name).render(context)
        return mark_safe(template)


class TypeaHeadForeignKeyWidget(TypeaHeadWidget):
    def __init__(self,
                 model,
                 field_related,
                 url=False,
                 name=False,
                 forward=None,
                 forward_id=None,
                 *args,
                 **kwargs):
        super().__init__(model, url, name, *args, **kwargs)
        self.field_related = field_related
        self.forward = forward or ''
        self.forward_id = forward_id or ''

    def get_context_data(self, name, value, attrs=None):
        return {
            'widget': {
                'name': self.name or name,
                'value': value,
                'value_txt': self.model.objects.filter(pk=value).first() if str(value).isdigit() else '',
                'url': self.url,
                'module': self.model.__module__,
                'model': self.model.__name__,
                'field_related': self.field_related,
                'forward': self.forward,
                'forward_id': self.forward_id
            }
        }


class CodeMirrorTextarea(forms.Textarea):
    """
    Textarea com editor CodeMirror (assets vendorizados em core/static/codemirror).
    Substitui o pacote django-codemirror-widget, descontinuado.
    """
    template_name = 'core/widgets/codemirror.html'

    def __init__(self, mode='javascript', theme='material', config=None, attrs=None):
        self.mode = mode
        self.theme = theme
        self.config = config or {}
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        import json
        context = super().get_context(name, value, attrs)
        context['widget']['mode'] = self.mode
        context['widget']['theme'] = self.theme
        context['widget']['config'] = json.dumps(self.config)
        return context

    class Media:
        css = {'all': ('codemirror/lib/codemirror.css', 'codemirror/theme/material.css')}
        js = ('codemirror/lib/codemirror.js', 'codemirror/mode/javascript/javascript.js',
              'codemirror/mode/python/python.js')


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Campo de upload múltiplo nativo do Django (substitui django-file-form)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'multiple': True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        cleaned = single_clean(data, initial)
        return [cleaned] if cleaned else []
