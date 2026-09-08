from django.urls import re_path as url, include
from rest_framework import routers
from . import views_api as views

router = routers.SimpleRouter()
router.register(r'type_task', views.TypeTaskViewSet, basename='type_task')
router.register(r'type_task_main', views.TypeTaskMainViewSet, basename='type_task_main')
router.register(r'task', views.TaskViewSet, basename='task')
router.register(r'task_dashboard', views.TaskDashboardEZLViewSet, basename='task_dashboard')
router.register(r'total_by_office', views.TotalToPayByOfficeViewSet, basename='total_by_office')
router.register(r'task_to_pay', views.TaskToPayViewSet, basename='task_to_pay')
router.register(r'amount_by_correspondent', views.AmountByCorrespondentViewSet, basename='amount_by_correspondent')
router.register(r'tasks_child', views.ChildTaskToPayViewSet, basename='tasks_child')
router.register(r'ecm_task', views.EcmTaskViewSet, basename='ecm_task')

urlpatterns = [url(r'^audience/$', views.list_audience_totals)]
