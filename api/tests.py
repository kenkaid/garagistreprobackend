from django.test import TestCase
from api.models import User, Mechanic, DTCReference, ScanSession, Vehicle
from api.services.diagnostics import DiagnosticService
from api.services.ai_service import DTCModelAI
from django.urls import reverse
from rest_framework.test import APIClient

class AuthTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password123')

    def test_obtain_token(self):
        """Teste l'obtention d'un jeton d'authentification."""
        url = reverse('api_token_auth')
        data = {'username': 'testuser', 'password': 'password123'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)

class DiagnosticIATestCase(TestCase):
    def setUp(self):
        # Création d'un utilisateur et d'un mécanicien
        self.user = User.objects.create_user(username='testmech', password='password123')
        self.mechanic = Mechanic.objects.create(user=self.user, shop_name="Test Garage", location="Abidjan")

        # Création d'une référence DTC
        self.dtc_ref = DTCReference.objects.create(
            code="P0101",
            brand="Toyota",
            description="Débitmètre d'air - problème de performance",
            meaning="Le capteur de débit d'air envoie des données incohérentes.",
            severity="high",
            est_labor_cost=5000,
            est_part_price_local=15000
        )

    def test_record_scan_and_ai_prediction(self):
        """Teste l'enregistrement d'un scan et la récupération des prédictions IA."""
        vehicle_data = {
            'license_plate': '1234AB01',
            'brand': 'Toyota',
            'model': 'Corolla',
            'year': 2015
        }
        dtc_codes = ["P0101"]

        # 1. Enregistrement du scan
        scan = DiagnosticService.record_scan(self.mechanic, vehicle_data, dtc_codes, notes="Ralenti instable")

        self.assertEqual(scan.vehicle.license_plate, '1234AB01')
        self.assertEqual(scan.found_dtcs.count(), 1)
        self.assertEqual(scan.found_dtcs.first().code, "P0101")

        # 2. Vérification des prédictions IA dans le scan (via le service appelé par DiagnosticService)
        # DiagnosticService appelle DTCModelAI.predict_costs
        self.assertEqual(scan.actual_labor_cost, 5000)
        self.assertEqual(scan.actual_parts_cost, 15000)

    def test_ai_training(self):
        """Teste l'entraînement de l'IA basé sur des sessions complétées."""
        vehicle = Vehicle.objects.create(license_plate="TEST1", brand="Toyota", model="Corolla")

        # Création d'une session complétée avec des coûts différents de la référence
        scan = ScanSession.objects.create(
            mechanic=self.mechanic,
            vehicle=vehicle,
            actual_labor_cost=10000,
            actual_parts_cost=20000,
            is_completed=True,
            notes="Cause: Débitmètre encrassé. Solution: Nettoyage du capteur."
        )
        scan.found_dtcs.add(self.dtc_ref)

        # Lancement de l'entraînement
        DTCModelAI.train()

        # Rafraîchir la référence DTC
        self.dtc_ref.refresh_from_db()

        # Le coût devrait avoir été mis à jour (moyenne pondérée ou lissage)
        # Formule dans le code : (ancien * 2 + nouveau) / 3
        # Labor: (5000 * 2 + 10000) / 3 = 6666.66 -> 6666
        self.assertEqual(self.dtc_ref.est_labor_cost, 6666)

        # Vérification de l'extraction des causes/solutions
        import json
        causes = json.loads(self.dtc_ref.probable_causes)
        solutions = json.loads(self.dtc_ref.suggested_solutions)

        self.assertTrue(any("débitmètre" in c.lower() for c in causes))
        self.assertTrue(any("nettoyage" in s.lower() for s in solutions))

    def test_predict_advanced(self):
        """Teste la méthode predict_advanced utilisée par le serializer."""
        vehicle_info = {'brand': 'Toyota'}
        prediction = DTCModelAI.predict_advanced(["P0101"], vehicle_info)

        diag = prediction['diagnostics'][0]
        self.assertEqual(diag['code'], "P0101")
        self.assertEqual(diag['severity'], "high")
        self.assertEqual(diag['estimated_labor'], 5000)

class DTCAutoCreationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testmech2', password='password123')
        self.mechanic = Mechanic.objects.create(user=self.user, shop_name="Test Garage 2", location="Abidjan")

    def test_auto_create_new_dtc(self):
        """Teste la création automatique d'un DTC inconnu lors d'un scan."""
        vehicle_data = {
            'license_plate': 'NEW_VEHICLE',
            'brand': 'Hyundai',
            'model': 'Tucson',
            'year': 2020
        }
        dtc_codes = ["P9999"] # Code qui n'existe pas en base

        # Vérifier qu'il n'existe pas avant
        from api.models import DTCReference
        self.assertFalse(DTCReference.objects.filter(code="P9999").exists())

        # Enregistrer le scan
        DiagnosticService.record_scan(self.mechanic, vehicle_data, dtc_codes)

        # Vérifier qu'il a été créé pour Hyundai
        self.assertTrue(DTCReference.objects.filter(code="P9999", brand="Hyundai").exists())
        ref = DTCReference.objects.get(code="P9999", brand="Hyundai")
        self.assertIn("Hyundai", ref.description)
        self.assertIn("Hyundai", ref.meaning)

    def test_auto_create_from_generic(self):
        """Teste la création d'un DTC spécifique à partir d'un générique existant."""
        from api.models import DTCReference
        # Créer un code générique
        DTCReference.objects.create(
            code="P8888",
            brand=None,
            description="Problème générique P8888",
            meaning="Explication générique",
            severity="low"
        )

        vehicle_data = {
            'license_plate': 'GENERIC_TO_SPECIFIC',
            'brand': 'Kia',
            'model': 'Sportage'
        }
        dtc_codes = ["P8888"]

        # Enregistrer le scan
        DiagnosticService.record_scan(self.mechanic, vehicle_data, dtc_codes)

        # Vérifier qu'un spécifique Kia a été créé avec les infos du générique
        self.assertTrue(DTCReference.objects.filter(code="P8888", brand="Kia").exists())
        kia_ref = DTCReference.objects.get(code="P8888", brand="Kia")
        self.assertEqual(kia_ref.description, "Problème générique P8888")
        self.assertEqual(kia_ref.severity, "low")

class AdvancedExpertiseTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='expert_mech', password='password123')
        self.mechanic = Mechanic.objects.create(user=self.user, shop_name="Expert Garage", location="Abidjan")
        
    def test_record_scan_with_mileage_and_safety(self):
        """Teste l'enregistrement d'un scan avec données de kilométrage et de sécurité."""
        vehicle_data = {'license_plate': 'EXPERT01', 'brand': 'Toyota'}
        dtc_codes = []
        mileage_data = {
            'mileage_ecu': 125000,
            'mileage_abs': 125000,
            'mileage_dashboard': 120000 # Simulation de fraude (5000km de moins au compteur)
        }
        safety_data = {
            'is_airbag_deployed': False,
            'crash_data_present': True, # Historique d'accident détecté électroniquement
            'srs_module_status': 'OK',
            'notes': 'Trace d\'impact ancien détectée dans le module SRS'
        }
        
        scan = DiagnosticService.record_scan(
            self.mechanic, vehicle_data, dtc_codes, 
            mileage_data=mileage_data, safety_data=safety_data
        )
        
        # Vérification kilométrage
        self.assertEqual(scan.mileage_ecu, 125000)
        self.assertEqual(scan.mileage_dashboard, 120000)
        self.assertEqual(scan.mileage_discrepancy, 5000)
        
        # Vérification sécurité
        from api.models import SafetyCheck
        safety = SafetyCheck.objects.get(scan_session=scan)
        self.assertTrue(safety.crash_data_present)
        self.assertEqual(safety.notes, 'Trace d\'impact ancien détectée dans le module SRS')

    def test_scan_types(self):
        """Teste la distinction entre diagnostic et vérification."""
        vehicle_data = {'license_plate': 'TYPE_TEST', 'brand': 'BMW'}
        
        # Scan initial
        scan1 = DiagnosticService.record_scan(self.mechanic, vehicle_data, ["P0101"], scan_type='DIAGNOSTIC')
        self.assertEqual(scan1.scan_type, 'DIAGNOSTIC')
        
        # Scan de vérification
        scan2 = DiagnosticService.record_scan(self.mechanic, vehicle_data, [], scan_type='VERIFICATION')
        self.assertEqual(scan2.scan_type, 'VERIFICATION')
        self.assertEqual(scan2.found_dtcs.count(), 0)

