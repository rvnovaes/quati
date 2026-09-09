from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from core.models import AddressType, ContactMechanismType, ContactMechanism, Team, ControlFirstAccessUser, EmailTemplate, AdminSettings
#Todo: Remover office
from core.models import Office, Invite, InviteOffice, OfficeRelGroup, CustomSettings, Company, CompanyUser, City, \
    State, Country, AreaOfExpertise, OfficeNetwork, OfficeOffices, CustomMessage
from task.models import TaskWorkflow, TaskShowStatus


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    pass


class TaskWorkflowInline(admin.TabularInline):
    model = TaskWorkflow
    fields = ('create_user', 'task_from', 'task_to', 'responsible_user')
    extra = 0


class TaskShowStatusInline(admin.TabularInline):
    model = TaskShowStatus
    fields = ('create_user', 'status_to_show', 'send_mail_template', 'mail_recipients')
    extra = 0

@admin.register(AdminSettings)
class AdmAdminSettings(admin.ModelAdmin):
    model = AdminSettings
    fields = ('rate_commission_requestor', 'rate_commission_correspondent')

    def has_delete_permission(self, request, obj=None):
        return True

    # def has_add_permission(self, request):
    #     return True

    def save_form(self, request, form, change):
        return super().save_form(request, form, change)


@admin.register(CustomSettings)
class CustomSettingsAdmin(admin.ModelAdmin):
    list_display = ('office',)
    search_fields = ['office__legal_name', 'office__name']
    fields = ['office', 'create_user', 'alter_user', 'show_task_in_admin_dash']
    inlines = [TaskShowStatusInline, TaskWorkflowInline]

    def save_form(self, request, form, change):
        return super().save_form(request, form, change)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    pass


@admin.register(CompanyUser)
class CompanyUserAdmin(admin.ModelAdmin):
    list_display = ['company', 'user', 'show_administrative_menus']


@admin.register(ContactMechanismType)
class ContactMechanismTypeAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'create_user', 'create_date', 'alter_user', 'alter_date'
    ]
    search_fields = ['name']
    list_filter = ['name']

    class Meta:
        verbose_name = 'Tipo de Contato'
        verbose_name_plural = 'Tipos de Contato'


@admin.register(ContactMechanism)
class ContactMechanism(admin.ModelAdmin):
    list_display = ['person', 'contact_mechanism_type', 'description']
    search_fields = ['person__legal_name', 'description']
    list_filter = ['contact_mechanism_type']

    class Meta:
        verbose_name = 'Mecanismo de Contato'
        verbose_name_plural = 'Mecanismos de Contato'


class VersionFilter(SimpleListFilter):
    title = 'Escritório de Origem'
    parameter_name = 'from_office__legal_name'
    template = 'admin/input_filter.html'

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        return [(i, i) for i in qs.values_list('from_office__legal_name',
                                               flat=True).distinct().order_by('from_office__legal_name')]

    def choices(self, changelist):
        # Grab only the "all" option.
        all_choice = next(super().choices(changelist))
        all_choice['query_parts'] = (
            (k, v)
            for k, v in changelist.get_filters_params().items()
            if k == self.parameter_name
        )
        yield all_choice

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(from_office__legal_name__unaccent__icontains=self.value())


@admin.register(OfficeOffices)
class OfficeOfficesAdmin(admin.ModelAdmin):
    list_display = ['from_office', 'to_office', 'person_reference']
    search_fields = ['from_office__legal_name', 'to_office__legal_name']
    list_filter = (VersionFilter,)
    readonly_fields = ('from_office', 'to_office')
    exclude = ('is_active',)

    def get_field_queryset(self, db, db_field, request):
        ret = super().get_field_queryset(db, db_field, request)
        if db_field.name == 'person_reference':
            office_office_id = list(request.resolver_match.args)
            if office_office_id:
                office = OfficeOffices.objects.get(pk__in=office_office_id).from_office
                ret = db_field.remote_field.model._default_manager.using(db).filter(
                    offices=office).order_by('legal_name')
        return ret

    def has_add_permission(self, request):
        return False


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    search_fields = ['legal_name', 'name']
    list_display = ['legal_name', 'cpf_cnpj']


@admin.register(Invite)
class InviteUserAdmin(admin.ModelAdmin):
    list_display = ['pk', 'create_user', 'person', 'office', 'status']
    fields = ['create_user', 'person', 'office', 'status']


@admin.register(InviteOffice)
class InviteOfficeAdmin(admin.ModelAdmin):
    list_display = ['pk', 'create_user', 'office_invite', 'office', 'status']
    fields = ['create_user', 'office_invite', 'office', 'status']


@admin.register(OfficeRelGroup)
class OfficeRelGroupAdmin(admin.ModelAdmin):
    list_display = ['pk', 'office', 'group']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['pk', 'name']


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    ordering = ('state', 'name')
    list_filter = ['state']
    list_display = ['name', 'state', 'court_district']
    search_fields = ['name']


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    search_fields = ['name']


@admin.register(AreaOfExpertise)
class AreaOfExpertiseAdmin(admin.ModelAdmin):
    search_fields = ['area']


@admin.register(OfficeNetwork)
class OfficeNetworkAdmin(admin.ModelAdmin):
    search_fields = ['name', 'members__legal_name']
    list_display = ['name', 'list_members']
    filter_horizontal = ['members']

@admin.register(CustomMessage)
class CustomMessageAdmin(admin.ModelAdmin):
    search_fields = ['message', 'link']    
    fields = ('initial_date', 'finish_date', 'title', 'message', 'link')


admin.site.register(AddressType)
admin.site.register(ControlFirstAccessUser)
admin.site.register(Country)
