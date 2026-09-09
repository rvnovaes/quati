from rest_framework import routers
from . import views_api as views

router = routers.SimpleRouter()

router.register(r'service_price_table', views.ServicePriceTableViewSet, basename='service_price_table')
router.register(r'cost_center', views.CostCenterViewSet, basename='cost_center')
router.register(r'policy_price', views.PolicyPriceViewSet, basename='policy_price')

urlpatterns = [

]


