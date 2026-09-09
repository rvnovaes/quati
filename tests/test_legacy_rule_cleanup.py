from types import SimpleNamespace

from django.urls import reverse
from model_bakery import baker

from core.models import Office, Person
from core.views_api import PersonViewSet
from financial.models import CostCenter
from lawsuit.forms import LawSuitForm
from lawsuit.models import CourtDistrictComplement, Folder, Instance
from lawsuit.views_api import FolderViewSet
from tests.support import OfficeTestCase


class LegacyRuleCleanupTests(OfficeTestCase):
    def setUp(self):
        self.setup_office()

    def test_folder_edit_opens_without_imported_placeholder(self):
        response = self.client.get(reverse("folder_update", kwargs={"pk": self.folder.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].instance.pk, self.folder.pk)

    def test_folder_edit_saves_without_imported_placeholder(self):
        response = self.client.post(reverse("folder_update", kwargs={"pk": self.folder.pk}), {
            "office": self.office.pk, "folder_number": self.folder.folder_number,
            "person_customer": self.customer.pk, "is_active": "on",
            "is_default": "on", "legacy_code": "referencia-historica",
        })
        self.assertEqual(response.status_code, 302)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.legacy_code, "referencia-historica")
        self.assertEqual(self.folder.person_customer_id, self.customer.pk)

    def test_old_marker_does_not_block_folder_edit(self):
        self.folder.legacy_code = "REGISTRO-INVÁLIDO"
        self.folder.save()
        response = self.client.get(reverse("folder_update", kwargs={"pk": self.folder.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].instance.pk, self.folder.pk)

    def test_folder_listing_and_search_treat_old_code_as_data(self):
        self.folder.legacy_code = "REGISTRO-INVÁLIDO"
        self.folder.save()
        other_office = baker.make(Office, create_user=self.user)
        other = baker.make(Folder, office=other_office, create_user=self.user)
        for params in ({}, {"legacy_code": self.folder.legacy_code}):
            with self.subTest(params=params):
                response = self.client.get(reverse("folder_list"), params)
                self.assertEqual(response.status_code, 200)
                ids = {row.pk for row in response.context["table"].data}
                self.assertIn(self.folder.pk, ids)
                self.assertNotIn(other.pk, ids)

    def test_form_choices_use_activity_and_office_not_magic_names(self):
        special_name = Instance._meta.verbose_name.upper() + "-INVÁLIDO"
        instance = baker.make(Instance, office=self.office, name=special_name, is_active=True)
        inactive = baker.make(Instance, office=self.office, is_active=False)
        other_office = baker.make(Office, create_user=self.user)
        other = baker.make(Instance, office=other_office, is_active=True)
        form = LawSuitForm(request=self.request)
        ids = set(form.fields["instance"].queryset.values_list("pk", flat=True))
        self.assertIn(instance.pk, ids)
        self.assertNotIn(inactive.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_api_queryset_preserves_office_scope_and_historical_codes(self):
        self.folder.legacy_code = "REGISTRO-INVÁLIDO"
        self.folder.save()
        other_office = baker.make(Office, create_user=self.user)
        other = baker.make(Folder, office=other_office, create_user=self.user)
        view = FolderViewSet()
        view.request = self.request
        view.request.auth = SimpleNamespace(application=SimpleNamespace(office=self.office))
        ids = set(view.get_queryset().values_list("pk", flat=True))
        self.assertIn(self.folder.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_person_api_keeps_office_links_without_magic_code_filter(self):
        self.customer.legacy_code = "REGISTRO-INVÁLIDO"
        self.customer.save()
        outsider = baker.make(Person)
        view = PersonViewSet()
        view.request = self.request
        view.request.auth = SimpleNamespace(application=SimpleNamespace(office=self.office))
        ids = set(view.get_queryset().values_list("pk", flat=True))
        self.assertIn(self.customer.pk, ids)
        self.assertNotIn(outsider.pk, ids)

    def test_financial_listing_uses_normal_ordering_and_office_scope(self):
        name = CostCenter._meta.verbose_name.upper() + "-INVÁLIDO"
        center = baker.make(CostCenter, office=self.office, name=name)
        other_office = baker.make(Office, create_user=self.user)
        other = baker.make(CostCenter, office=other_office)
        response = self.client.get(reverse("costcenter_list"))
        self.assertEqual(response.status_code, 200)
        rows = list(response.context["table"].data)
        self.assertIn(center.pk, {row.pk for row in rows})
        self.assertNotIn(other.pk, {row.pk for row in rows})
        self.assertEqual([row.name for row in rows], sorted(row.name for row in rows))

    def test_autocomplete_preserves_activity_and_office_filters(self):
        name = CourtDistrictComplement._meta.verbose_name.upper() + "-INVÁLIDO"
        complement = baker.make(CourtDistrictComplement, office=self.office, name=name, is_active=True)
        inactive = baker.make(CourtDistrictComplement, office=self.office, is_active=False)
        other_office = baker.make(Office, create_user=self.user)
        other = baker.make(CourtDistrictComplement, office=other_office, is_active=True)
        response = self.client.get(reverse("complemento_select2"))
        self.assertEqual(response.status_code, 200)
        ids = {str(row["id"]) for row in response.json()["results"]}
        self.assertIn(str(complement.pk), ids)
        self.assertNotIn(str(inactive.pk), ids)
        self.assertNotIn(str(other.pk), ids)
