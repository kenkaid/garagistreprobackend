from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.urls import path
from django.shortcuts import render, redirect
from django.db.models import Sum
from django.utils import timezone
from api.services.subscriptions import SubscriptionService

# --- CONFIGURATION DU SITE ADMIN ---

class GaragisteAdminSite(admin.AdminSite):
    site_header = "Administration Garagiste Pro"
    site_title = "Garagiste Pro Admin"
    index_title = "Tableau de Bord de Gestion"

    def get_app_list(self, request, app_label=None):
        """
        Custom app list to group models into 'Garagiste Pro', 'Prévention des pannes' and 'Configuration'.
        """
        app_dict = self._build_app_dict(request, app_label)
        if not app_dict:
            return []

        # List of models in each group
        garagiste_models = [
            'Mechanic', 'Vehicle', 'VehicleModel', 'DTCReference',
            'ScanSession', 'SubscriptionPlan', 'Subscription', 'Payment',
            'Review'
        ]
        prevention_models = [
            'IoTDevice', 'TelemetryData', 'PredictiveAlert',
            'MaintenanceReminder', 'RegionalEvent', 'AppNotification'
        ]
        store_models = [
            'SparePartStore', 'SparePartCategory', 'SparePart'
        ]
        config_models = [
            'User', 'GlobalSettings', 'UpcomingModule', 'WelcomeContent', 'Appointment', 'ChatMessage'
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

        # Group 3: Drive-to-Store
        ds_models = []
        for name in store_models:
            data = get_model_data(name)
            if data: ds_models.append(data)

        if ds_models:
            new_app_list.append({
                'name': '🛒 Drive-to-Store',
                'app_label': 'drive_to_store',
                'models': ds_models,
            })

        # Group 4: Configuration & Contenu
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

# --- IMPORTS DES MODÈLES ---
from api.models import (
    User, Mechanic, Vehicle, DTCReference, ScanSession, SubscriptionPlan,
    Subscription, Payment, VehicleModel, GlobalSettings, UpcomingModule,
    WelcomeContent, IoTDevice, TelemetryData, PredictiveAlert,
    MaintenanceReminder, RegionalEvent, Appointment, AppNotification, ChatMessage,
    SparePartStore, SparePartCategory, SparePart, Review
)

# --- CLASSES ADMIN ---

@admin.register(ChatMessage, site=admin_site)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'appointment', 'message_snippet', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('message', 'sender__username', 'receiver__username')
    raw_id_fields = ('sender', 'receiver', 'appointment')

    def message_snippet(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_snippet.short_description = "Message"

@admin.register(AppNotification, site=admin_site)
class AppNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'appointment', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'user__username', 'appointment__client__username')
    raw_id_fields = ('user', 'appointment')

@admin.register(Appointment, site=admin_site)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('client', 'mechanic', 'appointment_date', 'status', 'created_at')
    list_filter = ('status', 'appointment_date')
    search_fields = ('client__username', 'mechanic__shop_name', 'reason')
    date_hierarchy = 'appointment_date'

@admin.register(MaintenanceReminder, site=admin_site)
class MaintenanceReminderAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'reminder_type', 'title', 'due_date', 'is_completed')
    list_filter = ('reminder_type', 'is_completed')
    search_fields = ('vehicle__license_plate', 'title')

@admin.register(RegionalEvent, site=admin_site)
class RegionalEventAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_month', 'end_month')

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
            plan_name = sub.plan.name if sub.plan else "Plan inconnu"
            end_date = sub.end_date.strftime('%d/%m/%Y') if sub.end_date else "?"
            return f"{plan_name} (jusqu'au {end_date})"
        return "Aucun"
    subscription_status.short_description = "Abonnement Actif"

    def activate_trial_manually(self, request, queryset):
        for user in queryset:
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

@admin.register(Review, site=admin_site)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('mechanic', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('mechanic__shop_name', 'user__username', 'comment')
    raw_id_fields = ('mechanic', 'user', 'scan_session', 'appointment')

@admin.register(DTCReference, site=admin_site)
class DTCReferenceAdmin(admin.ModelAdmin):
    list_display = ('code', 'brand', 'description')
    list_filter = ('brand',)
    search_fields = ('code', 'description')

@admin.register(SubscriptionPlan, site=admin_site)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'target_user_type', 'tier', 'price', 'duration_days')
    list_filter = ('target_user_type', 'tier')
    search_fields = ('name', 'description')

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

@admin.register(SparePartStore, site=admin_site)
class SparePartStoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_name', 'phone', 'is_active')
    search_fields = ('name', 'location_name')

@admin.register(SparePartCategory, site=admin_site)
class SparePartCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')
    autocomplete_fields = ('compatible_dtcs',)

@admin.register(SparePart, site=admin_site)
class SparePartAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'store', 'price', 'brand', 'stock_status')
    list_filter = ('category', 'store', 'stock_status')
    search_fields = ('name', 'brand', 'category__name')
    raw_id_fields = ('category', 'store')

@admin.register(WelcomeContent, site=admin_site)
class WelcomeContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_active', 'created_at')
    list_editable = ('order', 'is_active')
    search_fields = ('title', 'description')

@admin.register(Mechanic, site=admin_site)
class MechanicAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'user', 'is_expert', 'average_rating', 'review_count')
    list_filter = ('is_expert',)
    search_fields = ('shop_name', 'user__username', 'specialties')
    raw_id_fields = ('user',)

@admin.register(Vehicle, site=admin_site)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'brand', 'model', 'year', 'owner')
    list_filter = ('brand', 'year')
    search_fields = ('license_plate', 'vin', 'owner__username', 'owner_name')
    raw_id_fields = ('owner', 'fleet_owner')

@admin.register(VehicleModel, site=admin_site)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ('brand', 'model', 'year_start', 'year_end')
    list_filter = ('brand',)
    search_fields = ('brand', 'model')

@admin.register(ScanSession, site=admin_site)
class ScanSessionAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'mechanic', 'scan_type', 'date', 'total_cost')
    list_filter = ('scan_type', 'date')
    search_fields = ('vehicle__license_plate', 'mechanic__shop_name')
    raw_id_fields = ('vehicle', 'mechanic')

@admin.register(Subscription, site=admin_site)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'plan')
    raw_id_fields = ('user', 'mechanic')

@admin.register(Payment, site=admin_site)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'subscription', 'amount', 'payment_method', 'status', 'payment_date')
    list_filter = ('status', 'payment_method')
    search_fields = ('transaction_id',)
    raw_id_fields = ('subscription',)

# Suppression des enregistrements simples redondants
