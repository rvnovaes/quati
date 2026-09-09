from .models import TypeTask, Task, Ecm, TypeTaskMain, TaskFilterViewModel
from rest_framework import serializers
from core.models import Person, Office
from core.serializers import OfficeDefault, CreateUserDefault, CreateUserSerializerMixin, OfficeSerializerMixin, \
    AuditSerializerMixin
from rest_framework.pagination import PageNumberPagination
from task.utils import validate_final_deadline_date
from task.messages import min_hour_error
from manager.utils import get_template_value_value
from manager.enums import TemplateKeys


class PersonAskedByDefault(object):
    requires_context = True

    def __call__(self, serializer_field):
        try:
            self.person_asked_by = serializer_field.context[
                'request'].auth.application.user.person
        except:
            self.person_asked_by = None
        return self._value()

    def _value(self):
        return self.person_asked_by

    def __repr__(self):
        return '%s()' % self.__class__.__name__


class TypeTaskMainSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeTaskMain
        fields = ('id', 'name', 'is_hearing')


class TypeTaskSerializer(serializers.ModelSerializer, CreateUserSerializerMixin, OfficeSerializerMixin):
    class Meta:
        model = TypeTask
        fields = ('id', 'name', 'type_task_main', 'legacy_code', 'create_user', 'office')


class TaskSerializer(serializers.ModelSerializer, AuditSerializerMixin, CreateUserSerializerMixin,
                     OfficeSerializerMixin):

    external_url = serializers.SerializerMethodField()

    class Meta:
        model = Task
        exclude = ('alter_date', 'alter_user', 'create_date', 'survey_result', 'chat', 'company_chat',
                   'price_category', 'executed_by_checkin', 'company_representative_checkin', 'amount_delegated',
                   'amount_to_receive', 'amount_to_pay', 'rate_type_receive', 'rate_type_pay', 'charge')
    
    def get_external_url(self, obj):
        return 'providencias/external-task-detail/' + obj.task_hash.hex

    def validate_person_asked_by(self, value):
        if not value:
            raise serializers.ValidationError("O escritório da sessão não possui um usuário padrão. "
                                              "Entre em contato com o suporte")
        return value

    def validate_legacy_code(self, value):
        office = self.fields['office'].get_default()
        if Task.objects.filter(office=office, legacy_code=value):
            raise serializers.ValidationError("O legacy_code informado já está sendo utilizado neste escritório")
        return value

    def validate_final_deadline_date(self, obj):
        office = self.fields['office'].get_default()
        if not validate_final_deadline_date(obj, office):
            min_hour = get_template_value_value(office, TemplateKeys.MIN_HOUR_OS.name)
            raise serializers.ValidationError(min_hour_error(min_hour))
        return obj


class TaskCreateSerializer(TaskSerializer):

    class Meta:
        model = Task
        fields = ('id', 'final_deadline_date', 'performance_place', 'movement', 'type_task', 'description',
                  'task_status', 'legacy_code', 'requested_date', 'create_user', 'office', 'task_hash')


class TaskDashboardSerializer(serializers.ModelSerializer):
    external_url = serializers.SerializerMethodField()
    have_child = serializers.SerializerMethodField()
    default_user = serializers.SerializerMethodField()

    class Meta:
        model = TaskFilterViewModel
        exclude = ('alter_date', 'system_prefix', 'task_hash')

    def get_external_url(self, obj):
        return 'providencias/external-task-detail/' + obj.task_hash.hex

    def get_have_child(self, obj):
        return obj.get_latest_child_not_refused != None

    def get_default_user(self, obj):
        default_user = obj.office.get_template_value(TemplateKeys.DEFAULT_USER.name)
        return default_user.id if default_user else None


class EcmTaskSerializer(serializers.ModelSerializer,
                        CreateUserSerializerMixin):
    class Meta:
        model = Ecm
        exclude = ('create_date', 'alter_date', 'alter_user', 'is_active', 'updated', 'ecm_related')

    def validate_task(self, obj):
        office = self.context['request'].auth.application.office
        if obj.office != office:
            raise serializers.ValidationError("A OS indicada não pertence ao escritório da sessão")
        return obj


class OfficeToPaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Office
        fields = ('pk', 'legal_name')


class TaskToPaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ('pk', 'amount', 'parent')


class AmountByCorrespondentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    executed_by_id = serializers.IntegerField()
    sol_legal_name = serializers.CharField()
    cor_legal_name = serializers.CharField()
    amount_delegated = serializers.IntegerField()
    amount_to_pay = serializers.IntegerField()


