from rest_framework import serializers
from rest_framework.authtoken.models import Token
from api.models import (
    User, Mechanic, Vehicle, DTCReference, ScanSession, ScanSessionDTC, SubscriptionPlan,
    Subscription, VehicleModel, Payment, UpcomingModule, WelcomeContent,
    SafetyCheck, IoTDevice, TelemetryData, PredictiveAlert,
    MaintenanceReminder, RegionalEvent, Appointment, AppNotification, ChatMessage,
    Review, SparePartStore, SparePart
)

class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.ReadOnlyField(source='sender.get_full_name')
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'appointment', 'sender', 'sender_name', 'receiver', 'message', 'is_read', 'is_me', 'created_at']
        read_only_fields = ['sender', 'created_at']

    def get_is_me(self, obj):
        request = self.context.get('request')
        if request:
            return obj.sender == request.user
        return False

class AppointmentSerializer(serializers.ModelSerializer):
    client_name = serializers.ReadOnlyField(source='client.get_full_name')
    mechanic_name = serializers.ReadOnlyField(source='mechanic.shop_name')
    vehicle_name = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = '__all__'
        read_only_fields = ['client', 'created_at', 'updated_at']

    def get_vehicle_name(self, obj):
        if obj.vehicle:
            return f"{obj.vehicle.brand} {obj.vehicle.model} ({obj.vehicle.license_plate})"
        if obj.notes and "véhicule" in obj.notes.lower():
            return obj.notes
        return "Véhicule non spécifié"

class MaintenanceReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceReminder
        fields = '__all__'

class RegionalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegionalEvent
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    active_subscription = serializers.SerializerMethodField()
    subscription_tier = serializers.CharField(read_only=True)
    is_trial = serializers.SerializerMethodField()
    trial_days_remaining = serializers.SerializerMethodField()
    has_vehicle = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'phone',
            'is_mechanic', 'user_type', 'shop_name', 'location',
            'active_subscription', 'subscription_tier', 'is_trial', 'trial_days_remaining', 'has_vehicle'
        ]

    def get_active_subscription(self, obj):
        sub = obj.active_subscription
        if sub:
            return SubscriptionSerializer(sub, context=self.context).data
        return None

    def get_is_trial(self, obj):
        sub = obj.active_subscription
        return sub.plan.tier == 'TRIAL' if sub and sub.plan else False

    def get_trial_days_remaining(self, obj):
        sub = obj.active_subscription
        if sub and sub.plan and sub.plan.tier == 'TRIAL':
            from django.utils import timezone
            import math
            remaining = sub.end_date - timezone.now()
            # On utilise ceil pour que s'il reste 13j et 23h, on affiche 14j
            total_seconds = remaining.total_seconds()
            if total_seconds > 0:
                days = math.ceil(total_seconds / 86400)
                # Si l'utilisateur vient de s'abonner (ex: 14 jours), on s'assure de ne pas afficher 13
                # à cause d'une micro-seconde de décalage.
                # On compare avec la durée du plan si c'est très proche
                plan_duration = sub.plan.duration_days
                if abs(days - plan_duration) <= 1 and total_seconds > (plan_duration - 1) * 86400:
                    return plan_duration
                return days
        return 0

    def get_has_vehicle(self, obj):
        if obj.user_type == 'INDIVIDUAL':
            return obj.personal_vehicles.exists()
        if obj.user_type == 'FLEET_OWNER':
            return obj.fleet_vehicles.exists()
        return False

class VehicleModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleModel
        fields = '__all__'

class RegisterSerializer(serializers.ModelSerializer):
    shop_name = serializers.CharField(write_only=True, required=False)
    location = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, min_length=8)
    user_type = serializers.ChoiceField(choices=User.USER_TYPE_CHOICES, default='MECHANIC')

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'phone', 'first_name', 'last_name', 'shop_name', 'location', 'user_type']

    def create(self, validated_data):
        shop_name = validated_data.pop('shop_name', None)
        location = validated_data.pop('location', None)
        password = validated_data.pop('password')
        user_type = validated_data.get('user_type', 'MECHANIC')

        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        # On synchronise is_mechanic pour la compatibilité
        user.is_mechanic = (user_type == 'MECHANIC')

        # Initialisation du shop_name et location
        if user_type == 'MECHANIC':
            user.shop_name = shop_name or f"Garage de {user.first_name or user.username}"
            user.location = location or "Non précisée"
        elif user_type == 'FLEET_OWNER':
            user.shop_name = shop_name or f"Flotte de {user.first_name or user.username}"
            user.location = location or "Non précisée"
        else:
            user.shop_name = shop_name
            user.location = location

        user.save()

        # Création automatique du profil mécanicien si c'est un mécanicien
        if user_type == 'MECHANIC':
            Mechanic.objects.create(
                user=user,
                shop_name=user.shop_name,
                location=user.location
            )

        # Activation automatique de la période d'essai pour tous les types d'utilisateurs
        from api.services.subscriptions import SubscriptionService
        SubscriptionService.activate_trial(user)

        return user

