from core.models import Person
from collections import OrderedDict
from django.db import transaction
from import_export import resources
from import_export.widgets import CharWidget, IntegerWidget
from import_export.results import RowResult, Result
from task.fields import CustomFieldImportExport
from task.instance_loaders import TaskModelInstanceLoader
from task.models import Task, TypeTask, TaskStatus
from task.utils import self_or_none, set_performance_place
from task.task_import import TRUE_FALSE_DICT, COLUMN_NAME_DICT, ImportFolder, ImportLawSuit, ImportMovement, ImportTask
from task.widgets import PersonAskedByWidget, TaskStatusWidget, DateTimeWidgetMixin, PersonCompanyRepresentative, \
    TypeTaskByWidget
import logging

logger = logging.getLogger('resources')


class TaskRowResult(RowResult):
    IMPORT_TYPE_WARNING = 'warning'

    def __init__(self):
        super().__init__()
        self.warnings = []


class TaskResult(Result):

    def __init__(self):
        super().__init__()
        self.totals = OrderedDict([(TaskRowResult.IMPORT_TYPE_NEW, 0),
                                   (TaskRowResult.IMPORT_TYPE_UPDATE, 0),
                                   (TaskRowResult.IMPORT_TYPE_DELETE, 0),
                                   (TaskRowResult.IMPORT_TYPE_SKIP, 0),
                                   (TaskRowResult.IMPORT_TYPE_WARNING, 0),
                                   (TaskRowResult.IMPORT_TYPE_ERROR, 0)])

    def row_warnings(self):
        return [(i + 1, row.warnings)
                for i, row in enumerate(self.rows) if row.warnings]

    def has_warnings(self):
        return bool(self.row_warnings())


