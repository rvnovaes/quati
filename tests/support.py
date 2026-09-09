"""Real domain setup shared by HTTP and form regression tests."""
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.utils import timezone
from model_bakery import baker
from core.models import Office, Person
from lawsuit.models import Folder, LawSuit, Movement
from task.models import Task, TaskStatus, TypeTask


def select_office(client, user, office):
    client.force_login(user)
    session = client.session
    session["custom_session_user"] = {
        str(user.pk): {"current_office": office.pk}
    }
    session.save()


class OfficeTestCase(TestCase):
    def setup_office(self):
        self.user = User.objects.create_user(
            username="test-admin", password="password", email="admin@example.test")
        self.office = baker.make(Office, create_user=self.user, legal_name="Office A")
        self.customer = self.office.persons.filter(is_customer=True).first()
        self.folder = baker.make(
            Folder, office=self.office, person_customer=self.customer,
            create_user=self.user, is_default=True)
        self.lawsuit = baker.make(
            LawSuit, folder=self.folder, office=self.office, create_user=self.user)
        self.movement = baker.make(
            Movement, law_suit=self.lawsuit, folder=self.folder, office=self.office, create_user=self.user)
        self.type_task = TypeTask.objects.filter(office=self.office).first()
        select_office(self.client, self.user, self.office)
        self.request = RequestFactory().get("/")
        self.request.user = self.user
        self.request.session = self.client.session
        self.post_request = RequestFactory().post("/")
        self.post_request.user = self.user
        self.post_request.session = self.client.session

    def make_task(self, **kwargs):
        defaults = dict(
            office=self.office, movement=self.movement, type_task=self.type_task,
            create_user=self.user, person_asked_by=self.user.person,
            person_executed_by=self.user.person, task_status=TaskStatus.OPEN,
            final_deadline_date=timezone.now() + timedelta(days=7),
            performance_place="Fórum de teste")
        defaults.update(kwargs)
        return baker.make(Task, **defaults)
