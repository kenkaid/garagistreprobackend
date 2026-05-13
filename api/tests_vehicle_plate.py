
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from api.models import User, Vehicle, Mechanic

class VehiclePlateTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testmechanic', password='password123', user_type='MECHANIC')
        self.mechanic = Mechanic.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

        self.vehicle = Vehicle.objects.create(
            license_plate='1234AB01',
            brand='TOYOTA',
            model='COROLLA',
            year=2015,
            owner=self.user
        )

    def test_get_vehicle_by_plate(self):
        # Test case-insensitive match
        url = reverse('vehicle-by-plate', kwargs={'plate': '1234ab01'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['brand'], 'TOYOTA')
        self.assertEqual(response.data['model'], 'COROLLA')
        self.assertEqual(response.data['year'], 2015)

    def test_get_vehicle_by_plate_not_found(self):
        url = reverse('vehicle-by-plate', kwargs={'plate': 'NONEXISTENT'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
