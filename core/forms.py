from django import forms
from django.db.models import Q
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User, Group
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.forms import ModelForm
from django.forms import CheckboxInput, formset_factory
from django.forms.models import inlineformset_factory
from django.utils.translation import gettext_lazy as _
from django.urls.base import reverse
from django.core.exceptions import FieldDoesNotExist
from localflavor.br.forms import BRCPFField, BRCNPJField
from allauth.account.adapter import get_adapter
from allauth.account.utils import filter_users_by_username, user_pk_to_url_str, user_email
from core.fields import CustomBooleanField
from core.models import ContactUs, Person, Address, City, ContactMechanism, ContactMechanismType, AddressType, \
    LegalType, Office, Invite, InviteOffice, Team
from core.utils import get_office_field, get_office_session, get_domain, get_person_field
from core.widgets import TypeaHeadForeignKeyWidget, MDSelect, CodeMirrorTextarea, MultipleFileField
from core.models import OfficeMixin, ImportXlsFile
from core.utils import validate_xlsx_header
from django.core.exceptions import ValidationError


code_mirror = CodeMirrorTextarea(
    mode="python",
    theme="material",
    config={
        'fixedGutter': True
    }
)
code_mirror_schema = CodeMirrorTextarea(
    mode="javascript",
    theme="material",
    config={
        'fixedGutter': True
    }
)


class BaseModelForm(forms.ModelForm):
    # Layout opcional: lista de linhas, cada linha uma tupla de nomes de campos.
    layout = None

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request:
            self.set_office_queryset()
        usermodel = self._meta.model._meta.app_label == 'auth'
        if usermodel:
            use_upload = False
        else:
            use_upload = getattr(self.instance, "use_upload", False)
        if self.initial.__len__() == 0 and use_upload:
            required = getattr(self.instance, "upload_required", False)
            documents = MultipleFileField(required=required)
            self.fields.update({'documents': documents})

    def get_model_verbose_name(self):
        return self._meta.model._meta.verbose_name

    def delete_temporary_files(self):
        # Compatibilidade com o antigo django-file-form: uploads agora são diretos, nada a limpar.
        return None

    def layout_rows(self):
        """Linhas do layout com os BoundFields correspondentes (para os templates de formulário)."""
        if not self.layout:
            return None
        rows = []
        for row in self.layout:
            rows.append([self[name] for name in row if name in self.fields])
        return rows

    def set_office_queryset(self):
        if get_office_session(self.request) and self.request.method == 'GET':
            for field in self.fields:
                if hasattr(self.fields[field], 'queryset'):
                    subclass_office = issubclass(self.fields[field].queryset.model,
                                                 OfficeMixin)
                    if subclass_office:
                        try:
                            self.fields[field].queryset = self.fields[
                                field].queryset.filter(
                                    office=get_office_session(
                                        request=self.request))
                        except:
                            pass
                    if hasattr(self.fields[field].queryset.model, 'offices') \
                            and not subclass_office:
                        try:
                            self.fields[field].queryset = self.fields[
                                field].queryset.filter(
                                    offices=get_office_session(self.request))
                        except:
                            pass

    def clean(self):
        """
        Sobrescrevemos o método clean para ajustar o valor retornado pelos campos que
        utilizam o widget 'TypeaHeadForeignKeyWidget'
        :return:
        """
        res = super().clean()
        for field, obj in self.base_fields.items():
            if isinstance(obj.widget, TypeaHeadForeignKeyWidget):
                record_id = res.get(field) if res.get(field) else 0
                res[field] = obj.widget.model.objects.filter(
                    pk=record_id).first()
        return res


class BaseForm(BaseModelForm):
    """
    Cria uma Form referência e adiciona o mesmo style a todos os widgets
    """
    is_active = CustomBooleanField(required=False, )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = self._meta.model._meta.verbose_name
        for field_name, field in self.fields.items():
            try:
                if field.widget.input_type != 'checkbox':
                    field.widget.attrs['class'] = 'form-control'
                if field.widget.input_type == 'text':
                    field.widget.attrs[
                        'style'] = 'width: 100%; display: table-cell; '
                # Preenche o o label de cada field do form de acordo com o verbose_name preenchido no modelo
                try:
                    field.label = (self._meta.model._meta.get_field(
                        field_name).verbose_name
                                   if not field.label else field.label)
                except FieldDoesNotExist:
                    pass
            except AttributeError:
                pass


