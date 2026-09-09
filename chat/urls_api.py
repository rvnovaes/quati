from django.urls import re_path as url, include
from django.contrib.auth.decorators import login_required
from rest_framework import routers
from . import views_api as views

router = routers.SimpleRouter()
router.register(r'chat', views.ChatViewSet, basename='chat')
router.register(
    r'unread_message', views.UnreadMessageViewSet, basename='unread_message')

urlpatterns = []
