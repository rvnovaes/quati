from django.db import models
from djmoney.models.fields import MoneyField
from core.models import Audit, Office, OfficeMixin, Address


class Plan(Audit):
    name = models.CharField(
        max_length=255, blank=False, null=False, verbose_name="Nome")
    description = models.TextField(
        blank=True, null=True, verbose_name="Descrição")
    month_value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default_currency='BRL',
        verbose_name="Valor mensal",
        null=False,
        blank=False)
    task_limit = models.IntegerField(
        verbose_name="Limite mensal", null=True, blank=True)
    custom_pricing = models.BooleanField(
        null=False, default=False, verbose_name='Preço customizado')
    custom_pricing_text = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Descrição para preço customizado')

    class Meta:
        ordering = ['month_value']
        verbose_name = "Plano"
        verbose_name_plural = "Planos"

    def __str__(self):
        return '{} ({})'.format(self.name, self.month_value)


class PlanOffice(Audit):
    office = models.ForeignKey(
        Office, on_delete=models.CASCADE, blank=False, null=False)
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, blank=False, null=False)
    subscription_date = models.DateTimeField(
        'Data de inscrição', auto_now_add=True, blank=False, null=False)
    cancelation_date = models.DateTimeField(
        'Data de cancelamento', auto_now_add=False, blank=True, null=True)
    month_value = MoneyField(
        max_digits=10,
        decimal_places=2,
        default_currency='BRL',
        verbose_name="Valor mensal",
        null=False,
        blank=False)
    task_limit = models.IntegerField(
        verbose_name="Limite mensal", null=True, blank=True)

    class Meta:
        ordering = ['office']

    def __str__(self):
        return '{} - {} - {}'.format(self.office.legal_name, self.plan.name,
                                     self.subscription_date)


class Charge(Audit):
    custom_id = models.CharField(verbose_name='Custom id', max_length=255, blank=True, null=True)
    charge_id = models.CharField(verbose_name='Transacao', max_length=255, blank=True, null=True)
    status = models.CharField(verbose_name='Status', max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(verbose_name='Data da transacao', blank=True, null=True)

    class Meta:
        ordering = ['-pk']

    def __str__(self):
        return self.charge_id or ''


class ChargeItem(Audit):
    charge = models.ForeignKey(Charge, verbose_name='Transacao', related_name='items', blank=True, null=True, on_delete=models.PROTECT)
    name = models.CharField(verbose_name='Item', max_length=255)
    value = models.IntegerField(verbose_name='Valor')
    amount = models.IntegerField(verbose_name='Quantidade')

    def __str__(self):
        return self.name or ''


class BillingDetails(Audit, OfficeMixin):
    full_name = models.CharField(
        verbose_name='Nome completo',
        max_length=255,
        blank=True, null=True
    )
    card_name = models.CharField(
        verbose_name='Nome no cartão',
        max_length=255,
        blank=True, null=True
    )
    email = models.EmailField(
        verbose_name='E-mail',
        max_length=255,
    )
    cpf_cnpj = models.CharField(
        max_length=255,
        verbose_name='CPF/CNPJ',
        blank=True, null=True
    )
    cpf = models.CharField(
        max_length=255,
        verbose_name='CPF',
        blank=True, null=True
    )
    birth_date = models.DateField(verbose_name='Data de nascimento')
    phone_number = models.CharField(
        verbose_name='Telefone',
        max_length=15
    )
    billing_address = models.ForeignKey(Address, verbose_name='Endereço de cobrança', on_delete=models.PROTECT)

    class Meta:
        ordering = ['office', 'card_name']

    def __str__(self):
        return '{} - {}'.format(self.office, self.card_name)