class ContactForm(ModelForm):
    class Meta:
        model = ContactUs
        fields = ['name', 'email', 'phone_number', 'message', 'is_active']

    name = forms.CharField(
        label=u'Nome',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control input-sm'}))

    email = forms.CharField(
        label=u'E-mail',
        required=True,
        max_length=255,
        widget=forms.EmailInput(attrs={'class': 'form-control input-sm'}))

    phone_number = forms.CharField(
        label=u'Telefone',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control input-sm'}))

    message = forms.CharField(
        label=u'Mensagem',
        required=True,
        widget=forms.Textarea(attrs={'class': 'form-control input-sm'}))


class ContactMechanismForm(BaseModelForm):
    class Meta:
        model = ContactMechanism
        fields = [
            'contact_mechanism_type', 'description', 'notes', 'is_active'
        ]

    contact_mechanism_type = forms.ModelChoiceField(
        queryset=ContactMechanismType.objects.all(),
        empty_label='',
        required=True,
        label='Tipo',
    )

    description = forms.CharField(
        label=u'Descrição',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control input-sm'}))

    notes = forms.CharField(
        label=u'Observação',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control input-sm'}))

    is_active = CustomBooleanField(
        required=False,
        label='Ativo',
        widget=CheckboxInput(attrs={
            'class': 'filled-in',
        }))


class AddressForm(BaseModelForm):
    city = forms.ModelChoiceField(label='Cidade',
                                  required=False,
                                  widget=MDSelect(url='/city/autocomplete_select2/', ),
                                  queryset=City.objects.all())
    address_type = forms.ModelChoiceField(
        queryset=AddressType.objects.all(),
        empty_label='',
        required=True,
        label='Tipo',
    )

    is_active = CustomBooleanField(
        required=False,
        label='Ativo',
        widget=CheckboxInput(attrs={
            'class': 'filled-in',
        }))

    layout = [
        ('address_type', ),
        ('street', 'number', 'complement'),
        ('city_region', 'city', 'zip_code'),
        ('notes', ),
        ('is_active', ),
    ]

    class Meta:
        model = Address
        fields = [
            'city',
            'address_type',
            'street',
            'number',
            'complement',
            'zip_code',
            'city_region',
            'notes',
            'is_active',
        ]

    def save(self, commit=True):
        saved = super().save(commit=False)
        saved.country = saved.city.state.country
        saved.state = saved.city.state
        if commit:
            saved.save()
        return saved


class PersonForm(BaseModelForm):
    legal_type = forms.ChoiceField(
        label='Tipo',
        choices=((x.value, x.format(x.value)) for x in LegalType),
        required=True,
    )

    auth_user = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        empty_label='',
        required=False,
        label='Usuário do sistema',
    )
    
    class Meta:
        model = Person
        fields = ['legal_name', 'name', 'legal_type', 'cpf_cnpj', 'is_lawyer', 'is_customer', 'is_supplier',
                  'is_active', 'import_from_legacy', 'refunds_correspondent_service', 'auth_user', 'company',
                  'legacy_code']

    def clean(self):
        cleaned_data = super().clean()
        document_type = cleaned_data.get('legal_type')
        document = cleaned_data.get('cpf_cnpj')
        if document_type == 'F' and document:
            try:
                BRCPFField().clean(document)
            except forms.ValidationError as exc:
                self._errors['cpf_cnpj'] = \
                    self.error_class(exc.messages)
                del cleaned_data['cpf_cnpj']
        elif document_type == 'J' and document:
            try:
                BRCNPJField().clean(document)
            except forms.ValidationError as exc:
                self._errors['cpf_cnpj'] = \
                    self.error_class(exc.messages)
                del cleaned_data['cpf_cnpj']

        return cleaned_data

    def __init__(self, *args, **kwargs):
        is_admin = kwargs.pop('is_admin', None)
        super().__init__(*args, **kwargs)
        if is_admin:
            self.layout = [
                ('legal_name', 'name'),
                ('legal_type', 'cpf_cnpj'),
                ('auth_user', 'import_from_legacy'),
                ('is_lawyer', 'is_customer', 'is_supplier', 'is_active'),
            ]
        else:
            self.layout = [
                ('legal_name', 'name'), ('legal_type', 'cpf_cnpj'),
                ('is_lawyer', 'is_customer', 'is_supplier', 'is_active')]


AddressFormSet = inlineformset_factory(
    Person, Address, form=AddressForm, extra=1, max_num=1)


class UserBaseForm(BaseForm):
    first_name = forms.CharField(
        label='Nome',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autofocus': ''
        }))

    last_name = forms.CharField(
        label='Sobrenome',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    email = forms.EmailField(
        label='E-mail',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance', None)
        self.fields['office'] = get_office_field(self.request, profile=instance)
        self.fields['office'].label = 'Escritório padrão'
        self.fields['person'] = get_person_field(self.request, user=instance)


class UserCreateForm(UserCreationForm, UserBaseForm):
    username = forms.CharField(
        label='Nome de usuário (login)',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    password1 = forms.CharField(
        label=_('Senha'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'type': 'password'
        }),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label=_('Confirmação de Senha'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'type': 'password'
        }),
        strip=False,
        help_text=_('Enter the same password as before, for verification.'),
    )

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'username', 'email', 'password1',
            'password2', 'groups', 'is_active'
        ]


class UserUpdateForm(UserChangeForm, UserBaseForm):
    username = forms.CharField(
        label='Nome de usuário (login)',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    is_active = CustomBooleanField(required=False, label='Ativo')

    password = forms.CharField(
        label='Senha',
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'type': 'password'
        }))

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'username', 'email', 'password',
            'is_active'
        ]


