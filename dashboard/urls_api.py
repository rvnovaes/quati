from django.urls import re_path as url, include
from rest_framework import routers
from . import views_api as views


router = routers.SimpleRouter()
router.register(r'dashboard', views.DashboardViewSet, basename='dashboard')

urlpatterns = [

]
