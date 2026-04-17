from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    MechanicViewSet, VehicleViewSet, ScanSessionViewSet,
    SubscriptionPlanViewSet, SubscriptionViewSet, RegisterView, AdminDashboardView,
    VehicleModelViewSet, DTCReferenceViewSet, GlobalSettingsView, UpcomingModuleViewSet,
    WelcomeContentViewSet, IoTDeviceViewSet, TelemetryViewSet, PredictiveAlertViewSet, FleetDashboardView,
    PersonalDashboardView
)

router = DefaultRouter()
router.register(r'users', MechanicViewSet, basename='user')
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

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('fleet-dashboard/', FleetDashboardView.as_view(), name='fleet-dashboard'),
    path('personal-dashboard/', PersonalDashboardView.as_view(), name='personal-dashboard'),
    path('settings/', GlobalSettingsView.as_view(), name='global-settings'),
    path('', include(router.urls)),
]
