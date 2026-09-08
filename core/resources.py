from core.models import State, City, ImportXlsFile
from import_export import resources
from import_export.widgets import CharWidget
from lawsuit.models import CourtDistrict
from task.widgets import UnaccentForeignKeyWidget

from import_export.fields import Field
from import_export.instance_loaders import BaseInstanceLoader


class CityInstanceLoader(BaseInstanceLoader):
    """
    Instance loader for Task model.

    Lookup for model instance by ``import_id_fields`` using non Null values for import_id_fields.
    """

    def get_queryset(self):
        return self.resource._meta.model.objects.all()

    def get_instance(self, row):
        ret = None
        params = {}
        for key in self.resource.get_import_id_fields():
            field = self.resource.fields[key]
            if key == 'name':
                params['{}__unaccent__iexact'.format(field.attribute)] = field.clean(row)
            else:
                params['{}'.format(field.attribute)] = field.clean(row)
            params['{}__isnull'.format(field.attribute)] = False
        instance = self.get_queryset().filter(**params).first()
        if instance:
            row['id'] = instance.id
            if not row['comarca']:
                row['comarca'] = instance.court_district.name if instance.court_district else ''
            ret = instance
        return ret


class CityResource(resources.ModelResource):
    state = Field(column_name='UF', attribute='state', widget=UnaccentForeignKeyWidget(State, 'initials'),
                  saves_null_values=False)
    name = Field(column_name='MUNICÍPIO', attribute='name', widget=CharWidget(), saves_null_values=False)
    court_district = Field(column_name='comarca', attribute='court_district',
                           widget=UnaccentForeignKeyWidget(CourtDistrict, 'name'), saves_null_values=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.office = None
        self.create_user = None
        self.office_id = None
        self._meta.instance_loader_class = CityInstanceLoader
        self.current_line = 0
        self.total_lines = 0
        self.status = 'Em andamento'
        self.file_id = None
        self.xls_file = None

    class Meta:
        model = City
        import_id_fields = ('name', 'state')
        fields = ('name', 'state', 'court_district', 'create_user')

    def get_court_district(self, row, row_errors):
        court_district = CourtDistrict.objects.filter(**{'name__unaccent__iexact': row['MUNICÍPIO'],
                                                         'state__initials__iexact': row['UF']}).first()
        return court_district.name if court_district else ''

    def before_import(self, dataset, **kwargs):
        self.file_id = kwargs.get('xls_file_id')
        self.xls_file = ImportXlsFile.objects.get(pk=self.file_id)
        self.total_lines = len(dataset)
        self.office = kwargs['office']
        self.create_user = kwargs['create_user']
        self.office_id = self.office.id

        dataset.insert_col(0, col=["", ] * dataset.height, header="id")
        dataset.insert_col(2, col=[int("{}".format(self.create_user.id)), ] * dataset.height, header="create_user")
        dataset.insert_col(dataset.width, col=["", ] * dataset.height, header="comarca")
        dataset.insert_col(dataset.width, col=[[], ] * dataset.height, header="warnings")

    def before_import_row(self, row, **kwargs):
        self.current_line += 1
        self.xls_file.log_file = "{\"status\": \"%s\" , \"current_line\": %d, \"total_lines\": %d}" % (
            self.status, self.current_line, self.total_lines)
        self.xls_file.save()
        row['UF'] = row['UF'].strip()
        row['MUNICÍPIO'] = row['MUNICÍPIO'].replace('*', '').strip()
        row_errors = []
        row['comarca'] = self.get_court_district(row, row_errors)
        if row_errors:
            raise Exception(row_errors)
