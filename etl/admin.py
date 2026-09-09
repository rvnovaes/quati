from etl.models import DashboardETL, ErrorETL
from django.contrib import admin
from django.utils.html import format_html


class DashboardErrorInline(admin.TabularInline):
    model = ErrorETL
    fk_name = 'log'
    max_num = 1
    readonly_fields = ('create_date', 'error')
    fields = (
        'create_date',
        'error',
    )


class DashboardETLAdmin(admin.ModelAdmin):
    readonly_fields = ('name', 'db_name_source', 'db_host_source',
                       'execution_date_start', 'execution_date_finish',
                       'read_quantity', 'imported_quantity', 'status',
                       'code_executed_query', 'quantity_errors')

    def quantity_errors(self, instance):
        return instance.errors.count()

    def execution_date_start(self, instance):
        return instance.execution_date_start

    def time_seconds_start(self, obj):
        return obj.execution_date_start.strftime("%d-%m-%Y às %H:%M:%S")

    def time_seconds_finish(self, obj):
        if not obj.execution_date_finish:
            return '-'
        return obj.execution_date_finish.strftime("%d-%m-%Y às %H:%M:%S")

    def code_executed_query(self, instance):
        return format_html('<pre><code class="prettyprint lang-sql">{}</code></pre>',
                           instance.executed_query)

    quantity_errors.short_description = 'Total de erros'
    time_seconds_start.short_description = 'Inicio'
    time_seconds_finish.short_description = 'Fim'
    list_display = [
        'name', 'db_name_source', 'db_host_source', 'time_seconds_start',
        'time_seconds_finish', 'read_quantity', 'imported_quantity',
        'quantity_errors', 'status'
    ]
    date_hierarchy = 'execution_date_start'
    fields = ('name', 'db_name_source', 'db_host_source',
              'execution_date_start', 'execution_date_finish', 'read_quantity',
              'imported_quantity', 'quantity_errors', 'status',
              'code_executed_query')

    inlines = [DashboardErrorInline]


admin.site.register(DashboardETL, DashboardETLAdmin)
