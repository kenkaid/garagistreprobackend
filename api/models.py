from django.db import models
from django.contrib.auth.models import AbstractUser
from django_quill.fields import QuillField

# === GESTION DES UTILISATEURS ET RÔLES ===
class User(AbstractUser):
    """
    Modèle utilisateur personnalisé.
    Permet de gérer les administrateurs, les mécaniciens, les propriétaires de flottes et les particuliers.
    """
    USER_TYPE_CHOICES = [
        ('MECHANIC', 'Mécanicien / Garagiste'),
        ('FLEET_OWNER', 'Propriétaire / Gestionnaire de Flotte'),
        ('INDIVIDUAL', 'Particulier / Personnel'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='MECHANIC')
    is_mechanic = models.BooleanField(default=True) # Gardé pour compatibilité
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)

    # Nouveaux champs pour centraliser les infos sans avoir besoin de profil séparé pour tous
    shop_name = models.CharField(max_length=150, blank=True, null=True, help_text="Nom du garage ou de la flotte")
    location = models.CharField(max_length=200, blank=True, null=True, help_text="Localisation géographique")
    has_used_trial = models.BooleanField(default=False, help_text="Indique si l'utilisateur a déjà utilisé sa période d'essai")

    @property
    def active_subscription(self):
        from api.models import Subscription
        from django.utils import timezone
        
        # PRIORITÉ 1: Abonnement lié via User
        sub = Subscription.objects.filter(
            user=self,
            is_active=True,
            end_date__gt=timezone.now()
        ).first()
        
        # PRIORITÉ 2: Abonnement lié via profil mécanicien
        if not sub and self.user_type == 'MECHANIC':
            try:
                sub = Subscription.objects.filter(
                    mechanic=self.mechanic_profile,
                    is_active=True,
                    end_date__gt=timezone.now()
                ).first()
            except:
                pass
        return sub

    @property
    def subscription_tier(self):
        active = self.active_subscription
        return active.plan.tier if active and active.plan else "NONE"

    @property
    def is_trial(self):
        return self.subscription_tier == 'TRIAL'

    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"

# === GESTION DES MÉCANICIENS ET FLOTTES ===
class Mechanic(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mechanic_profile')
    shop_name = models.CharField(max_length=150)
    location = models.CharField(max_length=200) # Ville/Quartier

    # Champs pour la géolocalisation et l'expertise
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    specialties = models.TextField(blank=True, null=True, help_text="Liste des spécialités (ex: Expert Ford, Électricien)")
    is_expert = models.BooleanField(default=False, help_text="Indique si le mécanicien est enregistré comme expert sur la carte")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def average_rating(self):
        from django.db.models import Avg
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0.0

    @property
    def review_count(self):
        return self.reviews.count()

    @property
    def badges(self):
        """
        Calcul dynamique des badges.
        """
        badges_list = []

        # 1. Badge "Top Fiabilité" : Bonne moyenne et nombre d'avis minimum
        if self.average_rating >= 4.5 and self.review_count >= 5:
            badges_list.append("Top Fiabilité")

        # 2. Badge "Diagnostic Rapide" : Beaucoup de scans effectués (expertise)
        # On pourrait aussi calculer la durée réelle si on avait un created_at et updated_at sur ScanSession
        scan_count = self.scansessions.count()
        if scan_count >= 20:
            badges_list.append("Diagnostic Rapide")

        # 3. Badge "Expert Local" : Très actif dans sa zone (beaucoup de rendez-vous)
        appt_count = self.appointments.filter(status='COMPLETED').count()
        if appt_count >= 10:
            badges_list.append("Expert Local")

        return badges_list

    @property
    def active_subscription(self):
        """
        Récupère l'abonnement actif.
        Priorité à l'abonnement lié directement au Mechanic, sinon celui de l'User.
        """
        from api.models import Subscription
        from django.utils import timezone
        sub = Subscription.objects.filter(
            mechanic=self,
            is_active=True,
            end_date__gt=timezone.now()
        ).first()
        
        if not sub:
            sub = self.user.active_subscription
            
        return sub

    @property
    def subscription_tier(self):
        active = self.active_subscription
        return active.plan.tier if active and active.plan else "NONE"

    @property
    def is_trial(self):
        return self.subscription_tier == 'TRIAL'

    def __str__(self):
        return f"{self.user.username} - {self.shop_name}" if self.user else f"Mecha #{self.id}"

class Review(models.Model):
    """
    Système de notation pour les mécaniciens.
    """
    mechanic = models.ForeignKey(Mechanic, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)]) # 1 à 5 étoiles
    comment = models.TextField(blank=True, null=True)

    # Lié à une session de scan ou un rendez-vous pour prouver la prestation
    scan_session = models.OneToOneField('ScanSession', on_delete=models.CASCADE, null=True, blank=True, related_name='review')
    appointment = models.OneToOneField('Appointment', on_delete=models.CASCADE, null=True, blank=True, related_name='review')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scan_session__isnull=False) | models.Q(appointment__isnull=False),
                name='review_must_have_intervention'
            )
        ]

    def __str__(self):
        return f"Note {self.rating}/5 pour {self.mechanic.shop_name} par {self.user.username}"

