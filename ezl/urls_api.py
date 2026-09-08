import os
from django.urls import re_path as url, include
from core.urls_api import router as router_core, urlpatterns as task_urlpatterns
from lawsuit.urls_api import router as router_lawsuit
from financial.urls_api import router as router_financial
from task.urls_api import router as router_task
from dashboard.urls_api import router as router_dashboard
from chat.urls_api import router as router_chat
from rest_framework.authtoken import views

urlpatterns = [
    url(r'^', include((router_lawsuit.urls, 'lawsuit'), namespace='lawsuit')),
    url(r'^', include((router_core.urls, 'core'), namespace='core')),
    url(r'^',
        include((router_financial.urls, 'financial'), namespace='financial')),
    url(r'^', include((router_task.urls, 'task'), namespace='task')),
    url(r'^',
        include((router_dashboard.urls, 'dashboard'), namespace='dashboard')),
    url(r'^', include((router_chat.urls, 'chat'), namespace='chat')),
    url(r'^', include('core.urls_api')),
    url(r'^', include('task.urls_api')),
    url(r'^oauth2/',
        include('oauth2_provider.urls', namespace='oauth2_provider')),
]
