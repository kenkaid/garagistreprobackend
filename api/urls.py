from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    MechanicViewSet, VehicleViewSet, ScanSessionViewSet,
    SubscriptionPlanViewSet, SubscriptionViewSet, RegisterView, AdminDashboardView,
    VehicleModelViewSet, DTCReferenceViewSet, GlobalSettingsView, UpcomingModuleViewSet,
    WelcomeContentViewSet, IoTDeviceViewSet, TelemetryViewSet, PredictiveAlertViewSet, FleetDashboardView,
    PersonalDashboardView, WavePaymentInitView, WaveWebhookView, AppConfigView, AppointmentViewSet,
    GaragesListView, ClientsSearchView, MaintenanceReminderViewSet, AppNotificationViewSet, ChatMessageViewSet,
    ReviewViewSet, SparePartStoreViewSet, SparePartViewSet
)

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'messages', ChatMessageViewSet, basename='message')
router.register(r'notifications', AppNotificationViewSet, basename='notification')
router.register(r'reminders', MaintenanceReminderViewSet, basename='reminder')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'users', MechanicViewSet, basename='user')
router.register(r'mechanics', MechanicViewSet, basename='mechanic')
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'vehicle-models', VehicleModelViewSet, basename='vehicle-model')
router.register(r'scans', ScanSessionViewSet, basename='scan')
router.register(r'dtcs', DTCReferenceViewSet, basename='dtc')
router.register(r'plans', SubscriptionPlanViewSet, basename='plan')
router.register(r'upcoming-modules', UpcomingModuleViewSet, basename='upcoming-module')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'welcome-content', WelcomeContentViewSet, basename='welcome-content')
router.register(r'devices', IoTDeviceViewSet, basename='device')
router.register(r'telemetry', TelemetryViewSet, basename='telemetry')
router.register(r'alerts', PredictiveAlertViewSet, basename='alert')
router.register(r'spare-part-stores', SparePartStoreViewSet, basename='spare-part-store')
router.register(r'spare-parts', SparePartViewSet, basename='spare-part')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('fleet-dashboard/', FleetDashboardView.as_view(), name='fleet-dashboard'),
    path('personal-dashboard/', PersonalDashboardView.as_view(), name='personal-dashboard'),
    path('garages/', GaragesListView.as_view(), name='garages-list'),
    path('clients/search/', ClientsSearchView.as_view(), name='clients-search'),
    path('payments/wave/init/', WavePaymentInitView.as_view(), name='wave-init'),
    path('payments/wave/webhook/', WaveWebhookView.as_view(), name='wave-webhook'),
    path('settings/', GlobalSettingsView.as_view(), name='global-settings'),
    path('app-config/', AppConfigView.as_view(), name='app-config'),
    path('', include(router.urls)),
]
