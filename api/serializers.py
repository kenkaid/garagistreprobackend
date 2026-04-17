from rest_framework import serializers
from rest_framework.authtoken.models import Token
from api.models import (
    User, Mechanic, Vehicle, DTCReference, ScanSession, SubscriptionPlan,
    Subscription, VehicleModel, Payment, UpcomingModule, WelcomeContent,
    SafetyCheck, IoTDevice, TelemetryData, PredictiveAlert
)

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

    class Meta:
        model = Mechanic
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'phone',
            'shop_name', 'location', 'is_active', 'created_at',
            'subscription_tier', 'is_trial', 'trial_days_remaining', 'active_subscription'
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
        brand = data.get('brand')
        model = data.get('model')
        year = data.get('year')

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

class DTCReferenceSerializer(serializers.ModelSerializer):
    # Mapping pour la compatibilité frontend (camelCase)
    possibleCauses = serializers.JSONField(source='probable_causes_list', read_only=True)
    suggestedFixes = serializers.JSONField(source='suggested_solutions_list', read_only=True)
    localPartPrice = serializers.IntegerField(source='est_part_price_local', read_only=True)
    importPartPrice = serializers.IntegerField(source='est_part_price_import', read_only=True)
    estimatedLaborCost = serializers.IntegerField(source='est_labor_cost', read_only=True)
    partImageUrl = serializers.URLField(source='part_image_url', read_only=True)
    partLocation = serializers.CharField(source='part_location', read_only=True)

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
            'last_trained_at'
        ]

class SafetyCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyCheck
        fields = ['id', 'is_airbag_deployed', 'crash_data_present', 'srs_module_status', 'notes', 'created_at']

class ScanSessionSerializer(serializers.ModelSerializer):
    vehicle = VehicleSerializer(read_only=True)
    mechanic_details = MechanicSerializer(source='mechanic', read_only=True)
    found_dtcs = DTCReferenceSerializer(many=True, read_only=True)
    total_cost = serializers.IntegerField(read_only=True)
    ai_predictions = serializers.SerializerMethodField()
    safety_check = SafetyCheckSerializer(read_only=True)
    mileage_discrepancy = serializers.IntegerField(read_only=True)
    health_score = serializers.IntegerField(read_only=True)
    buying_recommendation = serializers.CharField(read_only=True)

    class Meta:
        model = ScanSession
        fields = [
            'id', 'mechanic', 'mechanic_details', 'vehicle', 'date', 'notes',
            'found_dtcs', 'actual_labor_cost', 'actual_parts_cost', 'is_completed',
            'total_cost', 'ai_predictions', 'safety_check',
            'mileage_ecu', 'mileage_abs', 'mileage_dashboard', 'mileage_discrepancy',
            'health_score', 'buying_recommendation',
            'scan_type'
        ]

    def get_ai_predictions(self, obj):
        from api.services.ai_service import DTCModelAI
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
    class Meta:
        model = TelemetryData
        fields = '__all__'

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
