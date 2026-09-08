from django.urls import re_path as url

from . import views

urlpatterns = [
    url(r'^pesquisas/$', views.SurveyListView.as_view(), name='survey_list'),
    url(r'^pesquisas/criar/$',
        views.SurveyCreateView.as_view(),
        name='survey_add'),
    url(r'^pesquisas/(?P<pk>[0-9]+)/$',
        views.SurveyUpdateView.as_view(),
        name='survey_update'),
    url(r'^pesquisas/excluir$',
        views.SurveyDeleteView.as_view(),
        name='survey_delete'),
]
