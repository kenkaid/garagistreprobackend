from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.urls import path
from django.shortcuts import render, redirect
from django.db.models import Sum
from django.utils import timezone
from api.models import (
    User, Mechanic, Vehicle, DTCReference, ScanSession, SubscriptionPlan,
    Subscription, Payment, VehicleModel, GlobalSettings, UpcomingModule,
    WelcomeContent, IoTDevice, TelemetryData, PredictiveAlert
)
from api.services.subscriptions import SubscriptionService

class GaragisteAdminSite(admin.AdminSite):
    site_header = "Administration Garagiste Pro"
    site_title = "Garagiste Pro Admin"
    index_title = "Tableau de Bord de Gestion"

    def get_app_list(self, request, app_label=None):
        """
        Custom app list to group models into 'Garagiste Pro' and 'Prévention des pannes'.
        """
        app_dict = self._build_app_dict(request, app_label)
        if not app_dict:
            return []

        # List of models in each group
        garagiste_models = [
            'Mechanic', 'Vehicle', 'VehicleModel', 'DTCReference',
            'ScanSession', 'SubscriptionPlan', 'Subscription', 'Payment'
        ]
        prevention_models = [
            'IoTDevice', 'TelemetryData', 'PredictiveAlert'
        ]
        config_models = [
            'User', 'GlobalSettings', 'UpcomingModule', 'WelcomeContent'
        ]

        # Extract all models from api app
        api_models = []
        if 'api' in app_dict:
            api_models = app_dict['api']['models']

        # If User is in auth app, we might want to include it too if not re-registered
        if 'auth' in app_dict:
            api_models.extend(app_dict['auth']['models'])

        def get_model_data(name):
            for m in api_models:
                if m['object_name'] == name:
                    return m
            return None

        # Reconstruct apps
        new_app_list = []

        # Group 1: Garagiste Pro
        gp_models = []
        for name in garagiste_models:
            data = get_model_data(name)
            if data: gp_models.append(data)

        if gp_models:
            new_app_list.append({
                'name': '🛠️ Garagiste Pro',
                'app_label': 'garagiste_pro',
                'models': gp_models,
            })

        # Group 2: Prévention des pannes
        pp_models = []
        for name in prevention_models:
            data = get_model_data(name)
            if data: pp_models.append(data)

        if pp_models:
            new_app_list.append({
                'name': '🛡️ Prévention des pannes',
                'app_label': 'prevention_pannes',
                'models': pp_models,
            })

        # Group 3: Configuration & Contenu
        cc_models = []
        for name in config_models:
            data = get_model_data(name)
            if data: cc_models.append(data)

        if cc_models:
            new_app_list.append({
                'name': '⚙️ Configuration & Contenu',
                'app_label': 'config_contenu',
                'models': cc_models,
            })

        # Add other apps if any that are not already handled
        handled_apps = ['api', 'auth']
        for label, app in app_dict.items():
            if label not in handled_apps:
                new_app_list.append(app)

        return new_app_list

admin_site = GaragisteAdminSite(name='garagiste_admin')

@admin.register(User, site=admin_site)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Info Pro', {'fields': ('user_type', 'is_mechanic', 'phone', 'shop_name', 'location', 'has_used_trial')}),
    )
    list_display = UserAdmin.list_display + ('user_type', 'is_mechanic', 'shop_name', 'has_used_trial', 'subscription_status')
    list_filter = UserAdmin.list_filter + ('user_type', 'is_mechanic', 'has_used_trial')
    search_fields = UserAdmin.search_fields + ('phone', 'shop_name')
    actions = ['activate_trial_manually', 'deactivate_subscription']

    def subscription_status(self, obj):
        sub = obj.active_subscription
        if sub:
            return f"{sub.plan.name} (jusqu'au {sub.end_date.strftime('%d/%m/%Y')})"
        return "Aucun"
    subscription_status.short_description = "Abonnement Actif"

    def activate_trial_manually(self, request, queryset):
        for user in queryset:
            # On réinitialise has_used_trial pour permettre la réactivation si besoin
            user.has_used_trial = False
            user.save()
            SubscriptionService.activate_trial(user)
        self.message_user(request, f"Période d'essai activée pour {queryset.count()} utilisateurs.")
    activate_trial_manually.short_description = "Activer manuellement la période d'essai"

    def deactivate_subscription(self, request, queryset):
        for user in queryset:
            Subscription.objects.filter(user=user, is_active=True).update(is_active=False)
        self.message_user(request, f"Abonnements désactivés pour {queryset.count()} utilisateurs.")
    deactivate_subscription.short_description = "Désactiver tous les abonnements"

