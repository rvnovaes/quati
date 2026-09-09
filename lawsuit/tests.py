from django.urls import reverse
from tests.support import OfficeTestCase

from model_bakery import baker as mommy

from core.models import Person
from lawsuit.forms import LawSuitForm, CourtDivisionForm, InstanceForm, FolderForm, \
    CourtDistrictForm, TypeMovementForm, MovementForm
from lawsuit.models import LawSuit, CourtDistrict, CourtDivision, Folder, Instance, State, \
    Movement, TypeMovement, Organ

# TODO LawSuit, Views

# Status 200: conseguiu acessar a pagina
# Status 300: Redirecionamento
# Status 404: Nao encontrado
# model_mommy serve apenas para testes em modelos. Testes na view tem que ser feitos da maneira
# convencional


class LawSuitTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()

    def test_routine(self):
        c_inst = mommy.make(LawSuit)
        self.assertTrue(isinstance(c_inst, LawSuit))

    def test_valid_LawSuitForm(self):
        person_lawyer = mommy.make(
            Person, name='Adv', is_lawyer=True, is_active=True).id
        folder = mommy.make(Folder).id
        instance = mommy.make(Instance, office=self.office).id
        court_district = mommy.make(CourtDistrict).id
        organ = mommy.make(Organ, name='Court', is_active=True).id
        court_division = mommy.make(CourtDivision, office=self.office, is_active=True).id
        law_suit_number = '12345'

        data = {
            'person_lawyer': person_lawyer,
            'folder': folder,
            'instance': instance,
            'court_district': court_district,
            'organ': organ,
            'court_division': court_division,
            'law_suit_number': law_suit_number, 'type_lawsuit': 'JUDICIAL'
        }

        form = LawSuitForm(data={**data, "office": self.office.pk}, request=self.post_request)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_view(self):
        url = reverse('lawsuit_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('lawsuit_add', kwargs={'folder': self.folder.pk})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        c_inst = mommy.make(LawSuit)
        url = reverse(
            'lawsuit_update',
            kwargs={
                'folder': c_inst.folder.id,
                'pk': c_inst.id
            })
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(LawSuit)
        data = {'selection': [c_inst.id], 'parent_class': c_inst.folder.id}
        url = reverse('lawsuit_delete')
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(LawSuit.objects.filter(pk=c_inst.pk).exists())


class InstanceTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()

    # todo teste tem que ter o prefixo test_
    def test_routine(self):
        # mommy deixa as coisas bem mais faaceis
        c_inst = mommy.make(Instance, name='Random')
        self.assertTrue(isinstance(c_inst, Instance))

    def test_valid_InstanceForm(self):
        name = 'Tipo_Instacia_BLABLABLA'

        data = {'name': name}
        form = InstanceForm(data={**data, "office": self.office.pk}, request=self.post_request)
        print(form.errors)
        self.assertTrue(form.is_valid())

    def test_list_view(self):
        url = reverse('instance_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('instance_create')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        c_inst = mommy.make(Instance, name='123')
        url = reverse('instance_update', kwargs={'pk': c_inst.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(Instance, name='123')
        data = {'selection': [c_inst.id]}
        url = reverse('instance_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(type(c_inst).objects.filter(pk=c_inst.pk).exists())


class FolderTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        self.c_inst = mommy.make(Folder)

    def test_routine(self):
        self.assertTrue(isinstance(self.c_inst, Folder))

    def test_valid_FolderForm(self):
        legacy_code = '9999'
        person_customer = mommy.make(
            Person, name='Joao', is_active=True, is_customer=True).id

        data = {
            'legacy_code': legacy_code,
            'person_customer': person_customer,
            'cost_center': None
        }
        form = FolderForm(data={**data, "office": self.office.pk}, request=self.post_request)
        self.assertTrue(form.is_valid())

    def test_list_view(self):
        url = reverse('folder_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('folder_add')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        url = reverse('folder_update', kwargs={'pk': self.c_inst.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(Folder)
        data = {'selection': [c_inst.id]}
        url = reverse('folder_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(type(c_inst).objects.filter(pk=c_inst.pk).exists())


class CourtDivisionTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        self.c_inst = mommy.make(CourtDivision)

    def test_routine(self):
        self.assertTrue(isinstance(self.c_inst, CourtDivision))

    def test_valid_CourtDivisionForm(self):
        legacy_code = '9999'
        name = 'Test123'

        data = {'name': name, 'legacy_code': legacy_code}

        form = CourtDivisionForm(data={**data, "office": self.office.pk}, request=self.post_request)
        print(form.errors)
        self.assertTrue(form.is_valid())

    def test_list_view(self):
        url = reverse('courtdivision_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('courtdivision_add')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        url = reverse('courtdivision_update', kwargs={'pk': self.c_inst.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(CourtDivision)
        data = {'selection': [c_inst.id]}
        url = reverse('courtdivision_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(type(c_inst).objects.filter(pk=c_inst.pk).exists())


class CourtDistrictTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        self.c_inst = mommy.make(CourtDistrict)

    def test_routine(self):
        self.assertTrue(isinstance(self.c_inst, CourtDistrict))

    def test_valid_CourtDistrictForm(self):
        state = mommy.make(State, is_active=True).id
        name = 'Test123'

        data = {'name': name, 'state': state}
        form = CourtDistrictForm(data={**data, "office": self.office.pk}, request=self.post_request)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_view(self):
        url = reverse('courtdistrict_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('courtdistrict_add')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        url = reverse('courtdistrict_update', kwargs={'pk': self.c_inst.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(CourtDistrict)
        data = {'selection': [c_inst.id]}
        url = reverse('courtdistrict_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(type(c_inst).objects.filter(pk=c_inst.pk).exists())


class MovementTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        # self.c_inst = self.movement

    def test_routine(self):
        c_inst = self.movement
        self.assertTrue(isinstance(c_inst, Movement))

    def test_valid_MovementForm(self):
        legacy_code = '9999'
        person_lawyer = mommy.make(Person, is_active=True, is_lawyer=True).id

        law_suit = mommy.make(LawSuit, is_active=True).id
        type_movement = mommy.make(TypeMovement, is_active=True).id
        data = {
            'legacy_code': legacy_code,
            'person_lawyer': person_lawyer,
            'law_suit': law_suit,
            'type_movement': type_movement
        }

        form = MovementForm(data={**data, "office": self.office.pk}, request=self.post_request)
        print(form.errors)

        self.assertTrue(form.is_valid())

    def test_list_view(self):
        url = reverse('movement_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        c_inst = self.movement
        url = reverse('movement_add', kwargs={'lawsuit': c_inst.law_suit.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        c_inst = self.movement
        url = reverse(
            'movement_update',
            kwargs={
                'pk': c_inst.id,
                'lawsuit': c_inst.law_suit.id
            })
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    # def test_delete_view(self):
    #     c_inst = self.movement
    #     data = {'movement_list': {c_inst.id}, 'parent_class': c_inst.law_suit.id}
    #     url = reverse('movement_delete')
    #     resp = self.client.post(url, data, follow=True)
    #     # print(resp.context)

    #     self.assertEqual(resp.status_code, 200)


class TypeMovementTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()
        self.c_inst = mommy.make(TypeMovement, name='RandomTM')

    def test_routine(self):
        self.assertTrue(isinstance(self.c_inst, TypeMovement))

    # TODO Testar os Forms
    def test_valid_TypeMovementForm(self):
        # Diferente do que manda o tutorial realpython, nao se deve criar uma instancia para
        # testar o form
        name = 'Tipo_Movimentacao_BLABLABLA'
        legacy_code = '9999'
        uses_wo = True

        data = {'name': name, 'uses_wo': uses_wo, 'legacy_code': legacy_code}
        form = TypeMovementForm(data={**data, "office": self.office.pk}, request=self.post_request)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_view(self):
        url = reverse('type_movement_list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('type_movement_add')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        url = reverse('type_movement_update', kwargs={'pk': self.c_inst.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(TypeMovement)
        data = {'selection': [c_inst.id]}
        url = reverse('type_movement_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(type(c_inst).objects.filter(pk=c_inst.pk).exists())
