"""
Commande Django pour importer les codes DTC constructeurs (P1xxx, B, C, U)
les plus courants pour les marques principales.

Ces codes sont basés sur les standards SAE J2012 et les données publiques
des constructeurs automobiles.

Usage:
    python manage.py seed_brand_dtcs
    python manage.py seed_brand_dtcs --brand Renault
    python manage.py seed_brand_dtcs --dry-run
"""

import json
from django.core.management.base import BaseCommand
from api.models import DTCReference

# ============================================================
# BASE DE DONNÉES DES CODES CONSTRUCTEURS
# Format: { "BRAND": [ (code, description, severity), ... ] }
# ============================================================

BRAND_DTCS = {

    # ─────────────────────────────────────────────
    # RENAULT
    # ─────────────────────────────────────────────
    "Renault": [
        ("P1100", "Capteur de débit d'air massique - panne intermittente", "medium"),
        ("P1101", "Capteur de débit d'air massique - hors plage", "medium"),
        ("P1105", "Capteur de pression absolue - panne intermittente", "medium"),
        ("P1110", "Capteur de température d'air d'admission - panne intermittente", "low"),
        ("P1115", "Capteur de température du liquide de refroidissement - panne intermittente", "medium"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1121", "Capteur de position papillon - plage incohérente avec capteur MAP", "medium"),
        ("P1125", "Moteur de papillon - panne", "high"),
        ("P1130", "Sonde lambda 1 - plage de mesure insuffisante", "medium"),
        ("P1131", "Sonde lambda 1 - mélange trop pauvre détecté", "medium"),
        ("P1132", "Sonde lambda 1 - mélange trop riche détecté", "medium"),
        ("P1170", "Sonde lambda 1 - pas de commutation", "medium"),
        ("P1171", "Sonde lambda 1 - mélange trop pauvre lors de l'accélération", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Bobine d'allumage - panne du circuit primaire", "high"),
        ("P1310", "Bobine d'allumage B - panne du circuit primaire", "high"),
        ("P1320", "Bobine d'allumage C - panne du circuit primaire", "high"),
        ("P1330", "Bobine d'allumage D - panne du circuit primaire", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1401", "Vanne EGR - débit insuffisant détecté", "medium"),
        ("P1403", "Vanne EGR - panne du circuit de commande", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1601", "Calculateur moteur - panne de communication interne", "critical"),
        ("P1602", "Calculateur moteur - panne de mémoire", "critical"),
        ("P1610", "Immobiliseur - code non reconnu", "high"),
        ("P1611", "Immobiliseur - panne de communication avec l'antidémarrage", "high"),
        ("P1615", "Immobiliseur - panne du transpondeur", "high"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("P1701", "Boîte de vitesses automatique - panne du capteur de vitesse", "high"),
        ("P1750", "Boîte de vitesses automatique - panne de pression hydraulique", "high"),
        ("B1001", "Calculateur airbag - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1011", "Airbag conducteur - court-circuit à la masse", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("B1021", "Airbag passager - court-circuit à la masse", "critical"),
        ("B1030", "Prétensionneur ceinture conducteur - circuit ouvert", "critical"),
        ("B1031", "Prétensionneur ceinture conducteur - court-circuit", "critical"),
        ("B1040", "Prétensionneur ceinture passager - circuit ouvert", "critical"),
        ("B1050", "Airbag latéral gauche - circuit ouvert", "critical"),
        ("B1060", "Airbag latéral droit - circuit ouvert", "critical"),
        ("C1001", "Capteur de vitesse roue avant gauche ABS - panne", "critical"),
        ("C1002", "Capteur de vitesse roue avant droite ABS - panne", "critical"),
        ("C1003", "Capteur de vitesse roue arrière gauche ABS - panne", "critical"),
        ("C1004", "Capteur de vitesse roue arrière droite ABS - panne", "critical"),
        ("C1010", "Pompe hydraulique ABS - panne du circuit", "critical"),
        ("C1020", "Électrovanne ABS - panne du circuit", "critical"),
        ("C1100", "Capteur d'angle de braquage - panne", "high"),
        ("C1200", "Capteur de lacet ESP - panne", "high"),
        ("U0001", "Bus CAN haute vitesse - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
        ("U0101", "Perte de communication avec le calculateur boîte de vitesses", "high"),
        ("U0121", "Perte de communication avec le calculateur ABS/ESP", "critical"),
        ("U0140", "Perte de communication avec le calculateur de carrosserie", "high"),
        ("U0155", "Perte de communication avec le tableau de bord", "medium"),
    ],

    # ─────────────────────────────────────────────
    # PEUGEOT / CITROËN (PSA)
    # ─────────────────────────────────────────────
    "Peugeot": [
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1130", "Sonde lambda amont - plage insuffisante", "medium"),
        ("P1200", "Injecteur - panne du circuit de commande", "high"),
        ("P1300", "Bobine d'allumage - panne du circuit primaire", "high"),
        ("P1351", "Bobine d'allumage - circuit primaire trop haut", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1610", "Immobiliseur - code non reconnu", "high"),
        ("P1630", "Immobiliseur - panne de communication", "high"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("B1030", "Prétensionneur ceinture conducteur - panne", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("C1010", "Pompe hydraulique ABS - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
        ("U0121", "Perte de communication avec le calculateur ABS", "critical"),
    ],

    # ─────────────────────────────────────────────
    # VOLKSWAGEN / AUDI / SKODA / SEAT (VAG)
    # ─────────────────────────────────────────────
    "Volkswagen": [
        ("P1102", "Capteur de débit d'air - valeur trop basse", "medium"),
        ("P1103", "Capteur de débit d'air - valeur trop haute", "medium"),
        ("P1136", "Système de variation de calage d'arbre à cames - panne", "high"),
        ("P1137", "Système de variation de calage d'arbre à cames - plage insuffisante", "high"),
        ("P1176", "Sonde lambda - correction d'adaptation trop basse", "medium"),
        ("P1177", "Sonde lambda - correction d'adaptation trop haute", "medium"),
        ("P1296", "Capteur de température d'eau - pas de signal", "medium"),
        ("P1297", "Connexion entre capteur MAP et capteur MAF - panne", "medium"),
        ("P1386", "Contrôle anti-cliquetis - cylindre 1 - limite atteinte", "high"),
        ("P1387", "Contrôle anti-cliquetis - cylindre 2 - limite atteinte", "high"),
        ("P1388", "Contrôle anti-cliquetis - cylindre 3 - limite atteinte", "high"),
        ("P1389", "Contrôle anti-cliquetis - cylindre 4 - limite atteinte", "high"),
        ("P1411", "Vanne de recirculation des gaz secondaires - panne", "medium"),
        ("P1421", "Vanne de recirculation des gaz secondaires - circuit ouvert", "medium"),
        ("P1425", "Vanne de recirculation des gaz secondaires - court-circuit", "medium"),
        ("P1500", "Régulateur de ralenti - panne", "medium"),
        ("P1543", "Système de climatisation - panne du circuit de commande", "low"),
        ("P1600", "Alimentation calculateur moteur - panne", "critical"),
        ("P1602", "Calculateur moteur - panne de mémoire EEPROM", "critical"),
        ("P1606", "Calculateur moteur - panne du circuit de sortie", "critical"),
        ("P1624", "Immobiliseur - demande de code non satisfaite", "high"),
        ("P1625", "Immobiliseur - panne de communication CAN", "high"),
        ("P1640", "Calculateur moteur - panne interne", "critical"),
        ("P1693", "Calculateur moteur - panne du circuit de diagnostic", "high"),
        ("P1780", "Boîte de vitesses - panne du circuit de commande", "high"),
        ("B1001", "Calculateur airbag - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN haute vitesse - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # TOYOTA / LEXUS
    # ─────────────────────────────────────────────
    "Toyota": [
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1121", "Capteur de position papillon - plage incohérente", "medium"),
        ("P1125", "Moteur de papillon - panne", "high"),
        ("P1126", "Moteur de papillon - plage de mesure", "high"),
        ("P1127", "Moteur de papillon - circuit trop bas", "high"),
        ("P1128", "Moteur de papillon - circuit trop haut", "high"),
        ("P1129", "Moteur de papillon - circuit intermittent", "high"),
        ("P1130", "Sonde lambda 1 - plage insuffisante", "medium"),
        ("P1133", "Sonde lambda 1 - temps de réponse insuffisant", "medium"),
        ("P1135", "Sonde lambda 1 - chauffage - temps de réponse insuffisant", "medium"),
        ("P1150", "Sonde lambda 2 - plage insuffisante", "medium"),
        ("P1153", "Sonde lambda 2 - temps de réponse insuffisant", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Allumeur 1 - panne du circuit", "high"),
        ("P1305", "Allumeur 2 - panne du circuit", "high"),
        ("P1310", "Allumeur 3 - panne du circuit", "high"),
        ("P1315", "Allumeur 4 - panne du circuit", "high"),
        ("P1400", "Vanne EGR - panne du circuit de commande", "medium"),
        ("P1401", "Vanne EGR - débit insuffisant", "medium"),
        ("P1500", "Démarreur - signal de démarrage - panne du circuit", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1605", "Calculateur moteur - panne de mémoire de secours", "critical"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag SRS - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("B1030", "Prétensionneur ceinture conducteur - panne", "critical"),
        ("B1040", "Prétensionneur ceinture passager - panne", "critical"),
        ("C1201", "Système ABS - panne moteur", "critical"),
        ("C1203", "Système ABS - panne de communication avec calculateur moteur", "critical"),
        ("C1241", "Tension batterie ABS - trop basse", "high"),
        ("C1243", "Capteur de vitesse roue - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # BMW
    # ─────────────────────────────────────────────
    "BMW": [
        ("P1083", "Régulation du mélange - sonde lambda 1 - limite atteinte", "medium"),
        ("P1084", "Régulation du mélange - sonde lambda 2 - limite atteinte", "medium"),
        ("P1085", "Régulation du mélange - sonde lambda 1 - adaptation trop riche", "medium"),
        ("P1086", "Régulation du mélange - sonde lambda 2 - adaptation trop riche", "medium"),
        ("P1114", "Capteur de température d'eau - valeur trop basse", "medium"),
        ("P1115", "Capteur de température d'eau - valeur trop haute", "medium"),
        ("P1188", "Régulation du mélange - sonde lambda 1 - adaptation trop pauvre", "medium"),
        ("P1189", "Régulation du mélange - sonde lambda 2 - adaptation trop pauvre", "medium"),
        ("P1340", "Capteur de vilebrequin/arbre à cames - corrélation", "high"),
        ("P1386", "Contrôle anti-cliquetis - cylindre 1 - limite atteinte", "high"),
        ("P1421", "Vanne de recirculation des gaz secondaires - panne", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1624", "Immobiliseur - panne de communication", "high"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN haute vitesse - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # FORD
    # ─────────────────────────────────────────────
    "Ford": [
        ("P1000", "Système OBD - cycles de conduite de vérification non complétés", "low"),
        ("P1001", "Système OBD - test KOER non terminé", "low"),
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1101", "Capteur de débit d'air - hors plage de test", "medium"),
        ("P1120", "Capteur de position papillon - hors plage", "medium"),
        ("P1121", "Capteur de position papillon - incohérence avec capteur MAP", "medium"),
        ("P1130", "Sonde lambda 1 - plage insuffisante", "medium"),
        ("P1131", "Sonde lambda 1 - mélange trop pauvre", "medium"),
        ("P1132", "Sonde lambda 1 - mélange trop riche", "medium"),
        ("P1150", "Sonde lambda 2 - plage insuffisante", "medium"),
        ("P1151", "Sonde lambda 2 - mélange trop pauvre", "medium"),
        ("P1152", "Sonde lambda 2 - mélange trop riche", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Bobine d'allumage - panne du circuit primaire", "high"),
        ("P1400", "Vanne EGR - panne du circuit de commande", "medium"),
        ("P1401", "Vanne EGR - débit insuffisant", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # MERCEDES-BENZ
    # ─────────────────────────────────────────────
    "Mercedes": [
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1105", "Capteur de pression absolue - panne intermittente", "medium"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1130", "Sonde lambda 1 - plage insuffisante", "medium"),
        ("P1140", "Sonde lambda 1 - chauffage - panne", "medium"),
        ("P1200", "Injecteur - panne du circuit de commande", "high"),
        ("P1300", "Bobine d'allumage - panne du circuit primaire", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag SRS - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("B1030", "Prétensionneur ceinture conducteur - panne", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("C1010", "Pompe hydraulique ABS - panne", "critical"),
        ("U0001", "Bus CAN haute vitesse - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
        ("U0121", "Perte de communication avec le calculateur ABS/ESP", "critical"),
    ],

    # ─────────────────────────────────────────────
    # OPEL / VAUXHALL / GM
    # ─────────────────────────────────────────────
    "Opel": [
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1125", "Moteur de papillon - panne", "high"),
        ("P1130", "Sonde lambda 1 - plage insuffisante", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Bobine d'allumage - panne du circuit primaire", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # HONDA / ACURA
    # ─────────────────────────────────────────────
    "Honda": [
        ("P1106", "Capteur MAP - panne intermittente", "medium"),
        ("P1107", "Capteur MAP - panne intermittente circuit bas", "medium"),
        ("P1108", "Capteur MAP - panne intermittente circuit haut", "medium"),
        ("P1121", "Capteur de position papillon - panne intermittente", "medium"),
        ("P1122", "Capteur de position papillon - panne intermittente circuit bas", "medium"),
        ("P1128", "Sonde lambda - mélange trop pauvre", "medium"),
        ("P1129", "Sonde lambda - mélange trop riche", "medium"),
        ("P1162", "Sonde lambda amont - panne du circuit", "medium"),
        ("P1163", "Sonde lambda amont - temps de réponse insuffisant", "medium"),
        ("P1164", "Sonde lambda amont - plage insuffisante", "medium"),
        ("P1165", "Sonde lambda amont - panne intermittente", "medium"),
        ("P1166", "Sonde lambda amont - chauffage - panne du circuit", "medium"),
        ("P1167", "Sonde lambda amont - chauffage - panne intermittente", "medium"),
        ("P1168", "Sonde lambda amont - tension trop basse", "medium"),
        ("P1169", "Sonde lambda amont - tension trop haute", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Allumeur 1 - panne du circuit", "high"),
        ("P1301", "Allumeur 1 - panne intermittente", "high"),
        ("P1302", "Allumeur 2 - panne du circuit", "high"),
        ("P1303", "Allumeur 2 - panne intermittente", "high"),
        ("P1304", "Allumeur 3 - panne du circuit", "high"),
        ("P1305", "Allumeur 3 - panne intermittente", "high"),
        ("P1306", "Allumeur 4 - panne du circuit", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1491", "Vanne EGR - débit insuffisant", "medium"),
        ("P1498", "Vanne EGR - débit excessif", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("B1001", "Calculateur airbag SRS - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # NISSAN
    # ─────────────────────────────────────────────
    "Nissan": [
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1105", "Capteur MAP/BARO - commutation - panne", "medium"),
        ("P1110", "Capteur de température d'air - panne intermittente", "low"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1125", "Moteur de papillon - panne", "high"),
        ("P1130", "Sonde lambda 1 - plage insuffisante", "medium"),
        ("P1140", "Sonde lambda 1 - chauffage - panne", "medium"),
        ("P1148", "Sonde lambda 1 - circuit fermé - panne", "medium"),
        ("P1168", "Sonde lambda 2 - circuit fermé - panne", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Allumeur 1 - panne du circuit", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag SRS - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],

    # ─────────────────────────────────────────────
    # HYUNDAI / KIA
    # ─────────────────────────────────────────────
    "Hyundai": [
        ("P1100", "Capteur de débit d'air - panne intermittente", "medium"),
        ("P1120", "Capteur de position papillon - panne", "medium"),
        ("P1130", "Sonde lambda 1 - plage insuffisante", "medium"),
        ("P1200", "Injecteur - panne du circuit", "high"),
        ("P1300", "Bobine d'allumage - panne du circuit primaire", "high"),
        ("P1400", "Vanne EGR - panne du circuit", "medium"),
        ("P1500", "Alternateur - panne du circuit de charge", "high"),
        ("P1600", "Calculateur moteur - panne d'alimentation", "critical"),
        ("P1700", "Boîte de vitesses automatique - panne générale", "high"),
        ("B1001", "Calculateur airbag SRS - panne interne", "critical"),
        ("B1010", "Airbag conducteur - circuit ouvert", "critical"),
        ("B1020", "Airbag passager - circuit ouvert", "critical"),
        ("C1001", "Capteur ABS roue avant gauche - panne", "critical"),
        ("C1002", "Capteur ABS roue avant droite - panne", "critical"),
        ("C1003", "Capteur ABS roue arrière gauche - panne", "critical"),
        ("C1004", "Capteur ABS roue arrière droite - panne", "critical"),
        ("U0001", "Bus CAN - panne de communication", "high"),
        ("U0100", "Perte de communication avec le calculateur moteur", "critical"),
    ],
}


class Command(BaseCommand):
    help = "Importe les codes DTC constructeurs (P1xxx, B, C, U) dans DTCReference"

    def add_arguments(self, parser):
        parser.add_argument(
            "--brand",
            type=str,
            help="Importe uniquement les codes d'une marque spécifique (ex: Renault)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simule l'import sans écrire en base de données",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Affiche les détails de chaque code importé",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verbose = options["verbose"]
        brand_filter = options.get("brand")

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Mode DRY-RUN activé — aucune écriture en base"))

        total_created = 0
        total_updated = 0
        total_skipped = 0

        brands_to_process = BRAND_DTCS.items()
        if brand_filter:
            brands_to_process = [
                (b, dtcs) for b, dtcs in BRAND_DTCS.items()
                if b.lower() == brand_filter.lower()
            ]
            if not brands_to_process:
                self.stdout.write(self.style.ERROR(
                    f"Marque '{brand_filter}' non trouvée. "
                    f"Marques disponibles: {', '.join(BRAND_DTCS.keys())}"
                ))
                return

        for brand, dtcs in brands_to_process:
            self.stdout.write(self.style.SUCCESS(f"\n🏭 Import des codes {brand} ({len(dtcs)} codes)..."))

            for code, description, severity in dtcs:
                if verbose:
                    self.stdout.write(f"  [{brand}] {code}: {description[:60]} [{severity}]")

                if dry_run:
                    total_created += 1
                    continue

                try:
                    obj, created = DTCReference.objects.update_or_create(
                        code=code,
                        brand=brand,
                        defaults={
                            "description": description,
                            "severity": severity,
                        },
                    )
                    if created:
                        total_created += 1
                    else:
                        total_updated += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ✗ Erreur pour {code} ({brand}): {e}"))
                    total_skipped += 1

        self.stdout.write("\n" + "=" * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"🔍 DRY-RUN terminé : {total_created} codes seraient importés"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Import terminé : {total_created} nouveaux codes, "
                f"{total_updated} mis à jour, {total_skipped} ignorés"
            ))
            # Affiche le total en base
            total_in_db = DTCReference.objects.count()
            self.stdout.write(self.style.SUCCESS(
                f"📊 Total codes DTC en base : {total_in_db}"
            ))
