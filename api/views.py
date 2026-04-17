from rest_framework import viewsets, status, permissions, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.authtoken.models import Token
from api.models import (
    Mechanic, Vehicle, DTCReference, ScanSession, SubscriptionPlan, 
    Subscription, User, Payment, VehicleModel, GlobalSettings, 
    UpcomingModule, WelcomeContent, IoTDevice, TelemetryData, PredictiveAlert
)
from api.serializers import (
    MechanicSerializer, VehicleSerializer, DTCReferenceSerializer,
    ScanSessionSerializer, SubscriptionPlanSerializer, SubscriptionSerializer,
    RegisterSerializer, UserSerializer, VehicleModelSerializer, ChangePasswordSerializer, UpcomingModuleSerializer,
    WelcomeContentSerializer, IoTDeviceSerializer, TelemetryDataSerializer, PredictiveAlertSerializer
)
from api.services.diagnostics import DiagnosticService
from api.services.subscriptions import SubscriptionService

from django.db.models import Sum, Count
from django.utils import timezone

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
                    serializer = self.get_serializer(mechanic, data=request.data, partial=(request.method == 'PATCH'))
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    data = serializer.data
                else:
                    data = MechanicSerializer(mechanic).data
                
                if 'user_type' not in data:
                    data['user_type'] = user.user_type
                return Response(data)
            except Mechanic.DoesNotExist:
                pass # On retombe sur le cas User de base

        # Pour les autres types d'utilisateurs
        if request.method in ['PATCH', 'PUT']:
            serializer = UserSerializer(user, data=request.data, partial=(request.method == 'PATCH'))
            serializer.is_valid(raise_exception=True)
            serializer.save()
            data = serializer.data
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
        is_valid = SubscriptionService.is_subscription_valid(mechanic)
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
            subscription = SubscriptionService.change_subscription(
                mechanic, plan, transaction_id, duration_months, payment_method
            )

            return Response({
                'message': 'Plan d\'abonnement mis à jour avec succès',
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
    lookup_field = 'license_plate'

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return Vehicle.objects.all()

            # On montre les véhicules qui ont été scannés par ce mécanicien
            # OU les véhicules qu'il a recherchés par plaque (potentiellement)
            # Pour l'instant on garde ceux qu'il a scannés au moins une fois
            return Vehicle.objects.filter(scansession__mechanic__user=self.request.user).distinct()
        return Vehicle.objects.none()

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

            # Un mécanicien ne voit QUE ses propres scans (dans son garage)
            return ScanSession.objects.filter(
                mechanic__user=self.request.user
            ).select_related('mechanic__user', 'vehicle').prefetch_related('found_dtcs').order_by('-date')
        return ScanSession.objects.none()

    def create(self, request, *args, **kwargs):
        # Utilise le service pour la création
        mechanic = Mechanic.objects.get(user=request.user)

        # Vérification d'abonnement
        if not SubscriptionService.is_subscription_valid(mechanic):
            return Response(
                {
                    'error': 'Abonnement requis',
                    'detail': 'Votre abonnement est expiré ou inexistant. Veuillez souscrire à un plan.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        vehicle_data = request.data.get('vehicle')

        # Validation manuelle du véhicule via le serializer
        # Note: On utilise partial=True pour ne pas bloquer si le véhicule existe déjà
        # (le serializer VehicleSerializer pourrait renvoyer une erreur d'unicité sur license_plate)
        license_plate = vehicle_data.get('license_plate')
        existing_vehicle = Vehicle.objects.filter(license_plate__iexact=license_plate).first()

        vehicle_serializer = VehicleSerializer(existing_vehicle, data=vehicle_data, partial=True)
        if not vehicle_serializer.is_valid():
            return Response(vehicle_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Utilisation des données validées
        vehicle_data = vehicle_serializer.validated_data

        dtc_codes = request.data.get('dtc_codes', [])
        notes = request.data.get('notes', '')

        # Données d'expertise optionnelles
        mileage_data = request.data.get('mileage_data')
        safety_data = request.data.get('safety_data')

        # Ajout des champs de coûts s'ils sont présents
        actual_labor_cost = request.data.get('actual_labor_cost', 0)
        actual_parts_cost = request.data.get('actual_parts_cost', 0)
        is_completed = request.data.get('is_completed', False)
        scan_type = request.data.get('scan_type', 'DIAGNOSTIC')

        # ÉVITER LES DOUBLONS : Si on reçoit un ID, c'est une mise à jour
        scan_id = request.data.get('id')
        if scan_id:
            try:
                scan = ScanSession.objects.get(id=scan_id, mechanic=mechanic)

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
                dtc_refs = DTCReference.objects.filter(code__in=dtc_codes)
                scan.found_dtcs.set(dtc_refs)

                serializer = self.get_serializer(scan)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except (ScanSession.DoesNotExist, ValueError):
                pass

        # Déduplication intelligente : Si un scan pour ce véhicule par ce mécanicien existe déjà
        # dans les 60 dernières secondes (pour éviter les double-clics/erreurs de synchro),
        # on le met à jour au lieu d'en créer un nouveau.
        time_window = timezone.now() - timezone.timedelta(seconds=60)
        recent_scan = ScanSession.objects.filter(
            mechanic=mechanic,
            vehicle__license_plate=vehicle_data.get('license_plate', 'INCONNU'),
            date__gte=time_window
        ).first()

        if recent_scan:
            recent_scan.notes = notes
            recent_scan.actual_labor_cost = actual_labor_cost
            recent_scan.actual_parts_cost = actual_parts_cost
            recent_scan.is_completed = is_completed
            
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

            dtc_refs = []
            for code in dtc_codes:
                ref = DTCReference.objects.filter(code=code, brand=recent_scan.vehicle.brand).first()
                if not ref:
                    ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()
                if ref:
                    dtc_refs.append(ref)
            recent_scan.found_dtcs.set(dtc_refs)

            serializer = self.get_serializer(recent_scan)
            return Response(serializer.data, status=status.HTTP_200_OK)

        scan = DiagnosticService.record_scan(
            mechanic, 
            vehicle_data, 
            dtc_codes, 
            notes, 
            mileage_data=mileage_data, 
            safety_data=safety_data,
            scan_type=scan_type
        )

        # Mise à jour des coûts initiaux
        scan.actual_labor_cost = actual_labor_cost
        scan.actual_parts_cost = actual_parts_cost
        scan.is_completed = is_completed
        scan.save()

        serializer = self.get_serializer(scan)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer

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
        return Subscription.objects.filter(mechanic__user=self.request.user)

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
            subscription = SubscriptionService.activate_subscription(mechanic, plan, transaction_id)
            return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return TelemetryData.objects.none()
        if user.is_staff:
            return TelemetryData.objects.all()
        return TelemetryData.objects.filter(vehicle__fleet_owner=user)

    def create(self, request, *args, **kwargs):
        """
        Endpoint ultra-rapide pour les boîtiers.
        Format attendu: { "imei": "...", "voltage": 12.5, "fuel_level": 80, ... }
        """
        imei = request.data.get('imei')
        try:
            device = IoTDevice.objects.get(imei=imei, status='ACTIVE')
        except IoTDevice.DoesNotExist:
            return Response({"error": "Device non reconnu ou inactif"}, status=status.HTTP_403_FORBIDDEN)

        if not device.vehicle:
            return Response({"error": "Device non associé à un véhicule"}, status=status.HTTP_400_BAD_REQUEST)

        # Préparation des données
        data = request.data.copy()
        data['device'] = device.id
        data['vehicle'] = device.vehicle.id

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Analyse "Predictive" rapide en tâche de fond (simulée ici)
        self._analyze_telemetry(device.vehicle, serializer.validated_data)

        # Mise à jour du dernier ping
        device.last_ping = timezone.now()
        device.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _analyze_telemetry(self, vehicle, data):
        """
        Logique simplifiée pour les alertes prédictives.
        """
        # 1. Vérification Batterie
        voltage = data.get('voltage')
        if voltage and voltage < 11.8:
            PredictiveAlert.objects.get_or_create(
                vehicle=vehicle,
                alert_type='BATTERY',
                severity='WARNING',
                is_resolved=False,
                defaults={'message': "Tension batterie faible détectée. Risque de non-démarrage."}
            )
        
        # 2. Vérification Siphonnage (simplifié: baisse brutale > 5% sans moteur tournant/vitesse)
        # Nécessiterait de comparer avec le record précédent.
        
        # 3. Score conduite (accélérations brutales)
        accel_x = data.get('accel_x', 0)
        accel_y = data.get('accel_y', 0)
        if abs(accel_x) > 2.0 or abs(accel_y) > 2.0: # Seuils arbitraires
            PredictiveAlert.objects.create(
                vehicle=vehicle,
                alert_type='DRIVING',
                severity='INFO',
                message="Accélération ou freinage brutal détecté."
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
