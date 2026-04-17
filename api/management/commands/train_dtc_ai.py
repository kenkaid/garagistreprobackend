from django.core.management.base import BaseCommand
from api.services.ai_service import DTCModelAI

class Command(BaseCommand):
    help = "Entraîne le modèle d'IA pour les estimations de coûts DTC basées sur les sessions réelles."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Lancement de l'entraînement de l'IA DTC..."))
        success = DTCModelAI.train()
        if success:
            self.stdout.write(self.style.SUCCESS("Entraînement terminé avec succès."))
        else:
            self.stdout.write(self.style.WARNING("Entraînement terminé sans mise à jour (données insuffisantes)."))
