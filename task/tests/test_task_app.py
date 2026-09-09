import pytest
from datetime import timedelta
from uuid import uuid4
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from core.models import Person
from task.models import Ecm, Task, TaskStatus
from task.forms import TaskForm, TaskDetailForm
from tests.support import OfficeTestCase


class TaskTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        from django.contrib.auth.models import Group
        self.user.groups.add(Group.objects.get(
            name=f"{Person.REQUESTER_GROUP}-{self.office.pk}"))

    def test_model(self):
        task = self.make_task()
        task.refresh_from_db()
        self.assertTrue(task.task_number)
        self.assertEqual(task.office, self.office)
        self.assertEqual(task.movement, self.movement)

    def test_valid_TaskForm(self):
        data = {
            "office": self.office.pk,
            "person_asked_by": self.user.person.pk,
            "type_task": self.type_task.pk,
            "performance_place": "Fórum",
            "final_deadline_date": timezone.now() + timedelta(days=7),
            "description": "Retirar certidão",
        }
        form = TaskForm(data=data, request=self.request)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_view(self):
        response = self.client.get(reverse("task_list"))
        self.assertEqual(response.status_code, 200)

    def test_create_view(self):
        response = self.client.get(reverse("task_add", kwargs={
            "movement": self.movement.pk}))
        self.assertEqual(response.status_code, 200)

    def test_update_view(self):
        task = self.make_task()
        response = self.client.get(reverse("task_update", kwargs={
            "pk": task.pk, "movement": self.movement.pk}))
        self.assertEqual(response.status_code, 200)


class TaskHistoryTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()

    def test_status_change_records_history(self):
        task = self.make_task()
        before = task.history.count()
        task.task_status = TaskStatus.ACCEPTED
        task.alter_user = self.user
        task.save()
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.ACCEPTED)
        self.assertGreater(task.history.count(), before)
        self.assertEqual(task.history.first().task_status, task.task_status)


class EcmTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        self.task = self.make_task()

    def upload(self):
        response = self.client.post(reverse("ecm_add", kwargs={"pk": self.task.pk}), {
            "path": SimpleUploadedFile("certidao.txt", b"documento de teste")})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"], response.json())
        return Ecm.objects.get(pk=response.json()["id"])

    def test_create_view(self):
        ecm = self.upload()
        self.assertEqual(ecm.task, self.task)
        self.assertEqual(ecm.create_user, self.user)
        with ecm.path.open("rb") as stream:
            self.assertEqual(stream.read(), b"documento de teste")

    def test_empty_upload_is_rejected(self):
        response = self.client.post(reverse("ecm_add", kwargs={"pk": self.task.pk}))
        self.assertFalse(response.json()["success"])
        self.assertFalse(Ecm.objects.filter(task=self.task).exists())

    @pytest.mark.xfail(strict=True, raises=AssertionError, reason="BUG-002: EcmTask PROTECT prevents deleting uploaded ECM")
    def test_delete_view(self):
        ecm = self.upload()
        response = self.client.post(reverse("delete_ecm", kwargs={"pk": ecm.pk}))
        self.assertTrue(response.json()["is_deleted"], response.json())
        self.assertFalse(Ecm.objects.filter(pk=ecm.pk).exists())

    def test_external_download_requires_matching_hash(self):
        ecm = self.upload()
        url = reverse("external-media", kwargs={
            "path": ecm.path.name, "task_hash": self.task.task_hash})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"documento de teste")
        wrong = reverse("external-media", kwargs={
            "path": ecm.path.name, "task_hash": uuid4()})
        self.assertEqual(self.client.get(wrong).status_code, 404)

    def test_external_download_missing_file_is_404(self):
        ecm = self.upload()
        ecm.path.storage.delete(ecm.path.name)
        url = reverse("external-media", kwargs={
            "path": ecm.path.name, "task_hash": self.task.task_hash})
        self.assertEqual(self.client.get(url).status_code, 404)


class TaskDetailTest(OfficeTestCase):
    def test_valid_TaskDetailForm(self):
        form = TaskDetailForm(data={
            "execution_date": timezone.now(), "survey_result": "cumprido", "notes": "teste"})
        self.assertTrue(form.is_valid(), form.errors)
