import json
from django.core.management.base import BaseCommand
from api.models import DTCReference

class Command(BaseCommand):
    help = 'Importe des codes DTC à partir d\'un fichier JSON'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Le chemin vers le fichier JSON')

    def handle(self, *args, **options):
        file_path = options['json_file']

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            count = 0
            for item in data:
                # update_or_create permet de ne pas avoir de doublons si on relance l'import
                dtc, created = DTCReference.objects.update_or_create(
                    code=item.get('code'),
                    defaults={
                        'description': item.get('description', ''),
                        'meaning': item.get('meaning', ''),
                        'part_location': item.get('part_location', ''),
                        'est_labor_cost': item.get('est_labor_cost', 0),
                        'est_part_price_local': item.get('est_part_price_local', 0),
                        'est_part_price_import': item.get('est_part_price_import', 0),
                        'part_image_url': item.get('part_image_url', '')
                    }
                )
                if created:
                    count += 1

            self.stdout.write(self.style.SUCCESS(f'Succès : {count} nouveaux codes DTC importés !'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Fichier non trouvé : {file_path}'))
        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR('Erreur de formatage JSON dans le fichier.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Une erreur est survenue : {str(e)}'))
