from django.test import TestCase
from api.models import User, Mechanic, SubscriptionPlan, Subscription, Payment
from django.urls import reverse
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta

class SubscriptionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Création d'un utilisateur individuel
        self.individual_user = User.objects.create_user(username='individual', password='password123', user_type='INDIVIDUAL')

        # Création d'un mécanicien
        self.mechanic_user = User.objects.create_user(username='mechanic', password='password123', user_type='MECHANIC')
        self.mechanic = Mechanic.objects.create(user=self.mechanic_user, shop_name="Test Garage")

        # Création d'un plan
        self.plan = SubscriptionPlan.objects.create(
            name="Premium",
            tier="PREMIUM",
            price=10000,
            duration_days=30,
            target_user_type='MECHANIC'
        )
        self.plan_indiv = SubscriptionPlan.objects.create(
            name="Indiv Premium",
            tier="PREMIUM",
            price=5000,
            duration_days=30,
            target_user_type='INDIVIDUAL'
        )

    def test_change_plan_mechanic(self):
        """Teste le changement de plan pour un mécanicien."""
        self.client.force_authenticate(user=self.mechanic_user)
        url = reverse('user-change-plan') # /api/users/change_plan/
        data = {
            'plan_id': self.plan.id,
            'transaction_id': 'TX-MECH-001',
            'duration_months': 1,
            'payment_method': 'ORANGE'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['subscription']['plan']['id'], self.plan.id)

        # Vérifier en base
        # On vérifie qu'il est lié à la fois au User ET au Mechanic
        sub = Subscription.objects.get(user=self.mechanic_user, plan=self.plan, is_active=True)
        self.assertEqual(sub.mechanic, self.mechanic)

    def test_change_plan_individual(self):
        """Teste le changement de plan pour un particulier."""
        self.client.force_authenticate(user=self.individual_user)
        # On utilise le nouvel endpoint centralisé (ou l'alias)
        url = reverse('subscription-change-plan') # /api/subscriptions/change_plan/
        data = {
            'plan_id': self.plan_indiv.id,
            'transaction_id': 'TX-INDIV-001',
            'duration_months': 1,
            'payment_method': 'WAVE'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['subscription']['plan']['id'], self.plan_indiv.id)

        # Vérifier en base
        self.assertTrue(Subscription.objects.filter(user=self.individual_user, plan=self.plan_indiv, is_active=True).exists())

    def test_change_plan_via_mechanic_route_for_individual(self):
        """Teste que la redirection dans MechanicViewSet fonctionne aussi pour un Individual."""
        self.client.force_authenticate(user=self.individual_user)
        url = reverse('user-change-plan') # /api/users/change_plan/
        data = {
            'plan_id': self.plan_indiv.id,
            'transaction_id': 'TX-INDIV-002',
            'duration_months': 2,
            'payment_method': 'MTN'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        sub = Subscription.objects.get(user=self.individual_user, is_active=True)
        self.assertEqual(sub.plan, self.plan_indiv)
        # 2 mois = 60 jours
        expected_end = timezone.now() + timedelta(days=60)
        self.assertAlmostEqual(sub.end_date, expected_end, delta=timedelta(seconds=10))
