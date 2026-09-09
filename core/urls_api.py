from django.urls import re_path as url, include
from django.contrib.auth.decorators import login_required
from rest_framework import routers
from . import views_api as views

router = routers.SimpleRouter()
router.register(r'person', views.PersonViewSet, basename='person')
router.register(r'correspondent', views.CorrespondentViewSet, basename='correspondent')
router.register(r'company', views.CompanyViewSet, basename='company')
router.register(r'office', views.OfficeViewSet, basename='office')

urlpatterns = [url(r'^user_session/$', views.user_session_view)]
