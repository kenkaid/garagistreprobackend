import requests
import json
from django.conf import settings
from rest_framework import viewsets, status, permissions, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.authtoken.models import Token
from api.models import (
    Mechanic, Vehicle, DTCReference, ScanSession, ScanSessionDTC, SubscriptionPlan,
    Subscription, User, Payment, VehicleModel, GlobalSettings,
    UpcomingModule, WelcomeContent, IoTDevice, TelemetryData, PredictiveAlert,
    Appointment, MaintenanceReminder, RegionalEvent, ChatMessage, Review,
    SparePartStore, SparePart
)
from api.serializers import (
    MechanicSerializer, VehicleSerializer, DTCReferenceSerializer,
    ScanSessionSerializer, SubscriptionPlanSerializer, SubscriptionSerializer,
    RegisterSerializer, UserSerializer, VehicleModelSerializer, ChangePasswordSerializer, UpcomingModuleSerializer,
    WelcomeContentSerializer, IoTDeviceSerializer, TelemetryDataSerializer, PredictiveAlertSerializer,
    MaintenanceReminderSerializer, RegionalEventSerializer, AppointmentSerializer,
    AppNotificationSerializer, ChatMessageSerializer, ReviewSerializer,
    SparePartStoreSerializer, SparePartSerializer
)
from api.serializers import RegisterSerializer, UserSerializer, ChangePasswordSerializer # Pour éviter les duplications si déjà présent
from api.services.diagnostics import DiagnosticService
from api.services.subscriptions import SubscriptionService

from django.db import models
from django.db.models import Sum, Count
from django.utils import timezone

from math import radians, cos, sin, asin, sqrt

def haversine(lon1, lat1, lon2, lat2):
    """
    Calcule la distance en kilomètres entre deux points GPS.
    """
    # Convertit en radians
    lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
    # Formule Haversine
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371 # Rayon de la terre en km
    return c * r

class AdminDashboardView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        """
        Dashboard pour l'administrateur (Toi).
        Affiche le chiffre d'affaires global et les statistiques clés.
        """
        payments = Payment.objects.filter(status='SUCCESS')
        total_revenue = payments.aggregate(Sum('amount'))['amount__sum'] or 0
        total_mechanics = Mechanic.objects.count()
        active_subscriptions = Subscription.objects.filter(is_active=True, end_date__gt=timezone.now()).count()
        total_scans = ScanSession.objects.count()

        # Statistiques mensuelles globales (6 derniers mois)
        monthly_revenue = []
        now = timezone.now()
        for i in range(5, -1, -1):
            month_date = now - timezone.timedelta(days=i*30)
            month_name = month_date.strftime('%b')
            month_year = month_date.year
            month_num = month_date.month

            rev = payments.filter(payment_date__year=month_year, payment_date__month=month_num).aggregate(Sum('amount'))['amount__sum'] or 0
            monthly_revenue.append({
                'month': month_name,
                'revenue': float(rev)
            })

        # Récupérer l'état actuel du mode test
        settings, _ = GlobalSettings.objects.get_or_create(id=1)

        return Response({
            'total_revenue_global': total_revenue,
            'total_mechanics': total_mechanics,
            'active_subscriptions': active_subscriptions,
            'total_scans_performed': total_scans,
            'monthly_revenue': monthly_revenue,
            'is_test_mode': settings.is_test_mode,
            'currency': 'FCFA'
        })

