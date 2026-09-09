from django.urls import reverse
from task.models import TaskStatus
from tests.support import OfficeTestCase


class DashboardStatusCheckTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()

    def test_totals_for_selected_office(self):
        self.make_task(task_status=TaskStatus.OPEN)
        response = self.client.get(reverse("task_status_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["em_aberto"], 1)
        self.assertEqual(response.json()["office"], self.office.legal_name)

    def test_totals_change_after_acceptance(self):
        task = self.make_task(task_status=TaskStatus.OPEN)
        task.task_status = TaskStatus.ACCEPTED
        task.alter_user = self.user
        task.save()
        response = self.client.get(reverse("task_status_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["a_cumprir"], 1)
        self.assertNotIn("em_aberto", response.json())

    def test_post_is_not_supported(self):
        self.assertEqual(self.client.post(reverse("task_status_check")).status_code, 405)