from api.models_notifications import MaintenanceReminder, RegionalEvent, AppNotification

# === NOTIFICATIONS ET RAPPELS ===
# (Voir api/models_notifications.py pour les modèles détaillés)
class SubscriptionPlan(models.Model):
    USER_TYPE_CHOICES = [
        ('MECHANIC', 'Mécanicien / Garagiste'),
        ('FLEET_OWNER', 'Propriétaire / Gestionnaire de Flotte'),
        ('INDIVIDUAL', 'Particulier / Personnel'),
    ]
    PLAN_TIERS = [
        ('BASIC', 'Basique (Scans simples)'),
        ('PREMIUM', 'Premium (Scans + Historique)'),
        ('ULTIMATE', 'Ultimate (Scans + Historique + IA Predictif)'),
        # Tiers spécifiques à la flotte
        ('FLEET_BASIC', 'Flotte Basique'),
        ('FLEET_PRO', 'Flotte Pro'),
        # Tiers spécifiques aux particuliers
        ('PERSONAL_BASIC', 'Personnel Basique'),
        ('PERSONAL_PREMIUM', 'Personnel Premium'),
        ('TRIAL', 'Période d\'Essai (Gratuit)'),
    ]
    name = models.CharField(max_length=50) # ex: 'Mensuel', 'Annuel', 'Essai'
    target_user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='MECHANIC',
        help_text="Type d'utilisateur ciblé par ce plan"
    )
    tier = models.CharField(max_length=20, choices=PLAN_TIERS, default='BASIC')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField()
    description = models.TextField()
    features = models.ManyToManyField('Feature', blank=True, related_name='plans')

    def __str__(self):
        return f"{self.name} ({self.tier}) - {self.get_target_user_type_display()}"

class Feature(models.Model):
    """
    Représente une fonctionnalité ou option spécifique de l'application.
    """
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, unique=True, help_text="Code unique pour identifier la fonctionnalité dans le code (ex: scan_ia)")
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, help_text="Prix additionnel potentiel ou valeur de l'option")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        verbose_name = "Fonctionnalité"
        verbose_name_plural = "Fonctionnalités"

class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions', null=True, blank=True)
    mechanic = models.ForeignKey(Mechanic, on_delete=models.CASCADE, related_name='subscriptions_old', null=True, blank=True)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('WAVE', 'Wave'),
        ('ORANGE', 'Orange Money'),
        ('MTN', 'MTN Mobile Money'),
        ('MOOV', 'Moov Money'),
    ]
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='WAVE')
    transaction_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, default='PENDING') # PENDING, SUCCESS, FAILED

# === GESTION DES VÉHICULES ===
class VehicleModel(models.Model):
    """
    Base de données de référence pour les marques et modèles.
    """
    brand = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year_start = models.IntegerField(null=True, blank=True)
    year_end = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('brand', 'model', 'year_start', 'year_end')
        ordering = ['brand', 'model']

    def __str__(self):
        return f"{self.brand} {self.model}"

