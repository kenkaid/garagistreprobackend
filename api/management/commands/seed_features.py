from django.core.management.base import BaseCommand
from api.models import Feature

class Command(BaseCommand):
    help = 'Seed initial features from mobile home screens'

    def handle(self, *args, **options):
        # Liste des fonctionnalités — codes alignés avec le frontend mobile
        features_to_seed = [
            # Garage / Mécanicien
            {'name': 'Diagnostic OBD', 'code': 'scan_diagnostic', 'description': 'Accès au diagnostic de véhicule via OBD'},
            {'name': 'Rapports d\'historique', 'code': 'scan_history', 'description': 'Consultation de l\'historique des scans et rapports'},
            {'name': 'Expertise Véhicule', 'code': 'expertise_report', 'description': 'Module d\'expertise de véhicule (Garage & Flotte)'},
            {'name': 'Gestion Rendez-vous', 'code': 'appointment_booking', 'description': 'Gestion des rendez-vous clients'},
            {'name': 'Données en Temps Réel (Live)', 'code': 'live_monitor', 'description': 'Surveillance des données du véhicule en temps réel'},
            {'name': 'Tableau de Bord Financier', 'code': 'mechanic_dashboard', 'description': 'Statistiques et bilan financier du garage'},
            {'name': 'Base de données DTC', 'code': 'dtc_library', 'description': 'Accès à la base de données des codes d\'erreurs'},
            {'name': 'Expert sur la Carte', 'code': 'register_expert', 'description': 'Apparaître comme expert sur la carte publique'},
            {'name': 'Service Remorquage', 'code': 'towing_service', 'description': 'Accès aux services de remorquage'},
            {'name': 'Interprétation IA des pannes', 'code': 'ai_interpretation', 'description': 'Analyse approfondie des codes DTC par l\'intelligence artificielle'},
            {'name': 'Messagerie Interne', 'code': 'internal_messaging', 'description': 'Communication directe entre clients et professionnels'},
            {'name': 'Nouveautés / Modules à venir', 'code': 'upcoming_modules', 'description': 'Accès aux nouveaux modules en développement'},

            # Individual / Particulier
            {'name': 'Suivi des Trajets', 'code': 'trip_history', 'description': 'Historique et analyse des trajets effectués'},
            {'name': 'Rappels d\'Entretien', 'code': 'maintenance_reminders', 'description': 'Alertes pour les prochains entretiens du véhicule'},

            # Fleet / Flotte
            {'name': 'Gestion de Flotte', 'code': 'fleet_management', 'description': 'Suivi et gestion de l\'ensemble des véhicules de la flotte'},
            {'name': 'Journal de bord de flotte', 'code': 'fleet_history', 'description': 'Historique complet des activités de la flotte'},
            {'name': 'Prédictions de Pannes (IA)', 'code': 'ai_predictive_maintenance', 'description': 'Analyse prédictive des pannes potentielles'},
        ]

        created_count = 0
        updated_count = 0

        # On cherche un plan TRIAL pour y ajouter des fonctionnalités par défaut si nécessaire
        from api.models import SubscriptionPlan
        trial_plans = SubscriptionPlan.objects.filter(tier='TRIAL')
        
        # Par exemple, on peut vouloir que le plan TRIAL ait certaines fonctionnalités de base
        basic_trial_features = ['scan_diagnostic', 'upcoming_modules', 'dtc_library']
        
        for feature_data in features_to_seed:
            feature, created = Feature.objects.update_or_create(
                code=feature_data['code'],
                defaults={
                    'name': feature_data['name'],
                    'description': feature_data['description'],
                    'is_active': True
                }
            )
            
            # Associer au plan TRIAL si c'est une feature de base
            if feature.code in basic_trial_features:
                for plan in trial_plans:
                    plan.features.add(feature)

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded features: {created_count} created, {updated_count} updated.'))