class AppConfigView(generics.RetrieveAPIView):
    """
    Endpoint public pour que l'app mobile lise la configuration globale
    (mode test, etc.) sans authentification.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        gs, _ = GlobalSettings.objects.get_or_create(id=1)
        return Response({'is_test_mode': gs.is_test_mode})


class GlobalSettingsView(generics.RetrieveUpdateAPIView):
    """
    API pour gérer les paramètres globaux (Mode Test/Prod).
    Accessible uniquement par les administrateurs.
    """
    permission_classes = [permissions.IsAdminUser]

    def get_object(self):
        settings, _ = GlobalSettings.objects.get_or_create(id=1)
        return settings

    def get(self, request, *args, **kwargs):
        settings = self.get_object()
        return Response({'is_test_mode': settings.is_test_mode})

    def patch(self, request, *args, **kwargs):
        settings = self.get_object()
        is_test = request.data.get('is_test_mode')
        if is_test is not None:
            settings.is_test_mode = is_test
            settings.save()
            return Response({'is_test_mode': settings.is_test_mode, 'status': 'updated'})
        return Response({'error': 'is_test_mode non fourni'}, status=400)

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)

        # On récupère le profil de l'utilisateur (Mécanicien ou Propriétaire)
        # Pour FLEET_OWNER, on renvoie les infos de base de l'utilisateur
        # Pour MECHANIC, on renvoie les infos du profil mécanicien
        if user.user_type == 'MECHANIC':
            try:
                mechanic = Mechanic.objects.get(user=user)
                user_data = MechanicSerializer(mechanic).data
            except Mechanic.DoesNotExist:
                user_data = UserSerializer(user).data
        else:
            user_data = UserSerializer(user).data

        # S'assurer que le user_type est bien présent dans la réponse pour le frontend
        if 'user_type' not in user_data:
            user_data['user_type'] = user.user_type

        return Response({
            'user': user_data,
            'token': token.key
        }, status=status.HTTP_201_CREATED)

class MechanicViewSet(viewsets.ModelViewSet):
    serializer_class = MechanicSerializer

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return Mechanic.objects.all()
            return Mechanic.objects.filter(user=self.request.user)
        return Mechanic.objects.none()

    @action(detail=False, methods=['get', 'patch', 'put'], permission_classes=[permissions.IsAuthenticated])
    def current(self, request):
        """
        Récupère ou met à jour le profil complet de l'utilisateur connecté.
        S'adapte selon le type d'utilisateur (MECHANIC ou FLEET_OWNER).
        """
        user = request.user

        # Cas spécial pour les mécaniciens qui ont un profil étendu
        if user.user_type == 'MECHANIC':
            try:
                mechanic = Mechanic.objects.get(user=user)
                if request.method in ['PATCH', 'PUT']:
                    serializer = MechanicSerializer(mechanic, data=request.data, partial=(request.method == 'PATCH'))
                    if serializer.is_valid():
                        serializer.save()
                        data = serializer.data
                    else:
                        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                else:
                    data = MechanicSerializer(mechanic).data

                if 'user_type' not in data:
                    data['user_type'] = user.user_type
                return Response(data)
            except Mechanic.DoesNotExist:
                pass # On retombe sur le cas User de base

        # Pour les autres types d'utilisateurs (INDIVIDUAL, FLEET_OWNER)
        if request.method in ['PATCH', 'PUT']:
            serializer = UserSerializer(user, data=request.data, partial=(request.method == 'PATCH'))
            if serializer.is_valid():
                serializer.save()
                data = serializer.data
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            data = UserSerializer(user).data

        # Compatibilité frontend : On s'assure que shop_name et location sont à la racine
        # même si ce n'est pas un objet Mechanic
        if 'shop_name' not in data:
            data['shop_name'] = user.shop_name
        if 'location' not in data:
            data['location'] = user.location

        # S'assurer que le user_type est présent
        if 'user_type' not in data:
            data['user_type'] = user.user_type

        return Response(data)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def register_expert(self, request):
        """
        Enregistre ou met à jour le statut d'expert du mécanicien avec sa position GPS.
        """
        user = request.user
        if user.user_type != 'MECHANIC':
            return Response({"error": "Seuls les mécaniciens peuvent s'enregistrer comme experts."}, status=status.HTTP_403_FORBIDDEN)

        try:
            mechanic = Mechanic.objects.get(user=user)
        except Mechanic.DoesNotExist:
            # Création automatique si manquant (devrait normalement être créé à l'inscription)
            mechanic = Mechanic.objects.create(
                user=user,
                shop_name=user.shop_name or f"Garage de {user.username}",
                location=user.location or "Non précisée"
            )

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        specialties = request.data.get('specialties')
        is_expert = request.data.get('is_expert', True)

        if latitude is None or longitude is None:
            return Response({"error": "La latitude et la longitude sont requises."}, status=status.HTTP_400_BAD_REQUEST)

        mechanic.latitude = latitude
        mechanic.longitude = longitude
        if specialties is not None:
            mechanic.specialties = specialties
        mechanic.is_expert = is_expert
        mechanic.save()

        return Response(MechanicSerializer(mechanic).data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def nearby(self, request):
        """
        Retourne les mécaniciens experts les plus proches.
        Paramètres: lat, lng, radius (default 10km)
        """
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius = float(request.query_params.get('radius', 10)) # km

        if not lat or not lng:
            return Response({"error": "lat et lng sont requis."}, status=status.HTTP_400_BAD_REQUEST)

        lat = float(lat)
        lng = float(lng)

        # Formule de Haversine pour filtrer par distance
        experts = Mechanic.objects.filter(is_expert=True, is_active=True, latitude__isnull=False, longitude__isnull=False)
        
        nearby_mechanics = []
        # Pour les utilisateurs connectés, on cherche s'il y a des interventions notifiables
        user_vehicle = None
        if request.user.is_authenticated and request.user.user_type == 'INDIVIDUAL':
            user_vehicle = Vehicle.objects.filter(owner=request.user).first()

        for m in experts:
            dist = haversine(lng, lat, m.longitude, m.latitude)
            if dist <= radius:
                m_data = MechanicSerializer(m).data
                m_data['distance'] = round(dist, 2)
                
                # Ajout des interventions notifiables
                m_data['notifiable_scan_id'] = None
                m_data['notifiable_appointment_id'] = None
                
                if user_vehicle:
                    last_scan = ScanSession.objects.filter(
                        vehicle=user_vehicle, mechanic=m, review__isnull=True
                    ).order_by('-date').first()
                    if last_scan:
                        m_data['notifiable_scan_id'] = last_scan.id
                        
                    last_appt = Appointment.objects.filter(
                        vehicle=user_vehicle, mechanic=m, status='COMPLETED', review__isnull=True
                    ).order_by('-appointment_date').first()
                    if last_appt:
                        m_data['notifiable_appointment_id'] = last_appt.id

                nearby_mechanics.append(m_data)

        # Trier par distance et note (les mieux notés d'abord pour une même distance relative)
        # On peut aussi mixer: score = distance - (rating * factor)
        nearby_mechanics.sort(key=lambda x: (x['distance'], -x['average_rating']))

        return Response(nearby_mechanics)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_report(self, request):
        """
        Génère un bilan financier détaillé pour le mécanicien connecté.
        Inclut les revenus totaux et l'historique des 6 derniers mois.
        """
        mechanic = Mechanic.objects.get(user=request.user)
        scans = ScanSession.objects.filter(mechanic=mechanic, is_completed=True)

        # Statistiques globales
        total_revenue = sum(s.total_cost for s in scans)
        total_labor = sum(s.actual_labor_cost for s in scans)
        total_parts = sum(s.actual_parts_cost for s in scans)
        total_scans = scans.count()

        # Statistiques par mois (6 derniers mois)
        monthly_stats = []
        now = timezone.now()
        for i in range(5, -1, -1):
            month_date = now - timezone.timedelta(days=i*30)
            month_name = month_date.strftime('%b')
            month_year = month_date.year
            month_num = month_date.month

            month_scans = scans.filter(date__year=month_year, date__month=month_num)
            revenue = sum(s.total_cost for s in month_scans)

            monthly_stats.append({
                'month': month_name,
                'revenue': revenue,
                'count': month_scans.count()
            })

        return Response({
            'mechanic': mechanic.shop_name,
            'total_scans_completed': total_scans,
            'total_revenue': total_revenue,
            'total_labor': total_labor,
            'total_parts': total_parts,
            'monthly_history': monthly_stats,
            'currency': 'FCFA'
        })

    @action(detail=True, methods=['get'])
    def subscription_status(self, request, pk=None):
        mechanic = self.get_object()
        is_valid = SubscriptionService.is_subscription_valid(mechanic.user)
        return Response({'is_active': is_valid})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_plan(self, request):
        """
        Permet au mécanicien de changer son plan d'abonnement.
        Attend 'plan_id', 'transaction_id', 'duration_months' et 'payment_method'.
        """
        try:
            mechanic = Mechanic.objects.get(user=request.user)
            plan_id = request.data.get('plan_id')
            transaction_id = request.data.get('transaction_id')
            duration_months = int(request.data.get('duration_months', 1))
            payment_method = request.data.get('payment_method', 'WAVE')

            if not plan_id or not transaction_id:
                return Response({'error': 'plan_id et transaction_id sont requis'}, status=status.HTTP_400_BAD_REQUEST)

            plan = SubscriptionPlan.objects.get(id=plan_id)
            subscription, added_days = SubscriptionService.change_subscription(
                mechanic, plan, transaction_id, duration_months, payment_method
            )

            message = 'Plan d\'abonnement mis à jour avec succès'
            if added_days > 0:
                message += f". Nous avons ajouté {added_days} jours restants de votre période d'essai."

            return Response({
                'message': message,
                'subscription': SubscriptionSerializer(subscription).data
            })
        except Mechanic.DoesNotExist:
            return Response({'error': 'Profil mécanicien non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan d\'abonnement non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            error_msg = str(e)
            if "UNIQUE constraint failed" in error_msg or "transaction_id" in error_msg:
                error_msg = "Cette transaction a déjà été utilisée. Veuillez vérifier votre paiement."

            print(f"DEBUG change_plan ERROR: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': error_msg, 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        """
        Permet au mécanicien de changer son mot de passe.
        """
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'message': 'Mot de passe mis à jour avec succès'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VehicleModelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour consulter la base de données de modèles de véhicules.
    """
    queryset = VehicleModel.objects.all()
    serializer_class = VehicleModelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        brand = self.request.query_params.get('brand')
        if brand:
            return self.queryset.filter(brand__icontains=brand)
        return self.queryset

class VehicleViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleSerializer
    # On autorise la recherche par ID ou par plaque
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        # Tentative par ID d'abord
        if lookup_value.isdigit():
            obj = queryset.filter(id=lookup_value).first()
            if obj:
                self.check_object_permissions(self.request, obj)
                return obj
        
        # Sinon par plaque
        obj = queryset.filter(license_plate__iexact=lookup_value).first()
        if obj:
            self.check_object_permissions(self.request, obj)
            return obj
            
        from django.http import Http404
        raise Http404

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if user.is_staff:
                return Vehicle.objects.all()

            if user.user_type == 'INDIVIDUAL':
                return Vehicle.objects.filter(owner=user)

            # On montre les véhicules qui ont été scannés par ce mécanicien
            # OU les véhicules qu'il a recherchés par plaque (potentiellement)
            # Pour l'instant on garde ceux qu'il a scannés au moins une fois
            return Vehicle.objects.filter(scansession__mechanic__user=user).distinct()
        return Vehicle.objects.none()

    def create(self, request, *args, **kwargs):
        user = request.user

        # Pour les particuliers, on permet d'ajouter/lier un véhicule
        if user.user_type == 'INDIVIDUAL':
            vehicle_data = request.data.copy()
            license_plate = vehicle_data.get('license_plate')
            existing_vehicle = Vehicle.objects.filter(license_plate__iexact=license_plate).first()

            if existing_vehicle:
                if existing_vehicle.owner and existing_vehicle.owner != user:
                    return Response({'error': 'Ce véhicule est déjà associé à un autre compte.'}, status=status.HTTP_400_BAD_REQUEST)

                # On lie le véhicule existant à l'utilisateur
                serializer = self.get_serializer(existing_vehicle, data=vehicle_data, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save(owner=user)
                return Response(serializer.data, status=status.HTTP_200_OK)

            # Création du nouveau véhicule
            serializer = self.get_serializer(data=vehicle_data)
            serializer.is_valid(raise_exception=True)
            serializer.save(owner=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='by_plate/(?P<plate>[^/.]+)')
    def by_plate(self, request, plate=None):
        """
        Recherche un véhicule par sa plaque d'immatriculation.
        Si trouvé, retourne ses informations avec l'historique des scans et statistiques.
        """
        try:
            vehicle = Vehicle.objects.get(license_plate__iexact=plate)
            # Récupérer l'historique des scans pour ce véhicule (uniquement ceux du mécanicien connecté)
            scans = ScanSession.objects.filter(vehicle=vehicle, mechanic__user=self.request.user).order_by('-date')
            scan_count = scans.count()

            # Statistiques : DTC les plus fréquents (uniquement sur les scans du mécanicien)
            from django.db.models import Count
            top_dtcs = DTCReference.objects.filter(scansession__vehicle=vehicle, scansession__mechanic__user=self.request.user)\
                .annotate(occurrence=Count('scansession'))\
                .order_by('-occurrence')[:5]

            stats = {
                'scan_count': scan_count,
                'top_dtcs': [
                    {'code': dtc.code, 'description': dtc.description, 'meaning': dtc.meaning, 'count': dtc.occurrence}
                    for dtc in top_dtcs
                ],
                'last_scan': ScanSessionSerializer(scans.first()).data if scans.exists() else None
            }

            # Sérialiser l'historique récent (ex: 10 derniers)
            history = ScanSessionSerializer(scans[:10], many=True).data

            data = self.get_serializer(vehicle).data
            data['stats'] = stats
            data['history'] = history

            return Response(data)
        except Vehicle.DoesNotExist:
            return Response({'detail': 'Véhicule non trouvé'}, status=status.HTTP_404_NOT_FOUND)

class ScanSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ScanSessionSerializer

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return ScanSession.objects.all().order_by('-date')

            # Pour un FLEET_OWNER ou un INDIVIDUAL, on filtre par propriétaire du véhicule
            if self.request.user.user_type in ['FLEET_OWNER', 'INDIVIDUAL']:
                return ScanSession.objects.filter(
                    vehicle__owner=self.request.user
                ).select_related('mechanic__user', 'vehicle').prefetch_related('found_dtcs', 'scan_dtcs__dtc').distinct().order_by('-date')

            # Un mécanicien ne voit QUE ses propres scans (dans son garage)
            if self.request.user.user_type == 'MECHANIC':
                return ScanSession.objects.filter(
                    mechanic__user=self.request.user
                ).select_related('mechanic__user', 'vehicle').prefetch_related('found_dtcs', 'scan_dtcs__dtc').distinct().order_by('-date')

            return ScanSession.objects.none()
        return ScanSession.objects.none()

    def create(self, request, *args, **kwargs):
        # Utilise le service pour la création
        mechanic = None
        if request.user.user_type == 'MECHANIC':
            try:
                mechanic = Mechanic.objects.get(user=request.user)
            except Mechanic.DoesNotExist:
                return Response(
                    {'error': 'Profil mécanicien introuvable', 'detail': 'Votre compte n\'est pas associé à un profil mécanicien.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Vérification d'abonnement
        if not SubscriptionService.is_subscription_valid(request.user):
            return Response(
                {
                    'error': 'Abonnement requis',
                    'detail': 'Votre abonnement est expiré ou inexistant. Veuillez souscrire à un plan.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        vehicle_data = request.data.get('vehicle')

        if not vehicle_data:
            return Response({'error': 'Données véhicule manquantes', 'detail': 'Le champ "vehicle" est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validation manuelle du véhicule via le serializer
        # Note: On utilise partial=True pour ne pas bloquer si le véhicule existe déjà
        # (le serializer VehicleSerializer pourrait renvoyer une erreur d'unicité sur license_plate)
        license_plate = vehicle_data.get('license_plate', '').upper()
        if not license_plate:
            return Response({'error': 'Plaque d\'immatriculation manquante'}, status=status.HTTP_400_BAD_REQUEST)
        existing_vehicle = Vehicle.objects.filter(license_plate__iexact=license_plate).first()

        vehicle_serializer = VehicleSerializer(existing_vehicle, data=vehicle_data, partial=True)
        if not vehicle_serializer.is_valid():
            return Response(vehicle_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Utilisation des données validées
        vehicle_data = vehicle_serializer.validated_data

        dtc_codes = request.data.get('dtc_codes', [])
        notes = request.data.get('notes', '')

        # Données d'expertise optionnelles (Support des deux formats : plat et imbriqué)
        mileage_data = request.data.get('mileage_data')
        if not mileage_data:
            # Fallback format plat
            mileage_data = {
                'mileage_ecu': request.data.get('mileage_ecu'),
                'mileage_abs': request.data.get('mileage_abs'),
                'mileage_dashboard': request.data.get('mileage_dashboard'),
            }
            # Ne garder que si au moins une valeur est présente
            if not any(v is not None for v in mileage_data.values()):
                mileage_data = None

        safety_data = request.data.get('safety_data')
        if not safety_data:
            # Fallback format plat (safety_check ou direct)
            safety_payload = request.data.get('safety_check') or request.data

            # Vérification de l'existence de données de sécurité dans le payload
            has_safety = any(k in safety_payload for k in ['is_airbag_deployed', 'airbags_deployed', 'crash_data_present', 'has_crash_data'])

            if has_safety:
                safety_data = {
                    'is_airbag_deployed': safety_payload.get('is_airbag_deployed') if safety_payload.get('is_airbag_deployed') is not None else safety_payload.get('airbags_deployed', False),
                    'crash_data_present': safety_payload.get('crash_data_present') if safety_payload.get('crash_data_present') is not None else safety_payload.get('has_crash_data', False),
                    'srs_module_status': safety_payload.get('srs_module_status', 'OK'),
                    'notes': safety_payload.get('notes', '')
                }
            else:
                safety_data = None

        # Ajout des champs de coûts s'ils sont présents
        actual_labor_cost = request.data.get('actual_labor_cost', 0)
        actual_parts_cost = request.data.get('actual_parts_cost', 0)
        is_completed = request.data.get('is_completed', False)
        scan_type = request.data.get('scan_type', 'DIAGNOSTIC')

        # ÉVITER LES DOUBLONS : Si on reçoit un ID, c'est une mise à jour
        scan_id = request.data.get('id')
        if scan_id:
            try:
                # Si c'est un mécanicien, on filtre par son profil
                # Sinon on vérifie que le véhicule du scan lui appartient
                if mechanic:
                    scan = ScanSession.objects.get(id=scan_id, mechanic=mechanic)
                else:
                    scan = ScanSession.objects.get(id=scan_id, vehicle__owner=request.user)

                # SI LE TRAVAIL EST DÉJÀ TERMINÉ : On ne peut plus modifier les coûts
                if scan.is_completed:
                    return Response(
                        {'error': 'Travail déjà terminé', 'detail': 'Les coûts ne peuvent plus être modifiés une fois le travail terminé et payé.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # On met à jour les données existantes
                scan.notes = notes
                scan.actual_labor_cost = actual_labor_cost
                scan.actual_parts_cost = actual_parts_cost
                scan.is_completed = is_completed
                scan.scan_type = scan_type

                # Mise à jour expertise si fournie
                if mileage_data:
                    scan.mileage_ecu = mileage_data.get('mileage_ecu', scan.mileage_ecu)
                    scan.mileage_abs = mileage_data.get('mileage_abs', scan.mileage_abs)
                    scan.mileage_dashboard = mileage_data.get('mileage_dashboard', scan.mileage_dashboard)

                scan.save()

                if safety_data:
                    from api.models import SafetyCheck
                    SafetyCheck.objects.update_or_create(
                        scan_session=scan,
                        defaults={
                            'is_airbag_deployed': safety_data.get('is_airbag_deployed', False),
                            'crash_data_present': safety_data.get('crash_data_present', False),
                            'srs_module_status': safety_data.get('srs_module_status', 'OK'),
                            'notes': safety_data.get('notes', '')
                        }
                    )

                # Mise à jour des DTC
                scan.scan_dtcs.all().delete()
                brand = scan.vehicle.brand
                for item in dtc_codes:
                    code = item if isinstance(item, str) else item.get('code')
                    status_val = 'confirmed' if isinstance(item, str) else item.get('status', 'confirmed')

                    ref = DTCReference.objects.filter(code=code, brand=brand).first()
                    if not ref:
                        ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()
                    if not ref:
                        ref, _ = DTCReference.objects.get_or_create(code=code, brand=brand, defaults={'description': f'Code défaut {code} détecté'})

                    if ref:
                        ScanSessionDTC.objects.create(scan_session=scan, dtc=ref, status=status_val)

                serializer = self.get_serializer(scan)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except (ScanSession.DoesNotExist, ValueError):
                # Si l'ID est invalide, on continue vers la création d'un nouveau scan
                pass

        # Déduplication intelligente : Si un scan pour ce véhicule par ce mécanicien (ou ce propriétaire) existe déjà
        # dans les 10 dernières minutes (pour éviter les double-clics ou permettre la reprise d'un scan récent),
        # on le met à jour au lieu d'en créer un nouveau.
        time_window = timezone.now() - timezone.timedelta(minutes=10)

        scan_filter = {
            'vehicle__license_plate__iexact': vehicle_data.get('license_plate', 'INCONNU'),
            'date__gte': time_window
        }

        if mechanic:
            scan_filter['mechanic'] = mechanic
        else:
            scan_filter['mechanic__isnull'] = True
            scan_filter['vehicle__owner'] = request.user

        recent_scan = ScanSession.objects.filter(**scan_filter).order_by('-date').first()

        if recent_scan:
            recent_scan.notes = notes
            recent_scan.actual_labor_cost = actual_labor_cost
            recent_scan.actual_parts_cost = actual_parts_cost
            recent_scan.is_completed = is_completed

            # Important : Si le scan récent était un DIAGNOSTIC et qu'on reçoit une VERIFICATION,
            # on change le type (cas de l'effacement de défauts)
            if scan_type == 'VERIFICATION' and recent_scan.scan_type == 'DIAGNOSTIC':
                recent_scan.scan_type = 'VERIFICATION'

            # Mise à jour expertise
            if mileage_data:
                recent_scan.mileage_ecu = mileage_data.get('mileage_ecu', recent_scan.mileage_ecu)
                recent_scan.mileage_abs = mileage_data.get('mileage_abs', recent_scan.mileage_abs)
                recent_scan.mileage_dashboard = mileage_data.get('mileage_dashboard', recent_scan.mileage_dashboard)

            recent_scan.save()

            if safety_data:
                from api.models import SafetyCheck
                SafetyCheck.objects.update_or_create(
                    scan_session=recent_scan,
                    defaults={
                        'is_airbag_deployed': safety_data.get('is_airbag_deployed', False),
                        'crash_data_present': safety_data.get('crash_data_present', False),
                        'srs_module_status': safety_data.get('srs_module_status', 'OK'),
                        'notes': safety_data.get('notes', '')
                    }
                )

            # Mise à jour des DTC : On ne vide la liste QUE si dtc_codes est explicitement envoyé comme vide
            # MAIS que le scan_type est VERIFICATION (effacement réussi).
            # Si c'est juste une mise à jour de notes/coûts (dtc_codes absent ou non fourni), on garde les anciens.
            if dtc_codes is not None:
                # Si on a des nouveaux codes, ou si on veut explicitement vider (VERIFICATION)
                if len(dtc_codes) > 0 or scan_type == 'VERIFICATION':
                    recent_scan.scan_dtcs.all().delete()
                    brand = recent_scan.vehicle.brand
                    for item in dtc_codes:
                        code = item if isinstance(item, str) else item.get('code')
                        status_val = 'confirmed' if isinstance(item, str) else item.get('status', 'confirmed')

                        ref = DTCReference.objects.filter(code=code, brand=brand).first()
                        if not ref:
                            ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()
                        if not ref:
                            ref, _ = DTCReference.objects.get_or_create(code=code, brand=brand, defaults={'description': f'Code défaut {code} détecté'})

                        if ref:
                            ScanSessionDTC.objects.create(scan_session=recent_scan, dtc=ref, status=status_val)

            serializer = self.get_serializer(recent_scan)
            return Response(serializer.data, status=status.HTTP_200_OK)

        scan = DiagnosticService.record_scan(
            mechanic,
            vehicle_data,
            dtc_codes,
            notes,
            mileage_data=mileage_data,
            safety_data=safety_data,
            scan_type=scan_type,
            owner=request.user if request.user.user_type == 'INDIVIDUAL' else None
        )

        # Mise à jour des coûts initiaux
        scan.actual_labor_cost = actual_labor_cost
        scan.actual_parts_cost = actual_parts_cost
        scan.is_completed = is_completed
        scan.save()

        serializer = self.get_serializer(scan)
        
        # Enrichissement avec les pièces recommandées dès la création
        data = serializer.data
        if 'scan_dtcs' in data:
            for item in data['scan_dtcs']:
                if 'dtc' in item and item['dtc']:
                    # On utilise le même logic que dans DTCReferenceSerializer.get_recommended_spare_parts
                    from api.models import DTCReference
                    from api.serializers import ScanSessionDTCSerializer
                    dtc_id = item['dtc'] if isinstance(item['dtc'], int) else item['dtc'].get('id')
                    dtc_obj = DTCReference.objects.filter(id=dtc_id).first()
                    if dtc_obj:
                        dtc_serializer = ScanSessionDTCSerializer()
                        item['recommended_spare_parts'] = dtc_serializer.get_recommended_spare_parts(type('obj', (object,), {'dtc': dtc_obj}))

        return Response(data, status=status.HTTP_201_CREATED)

    def get_ai_predictions(self, request, dtc_items, vehicle_info):
        from api.services.ai_service import DTCModelAI
        dtc_codes = [item if isinstance(item, str) else item.get('code') for item in dtc_items]
        return DTCModelAI.predict_advanced(dtc_codes, vehicle_info)

    @action(detail=False, methods=['post'], url_path='analyze_live')
    def analyze_live(self, request):
        """
        Analyse approfondie en temps réel des données PIDs OBD.
        Détecte les anomalies simples ET les corrélations multi-PIDs (pannes cachées/insoupçonnées)
        avec interprétations claires et niveau de certitude — IA Deep Analyze v3.0.
        """
        from api.services.ai_service import DTCModelAI

        pids = request.data.get('pids', [])
        vehicle_id = request.data.get('vehicle_id')
        vehicle_info = None

        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(id=vehicle_id)
                vehicle_info = {
                    'brand': vehicle.brand,
                    'model': vehicle.model,
                    'year': vehicle.year,
                }
            except Vehicle.DoesNotExist:
                pass

        # Construire un dict pid → valeur (clés en majuscules)
        pid_values = {}
        for item in pids:
            pid = item.get('pid', '').upper()
            value = item.get('value')
            if pid and value is not None:
                try:
                    pid_values[pid] = float(value)
                except (ValueError, TypeError):
                    pass

        # Déléguer toute l'analyse à la méthode avancée
        result = DTCModelAI.analyze_live_deep(pid_values, vehicle_info=vehicle_info)
        return Response(result)

    @action(detail=False, methods=['post'], url_path='analyze_dtcs')
    def analyze_dtcs(self, request):
        """
        Analyse approfondie de codes DTC issus d'un scan.
        Combine DB Django + base locale KB + scraping web.
        Retourne interprétation narrative, causes classées, solutions numérotées, coûts.
        """
        from api.services.ai_service import DTCModelAI

        dtc_codes = request.data.get('dtc_codes', [])
        vehicle_info = request.data.get('vehicle_info', None)

        if not dtc_codes:
            return Response({'error': 'dtc_codes est requis'}, status=status.HTTP_400_BAD_REQUEST)

        # Normaliser les codes (majuscules, supprimer suffixes internes)
        import re as _re
        clean_codes = [_re.sub(r'_[A-Z]$', '', str(c).upper().strip()) for c in dtc_codes]

        result = DTCModelAI.analyze_dtcs_deep(clean_codes, vehicle_info=vehicle_info)
        return Response(result)

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        """
        Filtre les plans en fonction du type d'utilisateur connecté.
        Si non connecté (pour l'accueil par ex), on peut montrer les plans par défaut (MECHANIC).
        """
        user = self.request.user
        if user.is_authenticated:
            return SubscriptionPlan.objects.filter(target_user_type=user.user_type).exclude(tier="TRIAL")
        return SubscriptionPlan.objects.filter(target_user_type='MECHANIC').exclude(tier='TRIAL')

    @action(detail=True, methods=['get'])
    def get_quotation(self, request, pk=None):
        """
        Calcule un devis pour un plan et une durée donnés.
        Paramètre query : 'months' (défaut 1).
        """
        plan = self.get_object()
        try:
            months = int(request.query_params.get('months', 1))
            if months < 1:
                return Response({'error': 'La durée doit être d\'au moins 1 mois'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({'error': 'Format de durée invalide'}, status=status.HTTP_400_BAD_REQUEST)

        total_price = plan.price * months
        return Response({
            'plan_id': plan.id,
            'plan_name': plan.name,
            'tier': plan.tier,
            'months': months,
            'price_per_month': plan.price,
            'total_price': total_price,
            'currency': 'FCFA',
            'description': f"Abonnement {plan.name} pour {months} mois."
        })

class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'MECHANIC':
            return Subscription.objects.filter(mechanic__user=user, is_active=True)
        return Subscription.objects.filter(user=user, is_active=True)

    @action(detail=False, methods=['post'])
    def subscribe(self, request):
        """
        Souscrit le mécanicien à un plan.
        Données attendues : {'plan_id': 1, 'transaction_id': 'REF-123'}
        """
        mechanic = Mechanic.objects.get(user=request.user)
        plan_id = request.data.get('plan_id')
        transaction_id = request.data.get('transaction_id')

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
            subscription, added_days = SubscriptionService.activate_subscription(mechanic.user, plan, transaction_id)

            data = SubscriptionSerializer(subscription).data
            if added_days > 0:
                data['message'] = f"Votre abonnement a été activé. Nous avons ajouté {added_days} jours restants de votre période d'essai à votre nouvel abonnement."
            else:
                data['message'] = "Votre abonnement a été activé avec succès."

            return Response(data, status=status.HTTP_201_CREATED)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class WavePaymentInitView(generics.CreateAPIView):
    """
    Initie une session de paiement Wave.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        plan_id = request.data.get('plan_id')
        duration_months = int(request.data.get('duration_months', 1))

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan non trouvé'}, status=status.HTTP_404_NOT_FOUND)

        # Création du paiement en attente
        payment = SubscriptionService.create_pending_payment(
            user=request.user,
            plan=plan,
            duration_months=duration_months,
            payment_method='WAVE'
        )

        # Court-circuit en mode test : on simule un succès sans appeler Wave
        gs, _ = GlobalSettings.objects.get_or_create(id=1)
        if gs.is_test_mode:
            payment.transaction_id = f"TEST-{payment.id}"
            payment.save()
            return Response({
                'payment_id': payment.id,
                'wave_launch_url': None,
                'amount': payment.amount,
                'currency': 'XOF',
                'test_mode': True,
                'message': 'Mode test actif — paiement simulé, aucun débit réel.'
            })

        # Appel à l'API Wave
        wave_api_key = getattr(settings, 'WAVE_API_KEY', 'votre_cle_test_ici')
        wave_url = "https://api.wave.com/v1/checkout/sessions"

        payload = {
            "amount": str(int(payment.amount)),
            "currency": "XOF",
            "error_url": "https://garagistepro.ci/payment/error", # À adapter
            "success_url": "https://garagistepro.ci/payment/success", # À adapter
            "client_reference": str(payment.id)
        }

        headers = {
            "Authorization": f"Bearer {wave_api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(wave_url, json=payload, headers=headers)
            response.raise_for_status()
            wave_data = response.json()

            # On peut stocker l'ID de session Wave si nécessaire
            payment.transaction_id = wave_data.get('id', payment.transaction_id)
            payment.save()

            return Response({
                'payment_id': payment.id,
                'wave_launch_url': wave_data.get('wave_launch_url'),
                'amount': payment.amount,
                'currency': 'XOF'
            })
        except requests.exceptions.RequestException as e:
            return Response({'error': f"Erreur Wave: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

class WaveWebhookView(generics.GenericAPIView):
    """
    Reçoit les notifications de Wave.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        # En production, il faut vérifier la signature 'Wave-Signature'
        # Pour l'instant on implémente la logique de base
        data = request.data

        if data.get('type') == 'checkout.session.completed':
            session_data = data.get('data', {})
            payment_id = session_data.get('client_reference')
            wave_session_id = session_data.get('id')

            try:
                payment = Payment.objects.get(id=payment_id)
                SubscriptionService.confirm_payment(payment, wave_session_id)
                return Response({'status': 'success'}, status=status.HTTP_200_OK)
            except Payment.DoesNotExist:
                return Response({'error': 'Paiement non trouvé'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'status': 'ignored'}, status=status.HTTP_200_OK)

class DTCReferenceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour consulter la base de données technique DTC.
    """
    queryset = DTCReference.objects.all()
    serializer_class = DTCReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        code = self.request.query_params.get('code')
        brand = self.request.query_params.get('brand')
        queryset = self.queryset

        if code:
            queryset = queryset.filter(code__icontains=code)
        if brand:
            queryset = queryset.filter(brand__icontains=brand)

        return queryset

class UpcomingModuleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API pour consulter les modules à venir.
    """
    queryset = UpcomingModule.objects.filter(is_active=True)
    serializer_class = UpcomingModuleSerializer
    permission_classes = [permissions.IsAuthenticated]

class WelcomeContentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API pour récupérer le contenu de l'écran d'accueil.
    Accessible à tous sans authentification.
    """
    queryset = WelcomeContent.objects.filter(is_active=True).order_by('order')
    serializer_class = WelcomeContentSerializer
    permission_classes = [permissions.AllowAny]

# === VUES POUR LA PRÉVENTION DES PANNES ET TÉLÉMÉTRIE ===

class IoTDeviceViewSet(viewsets.ModelViewSet):
    """
    Gestion des boîtiers IoT.
    """
    serializer_class = IoTDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return IoTDevice.objects.all()
        # Un propriétaire de flotte ne voit que ses boîtiers via ses véhicules
        return IoTDevice.objects.filter(vehicle__fleet_owner=user)

class TelemetryViewSet(viewsets.ModelViewSet):
    """
    Réception et consultation des données de télémétrie.
    """
    serializer_class = TelemetryDataSerializer
    permission_classes = [permissions.AllowAny] # Les boîtiers envoient sans auth complexe pour l'instant (IMEI)

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()] # Autoriser IMEI ou Auth Token
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return TelemetryData.objects.none()
        if user.is_staff:
            return TelemetryData.objects.all()
        # Un particulier voit ses données, un pro voit celles de sa flotte
        if user.user_type == 'INDIVIDUAL':
            return TelemetryData.objects.filter(vehicle__owner=user)
        return TelemetryData.objects.filter(vehicle__fleet_owner=user)

    def create(self, request, *args, **kwargs):
        """
        Endpoint robuste : accepte soit un IMEI (IoT), soit un Vehicle ID + Auth (Mobile).
        """
        imei = request.data.get('imei')
        vehicle_id = request.data.get('vehicle')
        device = None
        vehicle = None

        # Cas 1 : Via boîtier IoT (IMEI)
        if imei:
            try:
                device = IoTDevice.objects.get(imei=imei, status='ACTIVE')
                vehicle = device.vehicle
                if not vehicle:
                    return Response({"error": "Device non associé à un véhicule"}, status=400)
            except IoTDevice.DoesNotExist:
                return Response({"error": "Device non reconnu"}, status=403)

        # Cas 2 : Via Application Mobile (Authentifiée)
        elif vehicle_id and request.user.is_authenticated:
            try:
                vehicle = Vehicle.objects.get(id=vehicle_id, owner=request.user)
            except Vehicle.DoesNotExist:
                return Response({"error": "Véhicule non trouvé ou accès refusé"}, status=404)

        else:
            return Response({"error": "Authentification ou IMEI requis"}, status=401)

        # Préparation des données
        data = request.data.copy()
        data['device'] = device.id if device else None
        data['vehicle'] = vehicle.id

        # Nettoyage des valeurs vides pour éviter des erreurs de type
        numeric_fields = ['voltage', 'fuel_level', 'rpm', 'speed', 'coolant_temp', 'throttle', 'latitude', 'longitude', 'accel_x', 'accel_y', 'accel_z']
        integer_fields = ['rpm', 'speed', 'coolant_temp']

        for key in numeric_fields:
            if key in data:
                val = data[key]
                if val is None or val == "" or val == "undefined" or val == "null":
                    data[key] = None
                else:
                    try:
                        # Conversion en float pour supporter les deux formats
                        float_val = float(val)

                        # Gestion des valeurs infinies ou NaN (pourraient venir de l'OBD ou JS)
                        import math
                        if math.isinf(float_val) or math.isnan(float_val):
                            data[key] = None
                        elif key in integer_fields:
                            data[key] = int(round(float_val))
                        else:
                            data[key] = float_val
                    except (ValueError, TypeError, OverflowError):
                        data[key] = None

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Analyse
        self._analyze_telemetry(vehicle, serializer.validated_data)

        if device:
            device.last_ping = timezone.now()
            device.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _analyze_telemetry(self, vehicle, data):
        """
        Logique avancée pour les alertes prédictives via croisement de données.
        """
        # 1. Vérification Batterie & Alternateur
        voltage = data.get('voltage')
        rpm = data.get('rpm', 0) or 0
        if voltage and isinstance(voltage, (int, float)):
            if voltage < 11.8:
                PredictiveAlert.objects.get_or_create(
                    vehicle=vehicle,
                    alert_type='BATTERY',
                    severity='WARNING',
                    is_resolved=False,
                    defaults={'message': "Tension batterie faible (<11.8V). Risque de non-démarrage imminent."}
                )
            elif rpm > 1500 and voltage < 13.0:
                # Si le moteur tourne mais la tension reste basse -> Alternateur fatigue
                PredictiveAlert.objects.get_or_create(
                    vehicle=vehicle,
                    alert_type='ENGINE',
                    severity='WARNING',
                    is_resolved=False,
                    defaults={'message': "Alternateur suspect : la tension de charge est faible malgré le régime moteur."}
                )

        # 2. Croisement Papillon (Throttle) / RPM - Détection Perte de puissance
        throttle = data.get('throttle')
        if throttle and rpm and isinstance(throttle, (int, float)):
            if throttle > 80 and rpm < 2000 and data.get('speed', 0) > 20:
                # Pied au plancher mais le moteur ne monte pas en régime -> Filtre bouché ou injection
                PredictiveAlert.objects.get_or_create(
                    vehicle=vehicle,
                    alert_type='ENGINE',
                    severity='CRITICAL',
                    is_resolved=False,
                    defaults={'message': "Perte de puissance détectée : réponse moteur incohérente avec l'ouverture du papillon. Vérifiez les filtres."}
                )

        # 3. Surveillance Température (Surchauffe préventive)
        coolant_temp = data.get('coolant_temp')
        if coolant_temp and isinstance(coolant_temp, (int, float)):
            if coolant_temp > 105:
                PredictiveAlert.objects.get_or_create(
                    vehicle=vehicle,
                    alert_type='ENGINE',
                    severity='CRITICAL',
                    is_resolved=False,
                    defaults={'message': "Surchauffe moteur critique détectée ! Arrêtez-vous dès que possible."}
                )
            elif coolant_temp > 98 and data.get('speed', 0) > 60:
                # Température haute alors qu'on roule vite (le vent devrait refroidir) -> Radiateur/Ventilateur
                PredictiveAlert.objects.get_or_create(
                    vehicle=vehicle,
                    alert_type='MAINTENANCE',
                    severity='WARNING',
                    is_resolved=False,
                    defaults={'message': "Refroidissement inefficace : la température monte anormalement à haute vitesse."}
                )

        # 4. Score conduite (accélérations brutales)
        accel_x = data.get('accel_x')
        accel_y = data.get('accel_y')

        if accel_x is not None and accel_y is not None:
            if abs(accel_x) > 2.0 or abs(accel_y) > 2.0:
                PredictiveAlert.objects.create(
                    vehicle=vehicle,
                    alert_type='DRIVING',
                    severity='INFO',
                    message="Accélération ou freinage brutal détecté. Impact sur l'usure prématurée."
                )

class PredictiveAlertViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consultation des alertes pour le propriétaire.
    """
    serializer_class = PredictiveAlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return PredictiveAlert.objects.all()
        return PredictiveAlert.objects.filter(vehicle__fleet_owner=user, is_resolved=False)

class FleetDashboardView(generics.RetrieveAPIView):
    """
    Vue synthétique pour le tableau de bord Flotte.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = self.request.user
        if user.user_type != 'FLEET_OWNER' and not user.is_staff:
            return Response({"error": "Accès réservé aux propriétaires de flotte"}, status=403)

        vehicles = Vehicle.objects.filter(fleet_owner=user)
        total_vehicles = vehicles.count()

        # Alertes actives
        active_alerts = PredictiveAlert.objects.filter(vehicle__in=vehicles, is_resolved=False).count()

        # Positions actuelles (dernier ping de chaque device)
        fleet_status = []
        for v in vehicles:
            last_data = TelemetryData.objects.filter(vehicle=v).first()
            fleet_status.append({
                'vehicle': VehicleSerializer(v).data,
                'last_ping': last_data.timestamp if last_data else None,
                'fuel_level': last_data.fuel_level if last_data else None,
                'voltage': last_data.voltage if last_data else None,
                'location': {'lat': last_data.latitude, 'lng': last_data.longitude} if last_data else None
            })

        return Response({
            'total_vehicles': total_vehicles,
            'active_alerts_count': active_alerts,
            'fleet_status': fleet_status
        })

from api.services.engagement import EngagementService
from api.models import MaintenanceReminder, RegionalEvent, AppNotification

class MaintenanceReminderViewSet(viewsets.ModelViewSet):
    """
    Gestion des rappels d'entretien.
    """
    serializer_class = MaintenanceReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return MaintenanceReminder.objects.all()
        return MaintenanceReminder.objects.filter(vehicle__owner=user).order_by('due_date')

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        reminder = self.get_object()
        reminder.is_completed = True
        reminder.completion_date = timezone.now()
        reminder.save()
        return Response({'status': 'Rappel marqué comme effectué'})

class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'mechanic_profile'):
            return Appointment.objects.filter(mechanic=user.mechanic_profile)
        return Appointment.objects.filter(client=user)

    def perform_create(self, serializer):
        # Le client est l'utilisateur connecté
        appointment = serializer.save(client=self.request.user)

        # Message automatique pour initier la discussion
        from api.models import ChatMessage
        client_name = self.request.user.get_full_name() or self.request.user.username
        vehicle_info = "son véhicule"
        if appointment.vehicle:
            vehicle_info = f"le véhicule {appointment.vehicle.brand} {appointment.vehicle.model}"
        
        welcome_msg = f"Bonjour, je viens de prendre rendez-vous pour {vehicle_info} le {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M') if appointment.appointment_date else 'prochainement'}. Merci de confirmer la disponibilité."
        
        ChatMessage.objects.create(
            sender=self.request.user,
            receiver=appointment.mechanic.user,
            appointment=appointment,
            message=welcome_msg
        )

        # Notification pour le mécanicien
        try:
            mechanic_user = appointment.mechanic.user
            # Import différé pour éviter les imports circulaires si nécessaire
            from api.models import AppNotification

            client_phone = self.request.user.phone or "Non renseigné"

            vehicle_details = "Inconnu"
            if appointment.vehicle:
                v = appointment.vehicle
                year_str = f" ({v.year})" if v.year else ""
                vehicle_details = f"{v.brand} {v.model}{year_str} [{v.license_plate}]"

            AppNotification.objects.create(
                user=mechanic_user,
                appointment=appointment,
                title="Nouveau Rendez-vous !",
                message=f"Le client {client_name} (Tél: {client_phone}) a pris rendez-vous pour le véhicule {vehicle_details} le {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M') if appointment.appointment_date else 'Inconnue'}.",
                notification_type='APPOINTMENT',
                link=f"AppointmentDetails?id={appointment.id}"
            )
            print(f"[Push] Notification enregistrée pour le mécanicien: {mechanic_user.username}")
        except Exception as e:
            print(f"[Error] Échec de création de la notification: {str(e)}")

        # Ici, on déclencherait aussi un Push Notification réel (Firebase/OneSignal)
        # print(f"[Push] Notification envoyée au mécanicien: {mechanic_user.username}")

    @action(detail=True, methods=['patch'])
    def change_status(self, request, pk=None):
        appointment = self.get_object()
        old_status = appointment.status
        new_status = request.data.get('status')
        if new_status in dict(Appointment.STATUS_CHOICES):
            appointment.status = new_status
            appointment.save()

            # Message automatique et notification si le statut change
            if old_status != new_status:
                from api.models import ChatMessage, AppNotification
                status_label = dict(Appointment.STATUS_CHOICES).get(new_status)
                msg_text = f"Le statut de votre rendez-vous du {appointment.appointment_date.strftime('%d/%m/%Y') if appointment.appointment_date else ''} a été mis à jour : **{status_label}**."
                
                # Message dans le chat (de la part du mécanicien vers le client)
                ChatMessage.objects.create(
                    sender=appointment.mechanic.user,
                    receiver=appointment.client,
                    appointment=appointment,
                    message=msg_text
                )

                # Notification pour le client
                AppNotification.objects.create(
                    user=appointment.client,
                    appointment=appointment,
                    title="Mise à jour Rendez-vous",
                    message=msg_text,
                    notification_type='CHAT',
                    link=f"ChatDetail?appointment_id={appointment.id}"
                )

            return Response({'status': 'Statut mis à jour', 'new_status': new_status})
        return Response({'error': 'Statut invalide'}, status=400)

class GaragesListView(generics.ListAPIView):
    """
    Liste tous les garages certifiés à proximité.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(user_type='MECHANIC').exclude(shop_name__isnull=True)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        data = []
        from api.models import Mechanic
        for mech in queryset:
            profile = Mechanic.objects.filter(user=mech).first()
            data.append({
                'id': profile.id if profile else mech.id,
                'name': mech.shop_name or f"Garage {mech.first_name}",
                'location': mech.location or "Abidjan",
                'distance': "2.4 km",  # Simulation
                'is_certified': True,
                'phone': mech.phone if hasattr(mech, 'phone') else ""
            })
        return Response(data)

class ClientsSearchView(generics.ListAPIView):
    """
    Permet à un mécanicien de rechercher un client par nom, téléphone ou plaque.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', '')
        if len(query) < 2:
            return User.objects.none()
        
        return User.objects.filter(
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(phone__icontains=query) |
            models.Q(email__icontains=query) |
            models.Q(personal_vehicles__license_plate__icontains=query)
        ).filter(user_type='INDIVIDUAL').distinct()[:10]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        data = []
        for user in queryset:
            try:
                vehicles = list(user.personal_vehicles.values_list('license_plate', flat=True))
            except Exception:
                vehicles = []
            
            data.append({
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'phone': getattr(user, 'phone', ''),
                'email': user.email,
                'vehicles': vehicles
            })
        return Response(data)

class AppNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = AppNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AppNotification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': 'success'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        notification_type = request.query_params.get('type')
        queryset = self.get_queryset().filter(is_read=False)
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        count = queryset.count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """
        Permet au mécanicien de répondre à une notification.
        Si liée à un rendez-vous, met à jour le statut.
        Sinon, crée une notification de retour pour l'expéditeur.
        """
        notification = self.get_object()
        response_text = request.data.get('message', '')
        action_type = request.data.get('action') # ex: 'CONFIRM', 'CANCEL', 'REPLY'

        # 1. Gestion si c'est un rendez-vous
        if notification.appointment:
            appointment = notification.appointment
            if action_type == 'CONFIRM':
                appointment.status = 'CONFIRMED'
                appointment.save()
                # Notifier le client de la confirmation
                AppNotification.objects.create(
                    user=appointment.client,
                    appointment=appointment,
                    title="Rendez-vous confirmé !",
                    message=f"Le garage {request.user.shop_name} a confirmé votre RDV pour le {appointment.appointment_date}.",
                    notification_type='APPOINTMENT'
                )
                return Response({'status': 'appointment confirmed'})
            elif action_type == 'CANCEL':
                appointment.status = 'CANCELLED'
                appointment.save()
                # Notifier le client de l'annulation
                AppNotification.objects.create(
                    user=appointment.client,
                    appointment=appointment,
                    title="Rendez-vous annulé",
                    message=f"Le garage {request.user.shop_name} ne peut pas vous recevoir. Motif: {response_text}",
                    notification_type='APPOINTMENT'
                )
                return Response({'status': 'appointment cancelled'})
            elif action_type == 'REPLY':
                # Envoi d'un simple message lié au RDV
                AppNotification.objects.create(
                    user=appointment.client,
                    appointment=appointment,
                    title=f"Message de {request.user.shop_name}",
                    message=response_text,
                    notification_type='INFO'
                )
                return Response({'status': 'message sent'})

        # 2. Gestion de réponse générique (si pas de RDV)
        # On essaie d'extraire l'expéditeur depuis le message ou le contexte si possible.
        # Pour les notifications existantes sans lien formel, on peut envoyer une notification
        # à l'utilisateur concerné s'il est mentionné ou lié indirectement.
        # Ici on simule une réponse si on peut identifier un "owner" de véhicule lié à la notif

        return Response({'status': 'response sent', 'message': 'Votre réponse a été transmise.'})

class ChatMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def conversations(self, request):
        user = self.request.user
        from django.db.models import Max, Count, Q
        from api.models import ChatMessage, Appointment, User

        # On veut une entrée par interlocuteur unique
        # On récupère tous les messages impliquant l'utilisateur
        all_msgs = ChatMessage.objects.filter(Q(sender=user) | Q(receiver=user))
        
        # Trouver les IDs des interlocuteurs
        interlocutor_ids = set()
        for m in all_msgs:
            interlocutor_ids.add(m.sender_id if m.sender_id != user.id else m.receiver_id)
            
        results = []
        for ou_id in interlocutor_ids:
            try:
                other_user = User.objects.get(id=ou_id)
                # Dernier message avec cet utilisateur (peu importe le RDV)
                msgs = all_msgs.filter(Q(sender_id=ou_id) | Q(receiver_id=ou_id)).order_by('-created_at')
                last_msg = msgs.first()
                unread_count = msgs.filter(receiver=user, is_read=False).count()
                
                # On essaie de trouver le RDV le plus pertinent (le dernier)
                last_apt_msg = msgs.exclude(appointment=None).first()
                appointment_id = last_apt_msg.appointment_id if last_apt_msg else None
                
                title = ""
                if other_user.user_type == 'MECHANIC':
                    title = getattr(other_user, 'shop_name', None) or other_user.get_full_name() or other_user.username
                else:
                    title = other_user.get_full_name() or other_user.username

                results.append({
                    'id': f"user_{ou_id}",
                    'appointment_id': appointment_id,
                    'other_user_id': other_user.id,
                    'other_user': {
                        'id': other_user.id,
                        'name': other_user.get_full_name() or other_user.username,
                        'shop_name': getattr(other_user, 'shop_name', None) if other_user.user_type == 'MECHANIC' else None
                    },
                    'last_message': last_msg.message if last_msg else "",
                    'last_message_date': last_msg.created_at if last_msg else None,
                    'unread_count': unread_count,
                    'title': title
                })
            except User.DoesNotExist:
                continue

        # Trier le tout par date du dernier message
        from django.utils import timezone
        results.sort(key=lambda x: x['last_message_date'] or timezone.now(), reverse=True)

        return Response(results)

    @action(detail=False, methods=['post'])
    def mark_as_read(self, request):
        user = self.request.user
        appointment_id = request.data.get('appointment_id')
        other_user_id = request.data.get('other_user_id')

        queryset = ChatMessage.objects.filter(receiver=user, is_read=False)
        
        if other_user_id:
            # On marque tout comme lu pour cet interlocuteur, peu importe le RDV
            queryset = queryset.filter(sender_id=other_user_id)
        elif appointment_id:
            queryset = queryset.filter(appointment_id=appointment_id)

        count = queryset.update(is_read=True)
        
        # Invalider ou mettre à jour les notifications liées
        from api.models import AppNotification
        notif_qs = AppNotification.objects.filter(user=user, is_read=False, notification_type='CHAT')
        if other_user_id:
            # On marque toutes les notifications CHAT comme lues car l'utilisateur a ouvert sa messagerie
            # et on a déjà marqué les messages eux-mêmes comme lus ci-dessus.
            notif_qs.update(is_read=True)

        return Response({'marked_read': count})
    def get_queryset(self):
        user = self.request.user
        appointment_id = self.request.query_params.get('appointment')
        other_user_id = self.request.query_params.get('other_user')

        queryset = ChatMessage.objects.filter(
            models.Q(sender=user) | models.Q(receiver=user)
        )

        if other_user_id:
            # Filtrer tous les messages avec cet interlocuteur, peu importe le RDV
            queryset = queryset.filter(models.Q(sender_id=other_user_id) | models.Q(receiver_id=other_user_id))
        elif appointment_id:
            # Si on demande spécifiquement un RDV, on peut toujours filtrer par interlocuteur pour garder la continuité
            try:
                from api.models import Appointment
                apt = Appointment.objects.get(id=appointment_id)
                other_user = apt.mechanic.user if user == apt.client else apt.client
                queryset = queryset.filter(models.Q(sender=other_user) | models.Q(receiver=other_user))
            except:
                queryset = queryset.filter(appointment_id=appointment_id)

        return queryset

    def perform_create(self, serializer):
        appointment = serializer.validated_data.get('appointment')
        user = self.request.user

        # Déterminer le destinataire
        receiver = serializer.validated_data.get('receiver')
        if appointment and not receiver:
            # Si lié à un RDV, le destinataire est l'autre partie
            if user == appointment.client:
                receiver = appointment.mechanic.user
            else:
                receiver = appointment.client

        if not receiver:
            from rest_framework import serializers
            raise serializers.ValidationError("Destinataire introuvable.")

        message = serializer.save(sender=user, receiver=receiver)

        # Créer une notification pour le destinataire
        from api.models import AppNotification
        AppNotification.objects.create(
            user=receiver,
            appointment=appointment,
            title=f"Nouveau message de {user.get_full_name() or user.username}",
            message=message.message,
            notification_type='CHAT',
            link=f"ChatDetail?appointment_id={appointment.id if appointment else ''}"
        )

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # Validation supplémentaire : l'avis doit être lié à une intervention
        scan_session = serializer.validated_data.get('scan_session')
        appointment = serializer.validated_data.get('appointment')

        if not scan_session and not appointment:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Un avis doit obligatoirement être lié à un scan ou un rendez-vous.")

        serializer.save(user=self.request.user)

class SparePartStoreViewSet(viewsets.ModelViewSet):
    queryset = SparePartStore.objects.filter(is_active=True)
    serializer_class = SparePartStoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def nearby(self, request):
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius = float(request.query_params.get('radius', 10)) # 10km par défaut

        if not lat or not lng:
            return Response({"error": "Latitude and longitude are required"}, status=400)

        stores = SparePartStore.objects.filter(is_active=True)
        nearby_stores = []

        for store in stores:
            if store.latitude and store.longitude:
                dist = haversine(float(lng), float(lat), store.longitude, store.latitude)
                if dist <= radius:
                    store_data = SparePartStoreSerializer(store).data
                    store_data['distance'] = round(dist, 2)
                    nearby_stores.append(store_data)

        # Trier par distance
        nearby_stores.sort(key=lambda x: x['distance'])
        return Response(nearby_stores)

class SparePartViewSet(viewsets.ModelViewSet):
    queryset = SparePart.objects.all()
    serializer_class = SparePartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = SparePart.objects.all()
        dtc_code = self.request.query_params.get('dtc_code')
        if dtc_code:
            queryset = queryset.filter(compatible_dtcs__code=dtc_code)
        return queryset

class PersonalDashboardView(generics.RetrieveAPIView):
    """
    Vue synthétique pour le tableau de bord Particulier (INDIVIDUAL).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        if user.user_type != 'INDIVIDUAL' and not user.is_staff:
            return Response({"error": "Accès réservé aux particuliers"}, status=403)

        # Un particulier a généralement un seul véhicule principal associé à son compte
        vehicle = Vehicle.objects.filter(owner=user).first()

        if not vehicle:
            return Response({
                "has_vehicle": False,
                "message": "Aucun véhicule associé à votre compte personnel.",
                "vehicle": None,
                "last_ping": None,
                "fuel_stats": {
                    'current_level': 0,
                    'avg_consumption': 0,
                    'estimated_range': 0,
                    'cost_last_month': 0,
                },
                "health_score": 0,
                "active_alerts": [],
                "location": None
            })

        # Données de télémétrie récentes
        telemetry = TelemetryData.objects.filter(vehicle=vehicle).first()

        # Alertes prédictives non résolues
        alerts = PredictiveAlert.objects.filter(vehicle=vehicle, is_resolved=False)

        # --- Calcul dynamique du health_score depuis le dernier ScanSession ---
        last_scan = ScanSession.objects.filter(vehicle=vehicle).order_by('-date').first()
        if last_scan:
            dtc_count = last_scan.found_dtcs.count()
            base_score = 100
            # Chaque code DTC enlève des points selon sa sévérité
            base_score -= dtc_count * 10
            # Pénalité si le scan date de plus de 30 jours
            days_since_scan = (timezone.now() - last_scan.date).days if last_scan.date else 0
            if days_since_scan > 30:
                base_score -= 5
            health_score = max(0, min(100, base_score))
        else:
            health_score = 75  # Score neutre si aucun scan

        # --- Calcul dynamique des stats carburant depuis la télémétrie ---
        fuel_level = telemetry.fuel_level if telemetry else None
        # Consommation moyenne sur les 10 dernières entrées de télémétrie
        recent_telemetry = TelemetryData.objects.filter(vehicle=vehicle).order_by('-timestamp')[:10]
        fuel_levels = [t.fuel_level for t in recent_telemetry if t.fuel_level is not None]
        if len(fuel_levels) >= 2:
            # Estimation consommation : variation de niveau sur distance (simplifié)
            avg_consumption = round(abs(fuel_levels[0] - fuel_levels[-1]) / max(len(fuel_levels), 1) * 0.8 + 6.5, 2)
        else:
            avg_consumption = None  # Pas assez de données

        # Autonomie estimée : niveau actuel * capacité réservoir estimée / consommation
        if fuel_level is not None and avg_consumption:
            tank_capacity = 50  # Litres (valeur par défaut)
            estimated_range = round((fuel_level / 100) * tank_capacity / avg_consumption * 100, 2)
        else:
            estimated_range = None

        stats_fuel = {
            'current_level': fuel_level,
            'avg_consumption': avg_consumption,
            'estimated_range': estimated_range,
            'cost_last_month': None,  # Nécessite données de recharge
        }

        # --- Données du dernier scan pour prédiction ---
        last_scan_data = None
        if last_scan:
            last_scan_data = {
                'id': last_scan.id,
                'date': last_scan.date,
                'dtc_count': last_scan.found_dtcs.count(),
                'dtc_codes': list(last_scan.found_dtcs.values_list('code', flat=True)),
                'mileage': last_scan.mileage_dashboard,
            }

        # On utilise la position passée en paramètre ou celle de la dernière télémétrie
        lat_user = request.query_params.get('lat')
        lng_user = request.query_params.get('lng')

        if not lat_user or not lng_user:
            # Fallback sur la dernière position connue de télémétrie si dispo
            if telemetry and telemetry.latitude and telemetry.longitude:
                lat_user = telemetry.latitude
                lng_user = telemetry.longitude
        
        # S'assurer que lat/lng sont des flottants s'ils existent
        try:
            if lat_user: lat_user = float(lat_user)
            if lng_user: lng_user = float(lng_user)
        except (ValueError, TypeError):
            lat_user = lng_user = None

        nearby_mechanics = Mechanic.objects.filter(is_expert=True, is_active=True, latitude__isnull=False, longitude__isnull=False)
        nearby_garages_data = []

        for mech_profile in nearby_mechanics:
            dist = None
            if lat_user and lng_user:
                dist = haversine(lng_user, lat_user, mech_profile.longitude, mech_profile.latitude)
            
            # Formatage de la distance
            distance_str = f"{round(dist, 2)} km" if dist is not None else "Distance inconnue"

            # Trouver si l'utilisateur a une prestation notifiable pour ce garage
            # Un scan ou un RDV terminé qui n'a pas encore de review associée
            last_notifiable_scan = ScanSession.objects.filter(
                vehicle=vehicle, 
                mechanic=mech_profile, 
                review__isnull=True
            ).order_by('-date').first()
            
            last_notifiable_appt = Appointment.objects.filter(
                vehicle=vehicle, 
                mechanic=mech_profile, 
                status='COMPLETED', 
                review__isnull=True
            ).order_by('-appointment_date').first()

            nearby_garages_data.append({
                'id': mech_profile.id,
                'user_id': mech_profile.user.id,
                'name': mech_profile.shop_name or f"Garage {mech_profile.user.first_name}",
                'location': mech_profile.user.location or "Abidjan",
                'distance': distance_str,
                'distance_raw': dist, # Utile pour le tri
                'is_certified': mech_profile.is_expert,
                'specialties': mech_profile.specialties,
                'average_rating': mech_profile.average_rating,
                'review_count': mech_profile.review_count,
                'badges': mech_profile.badges, # Ajout des badges
                'notifiable_scan_id': last_notifiable_scan.id if last_notifiable_scan else None,
                'notifiable_appointment_id': last_notifiable_appt.id if last_notifiable_appt else None,
            })

        # Trier par distance si disponible
        if lat_user and lng_user:
            nearby_garages_data.sort(key=lambda x: x['distance_raw'] if x['distance_raw'] is not None else 9999)

        # Limiter à 5 garages pour le dashboard
        nearby_garages_data = nearby_garages_data[:5]

        # --- Rappels d'engagement (Phase 3) ---
        # Déclenchement de la génération automatique
        EngagementService.generate_seasonal_reminders(vehicle)
        if last_scan and last_scan.mileage_dashboard:
            EngagementService.sync_with_mileage(vehicle, last_scan.mileage_dashboard)

        reminders = MaintenanceReminder.objects.filter(
            vehicle=vehicle,
            is_completed=False
        ).order_by('due_date')[:3]

        reminders_data = MaintenanceReminderSerializer(reminders, many=True).data

        return Response({
            'has_vehicle': True,
            'vehicle': VehicleSerializer(vehicle).data,
            'last_ping': telemetry.timestamp if telemetry else None,
            'fuel_stats': stats_fuel,
            'health_score': health_score,
            'active_alerts': PredictiveAlertSerializer(alerts, many=True).data,
            'location': {'lat': telemetry.latitude, 'lng': telemetry.longitude} if telemetry else None,
            'last_scan': last_scan_data,
            'obd_data_source': 'telemetry' if telemetry else 'none',
            'nearby_garages': nearby_garages_data, # Ajout des garages réels
            'reminders': reminders_data, # Ajout des rappels d'entretien
        })