class Vehicle(models.Model):
    license_plate = models.CharField(max_length=20, unique=True) # Plaque d'immatriculation
    vin = models.CharField(max_length=17, blank=True, null=True)
    chassis_number = models.CharField(max_length=50, blank=True, null=True) # Numéro de châssis
    brand = models.CharField(max_length=50) # Toyota, Hyundai, etc.
    model = models.CharField(max_length=50)
    year = models.IntegerField(null=True)
    owner_name = models.CharField(max_length=100, blank=True)
    owner_phone = models.CharField(max_length=20, blank=True)

    # Lien vers le propriétaire de flotte (si applicable)
    fleet_owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='fleet_vehicles', limit_choices_to={'user_type': 'FLEET_OWNER'})

    # Lien pour les particuliers (Propriétaire direct)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='personal_vehicles', limit_choices_to={'user_type': 'INDIVIDUAL'})

    def __str__(self):
        return f"{self.license_plate} ({self.brand} {self.model})"

# === MODULE PRÉVENTION ET TÉLÉMÉTRIE (Nouveau) ===

class IoTDevice(models.Model):
    """
    Boîtier OBD installé de manière permanente dans le véhicule.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Actif'),
        ('INACTIVE', 'Inactif'),
        ('STOLEN', 'Volé/Perdu'),
    ]
    imei = models.CharField(max_length=20, unique=True)
    serial_number = models.CharField(max_length=50, unique=True)
    vehicle = models.OneToOneField(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name='iot_device')
    installed_at = models.DateTimeField(null=True, blank=True)
    last_ping = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='INACTIVE')

    def __str__(self):
        return f"Device {self.serial_number} ({self.vehicle.license_plate if self.vehicle else 'Non assigné'})"

class TelemetryData(models.Model):
    """
    Données reçues en temps réel toutes les minutes.
    """
    device = models.ForeignKey(IoTDevice, on_delete=models.CASCADE, related_name='telemetry_history', null=True, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='telemetry_data')
    timestamp = models.DateTimeField(auto_now_add=True)

    # Énergie & Moteur
    voltage = models.FloatField(null=True, blank=True, help_text="Tension batterie (V)")
    fuel_level = models.FloatField(null=True, blank=True, help_text="Niveau carburant %")
    rpm = models.IntegerField(null=True, blank=True)
    speed = models.IntegerField(null=True, blank=True)
    engine_load = models.FloatField(null=True, blank=True)
    coolant_temp = models.IntegerField(null=True, blank=True)
    throttle = models.FloatField(null=True, blank=True, help_text="Position papillon %")

    # GPS & Accéléromètre
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    accel_x = models.FloatField(null=True, blank=True)
    accel_y = models.FloatField(null=True, blank=True)
    accel_z = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['vehicle', 'timestamp']),
        ]

    def __str__(self):
        return f"Telemetry {self.vehicle.license_plate} - {self.timestamp}"

class PredictiveAlert(models.Model):
    """
    Alertes générées par l'analyse des données de télémétrie.
    """
    ALERT_TYPES = [
        ('BATTERY', 'Batterie Faible'),
        ('ENGINE', 'Anomalie Moteur'),
        ('MAINTENANCE', 'Entretien Conseillé'),
        ('THEFT', 'Suspicion de Vol/Siphonnage'),
        ('DRIVING', 'Conduite Dangereuse'),
    ]
    SEVERITY_LEVELS = [
        ('INFO', 'Information'),
        ('WARNING', 'Avertissement'),
        ('CRITICAL', 'Critique'),
    ]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='predictive_alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='INFO')
    message = models.TextField()
    probability_score = models.FloatField(default=0.0, help_text="Confiance de l'IA (0-1)")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.vehicle.license_plate}"

# === BASE TECHNIQUE DTC (Centralisée) ===
class DTCReference(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Faible'),
        ('medium', 'Moyen'),
        ('high', 'Élevé'),
        ('critical', 'Critique'),
    ]
    code = models.CharField(max_length=10) # P0130, etc.
    brand = models.CharField(max_length=50, blank=True, null=True) # Vide pour générique, sinon 'Toyota', etc.
    description = models.TextField() # Nom technique court ou long (ex: "Sonde lambda 1, ligne 1 - panne du circuit")
    meaning = models.TextField(blank=True, null=True) # Explication vulgarisée (ex: "Le capteur d'oxygène ne fonctionne pas correctement...")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    part_image_url = models.URLField(blank=True, null=True)
    part_location = models.CharField(max_length=255, blank=True)
    est_labor_cost = models.IntegerField(default=0)
    est_part_price_local = models.IntegerField(default=0)
    est_part_price_import = models.IntegerField(default=0)

    # --- IA Prédictive Avancée (Basée sur l'historique réel) ---
    probable_causes = models.TextField(blank=True, null=True, help_text="Liste JSON des causes les plus probables")
    suggested_solutions = models.TextField(blank=True, null=True, help_text="Liste JSON des solutions les plus précises")
    symptoms = models.TextField(blank=True, null=True, help_text="Liste JSON des symptômes courants")
    tips = models.TextField(blank=True, null=True, help_text="Conseil pratique pour le mécanicien")
    warnings = models.TextField(blank=True, null=True, help_text="Avertissement sur les risques si non traité")
    last_trained_at = models.DateTimeField(null=True, blank=True)

    @property
    def probable_causes_list(self):
        import json
        try:
            return json.loads(self.probable_causes) if self.probable_causes else []
        except:
            return []

    @property
    def suggested_solutions_list(self):
        import json
        try:
            return json.loads(self.suggested_solutions) if self.suggested_solutions else []
        except:
            return []

    @property
    def symptoms_list(self):
        import json
        try:
            return json.loads(self.symptoms) if self.symptoms else []
        except:
            return []

    class Meta:
        unique_together = ('code', 'brand')
        verbose_name = "Référence DTC"
        verbose_name_plural = "Références DTC"

    def __str__(self):
        if self.brand:
            return f"{self.code} ({self.brand})"
        return f"{self.code} (Générique)"

    def save(self, *args, **kwargs):
        """
        Vulgarisation automatique des textes pour les mécaniciens ivoiriens.
        """
        import re
        import json

        def vulcanize(text):
            if not text: return text
            import re
            # 0. Suppression des mots en double
            text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text, flags=re.IGNORECASE)
            
            # On définit d'abord les cas spécifiques pour éviter les doubles remplacements
            text = re.sub(r"fuite d'air", "prise d'air (fuite d'air)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite de liquide", "fuite (ça coule)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite d'huile", "fuite d'huile (ça coule)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite de carburant", "fuite de carburant (ça coule)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite d'essence", "fuite d'essence (ça coule)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite de gasoil", "fuite de gasoil (ça coule)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite d'eau", "fuite d'eau (ça coule)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite de refroidissement", "fuite de refroidissement (ça coule)", text, flags=re.IGNORECASE)

            repls = [
                (r'défectueux', 'gâté'), (r'défaillant', 'gâté'), (r'défaillance', 'problème'),
                (r'dysfonctionnement', 'problème'), (r'endommagé', 'cassé ou gâté'),
                (r'corrodé', 'rouillé'), (r'obstruction', 'bouché'), (r'obstrué', 'bouché'),
                (r'remplacer', 'changer'), (r'inspection', 'regarder bien'),
                (r'inspecter', 'regarder bien'), (r'vérifier', 'contrôler'), (r'contrôle', 'contrôle'),
                (r'nettoyage', 'nettoyer'), (r'nettoyer', 'nettoyer'), (r'ajustement', 'régler'),
                (r'ajuster', 'régler'), (r'réparation', 'réparer'), (r'réparer', 'réparer'),
                (r'faisceau', 'fils de courant'), (r'câblage', 'fils de courant'), (r'connecteur', 'fiche'),
                (r'court-circuit', 'masse (court-circuit)'), (r'circuit ouvert', 'fil coupé'),
                (r'alimentation', 'courant'), (r'tension', 'voltage'), (r'pression', 'pression'),
                (r'capteur', 'capteur (sensor)'), (r'sonde', 'sonde (capteur)'),
                (r'consommation', 'boit le carburant'), (r'perte de puissance', "la voiture n'a plus la force"),
                (r'ralenti instable', 'le moteur tremble au repos'), (r'calage', "le moteur s'éteint"),
                (r'calculateur', 'ordinateur de bord (calculateur)'), (r'insuffisant', 'pas assez'),
                (r'solution', 'ce qu\'il faut faire'), (r'cause', 'pourquoi ça arrive'),
                (r'dû à', 'à cause de'), (r'cause probable', 'ce qui peut envoyer ça')
            ]
            for old, new in repls:
                # Utilisation de frontières de mots si possible, sinon simple re.sub
                pattern = r'\b' + old + r'\b' if not old.startswith(r'(') else old
                text = re.sub(pattern, new, text, flags=re.IGNORECASE)
            
            # Nettoyage final des répétitions
            text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text, flags=re.IGNORECASE)
            return text

        if self.meaning: self.meaning = vulcanize(self.meaning)
        if self.tips: self.tips = vulcanize(self.tips)
        if self.warnings: self.warnings = warnings = vulcanize(self.warnings)

        # Traitement des listes JSON
        for field in ['probable_causes', 'suggested_solutions', 'symptoms']:
            val = getattr(self, field)
            if val:
                try:
                    data = json.loads(val)
                    if isinstance(data, list):
                        new_data = [vulcanize(item) for item in data]
                        setattr(self, field, json.dumps(new_data))
                except: pass

        super().save(*args, **kwargs)

# === HISTORIQUE DES DIAGNOSTICS ===
class ScanSessionDTC(models.Model):
    """
    Modèle intermédiaire pour lier un DTC à une session de scan avec son statut.
    """
    STATUS_CHOICES = [
        ('confirmed', 'Confirmé'),
        ('pending', 'En attente (non confirmé)'),
        ('permanent', 'Permanent'),
    ]
    scan_session = models.ForeignKey('ScanSession', on_delete=models.CASCADE, related_name='scan_dtcs')
    dtc = models.ForeignKey(DTCReference, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')

    class Meta:
        unique_together = ('scan_session', 'dtc')

    def __str__(self):
        return f"{self.dtc.code} ({self.status}) in {self.scan_session}"

class ScanSession(models.Model):
    mechanic = models.ForeignKey(Mechanic, on_delete=models.CASCADE, null=True, blank=True, related_name='scansessions')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    found_dtcs = models.ManyToManyField(DTCReference, through=ScanSessionDTC)

    # --- Expertise Avancée (Kilométrage) ---
    mileage_ecu = models.PositiveIntegerField(null=True, blank=True, help_text="Kilométrage lu depuis le calculateur moteur")
    mileage_abs = models.PositiveIntegerField(null=True, blank=True, help_text="Kilométrage lu depuis le module ABS")
    mileage_dashboard = models.PositiveIntegerField(null=True, blank=True, help_text="Kilométrage affiché sur le tableau de bord")

    # --- Gestion Dynamique des Coûts (Bilan) ---
    actual_labor_cost = models.IntegerField(default=0) # Coût main d'oeuvre facturé
    actual_parts_cost = models.IntegerField(default=0) # Coût pièces facturé
    is_completed = models.BooleanField(default=False)  # Si le travail est terminé et payé

    # --- Type de scan ---
    SCAN_TYPES = [
        ('DIAGNOSTIC', 'Diagnostic initial'),
        ('VERIFICATION', 'Vérification après effacement'),
        ('EXPERT', 'Expertise d\'occasion'),
    ]
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPES, default='DIAGNOSTIC')

    @property
    def health_score(self):
        """
        Calcule un score de santé de 0 à 100 pour le véhicule.
        """
        score = 100

        # 1. Fraude au kilométrage
        discrepancy = self.mileage_discrepancy
        if discrepancy > 5000:
            score -= 50
        elif discrepancy > 1000:
            score -= 20

        # 2. Sécurité (Airbags/Crash Data)
        try:
            safety = self.safety_check
            if safety.crash_data_present or safety.is_airbag_deployed:
                score -= 100 # Directement à 0 ou négatif pour signaler un danger majeur
        except SafetyCheck.DoesNotExist:
            pass

        # 3. Codes défauts (DTC)
        dtcs = self.found_dtcs.all()
        for dtc in dtcs:
            if dtc.severity == 'critical':
                score -= 30
            elif dtc.severity == 'high':
                score -= 15
            elif dtc.severity == 'medium':
                score -= 5

        return max(0, score)

    @property
    def buying_recommendation(self):
        """
        Donne une recommandation d'achat basée sur le score de santé.
        """
        score = self.health_score
        if score >= 85:
            return "ACHETER"
        elif score >= 60:
            return "NÉGOCIER"
        else:
            return "FUIR"

    def __str__(self):
        return f"Scan {self.vehicle.license_plate} - {self.date.strftime('%d/%m/%Y')}"

    @property
    def mileage_discrepancy(self):
        """Calcule l'écart maximal de kilométrage entre les différents modules."""
        mileages = [m for m in [self.mileage_ecu, self.mileage_abs, self.mileage_dashboard] if m is not None]
        if len(mileages) < 2:
            return 0
        return max(mileages) - min(mileages)

    @property
    def total_cost(self):
        return self.actual_labor_cost + self.actual_parts_cost