class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Review
        fields = ['id', 'mechanic', 'user', 'user_name', 'rating', 'comment', 'scan_session', 'appointment', 'created_at']
        read_only_fields = ['user', 'created_at']

class MechanicSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', required=False, allow_blank=True)
    last_name = serializers.CharField(source='user.last_name', required=False, allow_blank=True)
    email = serializers.CharField(source='user.email', required=False, allow_blank=True)
    phone = serializers.CharField(source='user.phone', required=False, allow_blank=True)
    subscription_tier = serializers.CharField(read_only=True)
    is_trial = serializers.SerializerMethodField()
    trial_days_remaining = serializers.SerializerMethodField()
    active_subscription = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    badges = serializers.ReadOnlyField()

    class Meta:
        model = Mechanic
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'phone',
            'shop_name', 'location', 'latitude', 'longitude', 'specialties', 'is_expert',
            'is_active', 'created_at',
            'subscription_tier', 'is_trial', 'trial_days_remaining', 'active_subscription',
            'average_rating', 'review_count', 'badges'
        ]

    def get_is_trial(self, obj):
        sub = obj.user.active_subscription
        return sub.plan.tier == 'TRIAL' if sub and sub.plan else False

    def get_trial_days_remaining(self, obj):
        sub = obj.user.active_subscription
        if sub and sub.plan and sub.plan.tier == 'TRIAL':
            from django.utils import timezone
            import math
            remaining = sub.end_date - timezone.now()
            total_seconds = remaining.total_seconds()
            if total_seconds > 0:
                days = math.ceil(total_seconds / 86400)
                plan_duration = sub.plan.duration_days
                if abs(days - plan_duration) <= 1 and total_seconds > (plan_duration - 1) * 86400:
                    return plan_duration
                return days
        return 0

    def get_active_subscription(self, obj):
        sub = obj.user.active_subscription
        if sub:
            return SubscriptionSerializer(sub, context=self.context).data
        return None

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        user = instance.user

        # Debug: pour voir ce qui arrive (utile en développement)
        # print(f"DEBUG validated_data: {validated_data}")
        # print(f"DEBUG user_data: {user_data}")

        # Les champs avec source='user.field' se retrouvent dans validated_data['user']
        # s'ils ont été validés correctement par DRF.

        user_updated = False

        # 1. Mise à jour des champs utilisateur (first_name, last_name, etc.)
        for attr, value in user_data.items():
            setattr(user, attr, value)
            user_updated = True

        # 2. Synchroniser aussi shop_name et location sur User
        # Ces champs sont à la racine de validated_data car ils appartiennent au modèle Mechanic
        if 'shop_name' in validated_data:
            user.shop_name = validated_data['shop_name']
            user_updated = True
        if 'location' in validated_data:
            user.location = validated_data['location']
            user_updated = True

        if user_updated:
            user.save()

        # 3. Mise à jour des champs du modèle Mechanic
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance

class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'

    def validate(self, data):
        # On ignore la validation des années lors de la mise à jour si les champs sont partiels
        brand = data.get('brand') or (self.instance.brand if self.instance else None)
        model = data.get('model') or (self.instance.model if self.instance else None)
        year = data.get('year') or (self.instance.year if self.instance else None)

        if brand and model and year:
            # Recherche d'un modèle correspondant dans la base de référence
            # On utilise icontains pour être souple sur la casse et les espaces
            vehicle_model = VehicleModel.objects.filter(
                brand__iexact=brand,
                model__iexact=model
            ).first()

            if vehicle_model:
                if vehicle_model.year_start and year < vehicle_model.year_start:
                    raise serializers.ValidationError({
                        "year": f"L'année {year} est trop ancienne pour ce modèle. L'année minimale est {vehicle_model.year_start}."
                    })
                if vehicle_model.year_end and year > vehicle_model.year_end:
                    raise serializers.ValidationError({
                        "year": f"L'année {year} est trop récente pour ce modèle. L'année maximale est {vehicle_model.year_end}."
                    })

        return data

class SparePartStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = SparePartStore
        fields = ['id', 'name', 'location_name', 'address', 'phone', 'latitude', 'longitude', 'logo']

class SparePartSerializer(serializers.ModelSerializer):
    store_details = SparePartStoreSerializer(source='store', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = SparePart
        fields = ['id', 'store', 'store_details', 'category', 'category_name', 'name', 'brand', 'price', 'stock_status', 'description', 'image']

class DTCReferenceSerializer(serializers.ModelSerializer):
    # Mapping pour la compatibilité frontend (camelCase)
    possibleCauses = serializers.JSONField(source='probable_causes_list', read_only=True)
    suggestedFixes = serializers.JSONField(source='suggested_solutions_list', read_only=True)
    commonSymptoms = serializers.JSONField(source='symptoms_list', read_only=True)
    localPartPrice = serializers.IntegerField(source='est_part_price_local', read_only=True)
    importPartPrice = serializers.IntegerField(source='est_part_price_import', read_only=True)
    estimatedLaborCost = serializers.IntegerField(source='est_labor_cost', read_only=True)
    partImageUrl = serializers.URLField(source='part_image_url', read_only=True)
    partLocation = serializers.CharField(source='part_location', read_only=True)
    recommended_spare_parts = serializers.SerializerMethodField()

    class Meta:
        model = DTCReference
        fields = [
            'id', 'code', 'brand', 'description', 'meaning', 'severity',
            'part_image_url', 'partImageUrl',
            'part_location', 'partLocation',
            'est_labor_cost', 'estimatedLaborCost',
            'est_part_price_local', 'localPartPrice',
            'est_part_price_import', 'importPartPrice',
            'probable_causes', 'possibleCauses',
            'suggested_solutions', 'suggestedFixes',
            'symptoms', 'commonSymptoms',
            'tips', 'warnings',
            'last_trained_at', 'recommended_spare_parts'
        ]

    def get_recommended_spare_parts(self, obj):
        # 1. Identifier les catégories de pièces liées à ce code DTC
        # On cherche via les catégories qui contiennent ce DTC
        from api.models import SparePartCategory, SparePart
        
        categories = SparePartCategory.objects.filter(compatible_dtcs=obj)
        
        # Fallback sur le DTC générique si nécessaire
        if not categories.exists() and obj.brand:
            generic_dtc = DTCReference.objects.filter(code=obj.code, brand__isnull=True).first()
            if generic_dtc:
                categories = SparePartCategory.objects.filter(compatible_dtcs=generic_dtc)
        
        if not categories.exists():
            return []

        # 2. Récupérer les pièces (instances) appartenant à ces catégories
        parts = SparePart.objects.filter(category__in=categories)[:5]
        
        return SparePartSerializer(parts, many=True).data

class SafetyCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyCheck
        fields = ['id', 'is_airbag_deployed', 'crash_data_present', 'srs_module_status', 'notes', 'created_at']

class ScanSessionDTCSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source='dtc.code', read_only=True)
    description = serializers.CharField(source='dtc.description', read_only=True)
    meaning = serializers.CharField(source='dtc.meaning', read_only=True)
    severity = serializers.CharField(source='dtc.severity', read_only=True)
    dtc_details = DTCReferenceSerializer(source='dtc', read_only=True)
    
    # Direct access for DTCCard
    possibleCauses = serializers.JSONField(source='dtc.probable_causes_list', read_only=True)
    suggestedFixes = serializers.JSONField(source='dtc.suggested_solutions_list', read_only=True)
    commonSymptoms = serializers.JSONField(source='dtc.symptoms_list', read_only=True)
    recommended_spare_parts = serializers.SerializerMethodField()

    class Meta:
        model = ScanSessionDTC
        fields = [
            'id', 'dtc', 'code', 'description', 'meaning', 'severity', 'status', 'dtc_details',
            'possibleCauses', 'suggestedFixes', 'commonSymptoms', 'recommended_spare_parts'
        ]

    def get_recommended_spare_parts(self, obj):
        if not obj.dtc:
            return []
        return DTCReferenceSerializer().get_recommended_spare_parts(obj.dtc)