@admin.register(GlobalSettings, site=admin_site)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_test_mode', 'server_ip', 'updated_at')

    def has_add_permission(self, request):
        return not GlobalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_financial_link'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_site.admin_view(self.dashboard_view), name='global-financial-dashboard'),
        ]
        return custom_urls + urls

    def dashboard_view(self, request):
        payments = Payment.objects.filter(status='SUCCESS')
        total_revenue = float(payments.aggregate(Sum('amount'))['amount__sum'] or 0)
        total_mechanics = Mechanic.objects.count()
        active_subscriptions = Subscription.objects.filter(is_active=True, end_date__gt=timezone.now()).count()
        total_scans = ScanSession.objects.count()

        monthly_revenue = []
        now = timezone.now()
        max_rev = 0

        for i in range(5, -1, -1):
            month_date = now - timezone.timedelta(days=i*30)
            month_name = month_date.strftime('%b')
            month_year = month_date.year
            month_num = month_date.month

            rev = payments.filter(payment_date__year=month_year, payment_date__month=month_num).aggregate(Sum('amount'))['amount__sum'] or 0
            rev = float(rev)
            if rev > max_rev:
                max_rev = rev

            monthly_revenue.append({
                'month': month_name,
                'revenue': rev
            })

        for item in monthly_revenue:
            item['percentage'] = (item['revenue'] / max_rev * 90) + 5 if max_rev > 0 else 5

        context = {
            **self.admin_site.each_context(request),
            'title': "Bilan Financier Global",
            'total_revenue_global': total_revenue,
            'total_mechanics': total_mechanics,
            'active_subscriptions': active_subscriptions,
            'total_scans_performed': total_scans,
            'monthly_revenue': monthly_revenue,
            'currency': 'FCFA',
        }
        return render(request, 'admin/api/dashboard.html', context)

admin_site.register(Mechanic)
admin_site.register(Vehicle)
admin_site.register(VehicleModel)

@admin.register(DTCReference, site=admin_site)
class DTCReferenceAdmin(admin.ModelAdmin):
    list_display = ('code', 'brand', 'description')
    list_filter = ('brand',)
    search_fields = ('code', 'description')

admin_site.register(ScanSession)
@admin.register(SubscriptionPlan, site=admin_site)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'target_user_type', 'tier', 'price', 'duration_days')
    list_filter = ('target_user_type', 'tier')
    search_fields = ('name', 'description')

admin_site.register(Subscription)
admin_site.register(Payment)

@admin.register(IoTDevice, site=admin_site)
class IoTDeviceAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'imei', 'vehicle', 'status', 'last_ping')
    list_filter = ('status',)
    search_fields = ('serial_number', 'imei', 'vehicle__vin', 'vehicle__license_plate')

@admin.register(TelemetryData, site=admin_site)
class TelemetryDataAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'timestamp', 'voltage', 'fuel_level', 'speed', 'rpm')
    list_filter = ('vehicle', 'timestamp')
    date_hierarchy = 'timestamp'

@admin.register(PredictiveAlert, site=admin_site)
class PredictiveAlertAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'alert_type', 'severity', 'is_resolved', 'created_at')
    list_filter = ('alert_type', 'severity', 'is_resolved')
    search_fields = ('message', 'vehicle__vin')

@admin.register(UpcomingModule, site=admin_site)
class UpcomingModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'expected_release_date', 'is_active')
    list_filter = ('applicable_plans', 'is_active')
    search_fields = ('name', 'description')
    filter_horizontal = ('applicable_plans',)

@admin.register(WelcomeContent, site=admin_site)
class WelcomeContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_active', 'created_at')
    list_editable = ('order', 'is_active')
    search_fields = ('title', 'description')