# === CONFIGURATION GLOBALE ===
class GlobalSettings(models.Model):
    is_test_mode = models.BooleanField(default=True, verbose_name="Mode Test (Données simulées)")
    server_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP du Serveur", help_text="L'adresse IP publique du serveur VPS pour l'accès API")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuration Globale"
        verbose_name_plural = "Configurations Globales"

    def __str__(self):
        return "Configuration du Système"

    def save(self, *args, **kwargs):
        # S'assurer qu'il n'y a qu'une seule instance
        if not self.pk and GlobalSettings.objects.exists():
            return None
        return super(GlobalSettings, self).save(*args, **kwargs)

# === SÉCURITÉ ET EXPERTISE AVANCÉE ===
class SafetyCheck(models.Model):
    """
    Rapport de sécurité spécifique aux airbags et systèmes de retenue (SRS).
    """
    scan_session = models.OneToOneField(ScanSession, on_delete=models.CASCADE, related_name='safety_check')
    is_airbag_deployed = models.BooleanField(default=False)
    crash_data_present = models.BooleanField(default=False)
    srs_module_status = models.CharField(max_length=100, default='OK') # OK, ERR, NO_COMM
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vérification de Sécurité"
        verbose_name_plural = "Vérifications de Sécurité"

    def __str__(self):
        return f"Sécurité {self.scan_session.vehicle.license_plate}"

