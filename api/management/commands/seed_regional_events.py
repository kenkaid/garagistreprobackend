from django.core.management.base import BaseCommand
from api.models_notifications import RegionalEvent

class Command(BaseCommand):
    help = 'Initialise les événements saisonniers spécifiques à la Côte d\'Ivoire'

    def handle(self, *args, **options):
        events = [
            {
                'name': 'Harmattan (Saison des poussières)',
                'description': 'Période de vent sec et poussiéreux venant du Sahara.',
                'start_month': 12,
                'end_month': 2,
                'recommended_checks': ['AIR_FILTER', 'AC_SERVICE']
            },
            {
                'name': 'Grande Saison des Pluies',
                'description': 'Pluies intenses sur tout le territoire, risques d\'aquaplaning.',
                'start_month': 5,
                'end_month': 7,
                'recommended_checks': ['TYRES', 'OBD_CHECK']
            },
            {
                'name': 'Petite Saison des Pluies',
                'description': 'Reprise des précipitations modérées.',
                'start_month': 10,
                'end_month': 11,
                'recommended_checks': ['TYRES']
            },
            {
                'name': 'Période de forte chaleur',
                'description': 'Températures élevées impactant les moteurs et la clim.',
                'start_month': 3,
                'end_month': 4,
                'recommended_checks': ['AC_SERVICE', 'OBD_CHECK']
            }
        ]

        for event_data in events:
            event, created = RegionalEvent.objects.update_or_create(
                name=event_data['name'],
                defaults=event_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Créé : {event.name}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Mis à jour : {event.name}"))
