import datetime
from django.db import models
class MaintenanceReminder(models.Model):
    """
    Rappels d'entretien spécifiques au calendrier ivoirien et à l'état du véhicule.
    """
    REMINDER_TYPES = [
        ('OIL_CHANGE', 'Vidange Moteur'),
        ('AIR_FILTER', 'Filtre à Air (Saison des poussières)'),
        ('AC_SERVICE', 'Entretien Climatisation'),
        ('TYRES', 'Vérification Pneus (Saison des pluies)'),
        ('TECHNICAL_CONTROL', 'Contrôle Technique'),
        ('INSURANCE', 'Assurance'),
        ('OBD_CHECK', 'Scan Préventif OBD'),
    ]

    vehicle = models.ForeignKey('api.Vehicle', on_delete=models.CASCADE, related_name='maintenance_reminders')
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPES)
    title = models.CharField(max_length=100)
    message = models.TextField()
    due_date = models.DateField(null=True, blank=True)
    due_mileage = models.PositiveIntegerField(null=True, blank=True)
    is_sent = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_reminder_type_display()} - {self.vehicle.license_plate}"

class RegionalEvent(models.Model):
    """
    Événements saisonniers en Côte d'Ivoire impactant l'entretien auto.
    Ex: Harmattan (poussière), Saison des pluies.
    """
    name = models.CharField(max_length=100)
    description = models.TextField()
    start_month = models.PositiveSmallIntegerField(help_text="1 pour Janvier, 12 pour Décembre")
    end_month = models.PositiveSmallIntegerField()
    recommended_checks = models.JSONField(default=list, help_text="Liste des types de rappels conseillés")

    def __str__(self):
        return self.name

from django.conf import settings
class AppNotification(models.Model):
    """
    Système de notifications génériques (Clients et Mécaniciens).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='app_notifications')
    appointment = models.ForeignKey('api.Appointment', on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, default='INFO') # ex: APPOINTMENT, ALERT, SYSTEM
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, null=True, blank=True) # Lien profond vers un écran
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    class Meta:
        ordering = ['-created_at']