# === CONTENU DE L'ÉCRAN D'ACCUEIL ===
class WelcomeContent(models.Model):
    """
    Contenu à afficher sur l'écran d'accueil/onboarding de l'application.
    Permet de présenter l'application avec des images, vidéos et texte.
    """
    title = models.CharField(max_length=200, verbose_name="Titre")
    description = models.TextField(verbose_name="Description")
    image = models.ImageField(upload_to='welcome/', null=True, blank=True, verbose_name="Image de présentation")
    video_url = models.URLField(null=True, blank=True, verbose_name="URL de la vidéo (YouTube/Vimeo/etc.)")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contenu d'accueil"
        verbose_name_plural = "Contenus d'accueil"
        ordering = ['order']

    def __str__(self):
        return self.title

# === MODULES À VENIR ===
class Appointment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('CONFIRMED', 'Confirmé'),
        ('CANCELLED', 'Annulé'),
        ('COMPLETED', 'Terminé'),
    ]
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments')
    mechanic = models.ForeignKey(Mechanic, on_delete=models.CASCADE, related_name='appointments')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True)
    appointment_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rendez-vous"
        verbose_name_plural = "Rendez-vous"
        ordering = ['-appointment_date']

    def __str__(self):
        return f"RDV {self.client.get_full_name()} - {self.mechanic.shop_name} ({self.appointment_date})"