class ScanSessionSerializer(serializers.ModelSerializer):
    vehicle = VehicleSerializer(read_only=True)
    mechanic_details = MechanicSerializer(source='mechanic', read_only=True)
    user_details = serializers.SerializerMethodField() # Adapté pour gérer Mechanic ou User (Individual)
    found_dtcs = DTCReferenceSerializer(many=True, read_only=True)
    scan_dtcs = ScanSessionDTCSerializer(many=True, read_only=True)
    total_cost = serializers.IntegerField(read_only=True)
    ai_predictions = serializers.SerializerMethodField()
    safety_check = SafetyCheckSerializer(read_only=True)
    mileage_discrepancy = serializers.IntegerField(read_only=True)
    health_score = serializers.IntegerField(read_only=True)
    buying_recommendation = serializers.CharField(read_only=True)

    class Meta:
        model = ScanSession
        fields = [
            'id', 'mechanic', 'mechanic_details', 'user_details', 'vehicle', 'date', 'notes',
            'found_dtcs', 'scan_dtcs', 'actual_labor_cost', 'actual_parts_cost', 'is_completed',
            'total_cost', 'ai_predictions', 'safety_check',
            'mileage_ecu', 'mileage_abs', 'mileage_dashboard', 'mileage_discrepancy',
            'health_score', 'buying_recommendation',
            'scan_type'
        ]

    def get_user_details(self, obj):
        if obj.mechanic:
            return MechanicSerializer(obj.mechanic, context=self.context).data

        # Si pas de mécanicien, on renvoie les infos du propriétaire du véhicule (cas particulier)
        if obj.vehicle and obj.vehicle.owner:
            return UserSerializer(obj.vehicle.owner, context=self.context).data
        return None

    def get_ai_predictions(self, obj):
        from api.services.ai_service import DTCModelAI
        # Utiliser les codes de scan_dtcs qui contiennent aussi le statut
        dtc_codes = [sd.dtc.code for sd in obj.scan_dtcs.all()]
        if not dtc_codes:
            # Fallback sur found_dtcs si scan_dtcs est vide (compatibilité ascendante)
            dtc_codes = [dtc.code for dtc in obj.found_dtcs.all()]
            
        vehicle_info = {
            'brand': obj.vehicle.brand,
            'model': obj.vehicle.model,
            'year': obj.vehicle.year
        }
        return DTCModelAI.predict_advanced(dtc_codes, vehicle_info)

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'

class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    payment = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ['id', 'plan', 'start_date', 'end_date', 'is_active', 'payment']

    def get_payment(self, obj):
        payment = Payment.objects.filter(subscription=obj).first()
        if payment:
            return {
                'amount': payment.amount,
                'payment_method': payment.payment_method,
                'transaction_id': payment.transaction_id,
                'status': payment.status,
                'date': payment.payment_date
            }
        return None

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("L'ancien mot de passe est incorrect.")
        return value


def get_description_html(obj):
    description = obj.description
    if isinstance(description, dict):
        return description.get('html', '')
    if hasattr(description, 'html'):
        return description.html
    return str(description)


class UpcomingModuleSerializer(serializers.ModelSerializer):
    applicablePlans = SubscriptionPlanSerializer(source='applicable_plans', many=True, read_only=True)
    expectedReleaseDate = serializers.DateField(source='expected_release_date', read_only=True)
    description_html = serializers.SerializerMethodField()

    class Meta:
        model = UpcomingModule
        fields = ['id', 'name', 'description_html', 'expected_release_date', 'expectedReleaseDate', 'applicable_plans', 'applicablePlans', 'is_active', 'created_at']


