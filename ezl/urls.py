import os

from django.urls import re_path as url, include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from core import views_api
from core.views import (
    ClientAutocomplete, GenericAutocompleteForeignKey, LoginCustomView, PasswordResetViewMixin,
    CorrespondentAutocomplete, RequesterAutocomplete, ServiceAutocomplete, EditableListSave, PopupSuccessView,
    OfficeAutocomplete, OfficeCorrespondentAutocomplete, OriginRequesterAutocomplete, SocialRegister, TermsView)
from django.conf import settings
from task.views import DashboardView, TaskDetailView, DashboardSearchView, DashboardStatusCheckView, \
    TaskBulkCreateView, ToReceiveTaskReportView, ToPayTaskReportView, ToPayTaskReportTemplateView, ToPayTaskReportXlsxView
from core.views import oauth2_login, oauth2_callback


urlpatterns = [
    url(r'^', include('core.urls')),    
    url(r'^admin/', admin.site.urls),
    url(r'^accounts/login/$', LoginCustomView.as_view(), name='account_login'),
    url(r'^accounts/social_register/$', SocialRegister.as_view(), name='social_register'),
    url(r'^accounts/terms/$', TermsView.as_view(), name='terms'),
    url(r'^accounts/password/reset/$',
        PasswordResetViewMixin.as_view(),
        name='account_reset_password'),
    url(r'^accounts/google/login/$', oauth2_login),
    url(r'^accounts/google/login/callback/$', oauth2_callback),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^financeiro/', include('financial.urls'), name='financial'),
    url(r'^pesquisa/', include('survey.urls'), name='survey'),
    url(r'^processos/', include('lawsuit.urls'), name='lawsuit'),
    url(r'^v1/lawsuit/', include('lawsuit.urls_api'), name='lawsuit_api'),
    url(r'^providencias/', include('task.urls'), name='task'),
    url(r'^billing/', include('billing.urls')),
    url(r'^configuracoes/', include('manager.urls'), name='manager'),
    url(r'^dashboard/$',
        login_required(DashboardView.as_view()),
        name='dashboard'),
    url(r'^chat/', include('chat.urls'), name='chat'),
    url(r'^ecm/', include('ecm.urls', namespace='ecm')),
    url(r'^relatorios/os-a-receber$',
        ToReceiveTaskReportView.as_view(),
        name='task_report_to_receive'),
    url(r'^relatorios/os-a-pagar$',
        ToPayTaskReportTemplateView.as_view(),
        name='task_report_to_pay'),
    url(r'^relatorios/os-a-pagar-data$', ToPayTaskReportView.as_view(), name='task_report_to_pay_data'),
    url(r'^relatorios/os-a-pagar-xlsx$',
        ToPayTaskReportXlsxView.as_view(),
        name='task_report_to_pay_xlsx'),
    url(r'^dashboard/(?P<pk>[0-9]+)/$',
        login_required(TaskDetailView.as_view()),
        name='task_detail'),
    url(r'^dashboard/filtrar/$',
        login_required(DashboardSearchView.as_view()),
        name='task_search'),
    url(r'^dashboard/verificar_status/$',
        login_required(DashboardStatusCheckView.as_view()),
        name='task_status_check'),
    url(r'^dashboard/cadastrar/$',
        login_required(TaskBulkCreateView.as_view()),
        name='task_add'),
    url(r'^client_form',
        login_required(ClientAutocomplete.as_view()),
        name='client_autocomplete'),
    url(r'^office_form',
        login_required(OfficeAutocomplete.as_view()),
        name='office_autocomplete'),
    url(r'^correspondent_form',
        login_required(CorrespondentAutocomplete.as_view()),
        name='correspondent_autocomplete'),
    url(r'^office_correspondent_form',
        login_required(OfficeCorrespondentAutocomplete.as_view()),
        name='office_correspondent_form'),
    url(r'^requester_form',
        login_required(RequesterAutocomplete.as_view()),
        name='requester_autocomplete'),
    url(r'^origin_requester_form',
        login_required(OriginRequesterAutocomplete.as_view()),
        name='origin_requester_autocomplete'),    
    url(r'^service_form',
        login_required(ServiceAutocomplete.as_view()),
        name='service_autocomplete'),
    url(r'^generic_autocomplete_foreignkey',
        login_required(GenericAutocompleteForeignKey.as_view()),
        name='generic_autocomplete'),
    url(
        r'^qa/$',
        TemplateView.as_view(
            template_name='questionnaire/generic_survey.html')),
    url(r'^editable-list/save',
        csrf_exempt(EditableListSave.as_view()),
        name='editable-list-save'),
    url(r'^popup_success', PopupSuccessView.as_view(), name='popup_success'),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^api/v1/', include('ezl.urls_api')),
    url(r'^api/v1/rest-auth/', include('dj_rest_auth.urls')),    
] + static(
    settings.STATIC_URL,
    document_root=os.path.join(settings.BASE_DIR, 'static/'))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