class UpcomingModule(models.Model):
    name = models.CharField(max_length=150, verbose_name="Nom du module")
    description = QuillField(verbose_name="Description détaillée")
    expected_release_date = models.DateField(verbose_name="Date de sortie prévue")
    applicable_plans = models.ManyToManyField(SubscriptionPlan, blank=True, verbose_name="Plans concernés")
    is_active = models.BooleanField(default=True, verbose_name="Afficher sur l'app")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Module à venir"
        verbose_name_plural = "Modules à venir"
        ordering = ['expected_release_date']

    def __str__(self):
        return self.name

# === SYSTÈME DRIVE-TO-STORE (Magasins de pièces) ===

class SparePartStore(models.Model):
    """
    Magasin de pièces détachées partenaire.
    """
    name = models.CharField(max_length=200, verbose_name="Nom du magasin")
    location_name = models.CharField(max_length=255, verbose_name="Quartier/Ville (ex: Adjamé)")
    address = models.TextField(blank=True, verbose_name="Adresse complète")
    phone = models.CharField(max_length=50, blank=True, verbose_name="Téléphone")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    logo = models.ImageField(upload_to='stores/', null=True, blank=True)

    class Meta:
        verbose_name = "Magasin de pièces"
        verbose_name_plural = "Magasins de pièces"

    def __str__(self):
        return f"{self.name} ({self.location_name})"

