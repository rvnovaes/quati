# -*- coding: utf-8 -*-
# Author: Christian Douglas <christian.douglas.alcantara@gmail.com>
from django import template
from django.apps import apps
from ..models import Attachment

register = template.Library()


def get_model_name(object):
    app_label = object._meta.app_label
    model_name = object._meta.model_name
    return f'{app_label}.{model_name}'


@register.filter
def get_modelname_from_object(object):
    return get_model_name(object)


@register.simple_tag
def get_attachments(object, object_id):
    return Attachment.objects.filter(
        model_name=get_model_name(object),
        object_id=object_id
    )