class TaskResource(resources.ModelResource):
    movement = CustomFieldImportExport(column_name='movement', attribute='movement_id', saves_null_values=False,
                                       column_name_dict=COLUMN_NAME_DICT)
    task_number = CustomFieldImportExport(column_name='task_number', attribute='task_number', widget=IntegerWidget(),
                                          saves_null_values=True, column_name_dict=COLUMN_NAME_DICT)
    person_asked_by = CustomFieldImportExport(column_name='person_asked_by', attribute='person_asked_by',
                                              widget=PersonAskedByWidget(Person, 'legal_name'), saves_null_values=False,
                                              column_name_dict=COLUMN_NAME_DICT)
    person_company_representative = CustomFieldImportExport(column_name='person_company_representative',
                                                            attribute='person_company_representative',
                                                            widget=PersonCompanyRepresentative(Person, 'legal_name'),
                                                            saves_null_values=False,
                                                            column_name_dict=COLUMN_NAME_DICT)
    type_task = CustomFieldImportExport(column_name='type_task', attribute='type_task',
                                        widget=TypeTaskByWidget(TypeTask, 'name'), saves_null_values=False,
                                        column_name_dict=COLUMN_NAME_DICT)
    task_status = CustomFieldImportExport(column_name='task_status', attribute='task_status', widget=TaskStatusWidget(),
                                          column_name_dict=COLUMN_NAME_DICT, default=TaskStatus.REQUESTED.value)
    final_deadline_date = CustomFieldImportExport(column_name='final_deadline_date', attribute='final_deadline_date',
                                                  widget=DateTimeWidgetMixin(), saves_null_values=False,
                                                  column_name_dict=COLUMN_NAME_DICT)
    performance_place = CustomFieldImportExport(column_name='performance_place', attribute='performance_place',
                                                widget=CharWidget(), saves_null_values=False,
                                                column_name_dict=COLUMN_NAME_DICT)
    legacy_code = CustomFieldImportExport(column_name='legacy_code', attribute='legacy_code', widget=CharWidget(),
                                          saves_null_values=True, column_name_dict=COLUMN_NAME_DICT)
    system_prefix = CustomFieldImportExport(column_name='system_prefix', attribute='system_prefix',
                                            saves_null_values=False, column_name_dict=COLUMN_NAME_DICT)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.office = None
        self.create_user = None
        self.office_id = None
        self.default_type_movement = None
        self.folder = None
        self.lawsuit = None
        self.movement = None
        self.current_line = 0

    class Meta:
        instance_loader_class = TaskModelInstanceLoader
        model = Task
        import_id_fields = ('task_number', 'legacy_code')

    @classmethod
    def get_row_result_class(self):
        """
        Returns the class used to store the result of a row import.
        """
        return TaskRowResult

    @classmethod
    def get_result_class(self):
        """
        Returns the class used to store the result of an import.
        """
        return TaskResult

    def before_import(self, dataset, **kwargs):
        self.office = kwargs['office']
        self.create_user = kwargs['create_user']
        self.office_id = self.office.id
        for k, v in COLUMN_NAME_DICT.items():
            if v['column_name'] in dataset.headers:
                headers_index = dataset.headers.index(v['column_name'])
                dataset.headers[headers_index] = k

        dataset.insert_col(0, col=["", ] * dataset.height, header="id")
        dataset.insert_col(1, col=[int("{}".format(self.office.id)), ] * dataset.height, header="office")
        dataset.insert_col(2, col=[int("{}".format(self.create_user.id)), ] * dataset.height, header="create_user")
        dataset.insert_col(3, col=["", ] * dataset.height, header="movement")
        dataset.insert_col(dataset.width, col=[[], ] * dataset.height, header="warnings")

    def before_import_row(self, row, **kwargs):
        for column, value in row.items():
            row[column] = value.strip() if isinstance(value, str) else value
        row_errors = []
        row['warnings'] = []
        instance = None
        row['task_number'] = self_or_none(row.get('task_number'))
        row['legacy_code'] = self_or_none(row.get('legacy_code'))
        row['is_active'] = TRUE_FALSE_DICT.get('is_active', True)
        if row['task_number'] or row['legacy_code']:
            instance_loader = self._meta.instance_loader_class(self, row)
            instance = self.get_instance(instance_loader, row)
        if not instance:
            with transaction.atomic():
                self.folder, folder_errors = ImportFolder(row, row_errors, self.office, self.create_user).get_folder()
                row_errors.extend(folder_errors)
                if self.folder:
                    self.lawsuit, lawsuit_errors = ImportLawSuit(row, row_errors, self.office, self.create_user,
                                                                 self.folder).get_lawsuit()
                    row_errors.extend(lawsuit_errors)
                if self.lawsuit:
                    self.movement, movement_errors = ImportMovement(row, row_errors, self.office, self.create_user,
                                                                    self.lawsuit).get_movement()

                    row_errors.extend(movement_errors)
                if self.movement:
                    row['movement'] = self.movement.id
                if not row.get('performance_place', None) and self.movement:
                    row['performance_place'] = set_performance_place(self.movement)
                import_task = ImportTask(row, row_errors, self.office, self.create_user)
                if not import_task.validate_task():
                    row_errors.extend(import_task.get_errors())
                if row_errors:
                    transaction.set_rollback(True)
                    raise Exception(list(set(row_errors)))
        else:
            row['id'] = instance.id
            row['task_status'] = instance.task_status
            row['movement'] = instance.movement.id            
            if not row['performance_place']:
                row['performance_place'] = instance.performance_place

    def after_import_row(self, row, row_result, **kwargs):
        line_warnings = row.get('warnings', [])
        if line_warnings:
            for warning in line_warnings:
                row_result.warnings.append(warning)
            row_result.import_type = TaskRowResult.IMPORT_TYPE_WARNING

    def skip_row(self, instance, original):
        if instance.task_status not in [TaskStatus.REQUESTED.value, TaskStatus.ACCEPTED_SERVICE.value]:
            return True
        return super().skip_row(instance, original)
