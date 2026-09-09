from enum import Enum
from django.db import models
from core.models import Audit, OfficeMixin, OfficeManager
from task.models import Task

# Dicionário para retornar a solução referente à inconsistência encontrada
solution_dict = dict(
    TASKLESSMOVEMENT='Preencher a movimentação na OS',
    MOVEMENTLESSPROCESS='Preencher o processo na movimentação',
    TASKINATIVEFOLDER='Alterar o status da pasta para "Especial"',
    INVALIDCOURTDISTRICT='Preencher o campo comarca com um valor válido para Comarca, Cidade ou Complemento de comarca',
    BLANKCOURTDISTRICT='Preencher o campo comarca com um valor válido para Comarca, Cidade ou Complemento de comarca',
    BLANKFINALDEADLINEDATE='Preencher o campo prazo fatal com um valor válido.',
    MINHOUROSERROR='Alterar o prazo fatal da OS.',)


class Inconsistencies(Enum):
    TASKLESSMOVEMENT = 'OS sem movimentação'
    MOVEMENTLESSPROCESS = 'Movimentação sem processo'
    TASKINATIVEFOLDER = 'OS em Pasta Inativa'
    INVALIDCOURTDISTRICT = 'O valor preenchido no campo comarca não foi encontrado como Comarca, Cidade ou ' \
                           'Complemento de comarca'
    BLANKCOURTDISTRICT = 'O campo comarca não foi preenchido'
    BLANKFINALDEADLINEDATE = 'O campo prazo fatal não foi preenchido'
    MINHOUROSERROR = 'O prazo fatal da OS é menor que o mínimo configurado'

    def get_solution(self):
        return solution_dict[self.name]

    def __str__(self):
        return str(self.value)

    @classmethod
    def choices(cls):
        return [(x.value, x.name) for x in cls]


class DashboardETL(Audit, OfficeMixin):
    execution_date_start = models.DateTimeField(
        verbose_name='Inicio', auto_now_add=True, null=True, blank=True)
    execution_date_finish = models.DateTimeField(
        verbose_name='Fim', null=True, blank=True, editable=False)
    name = models.CharField(verbose_name='ETL', max_length=100, editable=False)
    status = models.BooleanField(
        verbose_name='Status', default=True, editable=False)
    read_quantity = models.IntegerField(
        verbose_name='Quantidade Lida', default=0, editable=False)
    imported_quantity = models.IntegerField(
        verbose_name='Quantidade importada', default=0, editable=False)
    executed_query = models.TextField(
        verbose_name='Query executada', null=True, blank=True, editable=False)
    db_name_source = models.CharField(
        verbose_name='DB de origem', max_length=50, blank=True, null=True)
    db_host_source = models.CharField(
        verbose_name='Host do db de origem',
        blank=True,
        null=True,
        max_length=20)

    class Meta:
        db_table = 'dashboard_etl'
        ordering = ('-execution_date_start', )
        verbose_name = 'Dashboard ETL'
        verbose_name_plural = 'Dashboard ETL'

    def __str__(self):
        return self.name


class ErrorETL(Audit):
    log = models.ForeignKey(
        DashboardETL, verbose_name='Erros', related_name='errors', on_delete=models.PROTECT)
    error = models.TextField(
        verbose_name='Descrição do erro',
        null=True,
        blank=True,
        editable=False)


class InconsistencyETL(Audit, OfficeMixin):
    """
    Classe responsável por armazenar as inconsistências ocorridas durante a execução da ETL.
    Desde que não tenham impedido a importação completa.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name=u'Providência')
    inconsistency = models.CharField(
        verbose_name=u'Inconsistência',
        blank=True,
        null=True,
        max_length=150,
        choices=((x.value, x.name.title()) for x in Inconsistencies))
    solution = models.CharField(
        verbose_name=u'Solução', blank=True, null=True, max_length=100)

    objects = OfficeManager()

    @property
    def inconsistency_desc(self):
        return Inconsistencies(self.inconsistency)
