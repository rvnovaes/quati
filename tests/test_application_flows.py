"""Regression contracts through real HTTP endpoints and persisted domain data."""
import json
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from guardian.core import ObjectPermissionChecker
from model_bakery import baker

from core.models import Office, OfficeMembership, Person
from lawsuit.models import Folder, LawSuit, Instance
from survey.models import Survey
from task.models import Task, TaskStatus, TaskSurveyAnswer
from task.mail import TaskMail
from tests.support import OfficeTestCase, select_office


class ApplicationFlows(OfficeTestCase):
    def setUp(self):
        self.setup_office()

    def other_office(self):
        user = User.objects.create_user("other-admin", email="other@example.test")
        return baker.make(Office, create_user=user, legal_name="Office B")

    def test_anonymous_cannot_open_private_pages(self):
        self.client.logout()
        for name in ("folder_list", "person_list", "task_list", "survey_list"):
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("next=", response.url)

    def test_office_creator_receives_object_permissions(self):
        other = self.other_office()
        checker = ObjectPermissionChecker(self.user)
        self.assertTrue(checker.has_perm("group_admin", self.office))
        self.assertFalse(checker.has_perm("group_admin", other))
        self.assertFalse(self.user.is_superuser)

    def test_folder_list_is_scoped_to_selected_office(self):
        other = self.other_office()
        foreign = baker.make(Folder, office=other, person_customer=self.customer)
        response = self.client.get(reverse("folder_list"))
        self.assertEqual(response.status_code, 200)
        ids = [row.record.pk for row in response.context["table"].rows]
        self.assertIn(self.folder.pk, ids)
        self.assertNotIn(foreign.pk, ids)

    def test_create_folder_persists_customer_office_and_audit(self):
        response = self.client.post(reverse("folder_add"), {
            "office": self.office.pk, "person_customer": self.customer.pk,
            "legacy_code": "new-folder"})
        self.assertEqual(response.status_code, 302)
        folder = Folder.objects.get(legacy_code="new-folder")
        self.assertEqual(folder.person_customer, self.customer)
        self.assertEqual(folder.office, self.office)
        self.assertEqual(folder.create_user, self.user)
        self.assertTrue(folder.folder_number)
        self.assertIn(str(folder.pk), response.url)

    def test_invalid_folder_does_not_persist(self):
        before = Folder.objects.count()
        response = self.client.post(reverse("folder_add"), {"office": self.office.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn("person_customer", response.context["form"].errors)
        self.assertEqual(Folder.objects.count(), before)

    def test_create_and_update_instance(self):
        response = self.client.post(reverse("instance_create"), {
            "office": self.office.pk, "name": "Instância de teste"})
        self.assertEqual(response.status_code, 302)
        instance = Instance.objects.get(name="Instância de teste")
        self.assertEqual(instance.create_user, self.user)
        response = self.client.post(reverse("instance_update", kwargs={"pk": instance.pk}), {
            "office": self.office.pk, "name": "Instância alterada", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        instance.refresh_from_db()
        self.assertEqual(instance.name, "Instância alterada")
        self.assertEqual(instance.alter_user, self.user)

    def test_batch_delete_removes_only_selected_instances(self):
        first, second = baker.make(Instance, office=self.office, name=baker.seq("Instance "), _quantity=2)
        response = self.client.post(reverse("instance_delete"), {"selection": [first.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Instance.objects.filter(pk=first.pk).exists())
        self.assertTrue(Instance.objects.filter(pk=second.pk).exists())

    def test_form_rejects_office_not_in_session(self):
        other = self.other_office()
        response = self.client.post(reverse("instance_create"), {
            "office": other.pk, "name": "Foreign write"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("office", response.context["form"].errors)
        self.assertFalse(Instance.objects.filter(name="Foreign write").exists())

    def test_questionnaire_create_and_update(self):
        data = {"office": self.office.pk, "name": "Questionário",
                "data": json.dumps({"elements": [{"type": "text", "name": "resultado"}]})}
        response = self.client.post(reverse("survey_add"), data)
        self.assertEqual(response.status_code, 302)
        survey = Survey.objects.get(name="Questionário")
        self.assertEqual(json.loads(survey.data)["elements"][0]["name"], "resultado")
        data.update(name="Questionário revisado", is_active="on")
        response = self.client.post(reverse("survey_update", kwargs={"pk": survey.pk}), data)
        self.assertEqual(response.status_code, 302)
        survey.refresh_from_db()
        self.assertEqual(survey.name, "Questionário revisado")
        self.assertEqual(survey.alter_user, self.user)

    def test_member_without_survey_permission_cannot_list(self):
        member = User.objects.create_user("member")
        baker.make(OfficeMembership, person=member.person, office=self.office)
        select_office(self.client, member, self.office)
        response = self.client.get(reverse("survey_list"))
        self.assertEqual(response.status_code, 403)

    def test_pending_survey_is_resolved_by_related_answer(self):
        survey = baker.make(Survey, office=self.office, data='{"elements": []}')
        self.type_task.survey = survey
        self.type_task.save()
        task = self.make_task()
        self.assertTrue(task.have_pending_surveys["survey_executed_by"])
        answer = baker.make(TaskSurveyAnswer, survey=survey, create_user=self.user,
                            survey_result={"resultado": "cumprido"})
        answer.tasks.add(task)
        task.refresh_from_db()
        self.assertFalse(task.have_pending_surveys["survey_executed_by"])
        self.assertEqual(task.tasksurveyanswer_set.get().survey_result, {"resultado": "cumprido"})

    def test_task_http_acceptance_persists_status_and_history(self):
        task = self.make_task()
        response = self.client.post(reverse("task_detail", kwargs={"pk": task.pk}), {
            "action": "ACCEPTED", "notes": "Aceita pelo correspondente"})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.ACCEPTED)
        self.assertEqual(task.alter_user, self.user)
        self.assertEqual(task.history.first().task_status, task.task_status)

    def test_task_http_completion_stores_questionnaire(self):
        survey = baker.make(Survey, office=self.office, data='{"elements": []}')
        self.type_task.survey = survey
        self.type_task.save()
        task = self.make_task(task_status=TaskStatus.ACCEPTED)
        response = self.client.post(reverse("task_detail", kwargs={"pk": task.pk}), {
            "action": "DONE", "execution_date": timezone.now().strftime("%d/%m/%Y %H:%M"),
            "survey_result": json.dumps({"resultado": "cumprido"}), "notes": "Concluída"})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DONE)
        answer = TaskSurveyAnswer.objects.get(tasks=task)
        self.assertEqual(answer.survey_result, {"resultado": "cumprido"})
        self.assertEqual(answer.create_user, self.user)
        self.assertIsNotNone(task.execution_date)

    def test_task_numbers_are_unique_within_office(self):
        first, second = self.make_task(), self.make_task()
        self.assertNotEqual(first.task_number, second.task_number)

    def test_financial_report_requires_permission(self):
        member = User.objects.create_user("finance-member")
        baker.make(OfficeMembership, person=member.person, office=self.office)
        select_office(self.client, member, self.office)
        self.assertEqual(self.client.get(reverse("task_report_to_receive")).status_code, 403)

    def test_pay_report_without_filters_is_empty(self):
        response = self.client.get(reverse("task_report_to_pay_data"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.json()), [])

    def test_accepted_email_contains_task_and_attachment(self):
        parent = self.make_task()
        task = self.make_task(task_status=TaskStatus.ACCEPTED, parent=parent)
        from task.models import Ecm
        baker.make(Ecm, task=parent, create_user=self.user,
                   path=SimpleUploadedFile("certidao.txt", b"conteudo"))
        mail.outbox.clear()
        sent = TaskMail(["dest@example.test", "dest@example.test", ""], task).send_mail()
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["dest@example.test"])
        self.assertIn(str(task.task_number), message.subject)
        self.assertIn(str(task.task_number), message.alternatives[0].content)
        self.assertEqual(message.attachments[0].content, b"conteudo")

    @override_settings(DEFAULT_TO_EMAIL="sandbox@example.test")
    def test_email_redirect_preserves_original_recipient_in_body(self):
        task = self.make_task(task_status=TaskStatus.ACCEPTED, parent=self.make_task())
        mail.outbox.clear()
        self.assertTrue(TaskMail(["original@example.test"], task).send_mail())
        self.assertEqual(mail.outbox[0].to, ["sandbox@example.test"])
        self.assertIn("original@example.test", mail.outbox[0].alternatives[0].content)

    def test_email_without_recipients_is_not_sent(self):
        task = self.make_task(task_status=TaskStatus.ACCEPTED, parent=self.make_task())
        mail.outbox.clear()
        self.assertFalse(TaskMail([], task).send_mail())
        self.assertEqual(mail.outbox, [])

    def test_email_delivery_failure_is_reported(self):
        task = self.make_task(task_status=TaskStatus.ACCEPTED, parent=self.make_task())
        with patch("django.core.mail.backends.locmem.EmailBackend.send_messages",
                   side_effect=ConnectionError("SMTP unavailable")) as smtp:
            self.assertFalse(TaskMail(["dest@example.test"], task).send_mail())
            smtp.assert_called_once()

    def test_create_user_stores_hashed_password_and_person(self):
        response = self.client.post(reverse("user_add"), {
            "username": "new-user", "first_name": "Ana", "last_name": "Teste",
            "email": "ana@example.test", "password1": "Test-password-123",
            "password2": "Test-password-123", "office": self.office.pk,
            f"office_{self.office.pk}": [Group.objects.get(
                name=f"{Person.REQUESTER_GROUP}-{self.office.pk}").pk]})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="new-user")
        self.assertTrue(user.check_password("Test-password-123"))
        self.assertEqual(user.person.legal_name, "Ana Teste")

    def test_mismatched_password_does_not_create_user(self):
        response = self.client.post(reverse("user_add"), {
            "username": "bad-user", "first_name": "Ana", "last_name": "Teste",
            "email": "ana@example.test", "password1": "Test-password-123",
            "password2": "different-password", "office": self.office.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn("password2", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="bad-user").exists())

    def test_create_lawsuit_in_folder(self):
        response = self.client.post(reverse("lawsuit_add", kwargs={"folder": self.folder.pk}), {
            "office": self.office.pk, "type_lawsuit": "ADMINISTRATIVE",
            "law_suit_number": "PROCESSO-TESTE", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        lawsuit = LawSuit.objects.get(law_suit_number="PROCESSO-TESTE")
        self.assertEqual(lawsuit.folder, self.folder)
        self.assertEqual(lawsuit.office, self.office)
        self.assertEqual(lawsuit.create_user, self.user)

    def test_update_lawsuit_preserves_folder(self):
        response = self.client.post(reverse("lawsuit_update", kwargs={
            "folder": self.folder.pk, "pk": self.lawsuit.pk}), {
            "office": self.office.pk, "type_lawsuit": "ADMINISTRATIVE",
            "law_suit_number": "PROCESSO-ALTERADO", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.lawsuit.refresh_from_db()
        self.assertEqual(self.lawsuit.law_suit_number, "PROCESSO-ALTERADO")
        self.assertEqual(self.lawsuit.folder, self.folder)

    def finished_pair(self):
        """Persist a financial snapshot; transitions are tested separately via HTTP."""
        correspondent = self.other_office()
        parent = self.make_task()
        child = self.make_task(office=correspondent, parent=parent)
        Task.objects.filter(pk__in=[parent.pk, child.pk]).update(
            task_status=TaskStatus.FINISHED, finished_date=timezone.now())
        Task.objects.filter(pk=parent.pk).update(
            amount=Decimal("200"), amount_to_pay=Decimal("100"),
            amount_delegated=Decimal("80"), billing_date=None)
        return parent, child

    def test_pay_report_amounts_and_office_scope(self):
        parent, child = self.finished_pair()
        response = self.client.get(reverse("task_report_to_pay_data"),
                                   {"office": "Office B", "group_by_tasks": "E"})
        self.assertEqual(response.status_code, 200)
        rows = json.loads(response.json())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["task_id"], parent.pk)
        self.assertEqual(Decimal(rows[0]["amount_to_pay"]), Decimal("100"))
        self.assertEqual(Decimal(rows[0]["fee"]), Decimal("20"))
        select_office(self.client, child.office.create_user, child.office)
        response = self.client.get(reverse("task_report_to_pay_data"),
                                   {"office": "Office B", "group_by_tasks": "E"})
        self.assertEqual(json.loads(response.json()), [])

    def test_pay_report_excludes_unfinished_tasks(self):
        parent, child = self.finished_pair()
        Task.objects.filter(pk=child.pk).update(task_status=TaskStatus.ACCEPTED)
        response = self.client.get(reverse("task_report_to_pay_data"),
                                   {"office": "Office B", "group_by_tasks": "E"})
        self.assertEqual(json.loads(response.json()), [])

    def test_billing_requires_selected_tasks(self):
        response = self.client.post(reverse("task_report_to_pay_data"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "tasks is required"})

    def test_billing_changes_only_tasks_in_session_office(self):
        parent, child = self.finished_pair()
        response = self.client.post(reverse("task_report_to_pay_data"),
                                    {"tasks[]": [parent.pk, child.pk]})
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertIsNotNone(parent.billing_date)
        self.assertIsNone(child.billing_date)

    def test_generic_form_multiple_attachments_are_saved(self):
        from ecm.models import Attachment
        response = self.client.post(reverse("instance_create"), {
            "office": self.office.pk, "name": "Com anexos",
            "documents": [SimpleUploadedFile("one.txt", b"one"),
                          SimpleUploadedFile("two.txt", b"two")]})
        self.assertEqual(response.status_code, 302)
        instance = Instance.objects.get(name="Com anexos")
        attachments = Attachment.objects.filter(model_name="lawsuit.instance", object_id=instance.pk)
        self.assertEqual(attachments.count(), 2)
        contents = []
        for attachment in attachments:
            self.assertEqual(attachment.create_user, self.user)
            with attachment.file.open("rb") as stream:
                contents.append(stream.read())
        self.assertCountEqual(contents, [b"one", b"two"])

    def test_task_creation_through_http(self):
        from datetime import timedelta
        self.user.groups.add(Group.objects.get(
            name=f"{Person.REQUESTER_GROUP}-{self.office.pk}"))
        response = self.client.post(reverse("task_add", kwargs={"movement": self.movement.pk}), {
            "office": self.office.pk, "person_asked_by": self.user.person.pk,
            "type_task": self.type_task.pk, "performance_place": "Fórum",
            "final_deadline_date": (timezone.now() + timedelta(days=7)).strftime("%d/%m/%Y %H:%M"),
            "description": "OS criada pela interface"})
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(description="OS criada pela interface")
        self.assertEqual(task.movement, self.movement)
        self.assertEqual(task.office, self.office)
        self.assertEqual(task.create_user, self.user)
        self.assertTrue(task.task_number)

    def test_pay_report_unbilled_status_filter(self):
        parent, child = self.finished_pair()
        response = self.client.get(reverse("task_report_to_pay_data"),
                                   {"status": "1", "group_by_tasks": "E"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["task_id"] for row in json.loads(response.json())], [parent.pk])

    def test_pay_report_billing_status_separates_billed_and_unbilled(self):
        unbilled, child = self.finished_pair()
        billed = self.make_task()
        billed_child = self.make_task(office=child.office, parent=billed)
        Task.objects.filter(pk__in=[billed.pk, billed_child.pk]).update(
            task_status=TaskStatus.FINISHED, finished_date=timezone.now())
        Task.objects.filter(pk=billed.pk).update(billing_date=timezone.now())
        for status, expected in (("0", {billed.pk}), ("1", {unbilled.pk}),
                                 ("", {billed.pk, unbilled.pk})):
            with self.subTest(status=status):
                response = self.client.get(reverse("task_report_to_pay_data"), {
                    "status": status, "office": "Office B", "group_by_tasks": "E"})
                self.assertEqual(response.status_code, 200)
                self.assertSetEqual(
                    {row["task_id"] for row in json.loads(response.json())}, expected)

    def test_survey_cannot_be_edited_from_another_office(self):
        other = self.other_office()
        survey = baker.make(Survey, office=other, name="Foreign survey", data="{}")
        response = self.client.post(reverse("survey_update", kwargs={"pk": survey.pk}), {
            "office": self.office.pk, "name": "Unauthorized edit", "data": "{}"})
        self.assertIn(response.status_code, (403, 404))
        survey.refresh_from_db()
        self.assertEqual(survey.name, "Foreign survey")
        self.assertEqual(survey.office, other)

    def test_task_return_clears_execution_date(self):
        task = self.make_task(task_status=TaskStatus.DONE, execution_date=timezone.now())
        response = self.client.post(reverse("task_detail", kwargs={"pk": task.pk}),
                                    {"action": "RETURN", "notes": "Complementar certidão"})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.RETURN)
        self.assertIsNone(task.execution_date)
        self.assertIsNotNone(task.return_date)

    def test_task_finish_records_finalization_date(self):
        task = self.make_task(task_status=TaskStatus.DONE)
        response = self.client.post(reverse("task_detail", kwargs={"pk": task.pk}),
                                    {"action": "FINISHED"})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FINISHED)
        self.assertIsNotNone(task.finished_date)

    def test_task_invalid_execution_date_does_not_change_status(self):
        task = self.make_task(task_status=TaskStatus.ACCEPTED)
        response = self.client.post(reverse("task_detail", kwargs={"pk": task.pk}),
                                    {"action": "DONE", "execution_date": "invalid-date"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("execution_date", response.context["form"].errors)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.ACCEPTED)

    def test_pay_report_exports_readable_xlsx(self):
        import io
        import zipfile
        from xml.etree import ElementTree
        self.finished_pair()
        response = self.client.get(reverse("task_report_to_pay_xlsx"),
                                   {"office": "Office B", "group_by_tasks": "E"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            self.assertGreaterEqual(len(sheet.findall(".//s:row", namespace)), 2)
            shared = archive.read("xl/sharedStrings.xml").decode()
            self.assertIn("Office B", shared)
