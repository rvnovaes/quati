from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase

from model_bakery import baker as mommy

from core.models import Person, City, Country, State, AddressType, ContactMechanism, ContactUs
from core.forms import PersonForm, AddressForm, UserCreateForm


class PersonTest(TestCase):
    def setUp(self):
        User.objects.create_user(username='username', password='password')
        self.client.login(username='username', password='password')

    def test_model(self):
        # mommy deixa as coisas bem mais faaceis
        c_inst = mommy.make(Person, name='Random')
        self.assertTrue(isinstance(c_inst, Person))

    def test_valid_PersonForm(self):
        legal_type = 'F'
        data = {'legal_type': legal_type, 'legal_name': 'some-legal-name'}
        form = PersonForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_list_view(self):
        url = reverse('person_list')
        resp = self.client.get(url)

        # Se consegue alcancar a pagina
        self.assertEqual(resp.status_code, 200)

    def test_create_view(self):
        url = reverse('person_add')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_update_view(self):
        c_inst = mommy.make(Person, legal_type='F')
        url = reverse('person_update', kwargs={'pk': c_inst.id})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_delete_view(self):
        c_inst = mommy.make(Person, name='Random')
        data = {'person_list': {c_inst.id}}
        url = reverse('person_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)


class AdressTest(TestCase):
    def test_model_city(self):
        c_inst = mommy.make(City)
        self.assertTrue(isinstance(c_inst, City))

    def test_model_country(self):
        c_inst = mommy.make(Country)
        self.assertTrue(isinstance(c_inst, Country))

    def test_model_state(self):
        c_inst = mommy.make(State)
        self.assertTrue(isinstance(c_inst, State))

    def test_valid_AddressForm(self):
        street = 'Grao Mogol'
        number = '123'
        city_region = 'Carmo'
        zip_code = '99999-999'
        country = mommy.make(Country, id=1).id  # Conforme os forms
        state = mommy.make(State, id=13, country_id=country).id
        city = mommy.make(City, state_id=state).id
        address_type = mommy.make(AddressType, name='comercial').id

        data = {
            'street': street,
            'number': number,
            'city_region': city_region,
            'zip_code': zip_code,
            'country': country,
            'state': state,
            'city': city,
            'address_type': address_type
        }

        form = AddressForm(data=data)
        print(form.errors)
        self.assertTrue(form.is_valid())


class ContactMechanismTest(TestCase):
    def test_model(self):
        c_inst = mommy.make(ContactMechanism)
        self.assertTrue(isinstance(c_inst, ContactMechanism))


class ContactUsTest(TestCase):
    def test_model(self):
        c_inst = mommy.make(ContactUs)
        self.assertTrue(isinstance(c_inst, ContactUs))


class AddressTypeTest(TestCase):
    def test_model(self):
        c_inst = mommy.make(AddressType, name='residencial')
        self.assertTrue(c_inst, AddressType)


class UserTest(TestCase):
    def test_model(self):
        c_isnt = mommy.make(
            User,
            first_name='Thiago',
            last_name='Rodrigues',
            username='thiago',
            email='thiago.ar17@gmail.com',
            password=123456)
        self.assertTrue(c_isnt, User)

    def test_invalid_senha_curta_UserCreateForm(self):
        data = {
            'first_name': 'Random',
            'last_name': 'RandomLast',
            'username': 'random',
            'email': 'random@random.com',
            'password1': '12345',
            'password2': '12345'
        }
        form = UserCreateForm(data=data)
        self.assertFalse(form.is_valid())
