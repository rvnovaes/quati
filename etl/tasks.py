from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from etl.models import DashboardETL


@shared_task()
def remove_old_etldashboard():
    date_limit = timezone.now() - timedelta(days=15)
    dashboards = DashboardETL.objects.filter(create_date__lte=date_limit)
    ret = {
        'total': DashboardETL.objects.all().count(),
        'excluidos': dashboards.count()
    }
    dashboards.delete()
    return ret