class SparePartCategory(models.Model):
    """
    Catégorie générique de pièce liée à des codes DTC.
    Fait le pont entre la technique (DTC) et le commerce (SparePart).
    """
    name = models.CharField(max_length=200, verbose_name="Nom de la catégorie (ex: Vanne EGR)")
    description = models.TextField(blank=True)
    compatible_dtcs = models.ManyToManyField('DTCReference', related_name='spare_part_categories', blank=True)
    image = models.ImageField(upload_to='part_categories/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nomenclature / Catégorie de pièce"
        verbose_name_plural = "Nomenclature / Catégories de pièces"

    def __str__(self):
        return self.name

class SparePart(models.Model):
    """
    Pièce détachée disponible dans un magasin.
    """
    store = models.ForeignKey(SparePartStore, on_delete=models.CASCADE, related_name='parts')
    category = models.ForeignKey(SparePartCategory, on_delete=models.CASCADE, related_name='instances', null=True, blank=True)
    name = models.CharField(max_length=200, verbose_name="Nom précis (ex: Vanne EGR Toyota 2010)")
    brand = models.CharField(max_length=100, blank=True, verbose_name="Marque de la pièce (ex: Bosch)")
    price = models.IntegerField(verbose_name="Prix (FCFA)")
    stock_status = models.CharField(max_length=20, choices=[('IN_STOCK', 'En stock'), ('OUT_OF_STOCK', 'Rupture'), ('ON_ORDER', 'Sur commande')], default='IN_STOCK')

    # Liaison supprimée au profit de la catégorie
    # compatible_dtcs = models.ManyToManyField(DTCReference, related_name='recommended_parts', blank=True)

    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='parts/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pièce en stock"
        verbose_name_plural = "Pièces en stock"

    def __str__(self):
        return f"{self.name} - {self.store.name} ({self.price} FCFA)"

class ChatMessage(models.Model):
    """
    Système de messagerie entre clients et mécaniciens.
    Généralement lié à un rendez-vous (Appointment).
    """
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message de chat"
        verbose_name_plural = "Messages de chat"
        ordering = ['created_at']

    def __str__(self):
        return f"De {self.sender.username} à {self.receiver.username} ({self.created_at})"

# === INTELLIGENCE ANALYTIQUE — BASELINE & HISTORIQUE ML ===

class VehicleBaseline(models.Model):
    """
    Valeurs "normales" apprises pour un véhicule précis.
    Calculées automatiquement à partir des sessions live.
    Permet de détecter des écarts par rapport au comportement habituel du véhicule.
    """
    vehicle = models.OneToOneField(Vehicle, on_delete=models.CASCADE, related_name='baseline')
    # Moyennes apprises (valeur centrale normale)
    avg_rpm = models.FloatField(null=True, blank=True)
    avg_coolant_temp = models.FloatField(null=True, blank=True)
    avg_oil_temp = models.FloatField(null=True, blank=True)
    avg_engine_load = models.FloatField(null=True, blank=True)
    avg_voltage = models.FloatField(null=True, blank=True)
    avg_fuel_trim_st = models.FloatField(null=True, blank=True)
    avg_fuel_trim_lt = models.FloatField(null=True, blank=True)
    avg_map_pressure = models.FloatField(null=True, blank=True)
    avg_iat = models.FloatField(null=True, blank=True)
    avg_throttle = models.FloatField(null=True, blank=True)
    # Écarts-types appris (tolérance normale)
    std_rpm = models.FloatField(null=True, blank=True)
    std_coolant_temp = models.FloatField(null=True, blank=True)
    std_engine_load = models.FloatField(null=True, blank=True)
    std_voltage = models.FloatField(null=True, blank=True)
    # Métadonnées d'apprentissage
    sample_count = models.IntegerField(default=0, help_text="Nombre de lectures utilisées pour calculer la baseline")
    last_updated = models.DateTimeField(auto_now=True)
    is_mature = models.BooleanField(default=False, help_text="True si >= 500 lectures (baseline fiable)")

    class Meta:
        verbose_name = "Baseline véhicule"
        verbose_name_plural = "Baselines véhicules"

    def __str__(self):
        return f"Baseline {self.vehicle.license_plate} ({self.sample_count} lectures)"


class VehiclePIDHistory(models.Model):
    """
    Historique des lectures PID pour entraînement du modèle ML.
    Chaque enregistrement = un snapshot complet de tous les PIDs à un instant T.
    Labelisé 'anomaly' si une anomalie IA a été détectée à ce moment.
    """
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='pid_history')
    timestamp = models.DateTimeField(auto_now_add=True)
    # PIDs principaux
    rpm = models.FloatField(null=True, blank=True)
    coolant_temp = models.FloatField(null=True, blank=True)
    oil_temp = models.FloatField(null=True, blank=True)
    engine_load = models.FloatField(null=True, blank=True)
    voltage = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    throttle = models.FloatField(null=True, blank=True)
    fuel_level = models.FloatField(null=True, blank=True)
    fuel_trim_st = models.FloatField(null=True, blank=True)
    fuel_trim_lt = models.FloatField(null=True, blank=True)
    map_pressure = models.FloatField(null=True, blank=True)
    iat = models.FloatField(null=True, blank=True)
    o2_upstream = models.FloatField(null=True, blank=True)
    o2_downstream = models.FloatField(null=True, blank=True)
    maf = models.FloatField(null=True, blank=True)
    # Label pour entraînement ML
    has_anomaly = models.BooleanField(default=False, help_text="True si une anomalie IA a été détectée")
    anomaly_severity = models.CharField(max_length=20, blank=True, help_text="critical/high/medium/low")
    anomaly_codes = models.JSONField(default=list, help_text="Liste des codes DTC virtuels détectés")

    class Meta:
        verbose_name = "Historique PID"
        verbose_name_plural = "Historiques PID"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['vehicle', 'timestamp']),
            models.Index(fields=['vehicle', 'has_anomaly']),
        ]

    def __str__(self):
        status = "⚠️" if self.has_anomaly else "✓"
        return f"{status} {self.vehicle.license_plate} — {self.timestamp.strftime('%d/%m/%Y %H:%M')}"


