from django.contrib.auth.models import User
from django.utils.safestring import mark_safe

import django_tables2 as tables
from django_tables2.utils import AttributeDict, A

from .models import Person, Address, Office, Invite, OfficeMembership, ContactMechanism, Team


class CheckBoxMaterial(tables.CheckBoxColumn):
    def __init__(self, attrs=None, checked=None, **extra):
        self.checked = checked
        kwargs = {'orderable': False, 'attrs': attrs}
        kwargs.update(extra)
        super(CheckBoxMaterial, self).__init__(**kwargs)

    # @property
    # def selectable(self):
    #     return True;

    def header(self):
        default = {'type': 'checkbox'}
        general = self.attrs.get('input')
        specific = self.attrs.get('th__input')
        attrs = AttributeDict(default, **(specific or general or {}))
        attrs['selectable'] = True
        return mark_safe(
            ('<input %s id="selection_header"  onclick="toggle(this)"/>') %
            attrs.as_html())

    def render(self, value, bound_column, record):
        default = {
            'type': 'checkbox',
            'name': bound_column.name,
            'value': value,
        }
        if self.is_checked(value, record):
            default.update({
                'checked': 'checked',
            })

        general = self.attrs.get('input')
        specific = self.attrs.get('td__input')
        attrs = AttributeDict(default, **(specific or general or {}))
        attrs['id'] = record.id
        return mark_safe(
            '<input name="selection" type="checkbox" %s onclick="showDeleteButton(this)"/>'
            % attrs.as_html())


class AddressTable(tables.Table):

    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequecence = ('selection', 'street', 'number', 'complement',
                      'city_region', 'zip_code', 'city', 'state', 'country',
                      'notes', 'address_type', 'is_active')
        model = Address
        fields = [
            'selection', 'street', 'number', 'complement', 'city_region',
            'zip_code', 'city', 'state', 'country', 'notes', 'address_type',
            'is_active'
        ]
        attrs = {"class": "table-striped table-bordered"}
        row_attrs = {
            'pk': lambda record: str(record.pk),
            'data_href': lambda record: '/pessoas/' + str(record.person.pk) + '/enderecos/' + str(record.pk) + '/'
        }


class AddressOfficeTable(AddressTable):
    class Meta:
        row_attrs = {
            'pk': lambda record: str(record.pk),
            'data_href': lambda record: '/escritorios/' + str(record.office.pk) + '/enderecos/' + str(record.pk) + '/'
        }


class PersonTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequecence = ('selection', 'legal_name', 'name', 'is_lawyer', 'legal_type', 'cpf_cnpj', 'is_active',
                      'is_customer', 'is_supplier', 'auth_user', 'legacy_code')
        model = Person
        fields = [
            'selection', 'legal_name', 'name', 'legal_type', 'cpf_cnpj', 'is_lawyer', 'is_customer', 'is_supplier',
            'auth_user', 'is_active', 'legacy_code'
        ]
        attrs = {"class": "table-striped table-bordered"}
        empty_text = "Não existem pessoas cadastradas"
        row_attrs = {
            'data_href': lambda record: '/pessoas/' + str(record.pk) + '/'
        }
        order_by = 'legal_name'


class UserTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)
    is_staff = tables.BooleanColumn()
    is_superuser = tables.BooleanColumn()

    def __init__(self,
                 *args,
                 first_name='Nome',
                 last_name='Sobrenome',
                 is_active="Ativo",
                 username="Nome de usuário (login)",
                 email="e-mail",
                 last_login="Último acesso",
                 date_joined="Data de registro",
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.base_columns['first_name'].verbose_name = first_name
        self.base_columns['last_name'].verbose_name = last_name
        self.base_columns['username'].verbose_name = username
        self.base_columns['email'].verbose_name = email
        self.base_columns['is_active'].verbose_name = is_active
        self.base_columns['last_login'].verbose_name = last_login
        self.base_columns['date_joined'].verbose_name = date_joined
        self.exclude = ('is_staff', 'is_superuser')

    class Meta:

        model = User
        fields = [
            'selection', 'first_name', 'last_name', 'username', 'email',
            'last_login', 'date_joined', 'is_active'
        ]
        attrs = {"class": "table-striped table-bordered"}

        empty_text = "Não existem usuários cadastradas"

        row_attrs = {
            'data_href': lambda record: '/usuarios/' + str(record.pk) + '/'
        }


class OfficeTable(tables.Table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.exclude = ('pk', 'name', 'legal_name')

    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        exclude = ('id', 'create_date', 'create_user', 'auth_user',
                   'alter_user', 'is_customer', 'is_supplier', 'alter_date',
                   'legacy_code', 'system_prefix', 'is_lawyer',
                   'import_from_legacy', 'public_office')
        sequence = ('selection', 'legal_name', 'name', 'legal_type',
                    'cpf_cnpj')
        model = Office
        row_attrs = {
            'data_href': lambda record: '/escritorios/' + str(record.pk) + '/'
        }


class InviteTable(tables.Table):
    class Meta:
        model = Invite
        fields = ('person', 'email', 'person__auth_user', 'status')


class InviteOfficeTable(tables.Table):
    class Meta:
        model = Invite
        fields = ('office_invite', 'status')


class OfficeMembershipTable(tables.Table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        paginate = False
        model = OfficeMembership
        fields = ('selection', 'person__legal_name', 'person__legal_type',
                  'person__cpf_cnpj', 'person__auth_user__username')


class OfficeMembershipOfficeTable(tables.Table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        model = OfficeMembership
        fields = ('selection', 'office__legal_name', 'office__cpf_cnpj')


class ContactMechanismTable(tables.Table):

    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        sequecence = ('selection', 'contact_mechanism_type', 'description',
                      'notes', 'is_active')
        model = ContactMechanism
        fields = [
            'selection', 'contact_mechanism_type', 'description', 'notes',
            'is_active'
        ]
        attrs = {"class": "table-striped table-bordered"}
        row_attrs = {
            'pk': lambda record: str(record.pk),
            'data_href':
            lambda record: '/pessoas/' + str(record.person.pk) + '/contatos/' + str(record.pk) + '/'
        }


class ContactMechanismOfficeTable(ContactMechanismTable):
    class Meta:
        row_attrs = {
            'pk': lambda record: str(record.pk),
            'data_href':
            lambda record: '/escritorios/' + str(record.office.pk) + '/contatos/' + str(record.pk) + '/'
        }


class TeamTable(tables.Table):
    selection = CheckBoxMaterial(accessor="pk", orderable=False)

    class Meta:
        model = Team
        fields = ['selection', 'name', 'is_active']
        attrs = {"class": "table-striped table-bordered"}
        row_attrs = {
            'data_href': lambda record: '/teams/' + str(record.pk) + '/'
        }
