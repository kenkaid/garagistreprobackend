import datetime
from django.utils import timezone

class EngagementService:
    @staticmethod
    def generate_seasonal_reminders(vehicle):
        """
        Génère des rappels basés sur le calendrier ivoirien.
        """
        from api.models_notifications import MaintenanceReminder, RegionalEvent
        now = timezone.now()
        current_month = now.month
        
        # Récupérer les événements régionaux actifs
        events = RegionalEvent.objects.filter(
            start_month__lte=current_month,
            end_month__gte=current_month
        )
        
        reminders = []
        for event in events:
            for check_type in event.recommended_checks:
                # Éviter les doublons récents
                exists = MaintenanceReminder.objects.filter(
                    vehicle=vehicle,
                    reminder_type=check_type,
                    created_at__gt=now - datetime.timedelta(days=30)
                ).exists()
                
                if not exists:
                    title, message = EngagementService.get_content_for_type(check_type, event.name)
                    reminder = MaintenanceReminder.objects.create(
                        vehicle=vehicle,
                        reminder_type=check_type,
                        title=title,
                        message=message,
                        due_date=now.date() + datetime.timedelta(days=7)
                    )
                    reminders.append(reminder)
        return reminders

    @staticmethod
    def get_content_for_type(check_type, event_name):
        content = {
            'AIR_FILTER': (
                f"Alerte {event_name} : Filtre à air",
                f"Avec {event_name}, la poussière est intense. Vérifiez votre filtre à air pour éviter de surconsommer du carburant."
            ),
            'TYRES': (
                f"Saison des Pluies : Sécurité Pneus",
                "Les routes sont glissantes. Vérifiez l'usure de vos pneus et votre système de freinage pour une sécurité maximale."
            ),
            'AC_SERVICE': (
                "Chaleur intense : Votre clim est prête ?",
                "Les températures montent. Un entretien de la climatisation vous assurera un confort optimal pendant vos trajets."
            ),
            'OBD_CHECK': (
                "Check-up préventif",
                "C'est le moment idéal pour un scan complet de votre véhicule afin de détecter d'éventuels problèmes cachés."
            )
        }
        return content.get(check_type, ("Rappel d'entretien", "Votre véhicule nécessite une attention particulière."))

    @staticmethod
    def sync_with_mileage(vehicle, current_mileage):
        """
        Génère des rappels basés sur le kilométrage (ex: vidange tous les 5000km ou 10000km).
        """
        from api.models_notifications import MaintenanceReminder
        # Logique simplifiée : vidange tous les 7500 km par exemple
        next_oil_change = ((current_mileage // 7500) + 1) * 7500
        
        if next_oil_change - current_mileage < 500:
             # Créer un rappel de vidange si on est à moins de 500km de l'échéance
             exists = MaintenanceReminder.objects.filter(
                 vehicle=vehicle,
                 reminder_type='OIL_CHANGE',
                 is_completed=False
             ).exists()
             
             if not exists:
                 MaintenanceReminder.objects.create(
                     vehicle=vehicle,
                     reminder_type='OIL_CHANGE',
                     title="Vidange Proche",
                     message=f"Vous approchez des {next_oil_change} km. Pensez à planifier votre vidange bientôt.",
                     due_mileage=next_oil_change
                 )
