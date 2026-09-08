#!/usr/bin/python
# -*- encoding: utf-8 -*-
from django import template

register = template.Library()


@register.simple_tag
def field_type(field):
    """
    Get the name of the field class.
    """
    if hasattr(field, 'field'):
        field = field.field
    s = str(type(field.widget).__name__)
    s = s.rpartition('Input')[0]
    s = s.lower()
    return s


@register.filter
def col_class(row):
    """Classe de coluna bootstrap para uma linha com N campos (form_rows.html)."""
    size = max(1, 12 // max(1, len(row)))
    return 'form-group col-sm-{}'.format(size)
