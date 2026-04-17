import json
from django.core.management.base import BaseCommand
from api.models import VehicleModel

class Command(BaseCommand):
    help = 'Pré-remplit la base de données avec des modèles de véhicules populaires (2001-2024)'

    def handle(self, *args, **options):
        # Liste simplifiée mais représentative des véhicules populaires en Côte d'Ivoire / Afrique de l'Ouest
        data = [
            # TOYOTA
            {"brand": "Toyota", "model": "Corolla", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "RAV4", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Camry", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Hilux", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Land Cruiser", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Land Cruiser Prado", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Yaris", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Avensis", "year_start": 2001, "year_end": 2018},
            {"brand": "Toyota", "model": "Fortuner", "year_start": 2005, "year_end": 2024},
            {"brand": "Toyota", "model": "Hiace", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Vitz", "year_start": 2001, "year_end": 2024},
            {"brand": "Toyota", "model": "Aurion", "year_start": 2006, "year_end": 2017},
            {"brand": "Toyota", "model": "Starlet", "year_start": 2020, "year_end": 2024},

            # HYUNDAI
            {"brand": "Hyundai", "model": "Tucson", "year_start": 2004, "year_end": 2024},
            {"brand": "Hyundai", "model": "Santa Fe", "year_start": 2001, "year_end": 2024},
            {"brand": "Hyundai", "model": "Elantra", "year_start": 2001, "year_end": 2024},
            {"brand": "Hyundai", "model": "Accent", "year_start": 2001, "year_end": 2024},
            {"brand": "Hyundai", "model": "i10", "year_start": 2007, "year_end": 2024},
            {"brand": "Hyundai", "model": "i20", "year_start": 2008, "year_end": 2024},
            {"brand": "Hyundai", "model": "i30", "year_start": 2007, "year_end": 2024},
            {"brand": "Hyundai", "model": "Creta", "year_start": 2014, "year_end": 2024},
            {"brand": "Hyundai", "model": "Sonata", "year_start": 2001, "year_end": 2024},
            {"brand": "Hyundai", "model": "Kona", "year_start": 2017, "year_end": 2024},

            # KIA
            {"brand": "Kia", "model": "Sportage", "year_start": 2001, "year_end": 2024},
            {"brand": "Kia", "model": "Sorento", "year_start": 2002, "year_end": 2024},
            {"brand": "Kia", "model": "Rio", "year_start": 2001, "year_end": 2024},
            {"brand": "Kia", "model": "Picanto", "year_start": 2004, "year_end": 2024},
            {"brand": "Kia", "model": "Cerato", "year_start": 2003, "year_end": 2024},
            {"brand": "Kia", "model": "Optima", "year_start": 2001, "year_end": 2024},
            {"brand": "Kia", "model": "K5", "year_start": 2010, "year_end": 2024},
            {"brand": "Kia", "model": "Mohave", "year_start": 2008, "year_end": 2024},

            # PEUGEOT
            {"brand": "Peugeot", "model": "206", "year_start": 2001, "year_end": 2012},
            {"brand": "Peugeot", "model": "207", "year_start": 2006, "year_end": 2014},
            {"brand": "Peugeot", "model": "208", "year_start": 2012, "year_end": 2024},
            {"brand": "Peugeot", "model": "301", "year_start": 2012, "year_end": 2024},
            {"brand": "Peugeot", "model": "307", "year_start": 2001, "year_end": 2008},
            {"brand": "Peugeot", "model": "308", "year_start": 2007, "year_end": 2024},
            {"brand": "Peugeot", "model": "407", "year_start": 2004, "year_end": 2011},
            {"brand": "Peugeot", "model": "508", "year_start": 2010, "year_end": 2024},
            {"brand": "Peugeot", "model": "3008", "year_start": 2009, "year_end": 2024},
            {"brand": "Peugeot", "model": "5008", "year_start": 2009, "year_end": 2024},
            {"brand": "Peugeot", "model": "Partner", "year_start": 2001, "year_end": 2024},

            # MERCEDES-BENZ
            {"brand": "Mercedes-Benz", "model": "Classe C", "year_start": 2001, "year_end": 2024},
            {"brand": "Mercedes-Benz", "model": "Classe E", "year_start": 2001, "year_end": 2024},
            {"brand": "Mercedes-Benz", "model": "Classe S", "year_start": 2001, "year_end": 2024},
            {"brand": "Mercedes-Benz", "model": "ML / GLE", "year_start": 2001, "year_end": 2024},
            {"brand": "Mercedes-Benz", "model": "GLC", "year_start": 2015, "year_end": 2024},
            {"brand": "Mercedes-Benz", "model": "GLA", "year_start": 2013, "year_end": 2024},
            {"brand": "Mercedes-Benz", "model": "Classe A", "year_start": 2001, "year_end": 2024},

            # FORD
            {"brand": "Ford", "model": "Focus", "year_start": 2001, "year_end": 2024},
            {"brand": "Ford", "model": "Fiesta", "year_start": 2001, "year_end": 2023},
            {"brand": "Ford", "model": "Ranger", "year_start": 2001, "year_end": 2024},
            {"brand": "Ford", "model": "Explorer", "year_start": 2001, "year_end": 2024},
            {"brand": "Ford", "model": "Fusion", "year_start": 2002, "year_end": 2020},
            {"brand": "Ford", "model": "Escape", "year_start": 2001, "year_end": 2024},
            {"brand": "Ford", "model": "Everest", "year_start": 2003, "year_end": 2024},

            # NISSAN
            {"brand": "Nissan", "model": "Qashqai", "year_start": 2007, "year_end": 2024},
            {"brand": "Nissan", "model": "X-Trail", "year_start": 2001, "year_end": 2024},
            {"brand": "Nissan", "model": "Patrol", "year_start": 2001, "year_end": 2024},
            {"brand": "Nissan", "model": "Sunny / Almera", "year_start": 2001, "year_end": 2024},
            {"brand": "Nissan", "model": "Juke", "year_start": 2010, "year_end": 2024},
            {"brand": "Nissan", "model": "Navara", "year_start": 2001, "year_end": 2024},
            {"brand": "Nissan", "model": "Tiida", "year_start": 2004, "year_end": 2024},

            # HONDA
            {"brand": "Honda", "model": "Civic", "year_start": 2001, "year_end": 2024},
            {"brand": "Honda", "model": "CR-V", "year_start": 2001, "year_end": 2024},
            {"brand": "Honda", "model": "Accord", "year_start": 2001, "year_end": 2024},
            {"brand": "Honda", "model": "HR-V", "year_start": 2001, "year_end": 2024},
            {"brand": "Honda", "model": "City", "year_start": 2001, "year_end": 2024},

            # MITSUBISHI
            {"brand": "Mitsubishi", "model": "L200", "year_start": 2001, "year_end": 2024},
            {"brand": "Mitsubishi", "model": "Pajero", "year_start": 2001, "year_end": 2024},
            {"brand": "Mitsubishi", "model": "Pajero Sport", "year_start": 2001, "year_end": 2024},
            {"brand": "Mitsubishi", "model": "Outlander", "year_start": 2001, "year_end": 2024},
            {"brand": "Mitsubishi", "model": "ASX", "year_start": 2010, "year_end": 2024},
            {"brand": "Mitsubishi", "model": "Lancer", "year_start": 2001, "year_end": 2017},

            # VOLKSWAGEN
            {"brand": "Volkswagen", "model": "Golf", "year_start": 2001, "year_end": 2024},
            {"brand": "Volkswagen", "model": "Passat", "year_start": 2001, "year_end": 2024},
            {"brand": "Volkswagen", "model": "Polo", "year_start": 2001, "year_end": 2024},
            {"brand": "Volkswagen", "model": "Tiguan", "year_start": 2007, "year_end": 2024},
            {"brand": "Volkswagen", "model": "Touareg", "year_start": 2002, "year_end": 2024},
            {"brand": "Volkswagen", "model": "Amarok", "year_start": 2010, "year_end": 2024},
            {"brand": "Volkswagen", "model": "Jetta", "year_start": 2001, "year_end": 2024},

            # BMW
            {"brand": "BMW", "model": "Série 3", "year_start": 2001, "year_end": 2024},
            {"brand": "BMW", "model": "Série 5", "year_start": 2001, "year_end": 2024},
            {"brand": "BMW", "model": "X1", "year_start": 2009, "year_end": 2024},
            {"brand": "BMW", "model": "X3", "year_start": 2003, "year_end": 2024},
            {"brand": "BMW", "model": "X5", "year_start": 2001, "year_end": 2024},

            # AUDI
            {"brand": "Audi", "model": "A3", "year_start": 2001, "year_end": 2024},
            {"brand": "Audi", "model": "A4", "year_start": 2001, "year_end": 2024},
            {"brand": "Audi", "model": "A6", "year_start": 2001, "year_end": 2024},
            {"brand": "Audi", "model": "Q3", "year_start": 2011, "year_end": 2024},
            {"brand": "Audi", "model": "Q5", "year_start": 2008, "year_end": 2024},
            {"brand": "Audi", "model": "Q7", "year_start": 2005, "year_end": 2024},

            # RENAULT
            {"brand": "Renault", "model": "Clio", "year_start": 2001, "year_end": 2024},
            {"brand": "Renault", "model": "Mégane", "year_start": 2001, "year_end": 2024},
            {"brand": "Renault", "model": "Logan", "year_start": 2004, "year_end": 2024},
            {"brand": "Renault", "model": "Sandero", "year_start": 2007, "year_end": 2024},
            {"brand": "Renault", "model": "Duster", "year_start": 2010, "year_end": 2024},
            {"brand": "Renault", "model": "Kwid", "year_start": 2015, "year_end": 2024},
            {"brand": "Renault", "model": "Kadjar", "year_start": 2015, "year_end": 2022},

            # SUZUKI
            {"brand": "Suzuki", "model": "Swift", "year_start": 2004, "year_end": 2024},
            {"brand": "Suzuki", "model": "Grand Vitara", "year_start": 2001, "year_end": 2024},
            {"brand": "Suzuki", "model": "Jimny", "year_start": 2001, "year_end": 2024},
            {"brand": "Suzuki", "model": "Ertiga", "year_start": 2012, "year_end": 2024},
            {"brand": "Suzuki", "model": "Baleno", "year_start": 2015, "year_end": 2024},
            {"brand": "Suzuki", "model": "Dzire", "year_start": 2008, "year_end": 2024},

            # MAZDA
            {"brand": "Mazda", "model": "Mazda 3", "year_start": 2003, "year_end": 2024},
            {"brand": "Mazda", "model": "Mazda 6", "year_start": 2002, "year_end": 2024},
            {"brand": "Mazda", "model": "CX-5", "year_start": 2012, "year_end": 2024},
            {"brand": "Mazda", "model": "BT-50", "year_start": 2006, "year_end": 2024},

            # CHEVROLET
            {"brand": "Chevrolet", "model": "Aveo", "year_start": 2002, "year_end": 2024},
            {"brand": "Chevrolet", "model": "Cruze", "year_start": 2008, "year_end": 2024},
            {"brand": "Chevrolet", "model": "Captiva", "year_start": 2006, "year_end": 2024},
            {"brand": "Chevrolet", "model": "Spark", "year_start": 2001, "year_end": 2024},

            # ISUZU
            {"brand": "Isuzu", "model": "D-Max", "year_start": 2002, "year_end": 2024},
            {"brand": "Isuzu", "model": "MU-X", "year_start": 2013, "year_end": 2024},

            # LAND ROVER
            {"brand": "Land Rover", "model": "Range Rover", "year_start": 2001, "year_end": 2024},
            {"brand": "Land Rover", "model": "Range Rover Sport", "year_start": 2005, "year_end": 2024},
            {"brand": "Land Rover", "model": "Range Rover Evoque", "year_start": 2011, "year_end": 2024},
            {"brand": "Land Rover", "model": "Discovery", "year_start": 2001, "year_end": 2024},
            {"brand": "Land Rover", "model": "Defender", "year_start": 2001, "year_end": 2024},

            # JEEP
            {"brand": "Jeep", "model": "Grand Cherokee", "year_start": 2001, "year_end": 2024},
            {"brand": "Jeep", "model": "Wrangler", "year_start": 2001, "year_end": 2024},
            {"brand": "Jeep", "model": "Compass", "year_start": 2006, "year_end": 2024},

            # LEXUS
            {"brand": "Lexus", "model": "RX", "year_start": 2001, "year_end": 2024},
            {"brand": "Lexus", "model": "LX", "year_start": 2001, "year_end": 2024},
            {"brand": "Lexus", "model": "GX", "year_start": 2002, "year_end": 2024},
            {"brand": "Lexus", "model": "IS", "year_start": 2001, "year_end": 2024},
            {"brand": "Lexus", "model": "ES", "year_start": 2001, "year_end": 2024},
        ]

        count = 0
        for item in data:
            obj, created = VehicleModel.objects.get_or_create(
                brand=item['brand'],
                model=item['model'],
                defaults={
                    'year_start': item['year_start'],
                    'year_end': item['year_end']
                }
            )
            if created:
                count += 1
            else:
                # Mise à jour si déjà existant
                obj.year_start = item['year_start']
                obj.year_end = item['year_end']
                obj.save()

        self.stdout.write(self.style.SUCCESS(f'Succès : {count} nouveaux modèles ajoutés.'))
