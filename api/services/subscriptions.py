from datetime import timedelta
from django.utils import timezone
from api.models import Subscription, Payment

class SubscriptionService:
    @staticmethod
    def activate_subscription(mechanic, plan, transaction_id, duration_months=1, payment_method='WAVE'):
        """
        Crée une nouvelle souscription après paiement réussi.
        La durée est calculée en mois (30 jours par mois).
        Désactive automatiquement toute souscription active précédente.
        """
        # Désactiver les abonnements actuels pour garantir un seul abonnement actif
        Subscription.objects.filter(mechanic=mechanic, is_active=True).update(is_active=False)

        duration_days = duration_months * 30
        end_date = timezone.now() + timedelta(days=duration_days)
        total_amount = plan.price * duration_months

        subscription = Subscription.objects.create(
            mechanic=mechanic,
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

        return subscription

    @staticmethod
    def is_subscription_valid(mechanic):
        """
        Vérifie si le mécanicien a un abonnement actif.
        """
        return Subscription.objects.filter(
            mechanic=mechanic,
            is_active=True,
            end_date__gt=timezone.now()
        ).exists()

    @staticmethod
    def change_subscription(mechanic, new_plan, transaction_id, duration_months=1, payment_method='WAVE'):
        """
        Bascule vers un nouveau plan d'abonnement.
        Alias pour activate_subscription qui gère maintenant la désactivation des anciens.
        """
        return SubscriptionService.activate_subscription(mechanic, new_plan, transaction_id, duration_months, payment_method)