class UpcomingModuleTestCase(TestCase):
    def setUp(self):
        from api.models import UpcomingModule, SubscriptionPlan
        from django.utils import timezone
        import json

        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_authenticate(user=self.user)

        self.plan = SubscriptionPlan.objects.create(name="Premium", tier="PREMIUM", price=10000, duration_days=30, description="Test")
        self.module = UpcomingModule.objects.create(
            name="Module Test",
            expected_release_date=timezone.now().date(),
            is_active=True
        )
        self.module.description = json.dumps({'html': '<p>Test</p>', 'delta': {}})
        self.module.save()
        self.module.applicable_plans.add(self.plan)

    def test_upcoming_modules_api(self):
        """Teste l'API des modules à venir."""
        url = reverse('upcoming-module-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Module Test")
        self.assertIn('description_html', response.data[0])
        self.assertEqual(response.data[0]['description_html'], '<p>Test</p>')
        self.assertEqual(len(response.data[0]['applicablePlans']), 1)
        self.assertEqual(response.data[0]['applicablePlans'][0]['tier'], "PREMIUM")

class FleetRegistrationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_fleet_owner_registration(self):
        """Teste l'inscription d'un propriétaire de flotte."""
        url = reverse('register')
        data = {
            "username": "fleet_test_user",
            "password": "password123",
            "confirm_password": "password123",
            "email": "fleet@example.com",
            "phone": "+2250102030405",
            "first_name": "Jean",
            "last_name": "Dupont",
            "shop_name": "Ma Super Flotte CI",
            "location": "Abidjan, Cocody",
            "user_type": "FLEET_OWNER"
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['user']['user_type'], 'FLEET_OWNER')
        
        # Vérifier que l'utilisateur a bien été créé
        user = User.objects.get(username="fleet_test_user")
        self.assertEqual(user.user_type, 'FLEET_OWNER')
        self.assertFalse(user.is_mechanic)
        
        # Vérifier que le shop_name a été utilisé comme first_name s'il était vide (notre logique dans le serializer)
        # En fait dans notre payload on a mis "Jean", donc first_name devrait rester "Jean"
        self.assertEqual(user.first_name, "Jean")
        
        # Tester avec first_name vide pour voir si shop_name est récupéré
        data["username"] = "fleet_test_user_2"
        data["phone"] = "+22500000000"
        data["first_name"] = ""
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201)
        user2 = User.objects.get(username="fleet_test_user_2")
        self.assertEqual(user2.first_name, "Ma Super Flotte CI")

    def test_mechanic_registration_still_works(self):
        """Vérifie que l'inscription mécanicien fonctionne toujours normalement."""
        url = reverse('register')
        data = {
            "username": "mech_test_user",
            "password": "password123",
            "confirm_password": "password123",
            "phone": "+22502020202",
            "shop_name": "Garage Pro",
            "location": "Plateau",
            "user_type": "MECHANIC"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201)
        
        user = User.objects.get(username="mech_test_user")
        self.assertEqual(user.user_type, 'MECHANIC')
        self.assertTrue(user.is_mechanic)
        
        # Vérifier le profil mécanicien
        mechanic = Mechanic.objects.get(user=user)
        self.assertEqual(mechanic.shop_name, "Garage Pro")
