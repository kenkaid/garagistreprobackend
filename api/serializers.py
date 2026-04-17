from rest_framework import serializers
from rest_framework.authtoken.models import Token
from api.models import (
    User, Mechanic, Vehicle, DTCReference, ScanSession, SubscriptionPlan,
    Subscription, VehicleModel, Payment, UpcomingModule, WelcomeContent,
    SafetyCheck, IoTDevice, TelemetryData, PredictiveAlert
)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'is_mechanic', 'user_type', 'shop_name', 'location']

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
        user.save()

        # Création automatique du profil mécanicien si c'est un mécanicien
        if user_type == 'MECHANIC':
            Mechanic.objects.create(
                user=user,
                shop_name=shop_name or f"Garage de {user.first_name or user.username}",
                location=location or "Non précisée"
            )
            # On synchronise aussi sur l'utilisateur pour la centralisation
            user.shop_name = shop_name or f"Garage de {user.first_name or user.username}"
            user.location = location or "Non précisée"
            user.save()
        elif user_type == 'FLEET_OWNER':
            # Le shop_name reçu pour un propriétaire est considéré comme le nom de sa flotte
            user.shop_name = shop_name or f"Flotte de {user.first_name or user.username}"
            user.location = location or "Non précisée"
            user.save()

        return user

class MechanicSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    email = serializers.CharField(source='user.email', required=False)
    phone = serializers.CharField(source='user.phone', required=False)
    subscription_tier = serializers.CharField(read_only=True)

    class Meta:
        model = Mechanic
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'phone', 'shop_name', 'location', 'is_active', 'created_at', 'subscription_tier']

    def update(self, instance, validated_data):
        user_data = {
            'first_name': validated_data.pop('first_name', instance.user.first_name),
            'last_name': validated_data.pop('last_name', instance.user.last_name),
            'email': validated_data.pop('email', instance.user.email),
            'phone': validated_data.pop('phone', instance.user.phone),
            'shop_name': validated_data.get('shop_name', instance.user.shop_name),
            'location': validated_data.get('location', instance.user.location),
        }
        user = instance.user

        # Mise à jour des champs de l'utilisateur lié
        for attr, value in user_data.items():
            setattr(user, attr, value)
        user.save()

        # Mise à jour des champs du mécanicien
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

    class Meta:
        model = ScanSession
        fields = [
            'id', 'mechanic', 'mechanic_details', 'vehicle', 'date', 'notes',
            'found_dtcs', 'actual_labor_cost', 'actual_parts_cost', 'is_completed',
            'total_cost', 'ai_predictions', 'safety_check',
            'mileage_ecu', 'mileage_abs', 'mileage_dashboard', 'mileage_discrepancy',
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

class UpcomingModuleSerializer(serializers.ModelSerializer):
    applicablePlans = SubscriptionPlanSerializer(source='applicable_plans', many=True, read_only=True)
    expectedReleaseDate = serializers.DateField(source='expected_release_date', read_only=True)
    description_html = serializers.SerializerMethodField()

    class Meta:
        model = UpcomingModule
        fields = ['id', 'name', 'description_html', 'expected_release_date', 'expectedReleaseDate', 'applicable_plans', 'applicablePlans', 'is_active', 'created_at']

    def get_description_html(self, obj):
        description = obj.description
        if isinstance(description, dict):
            return description.get('html', '')
        if hasattr(description, 'html'):
            return description.html
        return str(description)

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

    class Meta:
        model = PredictiveAlert
        fields = '__all__'
