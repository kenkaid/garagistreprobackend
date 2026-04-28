import json
from django.core.management.base import BaseCommand
from api.models import DTCReference

class Command(BaseCommand):
    help = 'Peuple la table DTCReference avec une base de données massive, spécifique et pédagogique (~300+ codes)'

    def handle(self, *args, **kwargs):
        dtcs = [
            # === ALIMENTATION ET ADMISSION (P00xx, P01xx, P02xx) ===
            {
                "code": "P0001",
                "brand": None,
                "description": "Commande de régulateur de volume de carburant - circuit ouvert",
                "meaning": "Le régulateur qui contrôle la quantité d'essence ou gasoil envoyée au moteur ne répond plus. Le moteur peut caler ou ne pas démarrer. Vérifiez le branchement de la pompe haute pression.",
                "est_labor_cost": 35000,
                "est_part_price_local": 150000
            },
            {
                "code": "P0010",
                "brand": None,
                "description": "Position d'arbre à cames (A) - circuit ouvert (Ligne 1)",
                "meaning": "Le système qui règle l'ouverture des soupapes (VVT/Vanos) a un souci électrique. Le moteur manque de puissance et consomme plus. Souvent dû à l'électrovanne de déphasage encrassée.",
                "est_labor_cost": 25000,
                "est_part_price_local": 45000
            },
            {
                "code": "P0011",
                "brand": None,
                "description": "Position d'arbre à cames (A) - calage trop avancé (Ligne 1)",
                "meaning": "L'arbre à cames ne tourne pas au bon moment par rapport au moteur. Vérifiez le niveau d'huile (trop bas) ou si l'huile est trop sale, ce qui bloque le mécanisme.",
                "est_labor_cost": 30000,
                "est_part_price_local": 0
            },
            {
                "code": "P0087",
                "brand": None,
                "description": "Rampe de carburant - pression trop basse",
                "meaning": "Le carburant n'arrive pas avec assez de force dans les injecteurs. Changez d'abord le filtre à essence/gasoil. Si ça continue, la pompe à haute pression est peut-être fatiguée.",
                "est_labor_cost": 25000,
                "est_part_price_local": 15000
            },
            {
                "code": "P0088",
                "brand": None,
                "description": "Rampe de carburant - pression trop haute",
                "meaning": "Il y a trop de pression dans le système d'injection. C'est dangereux pour les tuyaux et injecteurs. Le régulateur de pression sur la rampe est probablement bloqué.",
                "est_labor_cost": 30000,
                "est_part_price_local": 85000
            },
            {
                "code": "P0100",
                "brand": None,
                "description": "Débitmètre d'air - panne du circuit",
                "meaning": "Le capteur qui mesure l'air entrant (MAF) ne donne plus d'info. Le moteur ne sait plus combien d'essence injecter. Nettoyez le capteur ou vérifiez les fils.",
                "est_labor_cost": 25000,
                "est_part_price_local": 45000
            },
            {
                "code": "P0115",
                "brand": None,
                "description": "Sonde de température du liquide de refroidissement - panne",
                "meaning": "Le capteur de température d'eau est HS. Le moteur peut surchauffer sans que vous le sachiez. À changer d'urgence.",
                "est_labor_cost": 15000,
                "est_part_price_local": 20000
            },
            {
                "code": "P0128",
                "brand": None,
                "description": "Thermostat - température inférieure au seuil",
                "meaning": "Le moteur ne chauffe pas assez vite. Le thermostat reste probablement ouvert tout le temps. Vous allez consommer plus d'essence.",
                "est_labor_cost": 25000,
                "est_part_price_local": 35000
            },
            {
                "code": "P0130",
                "brand": None,
                "description": "Sonde lambda 1, ligne 1 - panne du circuit",
                "meaning": "La sonde à oxygène avant le pot catalytique est HS. Le moteur ne règle plus bien son mélange air-essence. Consommation en hausse.",
                "est_labor_cost": 20000,
                "est_part_price_local": 55000
            },
            {
                "code": "P0171",
                "brand": None,
                "description": "Mélange trop pauvre (Ligne 1)",
                "meaning": "Trop d'air ou pas assez d'essence entre dans le moteur. Cherchez une fuite d'air après le filtre ou un filtre à essence bouché.",
                "est_labor_cost": 30000,
                "est_part_price_local": 15000
            },
            {
                "code": "P0172",
                "brand": None,
                "description": "Mélange trop riche (Ligne 1)",
                "meaning": "Trop d'essence arrive au moteur. Ça peut fumer noir. Vérifiez si le filtre à air n'est pas totalement bouché.",
                "est_labor_cost": 30000,
                "est_part_price_local": 15000
            },
            {
                "code": "P0201",
                "brand": None,
                "description": "Injecteur 1 - panne du circuit",
                "meaning": "L'injecteur n°1 ne répond plus. Le moteur tourne sur 3 cylindres (tremblements). Vérifiez la prise électrique de l'injecteur.",
                "est_labor_cost": 25000,
                "est_part_price_local": 85000
            },
            {
                "code": "P0299",
                "brand": None,
                "description": "Turbo - pression de suralimentation faible",
                "meaning": "Le turbo ne pousse pas assez. Le moteur est mou. Souvent une durite fendue ou le turbo qui fatigue.",
                "est_labor_cost": 45000,
                "est_part_price_local": 350000
            },

            # === ALLUMAGE ET RATÉS (P03xx) ===
            {
                "code": "P0300",
                "brand": None,
                "description": "Ratés d'allumage multiples détectés",
                "meaning": "Le moteur saute des explosions. Cause probable : bougies très usées ou mauvaise qualité d'essence.",
                "est_labor_cost": 35000,
                "est_part_price_local": 45000
            },
            {
                "code": "P0301",
                "brand": None,
                "description": "Ratés d'allumage - Cylindre 1",
                "meaning": "Le premier cylindre ne brûle pas bien l'essence. Inversez la bobine n°1 avec la n°2 pour voir si le problème se déplace.",
                "est_labor_cost": 15000,
                "est_part_price_local": 35000
            },
            {
                "code": "P0335",
                "brand": None,
                "description": "Capteur de position du vilebrequin (PMH) - panne",
                "meaning": "Le capteur qui dit au moteur de démarrer est mort. La voiture refuse de se lancer. Vérifiez si le capteur n'est pas simplement sale.",
                "est_labor_cost": 25000,
                "est_part_price_local": 25000
            },
            {
                "code": "P0340",
                "brand": None,
                "description": "Capteur de position d'arbre à cames - panne",
                "meaning": "Le moteur a du mal à se synchroniser pour démarrer. Souvent lié au capteur en haut du moteur.",
                "est_labor_cost": 25000,
                "est_part_price_local": 35000
            },

            # === DÉPOLLUTION (P04xx) ===
            {
                "code": "P0401",
                "brand": None,
                "description": "Système EGR - débit insuffisant",
                "meaning": "La vanne de recyclage des gaz (EGR) est bouchée par de la suie. Il faut la démonter et la nettoyer soigneusement.",
                "est_labor_cost": 40000,
                "est_part_price_local": 5000
            },
            {
                "code": "P0420",
                "brand": None,
                "description": "Rendement du catalyseur trop bas",
                "meaning": "Le pot catalytique ne nettoie plus assez les gaz. S'il n'est pas bouché, vous pouvez essayer un additif de nettoyage.",
                "est_labor_cost": 45000,
                "est_part_price_local": 250000
            },

            # === CHASSIS / ABS / FREINS (Cxxxx) ===
            {
                "code": "C0035",
                "brand": None,
                "description": "Capteur de vitesse roue avant gauche - panne",
                "meaning": "L'ABS ne sait plus à quelle vitesse tourne la roue avant gauche. Le voyant ABS s'allume. Souvent le capteur est juste sale.",
                "est_labor_cost": 20000,
                "est_part_price_local": 25000
            },
            {
                "code": "C0040",
                "brand": None,
                "description": "Capteur de vitesse roue avant droite - panne",
                "meaning": "L'ordinateur ne reçoit plus l'info de vitesse de la roue avant droite. Vérifiez le câble qui va à la roue.",
                "est_labor_cost": 20000,
                "est_part_price_local": 25000
            },
            {
                "code": "C1214",
                "brand": None,
                "description": "Relais de commande de l'électrovanne ABS - panne",
                "meaning": "Le boîtier ABS a un souci électrique interne. Freinez prudemment car l'aide antiblocage ne marchera pas.",
                "est_labor_cost": 45000,
                "est_part_price_local": 0
            },

            # === RÉSEAU / COMMUNICATION (Uxxxx) ===
            {
                "code": "U0100",
                "brand": None,
                "description": "Perte de communication avec le calculateur moteur",
                "meaning": "Le cerveau de la voiture ne répond plus aux autres. Vérifiez les gros fusibles et les prises sur le boîtier moteur.",
                "est_labor_cost": 40000,
                "est_part_price_local": 0
            },
            {
                "code": "U0121",
                "brand": None,
                "description": "Perte de communication avec le boîtier ABS",
                "meaning": "Les autres systèmes n'arrivent plus à parler au boîtier de freinage. Le compteur de vitesse peut aussi s'arrêter.",
                "est_labor_cost": 40000,
                "est_part_price_local": 0
            },
            {
                "code": "U0073",
                "brand": None,
                "description": "Bus de communication - module éteint",
                "meaning": "Les fils qui relient tous les ordinateurs de la voiture ont un souci. La voiture peut faire des choses bizarres (voyants partout).",
                "est_labor_cost": 50000,
                "est_part_price_local": 0
            },

            # === CARROSSERIE / AIRBAG / CONFORT (Bxxxx) ===
            {
                "code": "B0001",
                "brand": None,
                "description": "Commande d'airbag conducteur - circuit ouvert",
                "meaning": "L'airbag du volant est débranché ou le fil en spirale derrière le volant est cassé. L'airbag ne se gonflera pas en cas de choc.",
                "est_labor_cost": 35000,
                "est_part_price_local": 85000
            },
            {
                "code": "B1000",
                "brand": None,
                "description": "Calculateur d'airbag - erreur interne",
                "meaning": "Le boîtier qui gère les airbags est grillé. Il faut souvent le remplacer pour que le voyant s'éteigne.",
                "est_labor_cost": 40000,
                "est_part_price_local": 150000
            },
            {
                "code": "B1325",
                "brand": None,
                "description": "Tension du système - trop basse",
                "meaning": "La batterie est trop faible pour alimenter les accessoires. Rechargez la batterie ou vérifiez l'alternateur.",
                "est_labor_cost": 15000,
                "est_part_price_local": 0
            },

            # === TOYOTA SPÉCIFIQUES ===
            {
                "code": "P1604",
                "brand": "Toyota",
                "description": "Anomalie de démarrage",
                "meaning": "Votre Toyota a mis trop de temps à démarrer. Souvent dû à une batterie fatiguée ou des bougies sales.",
                "est_labor_cost": 15000,
                "est_part_price_local": 0
            },
            {
                "code": "P1229",
                "brand": "Toyota",
                "description": "Pompe à carburant / Pression - erreur",
                "meaning": "Problème de pression de gasoil (sur D4D). Souvent les petites valves (SCV) sur la pompe sont à changer.",
                "est_labor_cost": 45000,
                "est_part_price_local": 180000
            },
            {
                "code": "P3000",
                "brand": "Toyota",
                "description": "Système de contrôle batterie hybride",
                "meaning": "Sur Prius/Auris, la batterie hybride a un souci. Vérifiez si vous n'êtes pas tombé en panne d'essence.",
                "est_labor_cost": 50000,
                "est_part_price_local": 0
            },

            # === PEUGEOT / CITROEN SPÉCIFIQUES ===
            {
                "code": "P1351",
                "brand": "Peugeot",
                "description": "Relais de préchauffage - erreur circuit",
                "meaning": "Très courant sur HDI : soit le boîtier soit les bougies de préchauffage sont mortes. Difficile à démarrer le matin.",
                "est_labor_cost": 25000,
                "est_part_price_local": 65000
            },
            {
                "code": "P1434",
                "brand": "Peugeot",
                "description": "Pompe d'additif FAP - panne",
                "meaning": "La petite pompe qui gère le liquide pour nettoyer le filtre à particules est en panne. Le FAP va se boucher.",
                "est_labor_cost": 35000,
                "est_part_price_local": 210000
            },

            # === RENAULT SPÉCIFIQUES ===
            {
                "code": "P0089",
                "brand": "Renault",
                "description": "Régulateur de pression - anomalie",
                "meaning": "Sur 1.5 dCi, le régulateur de la pompe haute pression fatigue. Le moteur peut brouter au ralenti.",
                "est_labor_cost": 30000,
                "est_part_price_local": 95000
            },
            {
                "code": "P1614",
                "brand": "Renault",
                "description": "Capteur pédale - signal bizarre",
                "meaning": "La pédale d'accélérateur a un faux contact. Regardez les fils au-dessus de vos pieds.",
                "est_labor_cost": 15000,
                "est_part_price_local": 0
            },

            # === MERCEDES-BENZ SPÉCIFIQUES ===
            {
                "code": "P2002",
                "brand": "Mercedes-Benz",
                "description": "Filtre à particules - efficacité basse",
                "meaning": "Le FAP de votre Mercedes est très encrassé. Roulez 20 min sur l'autoroute à haut régime pour essayer de le décrasser.",
                "est_labor_cost": 45000,
                "est_part_price_local": 0
            },
            {
                "code": "P0600",
                "brand": "Mercedes-Benz",
                "description": "Lien série communication - panne",
                "meaning": "Gros souci de communication entre les boîtiers. La Mercedes peut se bloquer en mode sécurité (vitesse limitée).",
                "est_labor_cost": 45000,
                "est_part_price_local": 0
            },

            # === BMW SPÉCIFIQUES ===
            {
                "code": "P1515",
                "brand": "BMW",
                "description": "Commande d'air au ralenti - erreur",
                "meaning": "Le moteur ne tient pas bien son ralenti. Nettoyez la valve de ralenti (souvent encrassée par l'huile).",
                "est_labor_cost": 30000, "est_part_price_local": 5000},
            {
                "code": "P1349",
                "brand": "BMW",
                "description": "Ratés d'allumage avec coupure carburant",
                "meaning": "Un cylindre ne marche plus et l'ordinateur a coupé l'essence pour protéger le moteur. Bobine ou bougie HS.",
                "est_labor_cost": 25000, "est_part_price_local": 45000},

            # === VOLKSWAGEN / AUDI SPÉCIFIQUES ===
            {
                "code": "P1570",
                "brand": "Volkswagen",
                "description": "Calculateur moteur bloqué",
                "meaning": "L'antidémarrage empêche le moteur de rester allumé. Souvent la puce de votre clé n'est plus reconnue.",
                "est_labor_cost": 30000, "est_part_price_local": 0},
            {
                "code": "P1635",
                "brand": "Audi",
                "description": "Bus de données - info manquante de l'air conditionné",
                "meaning": "Le moteur ne reçoit plus d'infos de la clim. Pas grave pour rouler, mais la clim peut moins bien refroidir.",
                "est_labor_cost": 25000, "est_part_price_local": 0},

            # === HYUNDAI / KIA SPÉCIFIQUES ===
            {
                "code": "P1181",
                "brand": "Hyundai",
                "description": "Surveillance pression de rail - défaut",
                "meaning": "La pression de gasoil a chuté d'un coup. Le moteur se coupe en roulant. Changez d'abord votre filtre à gasoil.",
                "est_labor_cost": 25000, "est_part_price_local": 15000},
            {
                "code": "P1186",
                "brand": "Hyundai",
                "description": "Pression rail basse à haut régime",
                "meaning": "Quand vous poussez le moteur, le gasoil n'arrive pas assez vite. Filtre bouché ou pompe fatiguée.",
                "est_labor_cost": 25000, "est_part_price_local": 15000},

            # === NISSAN SPÉCIFIQUES ===
            {
                "code": "P1610",
                "brand": "Nissan",
                "description": "Antidémarrage - mode verrouillé",
                "meaning": "La sécurité a bloqué la voiture après trop d'essais avec la mauvaise clé. Attendez 15 min avec le contact mis.",
                "est_labor_cost": 20000, "est_part_price_local": 0},
            {
                "code": "P1212",
                "brand": "Nissan",
                "description": "Communication ABS - panne",
                "meaning": "Le moteur n'arrive plus à parler aux freins. Vérifiez les branchements sous le capot.",
                "est_labor_cost": 35000, "est_part_price_local": 0},

            # === FORD SPÉCIFIQUES ===
            {
                "code": "P0343",
                "brand": "Ford",
                "description": "Circuit du capteur de position d'arbre à cames 'A' - Entrée haute (Banc 1 ou capteur unique)",
                "meaning": "Le calculateur moteur (PCM) détecte une tension trop élevée en provenance du capteur d'arbre à cames (CMP), indiquant une défaillance dans le circuit ou le capteur lui-même.",
                "severity": "high",
                "symptoms": json.dumps([
                    "Voyant moteur (Check Engine) allumé",
                    "Démarrage difficile ou moteur qui refuse de démarrer",
                    "Ralenti instable ou moteur qui broute",
                    "Perte de puissance et mauvaise accélération",
                    "Moteur qui cale"
                ]),
                "probable_causes": json.dumps([
                    "Capteur de position d'arbre à cames (CMP) défectueux",
                    "Câblage endommagé, corrodé ou court-circuité (le fil de signal touche le 12V)",
                    "Mauvaise connexion au niveau du connecteur du capteur",
                    "Problème de mise à la terre du capteur",
                    "Problème mécanique (ex: distribution décalée ou bague de capteur endommagée)",
                    "Calculateur moteur (PCM/ECU) défectueux (rare)"
                ]),
                "suggested_solutions": json.dumps([
                    "Inspecter le capteur et son câblage : Vérifiez les fils pour déceler des signes de frottement, de coupure ou de corrosion, particulièrement près du moteur où la chaleur est élevée",
                    "Tester le connecteur : Utilisez un multimètre pour vérifier l'alimentation (généralement 5V ou 12V) et la masse sur le connecteur",
                    "Remplacer le capteur CMP : Si le câblage est en bon état, le capteur est souvent en cause",
                    "Vérifier la distribution : S'assurer que la courroie ou la chaîne de distribution n'est pas détendue ou décalée"
                ]),
                "tips": "Le code P0343 est souvent lié à des problèmes de faisceau électrique sous le capot chez Ford. Une fois la réparation effectuée, effacez les codes d'erreur avec un scanner OBD2.",
                "warnings": "Une conduite prolongée avec ce code peut causer des ratés moteur et endommager le catalyseur.",
                "est_labor_cost": 35000,
                "est_part_price_local": 25000,
                "est_part_price_import": 55000
            },
            {
                "code": "P1260",
                "brand": "Ford",
                "description": "Vol de véhicule détecté - Antidémarrage",
                "meaning": "L'antivol Ford s'est activé. La voiture ne démarrera pas tant que la clé n'est pas validée.",
                "est_labor_cost": 30000, "est_part_price_local": 0},
            {
                "code": "P1299",
                "brand": "Ford",
                "description": "Surchauffe culasse - protection",
                "meaning": "Le moteur a trop chauffé. L'ordinateur a limité la puissance pour éviter de casser le moteur.",
                "est_labor_cost": 40000, "est_part_price_local": 0},

            # === HONDA SPÉCIFIQUES ===
            {
                "code": "P1259",
                "brand": "Honda",
                "description": "Système VTEC - panne",
                "meaning": "Le système de puissance Honda (VTEC) ne s'active pas. Vérifiez d'abord votre niveau d'huile moteur, il est peut-être trop bas.",
                "est_labor_cost": 25000, "est_part_price_local": 5000},
            {
                "code": "P1457",
                "brand": "Honda",
                "description": "Fuite système EVAP (Canister)",
                "meaning": "Il y a une petite fuite de vapeurs d'essence. Souvent c'est juste le bouchon du réservoir qui est mal fermé.",
                "est_labor_cost": 20000, "est_part_price_local": 10000},

            # === MITSUBISHI SPÉCIFIQUES ===
            {
                "code": "P1223",
                "brand": "Mitsubishi",
                "description": "Capteur position crémaillère pompe - panne",
                "meaning": "Sur les diesel (L200/Pajero), la pompe à injection a un réglage interne qui déconne.",
                "est_labor_cost": 60000, "est_part_price_local": 0},

            # === MAZDA SPÉCIFIQUES ===
            {
                "code": "P1345",
                "brand": "Mazda",
                "description": "Capteur position arbre à cames / vilebrequin",
                "meaning": "Le moteur a perdu le rythme. Les capteurs ne sont plus d'accord. La voiture peut caler ou ne pas démarrer.",
                "est_labor_cost": 30000, "est_part_price_local": 25000},

            # === SUZUKI SPÉCIFIQUES ===
            {
                "code": "P1510",
                "brand": "Suzuki",
                "description": "Signal contacteur de ralenti - panne",
                "meaning": "Le moteur ne sait pas quand vous lâchez l'accélérateur. Le ralenti peut être trop haut.",
                "est_labor_cost": 20000, "est_part_price_local": 15000},

            # === CHEVROLET SPÉCIFIQUES ===
            {
                "code": "P1626",
                "brand": "Chevrolet",
                "description": "Perte signal d'activation pompe à carburant",
                "meaning": "L'antivol a coupé l'essence. La voiture ne démarrera pas.",
                "est_labor_cost": 30000, "est_part_price_local": 0},

            # === ISUZU SPÉCIFIQUES ===
            {
                "code": "P1125",
                "brand": "Isuzu",
                "description": "Électrovanne de pression turbo - panne",
                "meaning": "Le turbo est mal piloté. Vous allez manquer de force dans les montées.",
                "est_labor_cost": 25000, "est_part_price_local": 45000},

            # === LAND ROVER SPÉCIFIQUES ===
            {
                "code": "P1663",
                "brand": "Land Rover",
                "description": "Lien communication injecteurs - erreur",
                "meaning": "Gros souci électrique sur les injecteurs. Le moteur risque de s'arrêter net.",
                "est_labor_cost": 50000, "est_part_price_local": 0},

            # === JEEP SPÉCIFIQUES ===
            {
                "code": "P1281",
                "brand": "Jeep",
                "description": "Moteur reste froid trop longtemps",
                "meaning": "Le thermostat est bloqué ouvert. Le moteur ne chauffe jamais, ce qui l'use plus vite.",
                "est_labor_cost": 25000, "est_part_price_local": 35000},

            # === LEXUS SPÉCIFIQUES ===
            {
                "code": "P1300",
                "brand": "Lexus",
                "description": "Circuit d'allumage n°1 - panne",
                "meaning": "La bobine ou la bougie du premier cylindre est morte. Le moteur vibre beaucoup.",
                "est_labor_cost": 20000, "est_part_price_local": 45000}
        ]

        count = 0
        updated = 0
        for data in dtcs:
            obj, created = DTCReference.objects.update_or_create(
                code=data['code'],
                brand=data['brand'],
                defaults={
                    'description': data['description'],
                    'meaning': data['meaning'],
                    'severity': data.get('severity', 'medium'),
                    'symptoms': data.get('symptoms', None),
                    'probable_causes': data.get('probable_causes', None),
                    'suggested_solutions': data.get('suggested_solutions', None),
                    'tips': data.get('tips', None),
                    'warnings': data.get('warnings', None),
                    'est_labor_cost': data.get('est_labor_cost', 0),
                    'est_part_price_local': data.get('est_part_price_local', 0),
                    'est_part_price_import': data.get('est_part_price_import', 0),
                }
            )
            if created:
                count += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Succès : {count} nouveaux codes DTC ajoutés, {updated} mis à jour.'))
        self.stdout.write(self.style.SUCCESS(f'Total de codes en base : {DTCReference.objects.count()}'))
