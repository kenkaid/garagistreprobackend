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
        Confirme un paiement et active ou prolonge la souscription associée.
        """
        if payment.status == 'SUCCESS':
            return payment.subscription

        subscription = payment.subscription
        user = subscription.user
        plan = subscription.plan

        # On s'assure de travailler avec l'objet User
        user_obj = getattr(user, 'user', user)

        # On cherche le profil mécanicien
        mechanic_obj = None
        if user_obj.user_type == 'MECHANIC':
            from api.models import Mechanic
            mechanic_obj = Mechanic.objects.filter(user=user_obj).first()

        # Récupération de l'abonnement actif actuel (avant d'activer celui-ci)
        active_sub = user_obj.active_subscription

        # Si on a déjà un abonnement actif au même plan, et que ce n'est PAS celui-ci
        if active_sub and active_sub.plan == plan and active_sub.id != subscription.id:
            # On transfère la durée du paiement en attente vers l'abonnement actif existant
            duration_months = 1
            if plan.price > 0:
                duration_months = int(payment.amount / plan.price)

            duration_days = (duration_months * 30)
            active_sub.end_date = active_sub.end_date + timedelta(days=duration_days)
            active_sub.is_active = True

            # Liaison mécanicien si manquante
            if mechanic_obj and not active_sub.mechanic:
                active_sub.mechanic = mechanic_obj

            active_sub.save()

            # On met à jour le paiement pour pointer vers l'abonnement prolongé
            payment.subscription = active_sub
            payment.status = 'SUCCESS'
            payment.transaction_id = transaction_id
            payment.save()

            # On supprime la souscription temporaire "PENDING" inutile
            subscription.delete()

            return active_sub

        # Sinon (Changement de plan ou pas d'abonnement actif), on suit la logique normale
        trial_days_remaining = 0
        prorata_days_bonus = 0

        if active_sub and active_sub.plan:
            # CAS 1: Fin de période d'essai
            if active_sub.plan.tier == 'TRIAL':
                remaining = active_sub.end_date - timezone.now()
                total_seconds = remaining.total_seconds()
                if total_seconds > 0:
                    trial_days_remaining = int(total_seconds // 86400)

            # CAS 2: Changement de plan payant (Calcul au prorata)
            elif active_sub.is_active and active_sub.plan.price > 0:
                # On calcule la valeur restante du plan actuel
                now = timezone.now()
                if active_sub.end_date > now:
                    # Durée totale de l'abonnement en cours (approximée par le dernier paiement ou date de début)
                    # Pour faire simple et robuste, on utilise la différence entre start_date et end_date
                    total_duration = active_sub.end_date - active_sub.start_date
                    remaining_duration = active_sub.end_date - now

                    if total_duration.total_seconds() > 0:
                        # Valeur résiduelle en pourcentage du temps restant
                        residual_ratio = remaining_duration.total_seconds() / total_duration.total_seconds()

                        # On calcule combien de jours "équivalents" cela représente sur le NOUVEAU plan
                        # Exemple: s'il reste 10€ de valeur et que le nouveau plan coûte 1€/jour, on donne 10 jours
                        # Nouveau prix journalier basé sur la durée prévue du plan
                        # Si le plan dure 30 jours, on divise par 30. S'il dure 365, par 365.
                        new_daily_price = float(plan.price) / float(plan.duration_days) if plan.duration_days > 0 else 0

                        if new_daily_price > 0:
                            # Valeur résiduelle basée sur le prix total de l'ancien plan (au moment de sa création)
                            old_total_value = float(active_sub.plan.price)
                            residual_value = old_total_value * residual_ratio
                            prorata_days_bonus = int(residual_value / new_daily_price)

        # Désactiver les anciens abonnements
        Subscription.objects.filter(user=user_obj, is_active=True).exclude(id=subscription.id).update(is_active=False)
        Subscription.objects.filter(mechanic__user=user_obj, is_active=True).exclude(id=subscription.id).update(is_active=False)

        # Calcul de la nouvelle date de fin
        duration_months = 1
        if plan.price > 0:
            duration_months = int(payment.amount / plan.price)

        duration_days = (duration_months * 30) + trial_days_remaining + prorata_days_bonus
        subscription.end_date = timezone.now() + timedelta(days=duration_days)
        subscription.is_active = True

        # S'assurer que le mécanicien est lié
        if mechanic_obj:
            subscription.mechanic = mechanic_obj

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
        Active ou prolonge une souscription après paiement réussi.
        Si l'utilisateur a déjà un abonnement actif au MÊME plan, on le prolonge.
        Sinon, on crée une nouvelle souscription et on désactive les anciennes.
        La durée est calculée en mois (30 jours par mois).
        """
        # On s'assure de travailler avec l'objet User pour la recherche d'abonnement actif
        user_obj = getattr(user, 'user', user)

        # On essaie de voir si on a un objet profil (Mechanic)
        mechanic_obj = None
        if hasattr(user, 'shop_name') and not hasattr(user, 'user_type'): # C'est déjà un Mechanic
            mechanic_obj = user
        elif user_obj.user_type == 'MECHANIC':
            # On cherche le profil mécanicien associé à cet utilisateur
            from api.models import Mechanic
            mechanic_obj = Mechanic.objects.filter(user=user_obj).first()

        # Récupération de l'abonnement actif via la propriété centralisée
        active_sub = user_obj.active_subscription

        # CAS 1: Prolongation du même plan
        if active_sub and active_sub.plan == plan and active_sub.is_active:
            # On s'assure que l'abonnement actif est bien lié au mécanicien s'il existe
            if mechanic_obj and not active_sub.mechanic:
                active_sub.mechanic = mechanic_obj
                active_sub.save()

            # On prolonge l'abonnement existant
            duration_days = (duration_months * 30)
            active_sub.end_date = active_sub.end_date + timedelta(days=duration_days)
            active_sub.is_active = True # Sécurité au cas où
            active_sub.save()

            # Enregistrement du paiement
            total_amount = plan.price * duration_months
            Payment.objects.create(
                subscription=active_sub,
                amount=total_amount,
                transaction_id=transaction_id,
                payment_method=payment_method,
                status='SUCCESS'
            )
            return active_sub, 0

        # CAS 2: Nouveau plan ou plan différent (ou essai vers premium)
        trial_days_remaining = 0
        prorata_days_bonus = 0

        if active_sub and active_sub.plan:
            # CAS 2.1: Fin de période d'essai
            if active_sub.plan.tier == 'TRIAL':
                remaining = active_sub.end_date - timezone.now()
                total_seconds = remaining.total_seconds()
                if total_seconds > 0:
                    trial_days_remaining = int(total_seconds // 86400)

            # CAS 2.2: Changement de plan payant (Calcul au prorata)
            elif active_sub.is_active and active_sub.plan.price > 0:
                now = timezone.now()
                if active_sub.end_date > now:
                    total_duration = active_sub.end_date - active_sub.start_date
                    remaining_duration = active_sub.end_date - now

                    if total_duration.total_seconds() > 0:
                        residual_ratio = remaining_duration.total_seconds() / total_duration.total_seconds()
                        new_daily_price = float(plan.price) / float(plan.duration_days) if plan.duration_days > 0 else 0
                        
                        if new_daily_price > 0:
                            # On se base sur le prix total de l'ancien plan
                            old_total_value = float(active_sub.plan.price)
                            residual_value = old_total_value * residual_ratio
                            prorata_days_bonus = int(residual_value / new_daily_price)

        # Désactiver TOUS les abonnements actuels pour cet utilisateur
        Subscription.objects.filter(user=user_obj, is_active=True).update(is_active=False)
        Subscription.objects.filter(mechanic__user=user_obj, is_active=True).update(is_active=False)

        duration_days = (duration_months * 30) + trial_days_remaining + prorata_days_bonus
        end_date = timezone.now() + timedelta(days=duration_days)
        total_amount = plan.price * duration_months

        # Création de la souscription. On lie à la fois User et Mechanic si possible
        subscription = Subscription.objects.create(
            user=user_obj,
            mechanic=mechanic_obj,
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
            subscription.delete()
            raise e

        return subscription, (trial_days_remaining + prorata_days_bonus)

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
        return SubscriptionService.activate_subscription(user, new_plan, transaction_id, duration_months, payment_method)
