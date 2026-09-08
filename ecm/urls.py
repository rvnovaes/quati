# -*- coding: utf-8 -*-
# Author: Christian Douglas <christian.douglas.alcantara@gmail.com>
from django.urls import re_path as url
from django.contrib.auth.decorators import login_required
from . import views

app_name = 'ecm'

urlpatterns = [
    url(r'^ajax-upload/$', login_required(views.UploadView.as_view()), name='ajax-upload'),
    url(r'^ajax_get_attachments', views.ajax_get_attachments, name='ajax-get-attachments'),
    url(r'^ajax-drop-attachment/(?P<pk>[0-9]+)/$', views.ajax_drop_attachment, name='ajax-drop-attachment'),

    url(r'^anexos-padrao/$', views.DefaultAttachmentRuleListView.as_view(), name='defaultattachmentrule_list'),
    url(r'^anexos-padrao/criar/$', views.DefaultAttachmentRuleCreateView.as_view(), name='defaultattachmentrule_add'),
    url(r'^anexos-padrao/(?P<pk>[0-9]+)/$', views.DefaultAttachmentRuleUpdateView.as_view(), name='defaultattachmentrule_update'),
    url(r'^anexos-padrao/excluir$', views.DefaultAttachmentRuleDeleteView.as_view(), name='defaultattachmentrule_delete'),
]
