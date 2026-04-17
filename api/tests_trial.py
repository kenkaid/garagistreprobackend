from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from api.models import User, Mechanic, Subscription, SubscriptionPlan

class TrialIntegrationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('register')

    def test_mechanic_registration_activates_trial(self):
        """
        Vérifie qu'un mécanicien qui s'inscrit reçoit automatiquement une période d'essai.
        """
        data = {
            "username": "new_mechanic",
            "email": "mech@example.com",
            "password": "password123",
            "phone": "0102030405",
            "first_name": "Jean",
            "last_name": "Dupont",
            "shop_name": "Garage Central",
            "location": "Abidjan",
            "user_type": "MECHANIC"
        }

        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, 201)

        user = User.objects.get(username="new_mechanic")
        self.assertTrue(user.has_used_trial)

        subscription = Subscription.objects.filter(user=user, is_active=True).first()

        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.plan.tier, 'TRIAL')
        self.assertEqual(subscription.plan.price, 0)
        self.assertEqual(subscription.plan.duration_days, 14)
        self.assertTrue(subscription.is_active)

    def test_fleet_owner_registration_activates_trial(self):
        """
        Vérifie qu'un propriétaire de flotte reçoit AUSSI une période d'essai automatiquement.
        """
        data = {
            "username": "fleet_owner",
            "email": "fleet@example.com",
            "password": "password123",
            "phone": "0505050505",
            "user_type": "FLEET_OWNER"
        }

        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, 201)

        user = User.objects.get(username="fleet_owner")
        self.assertTrue(user.has_used_trial)

        subscription = Subscription.objects.filter(user=user, is_active=True).first()
        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.plan.tier, 'TRIAL')
        self.assertEqual(subscription.plan.target_user_type, 'FLEET_OWNER')

    def test_manual_trial_activation_action(self):
        """
        Vérifie que la logique d'activation manuelle fonctionne (utilisée dans l'admin).
        """
        from api.services.subscriptions import SubscriptionService
        user = User.objects.create_user(username="manual_user", password="password123", user_type="INDIVIDUAL")

        # Activation manuelle
        SubscriptionService.activate_trial(user)

        self.assertTrue(user.has_used_trial)
        self.assertTrue(Subscription.objects.filter(user=user, is_active=True).exists())

        # Test de réactivation (simule l'action admin qui remet has_used_trial à False)
        user.has_used_trial = False
        user.save()

        SubscriptionService.activate_trial(user)
        self.assertEqual(Subscription.objects.filter(user=user).count(), 2)
        # L'ancien doit être inactif
        self.assertEqual(Subscription.objects.filter(user=user, is_active=True).count(), 1)

    def test_trial_days_remaining_in_serializer(self):
        """
        Vérifie que le serializer inclut bien le nombre de jours restants.
        """
        from api.serializers import UserSerializer
        user = User.objects.create_user(username="test_serial", password="password123", user_type="INDIVIDUAL")
        from api.services.subscriptions import SubscriptionService
        SubscriptionService.activate_trial(user)

        serializer = UserSerializer(user)
        data = serializer.data

        self.assertTrue(data['is_trial'])
        # Par défaut l'essai est de 14 jours
        self.assertEqual(data['trial_days_remaining'], 14)
        self.assertEqual(data['subscription_tier'], 'TRIAL')
