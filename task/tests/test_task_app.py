from django.contrib.auth.models import User, Group
# from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from model_bakery import baker as mommy

from core.models import Person
from lawsuit.models import Movement
from task.models import TypeTask, Task, Ecm, TaskHistory
from task.forms import TaskForm, TaskDetailForm

class TaskTest(TestCase):
    def setUp(self):
        User.objects.create_user(username='username', password='password')
        self.client.login(username='username', password='password')

        self.requester_group, nil = \
            Group.objects.get_or_create(name=Person.REQUESTER_GROUP)

        self.requester_user = User.objects.create(username='advogado-01')
        self.requester_user.groups.add(self.requester_group)

        self.correspondent_group, nil = \
            Group.objects.get_or_create(name=Person.CORRESPONDENT_GROUP)

        self.correspondent_user = User.objects.create(username='correspondente-01')
        self.correspondent_user.groups.add(self.correspondent_group)

    def test_model(self):
        # mommy deixa as coisas bem mais faaceis
        c_inst = mommy.make(Task)
        self.assertTrue(isinstance(c_inst, Task))

    def test_valid_TaskForm(self):
        movement = mommy.make(Movement).id

        type_task = mommy.make(TypeTask).id
        delegation_date = timezone.now()
        final_deadline_date = timezone.now()

        description = """
         Segundo o cliente ainda há três parcelas das cinco pactuadas no acordo. O processo foi
         remetido ao arquivo geral. Pedi que o correspondente retire extrato para instruir nosso
         pedido de desarquivamento e expedição de alvará, execução do saldo remanescente se for o
         caso. -- em 19/05/2016 11:14:43 por Aramalho -> Aguardando retorno do correspondente com o
         extrato da conta judicial. -- em 23/05/2016 11:10:54 por Aramalho -> Finalmente a
         secretaria nos oportunizou consulta aos autos e verificamos que foram expedidos dois
         alvarás: (i) 24.07.2015, referente à 1ª e 2ª parcelas, fls. 81 e (ii) 22.09.2015,
         referente às parcelas 3, 4 e 5, fls. 96. INFORMADO AO CLIENTE - Aguardar retorno. -- em
         31/05/2016 15:22:50 por Aramalho -> Petição feita - Acompanhar levantamento. -- em
         30/06/2016 14:24:14 por Aramalho -> Autos conclusos para apreciação da nossa petição. --
         em 02/08/2016 12:55:59 por Aramalho -> Autos conclusos para aprecisação da nossa petição.
         *** Prazo repassado de ANDRE CHEREM RAMALHO para ADRIANE GONÇALVES DE SOUSA por Aramalho
         em 28/11/2016 11:28:46 -- em 07/12/2016 15:30:24 por Agsousa -> Autos permanecem conclusos
          -- em 21/12/2016 13:31:36 por Agsousa -> Autos permanecem conclusos desde 07/06/2016 --
          em 25/01/2017 14:04:55 por Agsousa -> Autos permanecem conclusos -- em
          22/02/2017 14:17:27
          por Agsousa -> Autos permanecem conclusos -- em 21/03/2017 18:22:52 por Agsousa -> Autos
          permanecem conclusos *** Prazo repassado de ADRIANE GONÇALVES DE SOUSA para ANA CAROLINA
          MARCELINO DE ARAUJO SILVA por Agsousa em 21/03/2017 18:23:07 -- em 17/04/2017 13:38:33
          por
          Acsilva -> CONCLUSOS PARA DESPACHO JUIZ(A) PRESIDENTE(A) 31930 07/06/2016 Situação
          inalterada - autos conclusos - pendente expedição de alvará -- em 02/05/2017 16:23:41 por
           Acsilva -> CONCLUSOS PARA DESPACHO JUIZ(A) PRESIDENTE(A) 31930 07/06/2016 Situação
           inalterada - autos conclusos - pendente expedição de alvará
        """

        data = {'movement': movement,
                'person_asked_by': self.requester_user.person.id,
                'person_executed_by': self.correspondent_user.person.id,
                'type_task': type_task,
                'description': description,
                'delegation_date': delegation_date,
                'final_deadline_date': final_deadline_date}  # Unico requerido
        form = TaskForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_view(self):
        url = reverse('task_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        movement = mommy.make(Movement).id
        url = reverse('task_add', kwargs={'movement': movement})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        # Task tem algumas fk, o que pode causar erros se instanciados diretamente pelo mommy.
        # Neste caso deve-se instanciar cada objeto separadamente
        c_inst = mommy.make(Task, movement=mommy.make(Movement, legacy_code='999'),
                            person_asked_by=mommy.make(Person, is_active=True, is_lawyer=True),
                            person_executed_by=mommy.make(Person, is_lawyer=True),
                            type_task=mommy.make(TypeTask))

        url = reverse('task_update', kwargs={'pk': str(c_inst.id), 'movement': c_inst.movement.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    # def test_delete_view(self):
    #     c_inst = mommy.make(Task)
    #     data = {'task_list': {c_inst.id}, 'movement': c_inst.movement.id}
    #     url = reverse('task_delete')
    #     resp = self.client.post(url, data, follow=True)
    #     self.assertEqual(resp.status_code, 200)


class TaskHistoryTest(TestCase):
    def test_model(self):
        # mommy deixa as coisas bem mais faaceis
        c_inst = mommy.make(TaskHistory)
        self.assertTrue(isinstance(c_inst, TaskHistory))


class EcmTest(TestCase):
    def setUp(self):
        User.objects.create_user(username='username', password='password')
        self.client.login(username='username', password='password')

    def test_model(self):
        # mommy deixa as coisas bem mais faaceis
        c_inst = mommy.make(Ecm, path='ECM/something.pdf')
        self.assertTrue(isinstance(c_inst, Ecm))

    def test_create_view(self):
        task = mommy.make(Task, movement=mommy.make(Movement, legacy_code='999'),
                          person_asked_by=mommy.make(Person, name='joao', is_active=True,
                                                     is_lawyer=True),
                          person_executed_by=mommy.make(Person, name='pedro', is_lawyer=True),
                          type_task=mommy.make(TypeTask, name='TT123')).id
        url = reverse('ecm_add', kwargs={'pk': task})
        resp = self.client.post(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        task = mommy.make(Task, movement=mommy.make(Movement, legacy_code='999'),
                          person_asked_by=mommy.make(Person, name='joao', is_active=True,
                                                     is_lawyer=True),
                          person_executed_by=mommy.make(Person, name='pedro', is_lawyer=True),
                          type_task=mommy.make(TypeTask, name='TT123')).id
        url = reverse('delete_ecm', kwargs={'pk': task})
        resp = self.client.post(url)

        self.assertEqual(resp.status_code, 200)


class TaskDetailTest(TestCase):
    def test_valid_TaskDetailForm(self):
        data = {'execution_date': timezone.now(),
                'survey_result': 'cumprido', 'notes': 'teste'}
        form = TaskDetailForm(data=data)
        self.assertTrue(form.is_valid())
