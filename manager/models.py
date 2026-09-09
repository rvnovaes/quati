import json

from django.db.models import JSONField
from django.db import models

from .schemas import DEFAULT_VALUE
from .enums import TemplateKeys, TypeTemplate
from core.models import Audit, OfficeMixin, OfficeManager


class Template(Audit):
    name = models.CharField(verbose_name='Nome',
                            null=False,
                            blank=False,
                            max_length=255)
    template_key = models.CharField(verbose_name='Chave',
                                    null=False,
                                    blank=False,
                                    max_length=255,
                                    unique=True,
                                    choices=TemplateKeys.choices())
    description = models.TextField(verbose_name='Descrição',
                                   null=True,
                                   blank=True)
    type = models.CharField(null=False,
                            blank=False,
                            verbose_name='Tipo',
                            max_length=15,
                            choices=TypeTemplate.choices())
    parameters = JSONField(
        null=False,
        blank=False,
        verbose_name='Características disponíveis',)

    class Meta:
        ordering = ('name', 'type')
        verbose_name = 'Template de configuração'
        verbose_name_plural = 'Templates de configuração'

    def __str__(self):
        return self.name

    @property
    def default_value(self):
        from manager.template import GenericTemplate
        return GenericTemplate(self).default_python_value


def default_template_value():
    return json.dumps(DEFAULT_VALUE, indent=4)


class TemplateValue(OfficeMixin, Audit):

    template = models.ForeignKey(Template, verbose_name='Configuração', on_delete=models.PROTECT)
    value = JSONField(
        null=True,
        blank=True,
        verbose_name='Valor',
        default=default_template_value)

    objects = OfficeManager()

    class Meta:
        ordering = ('office', 'template')
        verbose_name = 'Configuração por escritório'
        verbose_name_plural = 'Configurações por escritório'

    @property
    def use_upload(self):
        return False
