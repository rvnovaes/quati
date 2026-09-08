import json
from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase
from model_bakery import baker as mommy
from task.models import Task, TaskStatus


class DashboardStatusCheckTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='username', password='password')
        self.client.login(username='username', password='password')

    def test_not_changed(self):
        task = mommy.make(Task, task_status=TaskStatus.OPEN)
        tasks = [[task.id, str(task.task_status)]]
        response = self.client.post(reverse('task_status_check'),
                                    data={"tasks": json.dumps(tasks)})
        data = response.json()
        self.assertFalse(data["has_changed"])

    def test_has_changed(self):
        task = mommy.make(Task, task_status=TaskStatus.OPEN)

        tasks = [[task.id, str(task.task_status)]]

        task.task_status = TaskStatus.ACCEPTED
        task.alter_user = self.user
        task.save()
        response = self.client.post(reverse('task_status_check'),
                                    data={"tasks": json.dumps(tasks)})
        data = response.json()
        self.assertTrue(data["has_changed"])
