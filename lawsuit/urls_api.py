from django.urls import re_path as url, include
from django.contrib.auth.decorators import login_required
from rest_framework import routers
from . import views_api as views

router = routers.SimpleRouter()

router.register(
    r'court_district', views.CourtDistrictViewSet, basename='court_district')
router.register(r'folder', views.FolderViewSet, basename='folder')
router.register(r'instance', views.InstanceViewSet, basename='instance')
router.register(r'lawsuit', views.LawSuitViewSet, basename='lawsuit')
router.register(
    r'court_division', views.CourtDivisionViewSet, basename='court_division')
router.register(
    r'type_movement', views.TypeMovementViewSet, basename='type_movement')
router.register(r'movement', views.MovementViewSet, basename='movement')
router.register(r'organ', views.OrganViewSet, basename='organ')
router.register(
    r'company/lawsuit',
    views.CompanyLawsuitViewSet,
    basename='company-lawsuit')

urlpatterns = [
    # urls para tela de criacao de OS
    url(r'lawsuit_common',
        views.LawsuitApiView.as_view(),
        name='lawsuit_common'),
    url(r'movement_common',
        views.MovementApiView.as_view(),
        name='movement_common'),
    url(r'task_common', views.TaskApiView.as_view(), name='task_common'),
]
