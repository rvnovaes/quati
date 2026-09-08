from django.db import models
from core.models import Company
from django.db.models import JSONField
import json
from .schemas import *


class Dashboard(models.Model):
    company = models.ForeignKey(Company, verbose_name='Empresa', on_delete=models.PROTECT)
    logo = models.ImageField(verbose_name='Logo', null=True, blank=True)
    refresh = models.IntegerField(
        verbose_name='Refresh por millesegundo', blank=True, null=True)

    def __str__(self):
        return self.company.name


class Component(models.Model):
    name = models.CharField(verbose_name='Nome', max_length=255)
    code = models.TextField(verbose_name='Codigo', blank=True, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


def default_card_schema():
    return json.dumps(CARD, indent=4)


def default_line_schema():
    return json.dumps(LINE, indent=4)


def default_doughnut_schema():
    return json.dumps(DOUGHNUT, indent=4)


def default_bar_schema():
    return json.dumps(BAR, indent=4)


class Card(Component):
    dashboards = models.ManyToManyField(
        Dashboard, related_name='cards', through='DashboardCard', blank=True)
    schema = JSONField(verbose_name=u'Schema', blank=True,
                       null=True, default=default_card_schema)


class LineChart(Component):
    dashboards = models.ManyToManyField(
        Dashboard, related_name='line_charts', through='DashboardLineChart', blank=True)
    schema = JSONField(verbose_name=u'Schema', blank=True,
                       null=True, default=default_line_schema)


class DoughnutChart(Component):
    dashboards = models.ManyToManyField(
        Dashboard, related_name='doughnut_charts', through='DashboardDoughnutChart', blank=True)
    schema = JSONField(verbose_name=u'Schema', blank=True,
                       null=True, default=default_doughnut_schema)


class BarChart(Component):
    dashboards = models.ManyToManyField(
        Dashboard, related_name='bar_charts', through='DashboardBarChart', blank=True)
    schema = JSONField(verbose_name=u'Schema', blank=True,
                       null=True, default=default_bar_schema)


class DashboardComponent(models.Model):
    dashboard = models.ForeignKey(
        Dashboard, on_delete=models.CASCADE, blank=True)
    sequence = models.IntegerField('Sequencia')

    class Meta:
        ordering = ['sequence']
        abstract = True


class DashboardLineChart(DashboardComponent):
    line_chart = models.ForeignKey(LineChart, on_delete=models.CASCADE, blank=True)


class DashboardCard(DashboardComponent):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, blank=True)


class DashboardDoughnutChart(DashboardComponent):
    doughnut_chart = models.ForeignKey(
        DoughnutChart, on_delete=models.CASCADE, blank=True)


class DashboardBarChart(DashboardComponent):
    bar_chart = models.ForeignKey(BarChart, on_delete=models.CASCADE, blank=True)