class ResetPasswordFormMixin(forms.Form):
    username = forms.CharField(
        label=_("Username"),
        required=True,
        widget=forms.TextInput(attrs={
            "size": "30",
            "placeholder": _("Username"),
        }))

    def clean_username(self):
        username = self.cleaned_data["username"]
        self.users = filter_users_by_username(username)
        if not self.users:
            raise forms.ValidationError(
                _(u"O Usuário informado não está vinculado"
                  " a nenhuma conta"))
        if not self.users[0].email or self.users[0].email == ' ':
            raise forms.ValidationError(
                _(u"O Usuário informado não possui e-mail registrado"))

        self.email = self.users[0].email
        return self.cleaned_data["username"]

    def save(self, request, **kwargs):
        current_site = get_current_site(request)
        username = self.cleaned_data["username"]

        token_generator = kwargs.get("token_generator",
                                     default_token_generator)

        self.context = {}
        for user in self.users:
            temp_key = token_generator.make_token(user)

            # send the password reset email
            try:
                base_url = request.META.get('HTTP_REFERER')[:-1]
            except:
                base_url = get_domain(request)
            path = reverse(
                "account_reset_password_from_key",
                kwargs=dict(uidb36=user_pk_to_url_str(user), key=temp_key))
            url = '{}{}'.format(base_url, path)

            context = {
                "current_site": current_site,
                "user": user,
                "password_reset_url": url,
                "request": request,
                'username': username
            }

            email = user_email(user)
            get_adapter(request).send_mail('account/email/password_reset_key',
                                           email, context)
            self.context = context
        return self.context


class RegisterNewUserForm(UserCreationForm):
    first_name = forms.CharField(
        label='Nome',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autofocus': ''
        }))

    last_name = forms.CharField(
        label='Sobrenome',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    email = forms.EmailField(
        label='E-mail',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    username = forms.CharField(
        label='Nome de usuário (login)',
        required=True,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    password1 = forms.CharField(
        label=_('Senha'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'type': 'password'
        }),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label=_('Confirmação de Senha'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'type': 'password'
        }),
        strip=False,
        help_text=_('Enter the same password as before, for verification.'),
    )

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'username', 'email', 'password1',
            'password2'
        ]

    def clean_email(self):
        email = self.cleaned_data.get('email')
        username = self.cleaned_data.get('username')
        if email and User.objects.filter(email=email).exclude(
                username=username).exists():
            raise forms.ValidationError(
                'Já existe usuário cadastrado com este e-mail.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(
                'O valor informado no campo usuário não está disponível')
        return username