class TaskToPayDashboardSerializer(serializers.ModelSerializer):
    have_child = serializers.SerializerMethodField()
    office_legal_name = serializers.SerializerMethodField()
    executed_by_legal_name = serializers.SerializerMethodField()
    executed_by_id = serializers.SerializerMethodField()
    type_task_name = serializers.SerializerMethodField()
    fee = serializers.SerializerMethodField()
    fee_child = serializers.SerializerMethodField()
    default_user = serializers.SerializerMethodField()
    law_suit_number = serializers.SerializerMethodField()
    cost_center_name = serializers.SerializerMethodField()
    court_district_name = serializers.SerializerMethodField()
    external_url = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ('id', 'have_child', 'office_id', 'office_legal_name', 'executed_by_id', 'executed_by_legal_name',
                  'type_task_name', 'task_number', 'finished_date', 'amount_delegated', 'amount_to_pay', 'amount',
                  'amount_to_receive', 'court_district_name', 'cost_center_name', 'fee', 'fee_child', 'default_user',
                  'law_suit_number', 'task_hash', 'external_url')

    def get_have_child(self, obj):
        return obj.get_latest_child_not_refused != None

    def get_office_legal_name(self, obj):
        return obj.office.legal_name

    def get_executed_by_legal_name(self, obj):
        return obj.get_latest_child_not_refused.office.legal_name if obj.get_latest_child_not_refused else obj.person_executed_by.legal_name

    def get_executed_by_id(self, obj):
        return obj.get_latest_child_not_refused.office.id if obj.get_child else obj.person_executed_by.id

    def get_type_task_name(self, obj):
        return obj.type_task.name

    def get_fee(self, obj):
        return obj.amount_to_pay - obj.amount_delegated

    def get_fee_child(self, obj):
        return obj.amount_to_receive - obj.amount

    def get_default_user(self, obj):
        default_user = obj.office.get_template_value(TemplateKeys.DEFAULT_USER.name)
        return default_user.id if default_user else None

    def get_law_suit_number(self, obj):
        return obj.movement.law_suit.law_suit_number

    def get_cost_center_name(self, obj):
        if obj.movement.folder.cost_center:
            return obj.movement.folder.cost_center.name
        return ''

    def get_court_district_name(self, obj):
        if obj.movement.law_suit.court_district:
            return obj.movement.law_suit.court_district.name
        return ''

    def get_external_url(self, obj):
        return 'providencias/external-task-detail/' + obj.task_hash.hex


class TaskCheckinSerializer(serializers.ModelSerializer):
    date_executed_by_checkin = serializers.SerializerMethodField()
    task_company_representative = serializers.SerializerMethodField()
    date_company_representative_checkin = serializers.SerializerMethodField()
    os_executor = serializers.SerializerMethodField()
    law_suit_number = serializers.SerializerMethodField()
    person_customer = serializers.SerializerMethodField()
    type_task_name = serializers.SerializerMethodField()

    class Meta:
        model = Task
        depth = 0
        fields = ('pk', 'task_number', 'type_task_name', 'final_deadline_date',
                  'os_executor', 'date_executed_by_checkin',
                  'task_company_representative', 'date_company_representative_checkin',
                  'law_suit_number', 'person_customer')

    def get_date_executed_by_checkin(self, obj):
        return obj.executed_by_checkin.date if obj.executed_by_checkin else None

    def get_task_company_representative(self, obj):
        return obj.company_representative_checkin.create_user.person.legal_name if obj.company_representative_checkin \
            else None

    def get_date_company_representative_checkin(self, obj):
        return obj.company_representative_checkin.date if obj.company_representative_checkin else None

    def get_os_executor(self, obj):
        return obj.os_executor

    def get_law_suit_number(self, obj):
        return obj.lawsuit_number

    def get_person_customer(self, obj):
        return obj.movement.law_suit.folder.person_customer.legal_name

    def get_type_task_name(self, obj):
        return obj.type_task.name


class TotalToPayByOfficeSerializer(serializers.Serializer):
    office_id = serializers.IntegerField()
    office_legal_name = serializers.CharField(max_length=255, source='office__legal_name')
    total_to_pay = serializers.DecimalField(max_digits=9, decimal_places=2)
    total_delegated = serializers.DecimalField(max_digits=9, decimal_places=2)


class CustomResultsSetPagination(PageNumberPagination):
    page_size_query_param = 'page_size'


class LargeResultsSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000
