from uuid import uuid4

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.middleware.csrf import get_token
from django.test import RequestFactory
from django.urls import reverse
from model_bakery import baker

from core.models import Office
from task.models import Ecm, EcmTask
from tests.support import OfficeTestCase, select_office


class EcmDeletionTests(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        self.task = self.make_task()
        self.ecm = Ecm.objects.create(
            task=self.task, create_user=self.user, exhibition_name="documento.txt",
            path=SimpleUploadedFile("documento.txt", b"conteudo preservado"))
        self.url = reverse("delete_ecm", kwargs={"pk": self.ecm.pk})

    def assert_preserved(self, links):
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())
        self.assertSetEqual(set(EcmTask.objects.filter(ecm=self.ecm)
                                .values_list("pk", flat=True)), links)
        with self.ecm.path.open("rb") as stream:
            self.assertEqual(stream.read(), b"conteudo preservado")

    def assert_rejected(self):
        links = set(EcmTask.objects.filter(ecm=self.ecm).values_list("pk", flat=True))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url)
        self.assertFalse(response.json()["is_deleted"], response.json())
        self.assert_preserved(links)

    def test_shared_attachment_preserves_all_links(self):
        EcmTask.objects.create(task=self.make_task(), ecm=self.ecm)
        self.assert_rejected()

    def test_outer_rollback_preserves_file_and_links(self):
        pk = self.ecm.pk
        links = set(EcmTask.objects.filter(ecm=self.ecm).values_list("pk", flat=True))
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaisesMessage(RuntimeError, "rollback"):
                with transaction.atomic():
                    self.ecm.delete()
                    self.assertFalse(Ecm.objects.filter(pk=pk).exists())
                    self.assertFalse(EcmTask.objects.filter(pk__in=links).exists())
                    raise RuntimeError("rollback")
        self.ecm.pk = pk
        self.assert_preserved(links)

    def test_post_requires_csrf_token(self):
        self.client.handler.enforce_csrf_checks = True
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())
        request = RequestFactory().get("/")
        token = get_token(request)
        self.client.cookies["csrftoken"] = request.META["CSRF_COOKIE"]
        response = self.client.post(self.url, HTTP_X_CSRFTOKEN=token)
        self.assertTrue(response.json()["is_deleted"], response.json())

    def test_legacy_attachment_is_preserved(self):
        self.ecm.legacy_code = "legacy-123"
        self.ecm.save()
        self.assert_rejected()

    def test_related_copies_are_preserved_from_either_side(self):
        copy = Ecm.objects.create(
            task=self.task, create_user=self.user, exhibition_name="copia.txt",
            path=SimpleUploadedFile("copia.txt", b"copia"), ecm_related=self.ecm)
        self.assert_rejected()
        self.url = reverse("delete_ecm", kwargs={"pk": copy.pk})
        self.assert_rejected()
        self.assertTrue(Ecm.objects.filter(pk=copy.pk).exists())
        self.assertTrue(copy.path.storage.exists(copy.path.name))

    def test_distinct_rows_using_same_file_are_preserved(self):
        copy = Ecm.objects.create(task=self.task, create_user=self.user,
                                  exhibition_name="copia.txt", path=self.ecm.path.name)
        self.assert_rejected()
        self.assertTrue(Ecm.objects.filter(pk=copy.pk).exists())

    def test_get_cannot_delete(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())

    def test_other_office_cannot_delete(self):
        other = baker.make(Office, create_user=self.user)
        select_office(self.client, self.user, other)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())

    def test_forged_office_session_cannot_delete(self):
        outsider = User.objects.create_user("outsider")
        select_office(self.client, outsider, self.office)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())

    def test_no_office_cannot_delete(self):
        session = self.client.session
        session.pop("custom_session_user")
        session.save()
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())

    def test_anonymous_internal_delete_is_rejected(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())

    def test_external_delete_requires_matching_hash(self):
        self.client.logout()
        wrong = reverse("delete_external_ecm", kwargs={
            "pk": self.ecm.pk, "task_hash": uuid4().hex})
        self.client.post(wrong)
        self.assertTrue(Ecm.objects.filter(pk=self.ecm.pk).exists())
        correct = reverse("delete_external_ecm", kwargs={
            "pk": self.ecm.pk, "task_hash": self.task.task_hash.hex})
        self.assertEqual(self.client.get(correct).status_code, 405)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(correct)
        self.assertTrue(response.json()["is_deleted"], response.json())
        self.assertFalse(Ecm.objects.filter(pk=self.ecm.pk).exists())
        self.assertFalse(self.ecm.path.storage.exists(self.ecm.path.name))

    def test_external_shared_attachment_is_preserved(self):
        EcmTask.objects.create(task=self.make_task(), ecm=self.ecm)
        self.client.logout()
        self.url = reverse("delete_external_ecm", kwargs={
            "pk": self.ecm.pk, "task_hash": self.task.task_hash.hex})
        self.assert_rejected()