class OfficeForm(BaseModelForm):
    class Meta:
        model = Office
        fields = [
            'legal_name', 'name', 'legal_type', 'cpf_cnpj', 'is_active'
        ]

    def clean(self):
        cleaned_data = super().clean()
        document_type = cleaned_data.get('legal_type')
        document = cleaned_data.get('cpf_cnpj')
        if document_type == 'F' and document:
            try:
                BRCPFField().clean(document)
            except forms.ValidationError as exc:
                self._errors['cpf_cnpj'] = \
                    self.error_class(exc.messages)
                del cleaned_data['cpf_cnpj']
        elif document_type == 'J' and document:
            try:
                BRCNPJField().clean(document)
            except forms.ValidationError as exc:
                self._errors['cpf_cnpj'] = \
                    self.error_class(exc.messages)
                del cleaned_data['cpf_cnpj']
        return cleaned_data


class OfficeProfileForm(OfficeForm):

    logo = forms.FileField(required=False)

    class Meta:
        model = Office
        fields = [
            'legal_name', 'name', 'legal_type', 'cpf_cnpj', 'is_active', 'logo'
        ]    


class InviteForm(forms.ModelForm):
    person = forms.CharField(
        widget=TypeaHeadForeignKeyWidget(
            model=Person, field_related='legal_name', name='person'))

    class Meta:
        model = Invite
        fields = ['office', 'person', 'invite_code', 'email', 'status']
        exclude = ['is_active']


InviteOfficeFormSet = inlineformset_factory(
    Office, Invite, form=InviteForm, extra=1, max_num=1)


class InviteOfficeForm(BaseForm):
    office_invite = forms.CharField(
        widget=TypeaHeadForeignKeyWidget(
            model=Office, field_related='legal_name', name='office_invite'))

    class Meta:
        model = InviteOffice
        fields = ['office', 'office_invite']
        exclude = ['is_active']


class TeamMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        if hasattr(obj, 'person'):
            return obj.person.legal_name
        return obj.username


class TeamForm(BaseForm):
    members = TeamMultipleChoiceField(queryset=User.objects.all())
    supervisors = TeamMultipleChoiceField(
        queryset=User.objects.filter(groups__name__contains='Supervisor'))

    class Meta:
        model = Team
        fields = ['office', 'name', 'members', 'supervisors', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'] = get_office_field(self.request)
        self.fields['supervisors'].queryset = self.fields[
            'supervisors'].queryset.filter(
                Q(person__offices=get_office_session(request=self.request)),
                ~Q(username__in=['admin', 'invalid_user']))
        self.fields['members'].queryset = self.fields[
            'members'].queryset.filter(
                Q(person__offices=get_office_session(request=self.request)),
                ~Q(username__in=['admin', 'invalid_user']))


class XlsxFileField(forms.FileField):
    """
    Field to validate xlsx extension and header 
    """

    def __init__(self, headers_to_check, *args, **kwargs):
        self.headers_to_check = headers_to_check
        super().__init__(*args, **kwargs)

    def validate(self, value):
        super().validate(value)
        if not value.name.endswith('.xlsx'):
            raise ValidationError(('Extensão inválida'), code='invalid')
        if not validate_xlsx_header(value, self.headers_to_check):
            msg = 'Cabeçalho inválido. O arquivo deve conter por padrão o seguinte cabeçalho: {}'.format(
                ' | '.join(self.headers_to_check))
            raise ValidationError((msg), code='invalid')


class ImportCityListForm(forms.ModelForm):
    file_xls = XlsxFileField(
        label='Arquivo', required=True, headers_to_check=['UF', 'MUNICÍPIO'])

    class Meta:
        model = ImportXlsFile
        fields = ('file_xls', )