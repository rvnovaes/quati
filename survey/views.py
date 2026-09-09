from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import View
from django.views.generic.edit import CreateView, UpdateView

from core.messages import CREATE_SUCCESS_MESSAGE, DELETE_SUCCESS_MESSAGE, UPDATE_SUCCESS_MESSAGE
from core.utils import get_office_session
from core.views import (
    AuditFormMixin, CustomLoginRequiredView, OfficePermissionRequiredMixin, SingleTableViewMixin,
)
from .forms import SurveyForm
from .models import Survey, SurveyPermissions
from .tables import SurveyTable


class SurveyAccessMixin(CustomLoginRequiredView, OfficePermissionRequiredMixin):
    """Authorize the selected office and scope every object lookup to it."""
    model = Survey
    permission_required = (SurveyPermissions.can_edit_surveys,)

    def has_permission(self):
        return bool(get_office_session(self.request)) and super().has_permission()

    def get_queryset(self):
        return super().get_queryset().filter(office=get_office_session(self.request))


class SurveyListView(SurveyAccessMixin, SingleTableViewMixin):
    table_class = SurveyTable
    ordering = ('id',)


class SurveyCreateView(SurveyAccessMixin, AuditFormMixin, CreateView):
    form_class = SurveyForm
    success_url = reverse_lazy('survey_list')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'survey_list'


class SurveyUpdateView(SurveyAccessMixin, AuditFormMixin, UpdateView):
    form_class = SurveyForm
    success_url = reverse_lazy('survey_list')
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_update_form'
    object_list_url = 'survey_list'


class SurveyDeleteView(SurveyAccessMixin, View):
    success_url = reverse_lazy('survey_list')

    def post(self, request, *args, **kwargs):
        try:
            selected_ids = {int(pk) for pk in request.POST.getlist('selection')}
        except (ValueError, TypeError):
            raise Http404('Questionário não encontrado')

        # Validate the entire batch before deleting anything. Lock the selected
        # rows so ownership cannot change between authorization and deletion.
        with transaction.atomic():
            surveys = Survey.objects.select_for_update().filter(
                office=get_office_session(request), pk__in=selected_ids)
            if set(surveys.values_list('pk', flat=True)) != selected_ids:
                raise Http404('Questionário não encontrado')
            try:
                surveys.delete()
            except ProtectedError:
                messages.error(
                    request, 'Não é possível excluir questionários vinculados a outros registros.')
            else:
                messages.success(
                    request, DELETE_SUCCESS_MESSAGE.format(Survey._meta.verbose_name_plural))
        return HttpResponseRedirect(self.success_url)