class VehicleMLModel(models.Model):
    """
    Modèle ML entraîné pour un véhicule ou une famille de véhicules.
    Stocke le modèle sérialisé (pickle) et ses métriques de performance.
    """
    SCOPE_CHOICES = [
        ('VEHICLE', 'Véhicule spécifique'),
        ('BRAND_MODEL', 'Marque + Modèle'),
        ('GLOBAL', 'Modèle global'),
    ]
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='GLOBAL')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, null=True, blank=True, related_name='ml_models')
    brand = models.CharField(max_length=50, blank=True, help_text="Marque si scope=BRAND_MODEL")
    model_name = models.CharField(max_length=50, blank=True, help_text="Modèle si scope=BRAND_MODEL")
    # Modèle sérialisé
    model_file = models.FileField(upload_to='ml_models/', null=True, blank=True)
    algorithm = models.CharField(max_length=50, default='RandomForest')
    # Métriques
    accuracy = models.FloatField(null=True, blank=True)
    precision = models.FloatField(null=True, blank=True)
    recall = models.FloatField(null=True, blank=True)
    f1_score = models.FloatField(null=True, blank=True)
    training_samples = models.IntegerField(default=0)
    is_active = models.BooleanField(default=False, help_text="Activer pour utilisation en production")
    trained_at = models.DateTimeField(auto_now_add=True)
    version = models.CharField(max_length=20, default='1.0')

    class Meta:
        verbose_name = "Modèle ML"
        verbose_name_plural = "Modèles ML"
        ordering = ['-trained_at']

    def __str__(self):
        scope_label = self.vehicle.license_plate if self.vehicle else self.brand or 'Global'
        return f"ML {self.algorithm} — {scope_label} v{self.version} ({'actif' if self.is_active else 'inactif'})"


class TowTruck(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nom / Entreprise")
    phone = models.CharField(max_length=20, verbose_name="Numéro de téléphone")
    city = models.CharField(max_length=100, verbose_name="Ville")
    district = models.CharField(max_length=100, verbose_name="Quartier", blank=True, null=True)
    is_available = models.BooleanField(default=True, verbose_name="Disponible")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Remorqueur"
        verbose_name_plural = "🚀 Remorqueurs"
        ordering = ['city', 'district']

    def __str__(self):
        return f"{self.name} ({self.city})"