class WelcomeContentSerializer(serializers.ModelSerializer):
    imageUrl = serializers.SerializerMethodField()
    videoUrl = serializers.URLField(source='video_url', read_only=True)

    class Meta:
        model = WelcomeContent
        fields = ['id', 'title', 'description', 'image', 'imageUrl', 'video_url', 'videoUrl', 'order', 'is_active']

    def get_imageUrl(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

# === NOUVEAUX SERIALIZERS POUR LA TÉLÉMÉTRIE ===

class IoTDeviceSerializer(serializers.ModelSerializer):
    vehicle_details = VehicleSerializer(source='vehicle', read_only=True)

    class Meta:
        model = IoTDevice
        fields = '__all__'

class TelemetryDataSerializer(serializers.ModelSerializer):
    voltage = serializers.FloatField(required=False, allow_null=True)
    fuel_level = serializers.FloatField(required=False, allow_null=True)
    throttle = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = TelemetryData
        fields = '__all__'

class AppNotificationSerializer(serializers.ModelSerializer):
    client_phone = serializers.SerializerMethodField()
    vehicle_details = serializers.SerializerMethodField()
    appointment_id = serializers.IntegerField(source='appointment.id', read_only=True)
    client_name = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()
    mechanic_id = serializers.SerializerMethodField()
    mechanic_name = serializers.SerializerMethodField()
    can_respond = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = AppNotification
        fields = [
            'id', 'user', 'appointment', 'appointment_id', 'title', 'message',
            'notification_type', 'is_read', 'created_at', 'link',
            'client_id', 'client_name', 'client_phone', 'vehicle_details',
            'mechanic_id', 'mechanic_name',
            'can_respond', 'actions'
        ]

    def get_can_respond(self, obj):
        # Un mécanicien peut répondre si c'est un rendez-vous en attente
        if obj.notification_type == 'APPOINTMENT' and obj.appointment:
            return obj.appointment.status == 'PENDING'
        return True # Par défaut, on permet une réponse simple

    def get_actions(self, obj):
        if obj.notification_type == 'APPOINTMENT' and obj.appointment:
            if obj.appointment.status == 'PENDING':
                return [
                    {'type': 'CONFIRM', 'label': 'Confirmer', 'need_message': False},
                    {'type': 'CANCEL', 'label': 'Refuser', 'need_message': True},
                    {'type': 'CHAT', 'label': 'Discuter', 'need_message': False}
                ]
            return [
                {'type': 'CHAT', 'label': 'Ouvrir le chat', 'need_message': False}
            ]
        return [
            {'type': 'CHAT', 'label': 'Répondre (Chat)', 'need_message': False}
        ]

    def get_client_id(self, obj):
        if obj.appointment and obj.appointment.client:
            return obj.appointment.client.id
        # Pour les notifications CHAT, retrouver l'expéditeur du dernier message
        if obj.notification_type == 'CHAT':
            from api.models import ChatMessage
            last_msg = ChatMessage.objects.filter(
                receiver=obj.user, appointment=obj.appointment
            ).order_by('-created_at').first()
            if last_msg:
                return last_msg.sender_id
        return None

    def get_client_name(self, obj):
        if obj.appointment and obj.appointment.client:
            return obj.appointment.client.get_full_name() or obj.appointment.client.username
        return None

    def get_mechanic_id(self, obj):
        if obj.appointment and obj.appointment.mechanic:
            return obj.appointment.mechanic.user_id
        # Pour les notifications CHAT, retrouver l'expéditeur du dernier message
        if obj.notification_type == 'CHAT':
            from api.models import ChatMessage
            last_msg = ChatMessage.objects.filter(
                receiver=obj.user, appointment=obj.appointment
            ).order_by('-created_at').first()
            if last_msg:
                return last_msg.sender_id
        return None

    def get_mechanic_name(self, obj):
        if obj.appointment and obj.appointment.mechanic:
            m = obj.appointment.mechanic
            return m.shop_name or m.user.get_full_name() or m.user.username
        return None

    def get_client_phone(self, obj):
        if obj.appointment and obj.appointment.client:
            return obj.appointment.client.phone
        return None

    def get_vehicle_details(self, obj):
        if obj.appointment and obj.appointment.vehicle:
            v = obj.appointment.vehicle
            year_str = f" ({v.year})" if v.year else ""
            return f"{v.brand} {v.model}{year_str} - {v.license_plate}"
        return None

class PredictiveAlertSerializer(serializers.ModelSerializer):
    vehicle_plate = serializers.CharField(source='vehicle.license_plate', read_only=True)
    vehicle_brand = serializers.CharField(source='vehicle.brand', read_only=True)
    vehicle_model = serializers.CharField(source='vehicle.model', read_only=True)
    vehicle_year = serializers.IntegerField(source='vehicle.year', read_only=True)
    vehicle_owner = serializers.CharField(source='vehicle.owner_name', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)

    class Meta:
        model = PredictiveAlert
        fields = '__all__'
