from django.urls import re_path as url
from django.contrib.auth.decorators import login_required

from . import views


urlpatterns = [
    url(r'^centros-de-custos/$', views.CostCenterListView.as_view(), name='costcenter_list'),
    url(r'^centros-de-custos/criar/$', views.CostCenterCreateView.as_view(), name='costcenter_add'),
    url(r'^centros-de-custos/(?P<pk>[0-9]+)/$', views.CostCenterUpdateView.as_view(), name='costcenter_update'),
    url(r'^centros-de-custos/excluir$', views.CostCenterDeleteView.as_view(), name='costcenter_delete'),
    url(r'^centros-de-custos/autocomplete', views.CostCenterAutocomplete.as_view(), name='costcenter_autocomplete'),
    url(r'^centros-de-custos/filter_autocomplete', views.CostCenterFilterAutocompleteSelect2.as_view(),
        name='costcenter_filter_autocomplete'),

    url(r'^tabelas-de-precos/$', views.ServicePriceTableListView.as_view(), name='servicepricetable_list'),
    url(r'^tabelas-de-precos/criar/$', views.ServicePriceTableCreateView.as_view(), name='servicepricetable_add'),
    url(r'^tabelas-de-precos/(?P<pk>[0-9]+)/$', views.ServicePriceTableUpdateView.as_view(), name='servicepricetable_update'),
    url(r'^tabelas-de-precos/excluir$', views.ServicePriceTableDeleteView.as_view(), name='servicepricetable_delete'),
    url(r'^tabelas-de-precos/detalhes/(?P<pk>[0-9]+)/$', views.ServicePriceTableDetailView.as_view(), name='servicepricetable_detail'),
    
    url(r'^import_service_price_table/$', views.import_service_price_table, name='import_service_price_table'),    
    url(r'^import_service_price_table_status/(?P<pk>[0-9]+)/$',
        login_required(views.ImportServicePriceTableStatus.as_view()),
        name='import_service_price_table_status'),    
    url(r'^ajax_get_log_import_service_price_table_data_table/$', 
        views.ajax_get_log_import_service_price_table_data_table,
        name='ajax_get_log_import_service_price_table_data_table'),    
    url(r'^politica-de-precos/$', views.PolicyPriceView.as_view(), name='policyprice_list'),
    url(r'^politica-de-precos/criar/$', views.PolicyPriceCreateView.as_view(), name='policyprice_add'),
    url(r'^politica-de-precos/(?P<pk>[0-9]+)/$', views.PolicyPriceUpdateView.as_view(), name='policyprice_update'),
    url(r'^politica-de-precos/excluir$', views.PolicyPriceDeleteView.as_view(), name='policyprice_delete'),    
]

