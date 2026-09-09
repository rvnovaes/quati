"""Authorization contracts for every public questionnaire endpoint."""
from django.contrib.auth.models import User
from django.urls import reverse
from model_bakery import baker
from core.models import Office, OfficeMembership
from survey.models import Survey
from tests.support import OfficeTestCase, select_office


class SurveyAuthorizationTests(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        other_user = User.objects.create_user("survey-other-admin")
        self.other = baker.make(Office, create_user=other_user, legal_name="Other office")
        self.own = baker.make(Survey, office=self.office, name="Own", data="{}")
        self.foreign = baker.make(Survey, office=self.other, name="Foreign", data="{}")

    def data(self, **overrides):
        data = {"office": self.office.pk, "name": "Edited", "data": '{"answer": 1}'}
        data.update(overrides)
        return data

    def test_foreign_questionnaire_cannot_be_read(self):
        response = self.client.get(reverse("survey_update", kwargs={"pk": self.foreign.pk}))
        self.assertEqual(response.status_code, 404)

    def test_foreign_questionnaire_cannot_be_deleted(self):
        response = self.client.post(reverse("survey_delete"), {"selection": [self.foreign.pk]})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Survey.objects.filter(pk=self.foreign.pk).exists())

    def test_mixed_office_batch_is_rejected_without_partial_deletion(self):
        response = self.client.post(reverse("survey_delete"), {
            "selection": [self.own.pk, self.foreign.pk]})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Survey.objects.filter(pk__in=[self.own.pk, self.foreign.pk]).count(), 2)

    def test_member_without_permission_cannot_create(self):
        member = User.objects.create_user("survey-member")
        baker.make(OfficeMembership, person=member.person, office=self.office)
        select_office(self.client, member, self.office)
        before = Survey.objects.count()
        self.assertEqual(self.client.get(reverse("survey_add")).status_code, 403)
        response = self.client.post(reverse("survey_add"), self.data())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Survey.objects.count(), before)

    def test_member_without_permission_cannot_read_update_or_delete(self):
        member = User.objects.create_user("survey-reader")
        baker.make(OfficeMembership, person=member.person, office=self.office)
        select_office(self.client, member, self.office)
        url = reverse("survey_update", kwargs={"pk": self.own.pk})
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.data()).status_code, 403)
        self.assertEqual(self.client.post(reverse("survey_delete"), {
            "selection": [self.own.pk]}).status_code, 403)
        self.own.refresh_from_db()
        self.assertEqual(self.own.name, "Own")

    def test_own_questionnaire_cannot_be_transferred_by_posting_office(self):
        response = self.client.post(reverse("survey_update", kwargs={"pk": self.own.pk}),
                                    self.data(office=self.other.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("office", response.context["form"].errors)
        self.own.refresh_from_db()
        self.assertEqual(self.own.office, self.office)
        self.assertEqual(self.own.name, "Own")

    def test_foreign_office_cannot_be_used_for_creation(self):
        before = Survey.objects.count()
        response = self.client.post(reverse("survey_add"), self.data(office=self.other.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("office", response.context["form"].errors)
        self.assertEqual(Survey.objects.count(), before)

    def test_authorized_batch_deletes_only_selected_questionnaires(self):
        response = self.client.post(reverse("survey_delete"), {"selection": [self.own.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Survey.objects.filter(pk=self.own.pk).exists())
        self.assertTrue(Survey.objects.filter(pk=self.foreign.pk).exists())

    def test_list_contains_only_selected_office(self):
        response = self.client.get(reverse("survey_list"))
        self.assertEqual(response.status_code, 200)
        ids = [row.record.pk for row in response.context["table"].rows]
        self.assertIn(self.own.pk, ids)
        self.assertNotIn(self.foreign.pk, ids)

    def test_anonymous_requests_require_login(self):
        self.client.logout()
        for name, kwargs in [("survey_list", {}), ("survey_add", {}),
                             ("survey_update", {"pk": self.own.pk})]:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name, kwargs=kwargs)).status_code, 302)
        self.assertEqual(self.client.post(reverse("survey_delete"), {
            "selection": [self.own.pk]}).status_code, 302)
        self.assertTrue(Survey.objects.filter(pk=self.own.pk).exists())

    def test_authenticated_user_without_office_is_denied(self):
        user = User.objects.create_user("no-office")
        self.client.force_login(user)
        session = self.client.session
        session.pop("custom_session_user", None)
        session.save()
        for name in ("survey_list", "survey_add"):
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_tampered_session_does_not_grant_foreign_office_permission(self):
        select_office(self.client, self.user, self.other)
        self.assertEqual(self.client.get(reverse("survey_list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("survey_update", kwargs={"pk": self.foreign.pk}),
                                         self.data(office=self.other.pk)).status_code, 403)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.name, "Foreign")

    def test_missing_or_invalid_batch_id_does_not_delete_valid_selection(self):
        for invalid_id in ("not-an-id", self.foreign.pk + 1000000):
            with self.subTest(invalid_id=invalid_id):
                response = self.client.post(reverse("survey_delete"), {
                    "selection": [self.own.pk, invalid_id]})
                self.assertEqual(response.status_code, 404)
                self.assertTrue(Survey.objects.filter(pk=self.own.pk).exists())

    def test_questionnaire_used_by_task_type_is_preserved(self):
        self.type_task.survey = self.own
        self.type_task.save()
        response = self.client.post(reverse("survey_delete"), {
            "selection": [self.own.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Survey.objects.filter(pk=self.own.pk).exists())
        self.assertTrue(any(message.level_tag == "error"
                            for message in response.wsgi_request._messages))

    def test_empty_selection_does_not_delete_questionnaires(self):
        response = self.client.post(reverse("survey_delete"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Survey.objects.filter(pk=self.own.pk).exists())
        self.assertTrue(Survey.objects.filter(pk=self.foreign.pk).exists())
