from datetime import timedelta
from django.utils import timezone
from api.models import Subscription, Payment

class SubscriptionService:
    @staticmethod
    def create_pending_payment(user, plan, duration_months=1, payment_method='WAVE'):
        """
        Prépare un enregistrement de paiement en attente.
        """
        # On ne crée plus d'objet Subscription ici pour éviter de polluer le frontend
        # avec des abonnements inactifs. On stocke juste le paiement.
        from api.models import SubscriptionPlan
        
        total_amount = plan.price * duration_months
        
        # On crée le paiement sans lui lier de souscription pour le moment
        # On lie l'utilisateur via une propriété temporaire ou on adapte le modèle Payment
        # Alternative: Créer la souscription MAIS ne pas la renvoyer dans le get_queryset si is_active=False
        
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            end_date=timezone.now(), # Date fictive
            is_active=False
        )
        
        payment = Payment.objects.create(
            subscription=subscription,
            amount=total_amount,
            transaction_id=f"PENDING-{subscription.id}-{timezone.now().timestamp()}",
            payment_method=payment_method,
            status='PENDING'
        )
        
        return payment

    @staticmethod
    def confirm_payment(payment, transaction_id):
        """
        Confirme un paiement et active la souscription associée.
        """
        if payment.status == 'SUCCESS':
            return payment.subscription

        subscription = payment.subscription
        user = subscription.user
        plan = subscription.plan
        
        # Calcul de la durée (logique similaire à activate_subscription)
        active_sub = Subscription.objects.filter(user=user, is_active=True).exclude(id=subscription.id).first()
        trial_days_remaining = 0
        if active_sub and active_sub.plan and active_sub.plan.tier == 'TRIAL':
            remaining = active_sub.end_date - timezone.now()
            total_seconds = remaining.total_seconds()
            if total_seconds > 0:
                trial_days_remaining = int(total_seconds // 86400)

        # Désactiver les anciens abonnements
        Subscription.objects.filter(user=user, is_active=True).exclude(id=subscription.id).update(is_active=False)

        # Calcul de la nouvelle date de fin (basé sur 30 jours par mois par défaut pour l'instant)
        # On pourrait passer duration_months si on le stockait, ici on suppose 1 mois par défaut ou on le déduit du montant
        duration_months = 1
        if plan.price > 0:
            duration_months = int(payment.amount / plan.price)
            
        duration_days = (duration_months * 30) + trial_days_remaining
        subscription.end_date = timezone.now() + timedelta(days=duration_days)
        subscription.is_active = True
        subscription.save()

        # Mettre à jour le paiement
        payment.status = 'SUCCESS'
        payment.transaction_id = transaction_id
        payment.save()

        return subscription

    @staticmethod
    def activate_trial(user):
        """
        Active une période d'essai gratuite si l'utilisateur n'en a pas déjà profité.
        Utilise les paramètres du plan TRIAL défini en base.
        """
        if user.has_used_trial:
            return None

        from api.models import SubscriptionPlan
        # On cherche un plan de type TRIAL pour le type d'utilisateur correspondant
        trial_plan = SubscriptionPlan.objects.filter(
            tier='TRIAL',
            target_user_type=user.user_type
        ).first()

        if not trial_plan:
            # Création d'un plan par défaut si inexistant
            trial_plan = SubscriptionPlan.objects.create(
                name="Essai Gratuit 14 Jours",
                target_user_type=user.user_type,
                tier='TRIAL',
                price=0,
                duration_days=14,
                description="Période d'essai gratuite pour découvrir l'application."
            )

        # Désactiver les abonnements actuels
        Subscription.objects.filter(user=user, is_active=True).update(is_active=False)

        end_date = timezone.now() + timedelta(days=trial_plan.duration_days)
        subscription = Subscription.objects.create(
            user=user,
            plan=trial_plan,
            end_date=end_date,
            is_active=True
        )

        user.has_used_trial = True
        user.save()

        return subscription

    @staticmethod
    def activate_subscription(user, plan, transaction_id, duration_months=1, payment_method='WAVE'):
        """
        Crée une nouvelle souscription après paiement réussi.
        La durée est calculée en mois (30 jours par mois).
        Désactive automatiquement toute souscription active précédente.
        Si l'utilisateur est en période d'essai, on ajoute les jours restants.
        """
        active_sub = Subscription.objects.filter(user=user, is_active=True).first()
        trial_days_remaining = 0
        if active_sub and active_sub.plan and active_sub.plan.tier == 'TRIAL':
            remaining = active_sub.end_date - timezone.now()
            # On utilise total_seconds pour avoir une précision à la seconde près
            total_seconds = remaining.total_seconds()
            if total_seconds > 0:
                # On arrondit à l'entier supérieur pour ne pas perdre de jours
                trial_days_remaining = int(total_seconds // 86400)

        # Désactiver les abonnements actuels pour garantir un seul abonnement actif
        Subscription.objects.filter(user=user, is_active=True).update(is_active=False)

        duration_days = (duration_months * 30) + trial_days_remaining
        end_date = timezone.now() + timedelta(days=duration_days)
        total_amount = plan.price * duration_months

        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            end_date=end_date,
            is_active=True
        )

        try:
            Payment.objects.create(
                subscription=subscription,
                amount=total_amount,
                transaction_id=transaction_id,
                payment_method=payment_method,
                status='SUCCESS'
            )
        except Exception as e:
            # Si le paiement échoue (ex: transaction_id en double), on annule la souscription
            subscription.delete()
            raise e

        return subscription, trial_days_remaining

    @staticmethod
    def is_subscription_valid(user):
        """
        Vérifie si l'utilisateur a un abonnement actif.
        """
        return Subscription.objects.filter(
            user=user,
            is_active=True,
            end_date__gt=timezone.now()
        ).exists()

    @staticmethod
    def change_subscription(user, new_plan, transaction_id, duration_months=1, payment_method='WAVE'):
        """
        Bascule vers un nouveau plan d'abonnement.
        """
        # Si on passe un objet Mechanic ou FleetOwner au lieu d'un User, on récupère le User
        user_obj = getattr(user, 'user', user)
        return SubscriptionService.activate_subscription(user_obj, new_plan, transaction_id, duration_months, payment_method)
