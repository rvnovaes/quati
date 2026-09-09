from django.contrib.auth.models import User
from django.urls import reverse
from django.test import override_settings
from tests.support import OfficeTestCase

from model_bakery import baker as mommy

from core.models import Person, City, Country, State, AddressType, ContactMechanism, ContactUs
from core.forms import PersonForm, AddressForm, UserCreateForm


class PersonTest(OfficeTestCase):
    def setUp(self):
        self.setup_office()

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
        data = {'selection': [c_inst.id]}
        url = reverse('person_delete')
        resp = self.client.post(url, data, follow=True)
        # print(resp.context)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(type(c_inst).objects.filter(pk=c_inst.pk).exists())


class AdressTest(OfficeTestCase):
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


class ContactMechanismTest(OfficeTestCase):
    def test_model(self):
        c_inst = mommy.make(ContactMechanism)
        self.assertTrue(isinstance(c_inst, ContactMechanism))


class ContactUsTest(OfficeTestCase):
    def test_model(self):
        c_inst = mommy.make(ContactUs)
        self.assertTrue(isinstance(c_inst, ContactUs))


class AddressTypeTest(OfficeTestCase):
    def test_model(self):
        c_inst = mommy.make(AddressType, name='residencial')
        self.assertTrue(c_inst, AddressType)


class UserTest(OfficeTestCase):
    def test_model(self):
        c_isnt = mommy.make(
            User,
            first_name='Thiago',
            last_name='Rodrigues',
            username='thiago',
            email='thiago.ar17@gmail.com',
            password=123456)
        self.assertTrue(c_isnt, User)

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    }])
    def test_invalid_senha_curta_UserCreateForm(self):
        self.setup_office()
        data = {
            'first_name': 'Random',
            'last_name': 'RandomLast',
            'username': 'random',
            'email': 'random@random.com',
            'password1': '12345',
            'password2': '12345'
        }
        data["office"] = self.office.pk
        form = UserCreateForm(data=data, request=self.post_request)
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)
        self.assertEqual(form.errors.as_data()["password2"][0].code, "password_too_short")
