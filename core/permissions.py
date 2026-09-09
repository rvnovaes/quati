from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core.models import Person, OfficeRelGroup, CorePermissions
from core.utils import get_office_session
from task.models import Permissions
from survey.models import SurveyPermissions
from financial.models import FinancialPermissions
from guardian.shortcuts import assign_perm, remove_perm
from guardian.core import ObjectPermissionChecker

GROUP_PERMISSIONS = {
    Person.ADMINISTRATOR_GROUP: (
        CorePermissions.group_admin,
        CorePermissions.view_reports,
        FinancialPermissions.view_financial_report,
        FinancialPermissions.billing_task,
        Permissions.can_access_general_data,
        Permissions.can_access_settings,
        Permissions.can_distribute_tasks,
        Permissions.view_all_tasks,
        Permissions.return_all_tasks,
        Permissions.validate_all_tasks,
        Permissions.view_checkin_report,
        Permissions.block_payment_tasks,
        SurveyPermissions.can_edit_surveys,
        SurveyPermissions.can_view_survey_results,
    ),
    Person.SUPERVISOR_GROUP: (
        CorePermissions.view_reports,
        FinancialPermissions.view_financial_report,
        Permissions.can_access_settings,
        Permissions.block_payment_tasks,
        Permissions.can_access_general_data,
        Permissions.can_distribute_tasks,
        Permissions.view_distributed_tasks,
        Permissions.view_requested_tasks,
        Permissions.view_delegated_tasks,
        Permissions.can_see_tasks_from_team_members,
        Permissions.view_checkin_report,
        SurveyPermissions.can_edit_surveys,
        SurveyPermissions.can_view_survey_results,
    ),
    Person.SERVICE_GROUP: (
        Permissions.view_distributed_tasks,
        Permissions.return_all_tasks,
        Permissions.validate_all_tasks,
        Permissions.block_payment_tasks,
        Permissions.can_access_general_data,
        Permissions.can_distribute_tasks,
        SurveyPermissions.can_edit_surveys,
        SurveyPermissions.can_view_survey_results,
    ),
    Person.CORRESPONDENT_GROUP: (
        Permissions.view_delegated_tasks,
    ),
    Person.REQUESTER_GROUP: (
        Permissions.return_all_tasks,
        Permissions.validate_all_tasks,
        Permissions.view_requested_tasks,
        Permissions.block_payment_tasks,
        Permissions.can_access_general_data,
    ),
    Person.COMPANY_REPRESENTATIVE: (
        Permissions.can_see_tasks_company_representative,
    ),
    Person.FINANCE_GROUP: (
        CorePermissions.view_reports,
        FinancialPermissions.view_financial_report,
        FinancialPermissions.billing_task,
    )
}


def create_permission(office):
    from core.models import Office
    content_type = ContentType.objects.get_for_model(Office)
    for group_name, permissions in GROUP_PERMISSIONS.items():
        name = '{}-{}'.format(group_name, office.id)
        group, nil = create_group(name)
        update_groups(
            group_name, '{}-{}-{}'.format(group_name, office.id,
                                          office.legal_name), office)
        group.permissions.clear()
        OfficeRelGroup.objects.filter(group=group).delete()
        for permission in Permissions:
            remove_perm(permission.name, group, office)
        for codename in permissions:
            permission, nil = Permission.objects.get_or_create(
                codename=codename.name,
                content_type=content_type,
                defaults={'name': codename.value})
            assign_perm(codename.name, group, office)
            group.permissions.add(permission)
            OfficeRelGroup.objects.get_or_create(office=office, group=group)


def create_group(group_name):
    return Group.objects.get_or_create(name=group_name)


def update_groups(group_name, name_to_search, office):
    groups = Group.objects.filter(name=name_to_search)
    for group in groups:
        if Group.objects.filter(
                name='{}-{}'.format(group_name, office.id)).exists():
            old_group = Group.objects.filter(
                name='{}-{}'.format(group_name, office.id)).first()
            for user in group.user_set.all():
                old_group.user_set.add(user)
            group.user_set.clear()
            group.delete()
        else:
            group.name = '{}-{}'.format(group_name, office.id)
            group.save()


class CustomPermissionRequiredMixin(PermissionRequiredMixin):
    """
    Customization of PermissionRequiredMixin class, using guardian methods

    require_all_perms: if set true, all permissions passed on permission_required will be required
    """
    require_all_perms = False
    login_url = '/'

    def has_permission(self):
        perms = self.get_permission_required()
        checker = ObjectPermissionChecker(self.request.user)
        user_has_perms = []
        for permission in perms:
            user_has_perms.append(checker.has_perm(permission, get_office_session(self.request)))

        has_perms = self._check_perms(user_has_perms)
        if not has_perms:
            messages.add_message(self.request, messages.ERROR,
                                 'Você não tem permissão para acessar o endereço solicitado.')
        return has_perms

    def _check_perms(self, user_has_perms):
        if self.require_all_perms:
            return False not in user_has_perms
        return True in user_has_perms
