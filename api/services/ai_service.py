import logging
import json
import re
import math
import pickle
import os
import requests
from django.utils import timezone
from django.db.models import Avg, Count
from api.models import ScanSession, DTCReference

logger = logging.getLogger(__name__)

class DTCModelAI:
    """
    Service d'IA prédictive pour l'analyse des coûts et diagnostics DTC.
    Entraîne les estimations de coût, causes et solutions basées sur l'historique réel.
    """

    @staticmethod
    def train():
        """
        Analyse toutes les sessions de scan terminées et met à jour les références DTC
        avec des données basées sur les retours réels des mécaniciens.
        """
        logger.info("Début de l'entraînement de l'IA DTC...")
        
        # On ne traite que les sessions marquées comme complétées pour avoir des données fiables
        completed_scans = ScanSession.objects.filter(is_completed=True).prefetch_related('found_dtcs', 'vehicle')
        
        if not completed_scans.exists():
            logger.warning("Aucune donnée de session complétée disponible pour l'entraînement.")
            return False

        dtc_stats = {}

        for scan in completed_scans:
            dtcs = scan.found_dtcs.all()
            if not dtcs:
                continue
            
            num_dtcs = dtcs.count()
            share_labor = scan.actual_labor_cost / num_dtcs
            share_parts = scan.actual_parts_cost / num_dtcs
            
            # Analyse des notes pour extraire causes et solutions (basique pour cette version)
            # Dans une version plus avancée, on utiliserait du NLP (Natural Language Processing)
            notes = scan.notes.lower() if scan.notes else ""
            
            for dtc in dtcs:
                key = (dtc.code, dtc.brand)
                if key not in dtc_stats:
                    dtc_stats[key] = {
                        'labor_sum': 0, 
                        'parts_sum': 0, 
                        'count': 0,
                        'notes_collected': []
                    }
                
                dtc_stats[key]['labor_sum'] += share_labor
                dtc_stats[key]['parts_sum'] += share_parts
                dtc_stats[key]['count'] += 1
                if scan.notes:
                    dtc_stats[key]['notes_collected'].append(scan.notes)

        # Mise à jour de la table DTCReference
        updates_count = 0
        for (code, brand), stats in dtc_stats.items():
            avg_labor = int(stats['labor_sum'] / stats['count'])
            avg_parts = int(stats['parts_sum'] / stats['count'])
            
            dtc_ref = DTCReference.objects.filter(code=code, brand=brand).first()
            if dtc_ref:
                # 1. Mise à jour des coûts (lissage)
                if dtc_ref.est_labor_cost == 0:
                    dtc_ref.est_labor_cost = avg_labor
                else:
                    dtc_ref.est_labor_cost = int((dtc_ref.est_labor_cost * 2 + avg_labor) / 3)
                
                if dtc_ref.est_part_price_local == 0:
                    dtc_ref.est_part_price_local = avg_parts
                else:
                    dtc_ref.est_part_price_local = int((dtc_ref.est_part_price_local * 2 + avg_parts) / 3)
                
                # 2. Analyse "avancée" des causes et solutions
                # On simule ici une extraction intelligente. En production, on utiliserait un modèle LLM ou NLP
                # pour transformer les notes disparates en causes/solutions structurées.
                if stats['notes_collected']:
                    causes, solutions = DTCModelAI._extract_insights_from_notes(stats['notes_collected'])
                    dtc_ref.probable_causes = json.dumps(causes)
                    dtc_ref.suggested_solutions = json.dumps(solutions)
                
                # 3. Ajustement de la sévérité basé sur l'historique (optionnel)
                # Si un code revient souvent avec des coûts élevés, on peut augmenter sa sévérité.
                if avg_labor + avg_parts > 100000:
                    dtc_ref.severity = 'high'
                elif avg_labor + avg_parts > 200000:
                    dtc_ref.severity = 'critical'
                
                dtc_ref.last_trained_at = timezone.now()
                dtc_ref.save()
                updates_count += 1

        logger.info(f"Entraînement terminé. {updates_count} références DTC mises à jour.")
        return True

    @staticmethod
    def _extract_insights_from_notes(notes_list):
        """
        Analyse une liste de notes pour en extraire des causes et solutions probables.
        Version simplifiée : On cherche des mots clés et on garde les phrases les plus fréquentes.
        """
        # Dans un cas réel, ici on appellerait une API de NLP ou on utiliserait un modèle local.
        # Pour cette implémentation, on va nettoyer et renvoyer les notes uniques les plus pertinentes.
        unique_insights = list(set([n.strip() for n in notes_list if len(n.strip()) > 10]))
        
        # Simulation d'extraction structurée
        causes = [n for n in unique_insights if any(word in n.lower() for word in ['cause', 'dû à', 'problème de', 'défectueux'])]
        solutions = [n for n in unique_insights if any(word in n.lower() for word in ['solution', 'réparation', 'remplacer', 'nettoyer', 'fixé'])]
        
        # Si rien n'est trouvé spécifiquement, on met les notes générales
        if not causes: causes = unique_insights[:3]
        if not solutions: solutions = unique_insights[:3]
        
        return causes[:5], solutions[:5]

    @staticmethod
    def predict_advanced(dtc_codes, vehicle_info=None):
        """
        Prédit les causes et solutions les plus probables pour un ensemble de DTC
        en tenant compte du contexte du véhicule.
        Enrichit automatiquement avec la base locale KB + scraping web si la DB est vide.
        """
        brand = vehicle_info.get('brand') if vehicle_info else None
        
        results = []
        total_labor = 0
        total_parts_min = 0
        total_parts_max = 0
        
        for code in dtc_codes:
            ref = DTCReference.objects.filter(code=code, brand=brand).first()
            if not ref:
                ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()
            
            if ref:
                causes = json.loads(ref.probable_causes) if ref.probable_causes else []
                solutions = json.loads(ref.suggested_solutions) if ref.suggested_solutions else []
                symptoms = json.loads(ref.symptoms) if ref.symptoms else []
                meaning = ref.meaning or ''

                # Enrichissement KB locale + web si données DB insuffisantes
                if not causes or not solutions:
                    kb = DTCModelAI._search_dtc_web(code, vehicle_info)
                    if kb:
                        if not causes:
                            causes = kb.get('web_causes', [])
                        if not solutions:
                            solutions = kb.get('web_solutions', [])
                        if not meaning:
                            meaning = kb.get('meaning', '')

                if not causes:
                    # Diversifier les causes génériques
                    generic_sets = [
                        ["Pièce gâtée quelque part"],
                        ["Mauvais contact électrique"],
                        ["Capteur (sensor) fatigué"]
                    ]
                    set_idx = sum(ord(char) for char in code) % len(generic_sets)
                    causes = generic_sets[set_idx]
                if not solutions:
                    generic_sol_sets = [
                        ["Regarder bien partout sur le moteur", "Contrôler les fils de courant"],
                        ["Nettoyer le capteur et sa fiche", "Vérifier les fusibles"],
                        ["Tester la continuité des fils", "Chercher une fuite"]
                    ]
                    set_idx = (sum(ord(char) for char in code) + 1) % len(generic_sol_sets)
                    solutions = generic_sol_sets[set_idx]

                results.append({
                    'code': code,
                    'description': ref.description,
                    'meaning': meaning,
                    'severity': ref.severity,
                    'symptoms': symptoms,
                    'commonSymptoms': symptoms,
                    'probable_causes': causes,
                    'possibleCauses': causes,
                    'suggested_solutions': solutions,
                    'suggestedFixes': solutions,
                    'tips': ref.tips or '',
                    'warnings': ref.warnings or '',
                    'estimated_labor': ref.est_labor_cost,
                    'estimatedLaborCost': ref.est_labor_cost,
                    'estimated_parts': {
                        'local': ref.est_part_price_local,
                        'import': ref.est_part_price_import
                    },
                    'localPartPrice': ref.est_part_price_local,
                    'importPartPrice': ref.est_part_price_import,
                    'partImageUrl': ref.part_image_url,
                    'partLocation': ref.part_location,
                })
                total_labor += ref.est_labor_cost
                total_parts_min += ref.est_part_price_local
                total_parts_max += max(ref.est_part_price_local, ref.est_part_price_import)
            else:
                # Code absent de la DB : enrichissement complet via KB locale + web
                kb = DTCModelAI._search_dtc_web(code, vehicle_info)
                if kb:
                    causes = kb.get('web_causes', [])
                    solutions = kb.get('web_solutions', [])
                    meaning = kb.get('meaning', f"Code {code}")
                    source = kb.get('web_source', 'inconnu')
                    results.append({
                        'code': code,
                        'description': meaning,
                        'meaning': meaning,
                        'severity': 'medium',
                        'symptoms': [],
                        'commonSymptoms': [],
                        'probable_causes': causes,
                        'possibleCauses': causes,
                        'suggested_solutions': solutions,
                        'suggestedFixes': solutions,
                        'tips': '',
                        'warnings': '',
                        'estimated_labor': 0,
                        'estimatedLaborCost': 0,
                        'localPartPrice': 0,
                        'importPartPrice': 0,
                        'data_source': source,
                    })
                else:
                    results.append({
                        'code': code,
                        'description': f"Code {code} — non répertorié",
                        'meaning': f"Le code {code} n'est pas encore dans notre base. Une recherche manuelle est recommandée.",
                        'severity': 'medium',
                        'symptoms': [],
                        'commonSymptoms': [],
                        'probable_causes': [
                            "Mauvais contact électrique ou fiche débranchée",
                            "Capteur (sensor) fatigué ou à nettoyer",
                            "Problème de communication entre les ordinateurs (CAN/LIN)",
                        ] if sum(ord(c) for c in code) % 2 == 0 else [
                            "Capteur (sensor) ou pièce gâtée",
                            "Fils de courant coupés ou fiche rouillée",
                            "Fuite ou pression anormale dans le système",
                        ],
                        'possibleCauses': [
                            "Mauvais contact électrique ou fiche débranchée",
                            "Capteur (sensor) fatigué ou à nettoyer",
                            "Problème de communication entre les ordinateurs (CAN/LIN)",
                        ] if sum(ord(c) for c in code) % 2 == 0 else [
                            "Capteur (sensor) ou pièce gâtée",
                            "Fils de courant coupés ou fiche rouillée",
                            "Fuite ou pression anormale dans le système",
                        ],
                        'suggested_solutions': [
                            "Nettoyer le capteur concerné et sa fiche",
                            "Vérifier les fusibles du compartiment moteur",
                            "Chercher plus de détails sur cette panne",
                        ] if sum(ord(c) for c in code) % 2 == 0 else [
                            "Regarder bien partout sur le moteur",
                            "Contrôler les fils de courant et les fiches",
                            "Faire un diagnostic plus poussé avec un expert",
                        ],
                        'suggestedFixes': [
                            "Nettoyer le capteur concerné et sa fiche",
                            "Vérifier les fusibles du compartiment moteur",
                            "Chercher plus de détails sur cette panne",
                        ] if sum(ord(c) for c in code) % 2 == 0 else [
                            "Regarder bien partout sur le moteur",
                            "Contrôler les fils de courant et les fiches",
                            "Faire un diagnostic plus poussé avec un expert",
                        ],
                        'estimated_labor': 0,
                        'estimatedLaborCost': 0,
                        'localPartPrice': 0,
                        'importPartPrice': 0,
                        'data_source': 'non_trouve',
                    })

        confidence = "Élevée (KB + DB)" if any(r.get('probable_causes') for r in results) else "Moyenne (Générique)"

        return {
            'diagnostics': results,
            'summary': {
                'total_estimated_labor': total_labor,
                'total_estimated_parts_min': total_parts_min,
                'total_estimated_parts_max': total_parts_max,
                'confidence_score': confidence,
                'engine_version': "IA Predict v3.2 (KB + DB + Web + Logic Variator)"
            }
        }

    @staticmethod
    def analyze_dtcs_deep(dtc_codes, vehicle_info=None):
        """
        Analyse approfondie de codes DTC issus d'un scan.
        Combine DB Django + base locale KB + scraping web pour une analyse experte.
        Retourne une interprétation narrative, des causes classées par probabilité,
        des solutions numérotées et des estimations de coûts.
        """
        brand = vehicle_info.get('brand', '') if vehicle_info else ''
        model = vehicle_info.get('model', '') if vehicle_info else ''
        year = vehicle_info.get('year', '') if vehicle_info else ''

        results = []
        total_labor = 0
        nb_critical = 0
        nb_high = 0

        # ── 3. Fusion intelligente (DB prioritaire, KB en complément) ────────
        def vulcanize_text(text):
            if not text: return text
            import re
            
            # 0. Suppression initiale des espaces multiples et normalisation
            text = re.sub(r'\s+', ' ', text).strip()

            # 1. Remplacements pour un langage "parlant" mais correct
            # On évite le mot "gâté" systématique qui fait peu professionnel
            # On privilégie "défectueux", "en panne", "abîmé"
            repls = [
                (r'défectueux', 'défectueux (en panne)'),
                (r'défaillant', 'en panne'),
                (r'défaillance', 'problème'),
                (r'dysfonctionnement', 'problème technique'),
                (r'endommagé', 'cassé ou abîmé'),
                (r'corrodé', 'rouillé'),
                (r'obstruction', 'bouchage'),
                (r'obstrué', 'bouché'),
                (r'remplacer', 'changer'),
                (r'inspection', 'contrôle visuel'),
                (r'inspecter', 'bien vérifier'),
                (r'vérifier', 'contrôler'),
                (r'nettoyage', 'nettoyer'),
                (r'nettoyer', 'nettoyer'),
                (r'ajustement', 'réglage'),
                (r'ajuster', 'régler'),
                (r'réparation', 'réparer'),
                (r'réparer', 'réparer'),
                (r'faisceau', 'faisceau (groupe de fils)'),
                (r'câblage', 'fils électriques'),
                (r'connecteur', 'fiche (prise)'),
                (r'court-circuit', 'court-circuit (masse)'),
                (r'circuit ouvert', 'fil coupé ou débranché'),
                (r'alimentation', 'alimentation électrique'),
                (r'tension', 'tension (voltage)'),
                (r'capteur', 'capteur (sensor)'),
                (r'sonde', 'sonde (capteur)'),
                (r'perte de puissance', "perte de puissance (le moteur n'a plus de force)"),
                (r'ralenti instable', 'le moteur tremble au repos'),
                (r'calage', "le moteur s'éteint tout seul"),
                (r'calculateur', 'ordinateur de bord (calculateur)'),
                (r'insuffisant', 'trop faible'),
                (r'excessif', 'trop élevé'),
                (r'solution', 'solution'),
                (r'cause', 'cause'),
                (r'dû à', 'à cause de'),
                (r'cause probable', 'cause probable'),
                (r'colmaté', 'bouché'),
                (r'manomètre', 'appareil de mesure de pression'),
                (r'valeur nominale', 'valeur normale'),
                (r'durite', 'tuyau (durite)'),
                (r'admission', "entrée d'air (admission)"),
                (r'échappement', 'sortie des gaz (échappement)'),
            ]
            
            for old, new in repls:
                pattern = r'\b' + old + r'\b'
                text = re.sub(pattern, new, text, flags=re.IGNORECASE)

            # 2. Cas spécifiques de fuites
            text = re.sub(r"fuite d'air", "prise d'air (fuite d'air)", text, flags=re.IGNORECASE)
            text = re.sub(r"fuite de (liquide|huile|carburant|essence|gasoil|eau|refroidissement)", r"fuite de \1 (écoulement)", text, flags=re.IGNORECASE)

            # 3. Suppression des répétitions de mots consécutifs (ex: "le le")
            text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text, flags=re.IGNORECASE)
            
            # 4. Suppression des répétitions de blocs entre parenthèses identiques
            # ex: "capteur (sensor) (sensor)" -> "capteur (sensor)"
            text = re.sub(r'(\([^\)]+\))\s*\1', r'\1', text)
            
            # 5. Nettoyage final
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Majuscule au début si besoin
            if text and len(text) > 0:
                text = text[0].upper() + text[1:]
                
            return text

        # ── 4. Déductions transversales (Logique de "Chef") ──────────────────
        chef_advice = []
        all_codes = [str(c).upper().strip() for c in dtc_codes]
        
        # Corrélation : Mélange Pauvre + Débitmètre
        if any(c in ['P0171', 'P0174'] for c in all_codes) and any(c in ['P0100', 'P0101', 'P0102'] for c in all_codes):
            chef_advice.append("👨‍🔧 LE CHEF DIT : Vos codes P0171/P0174 combinés au débitmètre indiquent presque sûrement que votre débitmètre d'air (MAF) est sale ou qu'il y a une grosse prise d'air après le filtre. Nettoyez le capteur d'abord !")
        
        # Corrélation : Ratés d'allumage multiples
        if 'P0300' in all_codes and any(c.startswith('P030') and c != 'P0300' for c in all_codes):
            chef_advice.append("👨‍🔧 LE CHEF DIT : Vous avez des ratés sur plusieurs cylindres. Ne changez pas qu'une seule bougie, vérifiez plutôt la bobine commune ou la pression d'essence qui arrive au moteur.")

        # Corrélation : Sonde Lambda + Catalyseur
        if 'P0420' in all_codes and any(c.startswith('P013') or c.startswith('P015') for c in all_codes):
            chef_advice.append("👨‍🔧 LE CHEF DIT : Avant de condamner votre catalyseur (P0420), réglez d'abord le problème des sondes lambda. Une mauvaise sonde fait mentir l'ordinateur sur l'état du pot d'échappement.")

        # Corrélation : Tension basse + multiples codes U
        if any(c.startswith('U') for c in all_codes) and len([c for c in all_codes if c.startswith('U')]) >= 2:
            chef_advice.append("👨‍🔧 LE CHEF DIT : Trop de codes de communication (Uxxxx) d'un coup. C'est souvent la batterie qui est fatiguée ou une cosse mal serrée. Vérifiez le courant avant de toucher aux boîtiers !")

        for code in dtc_codes:
            code = str(code).upper().strip()
            # ── 1. Chercher dans la DB Django ────────────────────────────────────
            ref = DTCReference.objects.filter(code=code, brand=brand).first()
            if not ref:
                ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()

            db_causes = []
            db_solutions = []
            db_symptoms = []
            db_meaning = ''
            db_severity = 'medium'
            db_labor = 0
            db_parts_local = 0
            db_parts_import = 0
            db_tips = ''
            db_warnings = ''

            if ref:
                db_causes = json.loads(ref.probable_causes) if ref.probable_causes else []
                db_solutions = json.loads(ref.suggested_solutions) if ref.suggested_solutions else []
                db_symptoms = json.loads(ref.symptoms) if ref.symptoms else []
                db_meaning = ref.meaning or ref.description or ''
                db_severity = ref.severity or 'medium'
                db_labor = ref.est_labor_cost or 0
                db_parts_local = ref.est_part_price_local or 0
                db_parts_import = ref.est_part_price_import or 0
                db_tips = ref.tips or ''
                db_warnings = ref.warnings or ''

            # ── 2. Enrichir avec KB locale + web ─────────────────────────────────
            kb = DTCModelAI._search_dtc_web(code, vehicle_info)
            kb_causes = kb.get('web_causes', []) if kb else []
            kb_solutions = kb.get('web_solutions', []) if kb else []
            kb_symptoms = kb.get('web_symptoms', []) if kb else []
            kb_meaning = kb.get('meaning', '') if kb else ''
            kb_severity = kb.get('web_severity') if kb else None
            kb_source = kb.get('web_source', '') if kb else ''

            final_solutions = db_solutions if db_solutions else kb_solutions
            final_symptoms = db_symptoms if db_symptoms else kb_symptoms
            final_meaning = db_meaning if db_meaning else kb_meaning if kb_meaning else f"Code {code} détecté"
            final_severity = db_severity if db_severity != 'medium' or not kb_severity else kb_severity

            # Dédupliquer et limiter
            seen = set()
            merged_causes = []
            for c in (db_causes + [x for x in kb_causes if x not in db_causes]):
                if c.lower() not in seen:
                    seen.add(c.lower())
                    merged_causes.append(c)
            merged_causes = merged_causes[:6]

            seen = set()
            merged_solutions = []
            for s in (db_solutions + [x for x in kb_solutions if x not in db_solutions]):
                if s.lower() not in seen:
                    seen.add(s.lower())
                    merged_solutions.append(s)
            merged_solutions = merged_solutions[:6]

            if not merged_causes:
                # Système de Smart Fallback basé sur le type de code
                if code.startswith('P0'):
                    merged_causes = [
                        "Problème général sur le moteur (standard OBD2)",
                        "Mauvais signal d'un capteur (sensor) important",
                        "Fils de courant coupés ou fiche mal branchée",
                        "Fuite d'air ou de carburant quelque part"
                    ]
                    merged_solutions = [
                        "Contrôler les fiches et les fils sur le moteur",
                        "Vérifier si y'a pas un tuyau percé ou débranché",
                        "Nettoyer le capteur (sensor) lié à ce code",
                        "Effacer le code et voir s'il revient après avoir roulé"
                    ]
                elif code.startswith('P1') or code.startswith('P2') or code.startswith('P3'):
                    merged_causes = [
                        f"Problème spécifique au constructeur {brand}",
                        "Capteur propriétaire ou module électronique fatigué",
                        "Mauvais réglage d'usine ou mise à jour nécessaire",
                        "Fils de courant (faisceau) abîmés ou fiche rouillée"
                    ]
                    merged_solutions = [
                        f"Chercher la note technique {brand} pour ce code {code}",
                        "Vérifier les fiches du calculateur moteur",
                        "Tester la résistance du composant lié à cette panne",
                        "Consulter un électricien auto expert en {brand}"
                    ]
                elif code.startswith('U'):
                    merged_causes = [
                        "Problème de communication entre les ordinateurs (réseau CAN)",
                        "Batterie faible ou voltage instable",
                        "Fiche de l'ordinateur de bord (calculateur) mal enfoncée",
                        "Un module ne répond plus sur le réseau"
                    ]
                    merged_solutions = [
                        "Vérifier le voltage de la batterie (doit être > 12.5V)",
                        "Contrôler si les fiches du calculateur sont bien fixées",
                        "Chercher s'il n'y a pas un court-circuit sur les fils de communication",
                        "Débrancher la batterie 10 minutes et rebrancher"
                    ]
                else:
                    # Varier les causes génériques selon le code (Fallback ultime)
                    generic_sets = [
                        [
                            "Pièce gâtée quelque part",
                            "Fils de courant coupés ou fiche rouillée",
                            "Petit problème dans l'ordinateur de bord"
                        ],
                        [
                            "Mauvais contact électrique ou fiche débranchée",
                            "Capteur (sensor) fatigué ou à nettoyer",
                            "Fuite ou pression anormale dans le système"
                        ],
                        [
                            "Problème de communication entre les calculateurs",
                            "Composant mécanique interne usé",
                            "Fusible grillé ou relais défaillant"
                        ]
                    ]
                    # Utiliser le code pour choisir un set
                    set_idx = sum(ord(char) for char in code) % len(generic_sets)
                    merged_causes = generic_sets[set_idx]

            if not merged_solutions:
                generic_sol_sets = [
                    [
                        "Regarder bien partout sur le moteur",
                        "Contrôler les fils de courant et les fiches",
                        "Chercher plus de détails sur cette panne"
                    ],
                    [
                        "Nettoyer le capteur concerné et sa fiche",
                        "Vérifier les fusibles du compartiment moteur",
                        "Faire un diagnostic plus poussé avec un expert"
                    ],
                    [
                        "Tester la continuité des fils électriques",
                        "Contrôler si y'a pas une prise d'air ou une fuite",
                        "Réinitialiser le calculateur et voir si ça revient"
                    ]
                ]
                set_idx = (sum(ord(char) for char in code) + 1) % len(generic_sol_sets)
                merged_solutions = generic_sol_sets[set_idx]

            seen = set()
            merged_symptoms = []
            for s in (db_symptoms + [x for x in kb_symptoms if x not in db_symptoms]):
                if s.lower() not in seen:
                    seen.add(s.lower())
                    merged_symptoms.append(s)
            merged_symptoms = merged_symptoms[:6]

            # ── 4. Interprétation narrative ───────────────────────────────────────
            # Vulgariser les textes venant du web ou des messages par défaut
            merged_causes = [vulcanize_text(c) for c in merged_causes]
            merged_solutions = [vulcanize_text(s) for s in merged_solutions]
            merged_symptoms = [vulcanize_text(s) for s in merged_symptoms]
            final_meaning = vulcanize_text(final_meaning)
            db_tips = vulcanize_text(db_tips)
            db_warnings = vulcanize_text(db_warnings)

            vehicle_ctx = f" sur votre {brand} {model} {year}".strip() if brand else ""
            import random
            severity_messages = {
                'critical': [
                    "⚠️ PANNE CRITIQUE — Arrêtez le véhicule immédiatement",
                    "❌ DANGER — Ne roulez plus avec le véhicule dans cet état",
                    "⚠️ ALERTE ROUGE — Panne sérieuse détectée, coupez le moteur",
                    "🆘 URGENCE MÉCANIQUE — Risque de casse moteur imminente",
                ],
                'high': [
                    "🔴 PANNE GRAVE — Réparation nécessaire rapidement",
                    "🚫 PROBLÈME SÉRIEUX — Conduisez le véhicule au garage dès aujourd'hui",
                    "🔴 DÉFAUT MAJEUR — Risque d'endommagement d'autres composants",
                    "🛑 ALERTE — Problème électrique ou mécanique important",
                ],
                'medium': [
                    "🟠 PROBLÈME — À vérifier dans les prochains jours",
                    "⚠️ ATTENTION — Anomalie détectée sur le système moteur",
                    "🟠 À CONTRÔLER — Prévoyez une visite chez votre mécanicien",
                    "⚙️ MAINTENANCE — Le système ne fonctionne pas de manière optimale",
                ],
                'low': [
                    "🟢 ANOMALIE MINEURE — À surveiller lors de vos prochains trajets",
                    "ℹ️ INFORMATION — Légère fatigue d'un composant détectée",
                    "🟡 À SURVEILLER — Pas d'urgence, mais restez vigilant",
                    "📝 NOTE — Un simple nettoyage ou réglage pourrait suffire",
                ],
            }
            
            # Choix d'un message basé sur le code pour que le même code ait toujours le même message
            # mais que des codes différents puissent avoir des messages différents
            msg_list = severity_messages.get(final_severity, severity_messages['medium'])
            msg_index = sum(ord(char) for char in code) % len(msg_list)
            severity_txt = msg_list[msg_index]

            interpretation = (
                f"{severity_txt}{vehicle_ctx}.\n"
                f"Diagnostic : {final_meaning}.\n"
                f"Cause probable : {merged_causes[0] if merged_causes else 'analyse en cours'}.\n"
                f"Action recommandée : {merged_solutions[0] if merged_solutions else 'consulter un expert'}."
            )
            if db_tips:
                interpretation += f"\n💡 Conseil : {db_tips}"

            # ── 5. Certitude ──────────────────────────────────────────────────────
            certitude = 90 if ref and db_causes else (75 if kb_causes else 40)

            entry = {
                'code': code,
                'description': final_meaning,
                'meaning': final_meaning,
                'severity': final_severity,
                'certitude': certitude,
                'interpretation': (
                    f"Sur votre {brand} {model}, ce code indique : {final_meaning}."
                ),
                'chef_note': next((advice for advice in chef_advice if code[:5] in advice), None),
                'symptoms': merged_symptoms,
                'commonSymptoms': merged_symptoms,
                'probable_causes': merged_causes,
                'possibleCauses': merged_causes,
                'suggested_solutions': merged_solutions,
                'suggestedFixes': merged_solutions,
                'tips': db_tips,
                'warnings': db_warnings,
                'estimated_labor': db_labor,
                'estimatedLaborCost': db_labor,
                'localPartPrice': db_parts_local,
                'importPartPrice': db_parts_import,
                'data_source': 'db+kb' if ref and kb else ('db' if ref else ('kb' if kb else 'generique')),
                'kb_source': kb_source,
            }
            results.append(entry)
            total_labor += db_labor
            if final_severity == 'critical':
                nb_critical += 1
            elif final_severity == 'high':
                nb_high += 1

        # ── Verdict global ────────────────────────────────────────────────────────
        if nb_critical > 0:
            verdict = "⚠️ DANGER : Votre véhicule présente des pannes critiques. L'utilisation du véhicule est fortement déconseillée avant réparation."
        elif nb_high > 0:
            verdict = "🔴 IMPORTANT : Plusieurs pannes graves ont été détectées. Une visite au garage est recommandée dans les plus brefs délais."
        elif len(results) > 3:
            verdict = "🟠 ATTENTION : De nombreuses anomalies ont été relevées. Un contrôle global du véhicule est conseillé pour éviter des pannes en cascade."
        elif results:
            verdict = "🟢 SUIVI : Quelques anomalies mineures ont été détectées. À surveiller lors du prochain entretien."
        else:
            verdict = "✅ RAS : Aucun défaut majeur n'a été identifié par l'analyse IA."

        return {
            'diagnostics': results,
            'summary': {
                'verdict': vulcanize_text(verdict),
                'chef_global_advice': chef_advice if chef_advice else ["Continuez l'entretien régulier de votre véhicule."],
                'nb_codes': len(results),
                'nb_critical': nb_critical,
                'nb_high': nb_high,
                'total_estimated_labor': total_labor,
                'engine_version': 'IA Deep DTC v4.2 (Standardized SAE + Smart Fallback)',
            }
        }

    @staticmethod
    def predict_costs(dtc_codes, brand=None):
        """
        Reste pour compatibilité descendante.
        """
        res = DTCModelAI.predict_advanced(dtc_codes, {'brand': brand})
        return {
            'estimated_labor': res['summary']['total_estimated_labor'],
            'estimated_parts_min': res['summary']['total_estimated_parts_min'],
            'estimated_parts_max': res['summary']['total_estimated_parts_max'],
            'confidence_score': res['summary']['confidence_score']
        }

    @staticmethod
    def analyze_live_deep(pid_values, vehicle_info=None):
        """
        Analyse approfondie en temps réel des données PIDs OBD.
        Détecte les anomalies simples, les corrélations multi-PIDs (pannes cachées),
        et retourne des interprétations claires avec niveau de certitude.

        pid_values : dict { 'PID_HEX': float_value }
        vehicle_info : dict { 'brand': str, 'year': int, 'model': str } (optionnel)
        """
        brand = vehicle_info.get('brand') if vehicle_info else None
        year = vehicle_info.get('year') if vehicle_info else None

        # ── 1. SEUILS SIMPLES ────────────────────────────────────────────────────
        # (pid, condition, dtc_virtuel, label_court, sévérité, certitude %)
        SIMPLE_RULES = [
            ('05', lambda v: v > 110,        'P0217', 'Le moteur chauffe trop (critique >110°C)',           'critical', 97),
            ('05', lambda v: 100 < v <= 110, 'P0218', 'Le moteur chauffe beaucoup (100-110°C)',    'high',     88),
            ('05', lambda v: 95 < v <= 100,  'P0217_W','Le moteur commence à chauffer (95-100°C)',         'medium',   75),
            ('0C', lambda v: v > 6500,       'P0219', 'Moteur tourne trop vite (>6500 RPM)',           'critical', 95),
            ('0C', lambda v: 5500 < v <= 6500,'P0220','Moteur tourne très vite (5500-6500 RPM)',        'high',     85),
            ('0C', lambda v: 0 < v < 400,    'P0300', 'Moteur tremble ou veut s\'éteindre (<400 RPM)',     'high',     80),
            ('42', lambda v: v < 11.0,       'P0562', 'Batterie presque déchargée (<11V)',              'critical', 96),
            ('42', lambda v: 11.0 <= v < 11.8,'P0562_W','Batterie faible (11-11.8V)',         'high',     87),
            ('42', lambda v: v > 15.5,       'P0563', 'Alternateur envoie trop de courant (>15.5V)',              'high',     90),
            ('2F', lambda v: v < 8,          'P0087', 'Plus de carburant dans le réservoir (<8%)',                     'critical', 99),
            ('2F', lambda v: 8 <= v < 15,    'P0087_W','Carburant presque fini (8-15%)',                  'high',     95),
            ('04', lambda v: v > 90,         'P0101', 'Le moteur travaille trop fort (>90%)',                'high',     82),
            ('04', lambda v: 80 < v <= 90,   'P0102', 'Le moteur travaille très fort (80-90%)',           'medium',   70),
            ('0B', lambda v: v > 210,        'P0106', 'Pression d\'air trop haute dans le moteur',        'high',     78),
            ('0F', lambda v: v > 65,         'P0113', 'L\'air qui entre est trop chaud (>65°C)',    'high',     80),
            ('0F', lambda v: 55 < v <= 65,   'P0113_W','L\'air qui entre est chaud (55-65°C)',   'medium',   68),
            ('11', lambda v: v > 92,         'P0122', 'La pédale d\'accélérateur est presque bloquée (>92%)',          'medium',   72),
            ('5C', lambda v: v > 135,        'P0524', 'L\'huile du moteur chauffe trop (critique >135°C)',   'critical', 94),
            ('5C', lambda v: 120 < v <= 135, 'P0524_W','L\'huile du moteur chauffe beaucoup (120-135°C)', 'high',     85),
            ('0D', lambda v: v > 200,        'P0500', 'La voiture roule trop vite (>200 km/h)',       'high',     90),
            ('33', lambda v: v < 95,         'P0190', 'Pression d\'air extérieure bizarrement basse',    'medium',   60),
        ]

        simple_anomalies = []
        for pid, cond, dtc, label, severity, certitude in SIMPLE_RULES:
            val = pid_values.get(pid)
            if val is not None:
                try:
                    if cond(val):
                        simple_anomalies.append({
                            'type': 'simple',
                            'pid': pid,
                            'value': val,
                            'dtc_code': dtc,
                            'label': label,
                            'severity': severity,
                            'certitude': certitude,
                        })
                except Exception:
                    pass

        # ── 2. CORRÉLATIONS MULTI-PIDs (PANNES CACHÉES) ──────────────────────────
        # Ces règles détectent des syndromes invisibles à l'analyse simple
        correlation_anomalies = []

        temp   = pid_values.get('05')
        rpm    = pid_values.get('0C')
        load   = pid_values.get('04')
        volt   = pid_values.get('42')
        fuel   = pid_values.get('2F')
        map_p  = pid_values.get('0B')
        iat    = pid_values.get('0F')
        tps    = pid_values.get('11')
        oil_t  = pid_values.get('5C')
        speed  = pid_values.get('0D')

        # Syndrome turbo : charge élevée + pression collecteur basse + température air haute
        if load and map_p and iat:
            if load > 75 and map_p < 120 and iat > 50:
                interpretation_text = (
                    "Le moteur travaille intensément ({:.0f}%) mais l'admission d'air est insuffisante ({:.0f} kPa) "
                    "et la température d'entrée est trop élevée ({:.0f}°C). Cela suggère un défaut du turbo. "
                    "Causes possibles : durite de turbo percée ou débranchée, clapet (wastegate) bloqué, ou intercooler obstrué."
                ).format(load, map_p, iat)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0B', '0F'],
                    'valeurs': {'charge': load, 'pression_collecteur': map_p, 'temp_air': iat},
                    'dtc_code': 'CORR_TURBO',
                    'label': 'Défaut de performance Turbo',
                    'severity': 'high',
                    'certitude': 82,
                    'interpretation': interpretation_text,
                    'actions': [
                        "Vérifier l'étanchéité des durites du turbo",
                        "Contrôler le fonctionnement de la wastegate",
                        "Inspecter l'intercooler (radiateur d'air)",
                        "Mesurer la pression de suralimentation réelle",
                    ],
                })

        # Syndrome alternateur défaillant : tension basse + RPM normal + charge élevée
        if volt and rpm and load:
            if volt < 12.5 and rpm > 800 and load > 40:
                interpretation_text = (
                    "La tension mesurée est de {:.1f}V alors que le moteur tourne à {:.0f} RPM. "
                    "L'alternateur devrait fournir entre 13.8V et 14.8V. "
                    "Causes probables : alternateur défectueux, régulateur hors service ou courroie détendue."
                ).format(volt, rpm, load)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['42', '0C', '04'],
                    'valeurs': {'tension': volt, 'rpm': rpm, 'charge': load},
                    'dtc_code': 'CORR_ALT',
                    'label': 'Sous-performance de l\'alternateur',
                    'severity': 'high',
                    'certitude': 88,
                    'interpretation': interpretation_text,
                    'actions': [
                        "Tester la charge de l'alternateur au multimètre (viser 13.8V-14.8V)",
                        "Vérifier la tension de la courroie d'accessoires",
                        "Inspecter les cosses et le câblage de la batterie",
                        "Contrôler la mise à la terre (tresse de masse) du moteur",
                    ],
                })

        # Syndrome refroidissement : température haute + RPM bas + charge faible (thermostat bloqué fermé)
        if temp and rpm and load:
            if temp > 95 and rpm < 1500 and load < 30:
                interpretation_text = (
                    "Le moteur est en surchauffe ({:.0f}°C) malgré un régime faible ({:.0f} RPM). "
                    "Cela indique souvent un thermostat (calorstat) bloqué en position fermée, "
                    "empêchant la circulation du liquide vers le radiateur. "
                    "Attention : risque de rupture du joint de culasse si vous continuez à rouler."
                ).format(temp, rpm, load)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['05', '0C', '04'],
                    'valeurs': {'temp': temp, 'rpm': rpm, 'charge': load},
                    'dtc_code': 'CORR_THERMO',
                    'label': 'Suspicion de thermostat bloqué',
                    'severity': 'critical',
                    'certitude': 91,
                    'interpretation': interpretation_text,
                    'actions': [
                        "COUPER le moteur immédiatement si la température dépasse 110°C",
                        "Vérifier le niveau du liquide de refroidissement après refroidissement",
                        "Remplacer le thermostat (calorstat)",
                        "Vérifier l'absence de gaz de combustion dans le circuit (test CO2)",
                        "Contrôler le déclenchement des motoventilateurs",
                    ],
                })

        # Syndrome injection : charge élevée + RPM instable + papillon normal (injecteurs encrassés)
        if load and rpm and tps:
            if load > 70 and rpm < 1000 and tps < 20:
                interpretation_text = (
                    "Le moteur peine ({:.0f}%) malgré une faible sollicitation de l'accélérateur ({:.0f}%) et un régime instable ({:.0f} RPM). "
                    "Le calculateur compense probablement un débit d'injection insuffisant. "
                    "Causes possibles : injecteurs encrassés ou faiblesse de la pompe à carburant."
                ).format(load, tps, rpm)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0C', '11'],
                    'valeurs': {'charge': load, 'rpm': rpm, 'tps': tps},
                    'dtc_code': 'CORR_INJECT',
                    'label': 'Défaut du système d\'injection',
                    'severity': 'high',
                    'certitude': 79,
                    'interpretation': interpretation_text,
                    'actions': [
                        "Procéder au nettoyage des injecteurs (additif ou ultrasons)",
                        "Mesurer la pression de la rampe d'injection",
                        "Tester le débit de la pompe à carburant",
                        "Remplacer le filtre à carburant si nécessaire",
                    ],
                })

        # Syndrome huile dégradée : température huile élevée + température moteur normale
        if oil_t and temp:
            if oil_t > 120 and temp < 95:
                interpretation_text = (
                    "La température d'huile est excessive ({:.0f}°C) alors que la température moteur reste normale ({:.0f}°C). "
                    "Cela suggère une huile dégradée, un niveau insuffisant ou un défaut de lubrification. "
                    "Une huile surchauffée perd ses propriétés protectrices et risque d'endommager les paliers moteur."
                ).format(oil_t, temp)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['5C', '05'],
                    'valeurs': {'temp_huile': oil_t, 'temp_moteur': temp},
                    'dtc_code': 'CORR_HUILE',
                    'label': 'Surchauffe d\'huile moteur',
                    'severity': 'high',
                    'certitude': 84,
                    'interpretation': interpretation_text,
                    'actions': [
                        "Contrôler immédiatement le niveau d'huile moteur",
                        "Vérifier la viscosité et l'aspect de l'huile (vidange recommandée si noire)",
                        "Effectuer une vidange avec une huile préconisée par le constructeur",
                        "Vérifier l'état de l'échangeur huile/eau (si présent)",
                    ],
                })

        # Syndrome consommation excessive : charge élevée + vitesse modérée + carburant qui baisse vite
        if load and speed and fuel:
            if load > 80 and speed < 80 and fuel < 30:
                interpretation_text = (
                    "La charge moteur est anormalement haute ({:.0f}%) pour une vitesse modérée ({:.0f} km/h). "
                    "Cette résistance inhabituelle entraîne une surconsommation. "
                    "Causes possibles : pneus sous-gonflés, étrier de frein grippé ou patinage de l'embrayage."
                ).format(load, speed, fuel)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0D', '2F'],
                    'valeurs': {'charge': load, 'vitesse': speed, 'carburant': fuel},
                    'dtc_code': 'CORR_CONSO',
                    'label': 'Surconsommation anormale détectée',
                    'severity': 'medium',
                    'certitude': 74,
                    'interpretation': interpretation_text,
                    'actions': [
                        "Vérifier la pression de gonflage des pneumatiques",
                        "Contrôler si un disque de frein chauffe anormalement (étrier grippé)",
                        "Tester l'absence de patinage du disque d'embrayage",
                        "Remplacer le filtre à air s'il est colmaté",
                    ],
                })

        # Syndrome démarrage difficile : tension basse + RPM instable au démarrage
        if volt and rpm:
            if volt < 11.5 and 0 < rpm < 600:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['42', '0C'],
                    'valeurs': {'tension': volt, 'rpm': rpm},
                    'dtc_code': 'CORR_BATT',
                    'label': 'Batterie insuffisante pour démarrage fiable',
                    'severity': 'high',
                    'certitude': 93,
                    'interpretation': (
                        "Tension de {:.1f}V avec régime à {:.0f} RPM. "
                        "La batterie ne fournit pas assez d'énergie au démarreur, causant un régime de démarrage insuffisant. "
                        "Risque de panne de démarrage imminente, surtout par temps froid. "
                        "Cause : batterie en fin de vie (> 4-5 ans), cellule défectueuse, ou décharge profonde répétée."
                    ).format(volt, rpm),
                    'actions': [
                        "Tester la batterie avec un testeur de charge (capacité réelle vs nominale)",
                        "Vérifier la date de fabrication de la batterie (étiquette sur le boîtier)",
                        "Contrôler les bornes de batterie (oxydation = résistance supplémentaire)",
                        "Mesurer la tension de charge de l'alternateur (13.8-14.8V moteur tournant)",
                        "Remplacer la batterie si > 4 ans ou capacité < 70% du nominal",
                    ],
                })

        # ── DÉTECTION COURTS-CIRCUITS & ANOMALIES ÉLECTRIQUES ────────────────────

        # Court-circuit masse : tension anormalement haute moteur tournant (régulateur court-circuité)
        if volt and rpm:
            if volt > 15.5 and rpm > 600:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['42', '0C'],
                    'valeurs': {'tension': volt, 'rpm': rpm},
                    'dtc_code': 'CORR_CC_ALT',
                    'label': '⚡ Court-circuit probable — Surtension alternateur',
                    'severity': 'critical',
                    'certitude': 94,
                    'interpretation': (
                        "Tension de {:.1f}V mesurée moteur tournant ({:.0f} RPM). "
                        "Une tension supérieure à 15.5V indique un régulateur de tension défaillant ou un court-circuit dans le circuit de charge. "
                        "Risque immédiat : destruction de l'électronique embarquée (calculateur, capteurs, fusibles), "
                        "surchauffe de la batterie pouvant provoquer un incendie. "
                        "Couper les équipements électriques non essentiels immédiatement."
                    ).format(volt, rpm),
                    'actions': [
                        "⚠️ URGENT : Couper la climatisation et les équipements électriques non vitaux",
                        "Mesurer la tension aux bornes de la batterie avec un multimètre",
                        "Vérifier le régulateur de tension intégré à l'alternateur",
                        "Contrôler le câblage entre alternateur et batterie (court-circuit possible)",
                        "Remplacer l'alternateur ou son régulateur de tension",
                        "Vérifier l'état de la batterie après l'incident (risque de gonflement)",
                    ],
                })

        # Court-circuit capteur : tension batterie instable (oscillation rapide simulée par valeur hors plage)
        if volt and rpm:
            if 11.8 < volt < 12.5 and rpm > 1500 and load and load > 50:
                # Alternateur qui charge insuffisamment sous charge = début de défaillance
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['42', '0C', '04'],
                    'valeurs': {'tension': volt, 'rpm': rpm, 'charge': load},
                    'dtc_code': 'CORR_ALT_PRED',
                    'label': '🔮 Prédiction : Alternateur en début de défaillance',
                    'severity': 'high',
                    'certitude': 78,
                    'interpretation': (
                        "Tension de {:.1f}V sous charge ({:.0f}% à {:.0f} RPM). "
                        "Un alternateur sain doit maintenir 13.8V-14.8V même sous forte charge. "
                        "Cette valeur basse sous charge indique une usure des charbons, "
                        "un enroulement partiellement court-circuité, ou une diode de redressement défaillante. "
                        "Sans intervention, la batterie se déchargera progressivement et le véhicule s'arrêtera."
                    ).format(volt, load, rpm),
                    'actions': [
                        "Tester l'alternateur sur banc de charge (mesure ampérage réel)",
                        "Vérifier les charbons de l'alternateur (usure > 50% = remplacement)",
                        "Contrôler les diodes de redressement (test au multimètre en mode diode)",
                        "Inspecter la courroie d'accessoires (glissement = sous-charge)",
                        "Prévoir le remplacement de l'alternateur avant panne totale",
                    ],
                })

        # Court-circuit sonde lambda / richesse : fuel trim extrême
        fuel_trim_st = pid_values.get('06')  # Short Term Fuel Trim Bank 1
        fuel_trim_lt = pid_values.get('07')  # Long Term Fuel Trim Bank 1
        o2_b1s1 = pid_values.get('14')       # O2 Sensor Bank1 Sensor1
        o2_b1s2 = pid_values.get('15')       # O2 Sensor Bank1 Sensor2

        if fuel_trim_st is not None and fuel_trim_lt is not None:
            if abs(fuel_trim_st) > 20 and abs(fuel_trim_lt) > 15:
                direction = "trop riche (trop de carburant)" if fuel_trim_st < 0 else "trop pauvre (manque de carburant)"
                dtc_pred = 'CORR_LAMBDA_RICH' if fuel_trim_st < 0 else 'CORR_LAMBDA_LEAN'
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['06', '07'],
                    'valeurs': {'fuel_trim_court': fuel_trim_st, 'fuel_trim_long': fuel_trim_lt},
                    'dtc_code': dtc_pred,
                    'label': f'⚡ Court-circuit sonde lambda ou mélange {direction}',
                    'severity': 'high',
                    'certitude': 87,
                    'interpretation': (
                        "Correction carburant court terme : {:.1f}% / long terme : {:.1f}%. "
                        "Des corrections aussi importantes ({}) indiquent que le calculateur lutte en permanence pour corriger le mélange. "
                        "Causes possibles : sonde lambda court-circuitée ou encrassée, injecteur fuyant (riche) ou bouché (pauvre), "
                        "prise d'air sur le collecteur d'admission (pauvre), ou catalyseur détérioré."
                    ).format(fuel_trim_st, fuel_trim_lt, direction),
                    'actions': [
                        "Lire les valeurs de la sonde lambda avec un oscilloscope (signal doit osciller 0.1V-0.9V)",
                        "Vérifier l'étanchéité du collecteur d'admission (spray carbu moteur tournant)",
                        "Contrôler les injecteurs (fuite statique = mélange riche)",
                        "Mesurer la résistance de la sonde lambda (court-circuit si < 5 Ohms)",
                        "Remplacer la sonde lambda si signal plat ou hors plage",
                    ],
                })

        # Sonde lambda morte (signal fixe = court-circuit interne)
        if o2_b1s1 is not None:
            if o2_b1s1 < 0.05 or o2_b1s1 > 0.95:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['14'],
                    'valeurs': {'o2_b1s1': o2_b1s1},
                    'dtc_code': 'CORR_O2_DEAD',
                    'label': '⚡ Sonde lambda probablement morte (signal figé)',
                    'severity': 'high',
                    'certitude': 85,
                    'interpretation': (
                        "Signal O2 figé à {:.3f}V. Une sonde lambda saine oscille rapidement entre 0.1V et 0.9V. "
                        "Un signal bloqué en bas indique un court-circuit vers la masse (fil coupé ou sonde grillée). "
                        "Un signal bloqué en haut indique un court-circuit vers le +12V. "
                        "Conséquence : le moteur tourne en boucle ouverte, consommation et pollution augmentent fortement."
                    ).format(o2_b1s1),
                    'actions': [
                        "Mesurer la résistance du fil de signal de la sonde (court-circuit si < 1 Ohm vers masse)",
                        "Vérifier la tension d'alimentation du chauffage de sonde (doit être ~12V)",
                        "Remplacer la sonde lambda (durée de vie : 80 000-120 000 km)",
                        "Contrôler l'absence de fuite d'échappement avant la sonde",
                    ],
                })

        # ── SYNDROMES PRÉDICTIFS AVANCÉS ─────────────────────────────────────────

        # Prédiction : usure bobine d'allumage (RPM instable + charge élevée + temp normale)
        if rpm and load and temp:
            if 600 < rpm < 900 and load > 25 and temp > 70 and tps and tps < 5:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['0C', '04', '05', '11'],
                    'valeurs': {'rpm': rpm, 'charge': load, 'temp': temp},
                    'dtc_code': 'CORR_BOBINE_PRED',
                    'label': '🔮 Prédiction : Bobine d\'allumage ou bougie en fin de vie',
                    'severity': 'medium',
                    'certitude': 72,
                    'interpretation': (
                        "Ralenti instable ({:.0f} RPM) avec charge élevée ({:.0f}%) moteur chaud ({:.0f}°C). "
                        "Ce profil est caractéristique d'un raté d'allumage intermittent sur un ou plusieurs cylindres. "
                        "Causes probables : bobine d'allumage en début de défaillance (résistance secondaire hors tolérance), "
                        "bougie encrassée ou électrode usée, ou fil de bougie fissuré. "
                        "Sans intervention, risque de catalyseur endommagé par les hydrocarbures imbrûlés."
                    ).format(rpm, load, temp),
                    'actions': [
                        "Lire les ratés d'allumage par cylindre (PID $0301-$0304)",
                        "Mesurer la résistance des bobines (primaire : 0.5-2 Ohms, secondaire : 6-15 kOhms)",
                        "Inspecter les bougies (électrode usée, dépôts noirs = richesse, blancs = pauvreté)",
                        "Remplacer bougies et bobines si > 60 000 km sans entretien",
                        "Vérifier l'absence de fissure sur les fils haute tension",
                    ],
                })

        # Prédiction : vanne EGR encrassée (charge élevée + RPM bas + temp élevée)
        if load and rpm and temp:
            if load > 60 and rpm < 1200 and temp > 85:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0C', '05'],
                    'valeurs': {'charge': load, 'rpm': rpm, 'temp': temp},
                    'dtc_code': 'CORR_EGR_PRED',
                    'label': '🔮 Prédiction : Vanne EGR encrassée ou bloquée',
                    'severity': 'medium',
                    'certitude': 68,
                    'interpretation': (
                        "Charge moteur élevée ({:.0f}%) à bas régime ({:.0f} RPM) avec température haute ({:.0f}°C). "
                        "La vanne EGR (recirculation des gaz d'échappement) encrassée peut rester ouverte en permanence, "
                        "introduisant des gaz brûlés dans l'admission et réduisant la puissance. "
                        "Symptômes associés : ralenti instable, à-coups à l'accélération, fumée noire."
                    ).format(load, rpm, temp),
                    'actions': [
                        "Nettoyer la vanne EGR avec un spray décarbonisant",
                        "Vérifier le fonctionnement électrique de la vanne (signal PWM du calculateur)",
                        "Contrôler le tuyau de dépression de la vanne EGR (si pneumatique)",
                        "Remplacer la vanne EGR si nettoyage insuffisant",
                        "Effectuer un décalaminage moteur (injection d'hydrogène ou additif)",
                    ],
                })

        # Prédiction : pompe à eau en début de défaillance (temp élevée + RPM variable)
        if temp and rpm and volt:
            if temp > 92 and rpm > 2000 and volt > 13.0:
                # Temp élevée malgré régime élevé (la pompe devrait refroidir davantage)
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['05', '0C', '42'],
                    'valeurs': {'temp': temp, 'rpm': rpm, 'volt': volt},
                    'dtc_code': 'CORR_POMPE_EAU',
                    'label': '🔮 Prédiction : Pompe à eau en début de défaillance',
                    'severity': 'high',
                    'certitude': 76,
                    'interpretation': (
                        "Température moteur élevée ({:.0f}°C) malgré un régime soutenu ({:.0f} RPM). "
                        "À régime élevé, la pompe à eau entraînée par la courroie devrait augmenter le débit de refroidissement. "
                        "Si la température reste haute ou monte, cela indique une pompe à eau dont l'ailette est corrodée ou cassée, "
                        "ou une courroie de distribution/accessoires qui glisse. "
                        "Risque : surchauffe progressive menant à la casse du joint de culasse."
                    ).format(temp, rpm),
                    'actions': [
                        "Vérifier le niveau et l'état du liquide de refroidissement (couleur, présence d'huile)",
                        "Contrôler la tension de la courroie de distribution (si pompe entraînée par distribution)",
                        "Inspecter la pompe à eau pour détecter une fuite (trace blanche autour de la pompe)",
                        "Remplacer la pompe à eau lors du prochain remplacement de courroie de distribution",
                        "Vérifier le fonctionnement des motoventilateurs (déclenchement à 90°C)",
                    ],
                })

        # Prédiction : catalyseur en fin de vie (O2 aval similaire à O2 amont)
        if o2_b1s1 is not None and o2_b1s2 is not None:
            # Si les deux sondes ont des signaux similaires, le catalyseur ne fait plus son travail
            if abs(o2_b1s1 - o2_b1s2) < 0.1 and o2_b1s1 > 0.3:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['14', '15'],
                    'valeurs': {'o2_amont': o2_b1s1, 'o2_aval': o2_b1s2},
                    'dtc_code': 'CORR_CATA_PRED',
                    'label': '🔮 Prédiction : Catalyseur en fin de vie',
                    'severity': 'medium',
                    'certitude': 80,
                    'interpretation': (
                        "Sonde O2 amont : {:.3f}V / aval : {:.3f}V. "
                        "Un catalyseur sain transforme les gaz et la sonde aval doit avoir un signal stable (~0.6-0.7V). "
                        "Quand les deux sondes oscillent de façon similaire, le catalyseur est épuisé et ne filtre plus. "
                        "Conséquences : pollution excessive, perte de puissance, risque de bouchage du catalyseur."
                    ).format(o2_b1s1, o2_b1s2),
                    'actions': [
                        "Effectuer un test d'efficacité catalyseur avec un analyseur de gaz",
                        "Vérifier l'absence de ratés d'allumage (détruisent le catalyseur)",
                        "Contrôler l'absence de fuite d'huile dans les gaz (fumée bleue)",
                        "Remplacer le catalyseur (coût élevé — prévoir devis)",
                        "Vérifier la conformité au contrôle technique antipollution",
                    ],
                })

        # Prédiction : joint de culasse en début de défaillance (temp élevée + tension basse + RPM instable)
        if temp and volt and rpm:
            if temp > 100 and volt < 12.8 and 400 < rpm < 800:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['05', '42', '0C'],
                    'valeurs': {'temp': temp, 'tension': volt, 'rpm': rpm},
                    'dtc_code': 'CORR_CULASSE_PRED',
                    'label': '🔮 Prédiction CRITIQUE : Possible début de casse joint de culasse',
                    'severity': 'critical',
                    'certitude': 82,
                    'interpretation': (
                        "Combinaison dangereuse : température {:.0f}°C + tension {:.1f}V + ralenti instable {:.0f} RPM. "
                        "Ce profil multi-symptômes est caractéristique d'un joint de culasse qui commence à lâcher : "
                        "les gaz de combustion entrent dans le circuit de refroidissement (surchauffe), "
                        "le liquide de refroidissement entre dans les cylindres (ralenti instable, fumée blanche), "
                        "et la batterie se décharge car le moteur tourne mal. "
                        "ARRÊTER le moteur immédiatement pour éviter la casse totale du moteur."
                    ).format(temp, volt, rpm),
                    'actions': [
                        "🚨 ARRÊTER le moteur immédiatement si température > 110°C",
                        "Vérifier la présence de mousse ou d'huile dans le vase d'expansion",
                        "Contrôler si la fumée d'échappement est blanche (liquide de refroidissement brûlé)",
                        "Tester la présence de gaz CO2 dans le circuit de refroidissement (test chimique)",
                        "Faire remorquer le véhicule — ne pas rouler avec ce profil de symptômes",
                        "Devis de remplacement joint de culasse chez un mécanicien expert",
                    ],
                })

        # Prédiction : VVT (calage variable) défaillant (charge élevée + RPM élevé + temp normale)
        if load and rpm and temp and tps:
            if load > 80 and rpm > 3000 and temp < 90 and tps > 60:
                # Charge très élevée à haut régime avec papillon ouvert = moteur qui manque de puissance en haut
                if load > rpm / 100:  # ratio anormal charge/RPM
                    correlation_anomalies.append({
                        'type': 'correlation',
                        'pids_impliques': ['04', '0C', '05', '11'],
                        'valeurs': {'charge': load, 'rpm': rpm, 'tps': tps},
                        'dtc_code': 'CORR_VVT_PRED',
                        'label': '🔮 Prédiction : Système VVT (calage variable) défaillant',
                        'severity': 'medium',
                        'certitude': 65,
                        'interpretation': (
                            "Charge {:.0f}% à {:.0f} RPM avec papillon ouvert à {:.0f}%. "
                            "Le rapport charge/régime est anormal : le moteur travaille trop fort pour sa vitesse de rotation. "
                            "Cela peut indiquer un système de calage variable des soupapes (VVT/VANOS/VTEC) défaillant, "
                            "bloqué en position basse performance. "
                            "Cause : huile moteur dégradée (le VVT est hydraulique), solénoïde VVT encrassé, ou filtre à huile colmaté."
                        ).format(load, rpm, tps),
                        'actions': [
                            "Effectuer une vidange d'huile avec huile de viscosité préconisée",
                            "Nettoyer ou remplacer le solénoïde de calage variable",
                            "Vérifier la pression d'huile moteur (doit être > 2 bar à chaud)",
                            "Contrôler le filtre à huile (remplacement si > 10 000 km)",
                            "Lire les codes DTC spécifiques au VVT (P0010-P0015)",
                        ],
                    })

        # Prédiction : roulements de roue ou transmission (vitesse élevée + charge élevée + RPM normal)
        if speed and load and rpm:
            if speed > 80 and load > 70 and rpm < 2500:
                # Charge élevée pour la vitesse et le régime = résistance mécanique anormale
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['0D', '04', '0C'],
                    'valeurs': {'vitesse': speed, 'charge': load, 'rpm': rpm},
                    'dtc_code': 'CORR_ROULEMENT_PRED',
                    'label': '🔮 Prédiction : Roulement de roue ou transmission en usure',
                    'severity': 'medium',
                    'certitude': 63,
                    'interpretation': (
                        "Charge moteur élevée ({:.0f}%) à {:.0f} km/h pour seulement {:.0f} RPM. "
                        "Ce ratio indique une résistance mécanique anormale dans la chaîne cinématique. "
                        "Causes possibles : roulement de roue en début d'usure (bruit de roulement à vitesse constante), "
                        "différentiel ou boîte de vitesses avec jeu excessif, ou frein qui frotte légèrement. "
                        "Sans intervention, risque de blocage de roue ou de casse de transmission."
                    ).format(load, speed, rpm),
                    'actions': [
                        "Écouter attentivement les bruits de roulement (grondement qui varie avec la vitesse)",
                        "Vérifier le jeu des roulements de roue (secouer la roue en diagonale)",
                        "Contrôler la température des moyeux après un trajet (roulement chaud = défaillant)",
                        "Inspecter le niveau d'huile de boîte de vitesses et de pont",
                        "Vérifier l'absence de frottement des plaquettes de frein",
                    ],
                })

        # ── 3. ENRICHISSEMENT VIA BASE DTC + RECHERCHE WEB ─────────────────────
        all_dtc_codes = [a['dtc_code'] for a in simple_anomalies] + [a['dtc_code'] for a in correlation_anomalies]
        # Normaliser les codes : retirer les suffixes internes _W (warning)
        def normalize_dtc(code):
            return re.sub(r'_W$', '', code)
        real_dtc_codes = list(set([
            normalize_dtc(c) for c in all_dtc_codes
            if c.startswith('P') and not c.startswith('CORR')
        ]))

        # Priorité 1 : base de connaissances locale (causes/solutions expertes)
        db_data = {}
        for code in real_dtc_codes:
            kb_info = DTCModelAI._search_dtc_web(code, vehicle_info)
            if kb_info:
                db_data[code] = kb_info

        # Priorité 2 : DB Django pour enrichir les coûts estimés
        if real_dtc_codes:
            ai_result = DTCModelAI.predict_advanced(real_dtc_codes, vehicle_info=vehicle_info)
            for diag in ai_result.get('diagnostics', []):
                c = diag['code']
                if c in db_data:
                    # Garder causes/solutions locales, ajouter seulement les coûts DB
                    db_data[c]['cout_main_oeuvre_estime'] = diag.get('estimated_labor') or 0
                    db_data[c]['cout_pieces_local'] = diag.get('localPartPrice') or 0
                    db_data[c]['cout_pieces_import'] = diag.get('importPartPrice') or 0
                else:
                    db_data[c] = diag

        # ── 4. CONSTRUCTION DES RÉSULTATS ENRICHIS ───────────────────────────────
        enriched_results = []

        for anomaly in simple_anomalies:
            dtc = normalize_dtc(anomaly['dtc_code'])
            db = db_data.get(dtc, {})
            enriched_results.append({
                'type': 'simple',
                'dtc_code': dtc,
                'pid': anomaly['pid'],
                'valeur_actuelle': anomaly['value'],
                'label': anomaly['label'],
                'severity': anomaly['severity'],
                'certitude': anomaly['certitude'],
                'interpretation': db.get('meaning') or db.get('description') or anomaly['label'],
                'causes_probables': db.get('web_causes') or db.get('probable_causes') or db.get('possibleCauses') or [],
                'actions_recommandees': db.get('web_solutions') or db.get('suggested_solutions') or db.get('suggestedFixes') or [],
                'symptomes': db.get('symptoms') or [],
                'avertissements': db.get('warnings') or '',
                'cout_main_oeuvre_estime': db.get('cout_main_oeuvre_estime') or db.get('estimated_labor') or 0,
                'cout_pieces_local': db.get('cout_pieces_local') or db.get('localPartPrice') or 0,
                'cout_pieces_import': db.get('cout_pieces_import') or db.get('importPartPrice') or 0,
            })

        for anomaly in correlation_anomalies:
            enriched_results.append({
                'type': 'correlation',
                'dtc_code': anomaly['dtc_code'],
                'pids_impliques': anomaly['pids_impliques'],
                'valeurs': anomaly['valeurs'],
                'label': anomaly['label'],
                'severity': anomaly['severity'],
                'certitude': anomaly['certitude'],
                'interpretation': anomaly['interpretation'],
                'causes_probables': [],
                'actions_recommandees': anomaly['actions'],
                'symptomes': [],
                'avertissements': '',
                'cout_main_oeuvre_estime': 0,
                'cout_pieces_local': 0,
                'cout_pieces_import': 0,
            })

        # Trier par sévérité puis certitude
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        enriched_results.sort(key=lambda x: (severity_order.get(x['severity'], 9), -x['certitude']))

        # ── 5. VERDICT GLOBAL ─────────────────────────────────────────────────────
        nb_critical  = sum(1 for r in enriched_results if r['severity'] == 'critical')
        nb_high      = sum(1 for r in enriched_results if r['severity'] == 'high')
        nb_corr      = sum(1 for r in enriched_results if r['type'] == 'correlation')
        nb_cc        = sum(1 for r in enriched_results if '⚡' in r.get('label', ''))
        nb_pred      = sum(1 for r in enriched_results if '🔮' in r.get('label', ''))

        if nb_critical > 0:
            verdict = "🔴 DANGER IMMÉDIAT — Arrêt recommandé"
            verdict_detail = (
                f"{nb_critical} anomalie(s) critique(s) détectée(s). "
                "Continuer à rouler risque d'endommager gravement le moteur ou de compromettre la sécurité."
            )
        elif nb_cc > 0:
            verdict = "⚡ COURT-CIRCUIT DÉTECTÉ — Vérification électrique urgente"
            verdict_detail = (
                f"{nb_cc} anomalie(s) électrique(s) détectée(s). "
                "Un court-circuit non traité peut détruire l'électronique embarquée ou provoquer un incendie."
            )
        elif nb_high > 0:
            verdict = "🟠 ATTENTION — Intervention urgente requise"
            verdict_detail = (
                f"{nb_high} anomalie(s) sévère(s) détectée(s). "
                "Planifier une intervention chez un mécanicien dans les 48-72h."
            )
        elif nb_pred > 0:
            verdict = "🔮 PRÉDICTION — Pannes à venir détectées"
            verdict_detail = (
                f"{nb_pred} panne(s) insoupçonnée(s) prédite(s) avant qu'elles ne surviennent. "
                "Planifier un contrôle préventif pour éviter une immobilisation."
            )
        elif enriched_results:
            verdict = "🟡 SURVEILLANCE — Anomalies mineures détectées"
            verdict_detail = "Anomalies non critiques. Surveiller l'évolution et planifier un contrôle."
        else:
            verdict = "🟢 NORMAL — Tous les paramètres sont dans les normes"
            verdict_detail = "Aucune anomalie détectée sur les PIDs analysés."

        return {
            'status': 'anomalies_detected' if enriched_results else 'ok',
            'verdict': verdict,
            'verdict_detail': verdict_detail,
            'anomalies': enriched_results,
            'summary': {
                'total_anomalies': len(enriched_results),
                'anomalies_critiques': nb_critical,
                'anomalies_severes': nb_high,
                'syndromes_caches': nb_corr,
                'courts_circuits': nb_cc,
                'predictions': nb_pred,
                'engine_version': 'IA Deep Analyze v4.0 (Court-circuit · Prédictif · Multi-PID)',
            }
        }

    # ══════════════════════════════════════════════════════════════════════════
    # COUCHE 4 — ANALYSE TEMPORELLE DES TENDANCES
    # Détecte si un paramètre monte/descend de façon anormale sur la durée
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def analyze_temporal_trends(pid_history_list):
        """
        Analyse une liste chronologique de snapshots PID pour détecter des tendances.

        pid_history_list : liste de dicts [{pid: value, ...}, ...] du plus ancien au plus récent.
                           Chaque dict représente une lecture (intervalle ~1s).

        Retourne une liste d'alertes de tendance avec prédiction temporelle.
        """
        if not pid_history_list or len(pid_history_list) < 10:
            return []

        trend_alerts = []

        TREND_PIDS = {
            '05': {'name': 'Température moteur', 'unit': '°C',  'danger_threshold': 105, 'critical_threshold': 115},
            '5C': {'name': 'Température huile',  'unit': '°C',  'danger_threshold': 125, 'critical_threshold': 140},
            '42': {'name': 'Tension batterie',   'unit': 'V',   'danger_threshold': 11.5,'critical_threshold': 11.0, 'descending': True},
            '2F': {'name': 'Niveau carburant',   'unit': '%',   'danger_threshold': 15,  'critical_threshold': 8,   'descending': True},
            '0C': {'name': 'Régime moteur',      'unit': 'RPM', 'danger_threshold': 5500,'critical_threshold': 6500},
        }

        window = min(20, len(pid_history_list))
        recent = pid_history_list[-window:]

        for pid, config in TREND_PIDS.items():
            values = [snap.get(pid) for snap in recent if snap.get(pid) is not None]
            if len(values) < 5:
                continue

            n_v = len(values)
            x_mean = (n_v - 1) / 2
            y_mean = sum(values) / n_v
            numerator   = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
            denominator = sum((i - x_mean) ** 2 for i in range(n_v))
            slope = numerator / denominator if denominator != 0 else 0

            current_val = values[-1]
            is_descending = config.get('descending', False)
            min_slope = 0.05 if pid in ('05', '5C', '0C') else 0.005

            if is_descending:
                if slope < -min_slope and current_val > config['critical_threshold']:
                    seconds_to_danger   = (current_val - config['danger_threshold'])   / abs(slope) if slope != 0 else 9999
                    seconds_to_critical = (current_val - config['critical_threshold']) / abs(slope) if slope != 0 else 9999
                    if seconds_to_critical < 300:
                        severity = 'critical' if seconds_to_critical < 60 else 'high'
                        trend_alerts.append({
                            'type': 'trend',
                            'pid': pid,
                            'label': f'📉 Tendance : {config["name"]} en chute',
                            'current_value': round(current_val, 1),
                            'slope_per_second': round(slope, 4),
                            'unit': config['unit'],
                            'seconds_to_danger': max(0, round(seconds_to_danger)),
                            'seconds_to_critical': max(0, round(seconds_to_critical)),
                            'severity': severity,
                            'certitude': 85,
                            'interpretation': (
                                f"{config['name']} actuelle : {current_val:.1f}{config['unit']}. "
                                f"Tendance à la baisse de {abs(slope):.3f}{config['unit']}/s. "
                                f"Seuil danger ({config['danger_threshold']}{config['unit']}) atteint dans ~{max(0,round(seconds_to_danger))}s. "
                                f"Seuil critique ({config['critical_threshold']}{config['unit']}) dans ~{max(0,round(seconds_to_critical))}s."
                            ),
                            'actions': [
                                f"Surveiller {config['name']} en continu",
                                "Préparer un arrêt si la valeur continue de baisser",
                            ],
                        })
            else:
                if slope > min_slope and current_val < config['critical_threshold']:
                    seconds_to_danger   = (config['danger_threshold']   - current_val) / slope if slope != 0 else 9999
                    seconds_to_critical = (config['critical_threshold'] - current_val) / slope if slope != 0 else 9999
                    if seconds_to_critical < 300:
                        severity = 'critical' if seconds_to_critical < 60 else 'high'
                        trend_alerts.append({
                            'type': 'trend',
                            'pid': pid,
                            'label': f'📈 Tendance : {config["name"]} en hausse anormale',
                            'current_value': round(current_val, 1),
                            'slope_per_second': round(slope, 4),
                            'unit': config['unit'],
                            'seconds_to_danger': max(0, round(seconds_to_danger)),
                            'seconds_to_critical': max(0, round(seconds_to_critical)),
                            'severity': severity,
                            'certitude': 85,
                            'interpretation': (
                                f"{config['name']} actuelle : {current_val:.1f}{config['unit']}. "
                                f"Tendance à la hausse de {slope:.3f}{config['unit']}/s. "
                                f"Seuil danger ({config['danger_threshold']}{config['unit']}) atteint dans ~{max(0,round(seconds_to_danger))}s. "
                                f"Seuil critique ({config['critical_threshold']}{config['unit']}) dans ~{max(0,round(seconds_to_critical))}s."
                            ),
                            'actions': [
                                f"Surveiller {config['name']} en continu",
                                "Réduire la charge moteur si possible",
                                "Prévoir un arrêt si la tendance se confirme",
                            ],
                        })

        return trend_alerts

    # ══════════════════════════════════════════════════════════════════════════
    # COUCHE 5 — APPRENTISSAGE PAR VÉHICULE (BASELINE)
    # Mémorise les valeurs normales de CE véhicule et alerte sur les écarts
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def update_vehicle_baseline(vehicle_id, pid_values):
        """
        Met à jour la baseline d'un véhicule avec les nouvelles valeurs PID.
        Utilise une moyenne mobile exponentielle (EMA) pour un apprentissage progressif.
        """
        try:
            from api.models import VehicleBaseline, Vehicle
            vehicle = Vehicle.objects.get(pk=vehicle_id)
            baseline, _ = VehicleBaseline.objects.get_or_create(vehicle=vehicle)

            PID_FIELD_MAP = {
                '0C': 'avg_rpm',        '05': 'avg_coolant_temp',
                '5C': 'avg_oil_temp',   '04': 'avg_engine_load',
                '42': 'avg_voltage',    '06': 'avg_fuel_trim_st',
                '07': 'avg_fuel_trim_lt','0B': 'avg_map_pressure',
                '0F': 'avg_iat',        '11': 'avg_throttle',
            }
            STD_FIELD_MAP = {
                '0C': 'std_rpm', '05': 'std_coolant_temp',
                '04': 'std_engine_load', '42': 'std_voltage',
            }

            n = baseline.sample_count
            alpha = max(0.02, 1.0 / (n + 1)) if n < 500 else 0.02

            for pid, field in PID_FIELD_MAP.items():
                val = pid_values.get(pid)
                if val is None:
                    continue
                current = getattr(baseline, field)
                setattr(baseline, field, val if current is None else alpha * val + (1 - alpha) * current)

            for pid, field in STD_FIELD_MAP.items():
                val = pid_values.get(pid)
                avg_field = PID_FIELD_MAP.get(pid)
                if val is None or avg_field is None:
                    continue
                avg_val = getattr(baseline, avg_field)
                if avg_val is None:
                    continue
                deviation = abs(val - avg_val)
                current_std = getattr(baseline, field)
                setattr(baseline, field, deviation if current_std is None else alpha * deviation + (1 - alpha) * current_std)

            baseline.sample_count = n + 1
            baseline.is_mature = baseline.sample_count >= 500
            baseline.save()
            return True
        except Exception as e:
            logger.warning(f"[Baseline] Erreur mise à jour baseline véhicule {vehicle_id}: {e}")
            return False

    @staticmethod
    def analyze_baseline_deviation(vehicle_id, pid_values):
        """
        Compare les valeurs PID actuelles à la baseline apprise du véhicule.
        Retourne des alertes si un paramètre s'écarte anormalement de la normale.
        Nécessite au moins 100 lectures pour être fiable.
        """
        try:
            from api.models import VehicleBaseline, Vehicle
            vehicle = Vehicle.objects.get(pk=vehicle_id)
            baseline = VehicleBaseline.objects.filter(vehicle=vehicle).first()
        except Exception:
            return []

        if not baseline or baseline.sample_count < 100:
            return []

        deviation_alerts = []

        CHECKS = [
            ('0C', baseline.avg_rpm,         baseline.std_rpm,         'RPM',               'tr/min', 3.0),
            ('05', baseline.avg_coolant_temp, baseline.std_coolant_temp,'Température moteur', '°C',    2.5),
            ('04', baseline.avg_engine_load,  baseline.std_engine_load, 'Charge moteur',      '%',     2.5),
            ('42', baseline.avg_voltage,      baseline.std_voltage,     'Tension batterie',   'V',     2.0),
        ]

        for pid, avg, std, name, unit, threshold_sigma in CHECKS:
            val = pid_values.get(pid)
            if val is None or avg is None or std is None or std < 0.1:
                continue
            sigma = abs(val - avg) / std
            if sigma >= threshold_sigma:
                direction = "supérieure" if val > avg else "inférieure"
                severity = 'critical' if sigma >= threshold_sigma * 1.5 else 'high' if sigma >= threshold_sigma * 1.2 else 'medium'
                deviation_alerts.append({
                    'type': 'baseline_deviation',
                    'pid': pid,
                    'label': f'🧠 Écart baseline : {name} anormale pour ce véhicule',
                    'current_value': round(val, 1),
                    'baseline_avg': round(avg, 1),
                    'baseline_std': round(std, 2),
                    'sigma': round(sigma, 1),
                    'unit': unit,
                    'severity': severity,
                    'certitude': min(95, int(60 + sigma * 10)),
                    'interpretation': (
                        f"{name} actuelle : {val:.1f}{unit}. "
                        f"Valeur normale pour ce véhicule : {avg:.1f} ± {std:.1f}{unit}. "
                        f"Écart de {sigma:.1f}σ ({direction} à la normale). "
                        f"Ce véhicule se comporte différemment de ses habitudes — investigation recommandée."
                    ),
                    'actions': [
                        "Comparer avec les sessions précédentes de ce véhicule",
                        "Vérifier si un entretien récent a modifié le comportement",
                        "Lancer une analyse IA complète pour identifier la cause",
                    ],
                    'baseline_maturity': baseline.sample_count,
                })

        return deviation_alerts

    # ══════════════════════════════════════════════════════════════════════════
    # COUCHE 6 — MODÈLE ML (RANDOM FOREST) — PRÊT POUR PRODUCTION
    # Désactivé jusqu'à accumulation de données réelles suffisantes
    # ══════════════════════════════════════════════════════════════════════════

    ML_FEATURES = ['rpm', 'coolant_temp', 'oil_temp', 'engine_load', 'voltage',
                   'speed', 'throttle', 'fuel_trim_st', 'fuel_trim_lt',
                   'map_pressure', 'iat', 'o2_upstream', 'o2_downstream', 'maf']

    @staticmethod
    def record_pid_snapshot(vehicle_id, pid_values, anomaly_result=None):
        """
        Enregistre un snapshot PID en base pour alimenter l'entraînement ML futur.
        À appeler à chaque cycle live (toutes les ~2s).
        """
        try:
            from api.models import VehiclePIDHistory, Vehicle
            vehicle = Vehicle.objects.get(pk=vehicle_id)

            has_anomaly = False
            severity = ''
            codes = []
            if anomaly_result and anomaly_result.get('status') == 'anomalies_detected':
                anomalies = anomaly_result.get('anomalies', [])
                if anomalies:
                    has_anomaly = True
                    severity = anomalies[0].get('severity', '')
                    codes = [a.get('dtc_code', '') for a in anomalies]

            VehiclePIDHistory.objects.create(
                vehicle=vehicle,
                rpm=pid_values.get('0C'),
                coolant_temp=pid_values.get('05'),
                oil_temp=pid_values.get('5C'),
                engine_load=pid_values.get('04'),
                voltage=pid_values.get('42'),
                speed=pid_values.get('0D'),
                throttle=pid_values.get('11'),
                fuel_level=pid_values.get('2F'),
                fuel_trim_st=pid_values.get('06'),
                fuel_trim_lt=pid_values.get('07'),
                map_pressure=pid_values.get('0B'),
                iat=pid_values.get('0F'),
                o2_upstream=pid_values.get('14'),
                o2_downstream=pid_values.get('15'),
                maf=pid_values.get('10'),
                has_anomaly=has_anomaly,
                anomaly_severity=severity,
                anomaly_codes=codes,
            )
            return True
        except Exception as e:
            logger.warning(f"[ML] Erreur enregistrement snapshot PID: {e}")
            return False

    @staticmethod
    def train_vehicle_ml_model(vehicle_id=None, min_samples=500):
        """
        Entraîne un modèle Random Forest sur l'historique PID d'un véhicule.
        Nécessite au moins `min_samples` enregistrements labelisés.
        En production : appeler via une tâche Celery planifiée (ex: toutes les nuits).
        """
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            from sklearn.preprocessing import StandardScaler
            import numpy as np
            from api.models import VehiclePIDHistory, VehicleMLModel, Vehicle
        except ImportError:
            logger.error("[ML] scikit-learn non installé. Installer avec: pip install scikit-learn numpy")
            return None

        try:
            qs = VehiclePIDHistory.objects.all()
            if vehicle_id:
                qs = qs.filter(vehicle_id=vehicle_id)

            total = qs.count()
            if total < min_samples:
                logger.warning(f"[ML] Données insuffisantes : {total}/{min_samples} enregistrements.")
                return {'status': 'insufficient_data', 'available': total, 'required': min_samples}

            features = DTCModelAI.ML_FEATURES
            X, y = [], []
            for record in qs.values(*features, 'has_anomaly'):
                X.append([record.get(f) or 0.0 for f in features])
                y.append(1 if record['has_anomaly'] else 0)

            import numpy as np
            X = np.array(X, dtype=float)
            y = np.array(y)

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42, stratify=y
            )

            clf = RandomForestClassifier(
                n_estimators=200, max_depth=15, min_samples_split=5,
                class_weight='balanced', random_state=42, n_jobs=-1,
            )
            clf.fit(X_train, y_train)

            y_pred = clf.predict(X_test)
            metrics = {
                'accuracy':  round(float(accuracy_score(y_test, y_pred)), 4),
                'precision': round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
                'recall':    round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
                'f1':        round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
            }
            logger.info(f"[ML] Métriques entraînement: {metrics}")

            model_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'ml_models')
            os.makedirs(model_dir, exist_ok=True)
            scope = f"vehicle_{vehicle_id}" if vehicle_id else "global"

            with open(os.path.join(model_dir, f"rf_{scope}.pkl"), 'wb') as f:
                pickle.dump(clf, f)
            with open(os.path.join(model_dir, f"scaler_{scope}.pkl"), 'wb') as f:
                pickle.dump(scaler, f)

            vehicle_obj = Vehicle.objects.get(pk=vehicle_id) if vehicle_id else None
            ml_record = VehicleMLModel.objects.create(
                scope='VEHICLE' if vehicle_id else 'GLOBAL',
                vehicle=vehicle_obj,
                algorithm='RandomForest',
                accuracy=metrics['accuracy'],
                precision=metrics['precision'],
                recall=metrics['recall'],
                f1_score=metrics['f1'],
                training_samples=total,
                is_active=metrics['f1'] >= 0.75,
                version='1.0',
            )

            return {
                'status': 'success',
                'model_id': ml_record.id,
                'metrics': metrics,
                'training_samples': total,
                'auto_activated': ml_record.is_active,
            }

        except Exception as e:
            logger.error(f"[ML] Erreur entraînement: {e}")
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def predict_with_ml(vehicle_id, pid_values):
        """
        Utilise le modèle ML entraîné pour prédire si les valeurs PID actuelles
        indiquent une anomalie. Retourne None si aucun modèle actif disponible.
        """
        try:
            import numpy as np
            from api.models import VehicleMLModel
        except ImportError:
            return None

        try:
            ml_record = (
                VehicleMLModel.objects.filter(vehicle_id=vehicle_id, is_active=True).order_by('-trained_at').first()
                or VehicleMLModel.objects.filter(scope='GLOBAL', is_active=True).order_by('-trained_at').first()
            )
            if not ml_record:
                return None

            scope = f"vehicle_{vehicle_id}" if ml_record.scope == 'VEHICLE' else "global"
            model_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'ml_models')
            model_path  = os.path.join(model_dir, f"rf_{scope}.pkl")
            scaler_path = os.path.join(model_dir, f"scaler_{scope}.pkl")

            if not os.path.exists(model_path):
                return None

            with open(model_path, 'rb') as f:
                clf = pickle.load(f)
            with open(scaler_path, 'rb') as f:
                scaler = pickle.load(f)

            features = DTCModelAI.ML_FEATURES
            row = np.array([[pid_values.get(f) or 0.0 for f in features]], dtype=float)
            row_scaled = scaler.transform(row)

            proba = clf.predict_proba(row_scaled)[0]
            anomaly_proba = float(proba[1]) if len(proba) > 1 else 0.0

            if anomaly_proba < 0.6:
                return None

            return {
                'type': 'ml_prediction',
                'label': f'🤖 Modèle ML : Anomalie probable ({anomaly_proba*100:.0f}% de confiance)',
                'severity': 'high' if anomaly_proba >= 0.8 else 'medium',
                'certitude': int(anomaly_proba * 100),
                'interpretation': (
                    f"Le modèle Random Forest entraîné sur {ml_record.training_samples} sessions réelles "
                    f"détecte une combinaison de paramètres anormale avec {anomaly_proba*100:.0f}% de confiance. "
                    f"Métriques du modèle : F1={ml_record.f1_score:.2f}, Précision={ml_record.precision:.2f}."
                ),
                'actions': [
                    "Lancer une analyse IA complète pour identifier la cause précise",
                    "Comparer avec les sessions précédentes de ce véhicule",
                ],
                'model_version': ml_record.version,
                'model_f1': ml_record.f1_score,
            }

        except Exception as e:
            logger.warning(f"[ML] Erreur prédiction ML: {e}")
            return None

    # ── BASE DE CONNAISSANCES DTC LOCALE (codes les plus fréquents) ──────────
    DTC_KNOWLEDGE_BASE = {
        'P0087': {
            'meaning': "Pression de carburant trop basse dans le rail d'injection — le moteur n'a pas assez de force car le carburant n'arrive pas bien.",
            'web_causes': [
                "Pompe à carburant fatiguée ou gâtée",
                "Filtre à carburant bouché (entretien négligé)",
                "Régulateur de pression défectueux",
                "Fuite sur le tuyau de carburant",
                "Injecteurs encrassés qui boivent trop de pression",
            ],
            'web_solutions': [
                "Mesurer la pression avec un appareil (doit être entre 3 et 4 bar)",
                "Changer le filtre à carburant (à faire tous les 30 000 km)",
                "Contrôler la pompe à essence/gasoil",
                "Bien regarder s'il n'y a pas une fuite sous la voiture",
                "Nettoyer les injecteurs chez un expert",
            ],
        },
        'P0101': {
            'meaning': "Le capteur de débit d'air (MAF) envoie des valeurs bizarres — l'ordinateur de bord ne sait plus comment doser l'air.",
            'web_causes': [
                "Capteur MAF sale (poussière ou huile)",
                "Prise d'air entre le capteur et le moteur",
                "Filtre à air très sale qui bloque l'entrée",
                "Fiche ou fils du capteur abîmés",
                "Capteur MAF gâté net",
            ],
            'web_solutions': [
                "Nettoyer le capteur avec un spray spécial (ne pas toucher le fil interne)",
                "Bien regarder les gros tuyaux d'air (chercher trou ou déchirure)",
                "Changer le filtre à air",
                "Contrôler la fiche et les fils du capteur",
                "Changer le capteur si le nettoyage n'a rien donné",
            ],
        },
        'P0106': {
            'meaning': "Le capteur de pression (MAP) ne travaille pas bien — les informations de pression dans le moteur sont fausses.",
            'web_causes': [
                "Capteur MAP gâté ou très sale",
                "Prise d'air (fuite) sur le moteur",
                "Petit tuyau de dépression percé ou débranché",
                "Fils du capteur qui se touchent (court-circuit)",
            ],
            'web_solutions': [
                "Bien regarder tous les petits tuyaux d'air sur le moteur",
                "Contrôler le voltage du capteur avec un appareil",
                "Changer le capteur MAP s'il est gâté",
                "Vérifier si le moteur ne siffle pas (signe de fuite d'air)",
            ],
        },
        'P0113': {
            'meaning': "L'air qui entre dans le moteur est trop chaud — le capteur de température d'air (IAT) signale une chaleur anormale.",
            'web_causes': [
                "Capteur de température d'air gâté (valeur bloquée)",
                "Filtre à air bouché qui aspire l'air chaud du moteur",
                "Radiateur d'air (Intercooler) percé ou bouché sur moteur turbo",
                "La chaleur du moteur entre directement dans l'admission",
            ],
            'web_solutions': [
                "Changer le filtre à air s'il est vieux",
                "Nettoyer ou changer le radiateur d'air (si turbo)",
                "Changer le petit capteur de température d'air",
                "Vérifier que la boîte à air est bien fermée",
            ],
        },
        'P0122': {
            'meaning': "Le capteur de position du papillon (TPS) ne donne pas assez de signal — l'ordinateur ne sait pas si tu accélères.",
            'web_causes': [
                "Capteur TPS gâté ou mal réglé",
                "Fils du capteur coupés ou en masse",
                "Fiche du capteur rouillée ou mal branchée",
                "Le clapet d'air (papillon) est trop sale et reste coincé",
            ],
            'web_solutions': [
                "Nettoyer le corps de papillon avec un spray",
                "Vérifier si le courant arrive bien au capteur (5V)",
                "Régler le capteur si c'est possible sur ce modèle",
                "Changer le capteur TPS s'il est gâté",
            ],
        },
        'P0190': {
            'meaning': "Le capteur de pression de la rampe à injection a un souci — le signal est faux ou absent.",
            'web_causes': [
                "Capteur de pression de rampe gâté",
                "La pompe haute pression ne donne pas assez de force",
                "Fils abîmés ou fiche rouillée sur le capteur",
                "Grosse fuite de carburant sur le circuit haute pression",
            ],
            'web_solutions': [
                "Mesurer la pression réelle avec un appareil de garage",
                "Contrôler les fils et la fiche du capteur",
                "Changer le capteur de pression de rampe",
                "Contrôler la pompe haute pression (surtout sur Diesel)",
            ],
        },
        'P0217': {
            'meaning': "Le moteur chauffe trop (surchauffe) — attention, risque de casser le moteur rapidement !",
            'web_causes': [
                "Pas assez d'eau dans le radiateur (fuite)",
                "Le thermostat est bloqué et l'eau ne circule plus",
                "Le ventilateur ne tourne pas (moteur de ventilo gâté)",
                "Radiateur bouché par la saleté ou le calcaire",
                "Pompe à eau gâtée (l'eau ne bouge plus)",
                "Joint de culasse gâté (mélange eau et huile)",
            ],
            'web_solutions': [
                "Vérifier le niveau d'eau (ATTENTION : seulement moteur froid !)",
                "Tester si le thermostat s'ouvre bien",
                "Vérifier si le ventilateur se déclenche quand le moteur est chaud",
                "Nettoyer le radiateur au jet d'eau",
                "Changer la pompe à eau si elle fait du bruit ou fuit",
            ],
        },
        'P0218': {
            'meaning': "Température du liquide de refroidissement très élevée — seuil d'alerte dépassé, intervention nécessaire.",
            'web_causes': [
                "Thermostat en début de défaillance",
                "Radiateur partiellement obstrué",
                "Ventilateur de refroidissement en sous-régime",
                "Niveau de liquide légèrement bas",
            ],
            'web_solutions': [
                "Vérifier le niveau et la qualité du liquide de refroidissement",
                "Contrôler le thermostat et le ventilateur",
                "Purger le circuit de refroidissement (présence d'air)",
                "Planifier un contrôle complet du circuit de refroidissement",
            ],
        },
        'P0219': {
            'meaning': "Régime moteur excessif — le moteur tourne au-delà de sa limite de sécurité, risque de casse mécanique.",
            'web_causes': [
                "Accélérateur bloqué mécaniquement ou électroniquement",
                "Capteur de position pédale d'accélérateur défectueux",
                "Régulateur de régime (governor) défaillant",
                "Fuite d'air importante aspirée directement (emballement diesel)",
                "Câble d'accélérateur coincé",
            ],
            'web_solutions': [
                "Relâcher immédiatement l'accélérateur et réduire la vitesse",
                "Vérifier le câble d'accélérateur (coincement, gaine abîmée)",
                "Contrôler le capteur de position pédale (APP sensor)",
                "Inspecter les durites d'admission pour fuite d'air (diesel)",
                "Faire un diagnostic électronique complet de l'unité de gestion moteur",
            ],
        },
        'P0220': {
            'meaning': "Régime moteur très élevé — proche de la zone rouge, risque d'usure prématurée.",
            'web_causes': [
                "Conduite sportive prolongée en zone rouge",
                "Capteur de régime (CKP) envoyant des valeurs erronées",
                "Problème de boîte de vitesses (rapport non engagé)",
            ],
            'web_solutions': [
                "Éviter de maintenir le régime au-delà de 5500 RPM",
                "Vérifier le capteur de vilebrequin (CKP)",
                "Contrôler la boîte de vitesses",
            ],
        },
        'P0300': {
            'meaning': "Ratés d'allumage aléatoires détectés sur plusieurs cylindres — le moteur tremble car la combustion ne se fait pas bien.",
            'web_causes': [
                "Bougies d'allumage très fatiguées ou gâtées",
                "Bobines d'allumage qui donnent un courant faible",
                "Injecteurs encrassés ou gâtés",
                "Le moteur n'a plus assez de compression",
                "Pression de carburant trop basse",
                "Fils ou fiche du capteur de vilebrequin abîmés",
            ],
            'web_solutions': [
                "Changer les bougies d'allumage (entretien tous les 30 000 km)",
                "Tester les bobines d'allumage",
                "Nettoyer ou changer les injecteurs",
                "Mesurer la compression des cylindres chez un expert",
                "Vérifier la pression de la pompe à essence",
            ],
        },
        'P0500': {
            'meaning': "Le capteur de vitesse du véhicule ne travaille pas bien — le compteur de vitesse peut rester à zéro.",
            'web_causes': [
                "Capteur de vitesse gâté net",
                "Fils coupés ou fiche rouillée sur le capteur",
                "Petit engrenage dans la boîte de vitesses cassé",
                "Fils qui se touchent entre le capteur et le tableau de bord",
            ],
            'web_solutions': [
                "Bien regarder si les fils du capteur de vitesse ne sont pas coupés",
                "Changer le capteur de vitesse s'il est gâté",
                "Contrôler les dents du pignon dans la boîte",
                "Vérifier si le compteur de vitesse réagit sur un appareil de diagnostic",
            ],
        },
        'P0524': {
            'meaning': "La pression d'huile moteur est trop basse — danger, le moteur peut casser si tu roules !",
            'web_causes': [
                "Pas assez d'huile dans le moteur (fuite ou moteur qui boit l'huile)",
                "Pompe à huile fatiguée ou gâtée",
                "Huile trop vieille ou trop fluide (perte de force)",
                "Le capteur de pression d'huile est gâté et ment",
                "Coussinets de vilebrequin usés (trop de jeu)",
            ],
            'web_solutions': [
                "Arrêter le moteur direct et vérifier le niveau d'huile",
                "Faire la vidange avec une bonne huile si c'est trop vieux",
                "Mesurer la pression réelle avec un manomètre",
                "Changer la pompe à huile si elle ne pousse plus",
                "Changer le capteur de pression d'huile",
            ],
        },
        'P0562': {
            'meaning': "La tension (voltage) du système est trop basse — la batterie ou l'alternateur ont un souci.",
            'web_causes': [
                "Batterie faible ou très vieille",
                "L'alternateur ne charge pas assez",
                "Fils de batterie (cosses) sales ou mal serrés",
                "Consommation de courant anormale même moteur éteint",
            ],
            'web_solutions': [
                "Nettoyer et bien serrer les deux bornes de la batterie",
                "Mesurer le voltage moteur tournant (doit être entre 13.8V et 14.5V)",
                "Changer la batterie si elle ne tient plus la charge",
                "Faire réviser l'alternateur chez un électricien auto",
            ],
        },
        'P0563': {
            'meaning': "Tension du système électrique trop élevée — surtension pouvant endommager les équipements électroniques.",
            'web_causes': [
                "Régulateur de tension de l'alternateur défectueux",
                "Alternateur en court-circuit interne",
                "Mauvaise connexion de masse de l'alternateur",
            ],
            'web_solutions': [
                "Mesurer la tension aux bornes de batterie moteur tournant (ne doit pas dépasser 14.8V)",
                "Remplacer le régulateur de tension ou l'alternateur complet",
                "Vérifier et nettoyer la masse de l'alternateur",
            ],
        },
        'P0420': {
            'meaning': "Efficacité du catalyseur insuffisante (banc 1) — le pot catalytique ne convertit plus correctement les gaz d'échappement.",
            'web_causes': [
                "Catalyseur usé ou empoisonné (plomb, huile, liquide de refroidissement)",
                "Sonde lambda aval défectueuse (signal erroné)",
                "Sonde lambda amont défectueuse (mélange air/carburant incorrect)",
                "Fuite d'échappement avant le catalyseur faussant les mesures",
                "Carburant de mauvaise qualité ou huile brûlée détruisant le catalyseur",
                "Injecteurs défaillants enrichissant le mélange et surchauffant le catalyseur",
            ],
            'web_solutions': [
                "Vérifier les sondes lambda amont et aval (oscilloscope : signal aval doit être stable)",
                "Inspecter le catalyseur visuellement (bruit de ferraille = substrat cassé)",
                "Contrôler les injecteurs et la richesse du mélange",
                "Rechercher une fuite d'échappement avant le catalyseur",
                "Remplacer le catalyseur si substrat détruit (coût élevé : prévoir 80 000–200 000 FCFA)",
                "Remplacer la sonde lambda aval si signal plat ou inversé",
            ],
        },
        'P0430': {
            'meaning': "Efficacité du catalyseur insuffisante (banc 2) — même problème que P0420 mais sur le second banc (moteur V6/V8).",
            'web_causes': [
                "Catalyseur banc 2 usé ou empoisonné",
                "Sonde lambda aval banc 2 défectueuse",
                "Fuite d'échappement côté banc 2",
            ],
            'web_solutions': [
                "Mêmes procédures que P0420 appliquées au banc 2",
                "Vérifier la sonde lambda aval banc 2",
                "Remplacer le catalyseur banc 2 si nécessaire",
            ],
        },
        'P0300': {
            'meaning': "Ratés d'allumage aléatoires détectés sur plusieurs cylindres — le moteur tourne irrégulièrement.",
            'web_causes': [
                "Bougies d'allumage usées ou encrassées",
                "Bobines d'allumage défaillantes (une ou plusieurs)",
                "Injecteurs encrassés ou défaillants",
                "Fuite de compression sur un ou plusieurs cylindres",
                "Fuite d'admission (joint de collecteur percé)",
                "Pression carburant insuffisante",
                "Problème de calage de distribution (chaîne ou courroie étirée)",
            ],
            'web_solutions': [
                "Remplacer les bougies d'allumage (entretien recommandé tous les 30 000–60 000 km)",
                "Tester chaque bobine d'allumage (permuter pour identifier la défaillante)",
                "Nettoyer ou remplacer les injecteurs",
                "Effectuer un test de compression sur tous les cylindres",
                "Inspecter le joint de collecteur d'admission",
                "Vérifier la pression carburant au rail",
                "Contrôler le calage de distribution",
            ],
        },
        'P0301': {
            'meaning': "Ratés d'allumage détectés sur le cylindre 1 — combustion incomplète ou absente sur ce cylindre.",
            'web_causes': [
                "Bougie d'allumage cylindre 1 défectueuse",
                "Bobine d'allumage cylindre 1 défaillante",
                "Injecteur cylindre 1 encrassé ou bloqué",
                "Fuite de compression cylindre 1 (soupape, segment, joint de culasse)",
            ],
            'web_solutions': [
                "Remplacer la bougie d'allumage du cylindre 1",
                "Permuter la bobine du cylindre 1 avec un autre cylindre pour tester",
                "Nettoyer ou remplacer l'injecteur du cylindre 1",
                "Effectuer un test de compression sur le cylindre 1",
            ],
        },
        'P0171': {
            'meaning': "Le mélange air/carburant est trop pauvre — le moteur reçoit trop d'air ou pas assez de carburant.",
            'web_causes': [
                "Fuite d'air après le capteur (tuyau d'air percé ou débranché)",
                "Capteur de débit d'air (MAF) sale ou gâté",
                "Injecteurs bouchés qui ne donnent pas assez d'essence",
                "Pompe à carburant fatiguée qui ne pousse pas fort",
                "Filtre à carburant bouché",
                "La sonde lambda amont est gâtée",
            ],
            'web_solutions': [
                "Bien chercher un sifflement ou un trou sur les tuyaux d'air",
                "Nettoyer le capteur de débit d'air (MAF)",
                "Changer le filtre à carburant",
                "Tester la pression de la pompe à essence",
                "Nettoyer les injecteurs",
                "Contrôler la sonde lambda",
            ],
        },
        'P0172': {
            'meaning': "Le mélange air/carburant est trop riche — le moteur reçoit trop de carburant ou pas assez d'air.",
            'web_causes': [
                "Injecteur qui fuit ou reste ouvert (il pisse l'essence)",
                "Capteur de débit d'air (MAF) qui ment (donne trop de valeur)",
                "Régulateur de pression de carburant gâté (pression trop haute)",
                "Filtre à air très sale qui étouffe le moteur",
                "Sonde lambda gâtée",
            ],
            'web_solutions': [
                "Changer le filtre à air s'il est très noir",
                "Nettoyer ou changer les injecteurs qui fuient",
                "Contrôler la pression de carburant",
                "Tester le capteur de débit d'air",
            ],
        },
        'P0340': {
            'meaning': "Le capteur de position d'arbre à cames (sensor) ne travaille pas — l'ordinateur de bord est perdu et ne sait pas quand envoyer l'étincelle.",
            'web_causes': [
                "Capteur d'arbre à cames gâté net",
                "Fils coupés ou fiche rouillée sur le capteur",
                "La chaîne ou courroie de distribution a sauté une dent",
                "Fils qui se touchent (court-circuit) sur le capteur",
            ],
            'web_solutions': [
                "Changer le capteur d'arbre à cames",
                "Bien contrôler si les fils ne sont pas coupés ou brûlés",
                "Vérifier le calage de la distribution",
                "Nettoyer la fiche du capteur",
            ],
        },
        'P0335': {
            'meaning': "Le capteur de régime moteur (vilebrequin) ne donne pas de signal — la voiture peut refuser de démarrer ou s'éteindre net.",
            'web_causes': [
                "Capteur de vilebrequin gâté ou sale",
                "Cible métallique sur le moteur abîmée (roue phonique)",
                "Fils coupés ou brûlés par la chaleur du moteur",
                "Le capteur est trop loin de sa cible",
            ],
            'web_solutions': [
                "Changer le capteur de vilebrequin",
                "Contrôler le faisceau électrique (les fils) vers le capteur",
                "Nettoyer la fiche avec un spray contact",
                "Vérifier si le capteur est bien serré à sa place",
            ],
        },
        'P0401': {
            'meaning': "Débit insuffisant du système EGR (recirculation des gaz d'échappement) — le système antipollution ne fonctionne pas correctement.",
            'web_causes': [
                "Vanne EGR encrassée ou bloquée fermée",
                "Conduit EGR obstrué par des dépôts de carbone",
                "Capteur de position de la vanne EGR défectueux",
                "Fuite dans le circuit de dépression de la vanne EGR",
            ],
            'web_solutions': [
                "Nettoyer la vanne EGR et ses conduits (décalaminage)",
                "Tester la vanne EGR (ouverture/fermeture à la commande)",
                "Vérifier le circuit de dépression ou électrique de la vanne",
                "Remplacer la vanne EGR si bloquée ou défectueuse",
            ],
        },
        'P0455': {
            'meaning': "Fuite importante détectée dans le système EVAP (contrôle des vapeurs de carburant) — souvent le bouchon de réservoir mal fermé.",
            'web_causes': [
                "Bouchon de réservoir desserré, mal fermé ou joint usé",
                "Durite EVAP fissurée ou déconnectée",
                "Purge EVAP (canister) défaillante",
                "Réservoir de carburant fissuré",
            ],
            'web_solutions': [
                "Vérifier et resserrer le bouchon de réservoir (ou le remplacer si joint usé)",
                "Inspecter toutes les durites EVAP pour fissures",
                "Tester la purge EVAP (canister) à la commande",
                "Effectuer un test de fumée sur le circuit EVAP",
            ],
        },
        'U0100': {
            'meaning': "L'ordinateur de bord (calculateur) ne répond plus — le réseau de communication de la voiture est coupé ou en panne.",
            'web_causes': [
                "Ordinateur du moteur (ECM) gâté ou n'a plus de courant",
                "Fils de communication (Bus CAN) coupés ou en masse",
                "Fiche de l'ordinateur rouillée ou mal branchée",
                "Fusible ou relais de l'ordinateur grillé",
            ],
            'web_solutions': [
                "Contrôler tous les fusibles de la voiture",
                "Vérifier si les fiches de l'ordinateur sont bien fixées",
                "Mesurer la batterie (doit être bien chargée)",
                "Chercher s'il n'y a pas un fils coupé quelque part",
            ],
        },
        'P0128': {
            'meaning': "Le moteur reste trop froid — l'eau ne chauffe pas assez vite ou le capteur se trompe.",
            'web_causes': [
                "Le thermostat est bloqué ouvert (l'eau circule trop)",
                "Capteur de température d'eau gâté",
                "Le ventilateur tourne tout le temps même moteur froid",
            ],
            'web_solutions': [
                "Changer le thermostat (c'est souvent lui qui reste ouvert)",
                "Contrôler le capteur de température",
                "Vérifier si le ventilateur ne tourne pas en permanence",
            ],
        },
        'P0016': {
            'meaning': "Le moteur est décalé — le haut et le bas du moteur ne tournent plus ensemble (problème de distribution).",
            'web_causes': [
                "Chaîne ou courroie de distribution qui a sauté ou s'est allongée",
                "Tendeur de chaîne fatigué ou manque de pression d'huile",
                "Électrovanne VVT sale ou gâtée",
                "Huile trop vieille qui bloque le système de calage",
            ],
            'web_solutions': [
                "Vérifier le calage de la distribution direct",
                "Faire la vidange avec une bonne huile",
                "Contrôler le tendeur de chaîne",
                "Changer le capteur d'arbre à cames ou de vilebrequin",
            ],
        },
        'P0157': {
            'meaning': "Le capteur d'oxygène (sonde lambda) signale un mélange trop pauvre — il y a trop d'air ou la sonde est gâtée.",
            'web_causes': [
                "Fuite d'air sur le moteur ou l'échappement",
                "Sonde lambda (capteur d'oxygène) gâtée",
                "La pompe à essence ne pousse pas assez",
                "Injecteur bouché ou sale",
                "Fils de la sonde coupés ou brûlés",
            ],
            'web_solutions': [
                "Bien regarder s'il n'y a pas un sifflement (fuite d'air)",
                "Contrôler les fils et la fiche de la sonde",
                "Changer la sonde lambda si elle ne réagit plus",
                "Nettoyer les injecteurs",
            ],
            'web_symptoms': [
                "Voyant moteur allumé (MIL)",
                "Perte de force du moteur",
                "Le moteur tremble ou s'éteint",
                "La voiture boit trop de carburant",
            ],
            'web_severity': 'medium',
        },
        'P0274': {
            'meaning': "Problème sur l'injecteur du cylindre numéro 5 — le courant ne passe pas bien dans l'injecteur.",
            'web_causes': [
                "Injecteur numéro 5 gâté (court-circuit)",
                "Fils de l'injecteur coupés ou rouillés",
                "Fiche de l'injecteur mal branchée",
                "Petit souci dans l'ordinateur de bord",
            ],
            'web_solutions': [
                "Nettoyer l'injecteur et sa fiche",
                "Vérifier si le courant arrive bien à l'injecteur",
                "Changer l'injecteur numéro 5",
            ],
            'web_symptoms': [
                "Moteur qui boite (tourne sur 3 pattes)",
                "Perte de force et de vitesse",
                "Consommation en hausse",
                "Voyant moteur qui clignote (danger)",
            ],
            'web_severity': 'high',
        },
    }

    @staticmethod
    def _search_dtc_web(code, vehicle_info=None):
        """
        Recherche les informations d'un code DTC.
        Priorité 1 : base de connaissances locale (instantané, fiable).
        Priorité 2 : scraping obd-codes.com (fallback).
        """
        # ── Source 1 : base locale ────────────────────────────────────────────────
        local = DTCModelAI.DTC_KNOWLEDGE_BASE.get(code)
        if local:
            logger.info(f"[DTC KB] {code} trouvé dans la base locale")
            return {**local, 'web_source': 'base_locale'}

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        }

        # ── Source 2 : obd-codes.com (Fallback Principal) ─────────────────────────
        try:
            url = f"https://www.obd-codes.com/{code.lower()}"
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                html = resp.text
                meaning, causes, solutions = None, [], []

                m = re.search(r'<h1[^>]*>([^<]{10,200})</h1>', html, re.IGNORECASE)
                if m:
                    meaning = re.sub(r'\s+', ' ', m.group(1)).strip()

                # Extraction robuste des causes
                causes_patterns = [
                    r'(?:possible causes?|causes include)[^<]*</[^>]+>(.*?)</(?:ul|ol)>',
                    r'<b>Causes</b><br />(.*?)(?:<b>|$)',
                    r'Potential causes for this fault code include:(.*?)(?:<ul>|<li>|$)',
                ]
                for p in causes_patterns:
                    causes_sec = re.search(p, html, re.IGNORECASE | re.DOTALL)
                    if causes_sec:
                        causes = [re.sub(r'<[^>]+>', '', i).strip()
                                  for i in re.findall(r'<li[^>]*>(.*?)</li>|([^<>\r\n]{15,150})', causes_sec.group(1), re.DOTALL)
                                  if (i[0] or i[1]).strip() and len((i[0] or i[1]).strip()) > 5][:6]
                        causes = [c.strip() for c in causes if c.strip()]
                        if causes: break

                # Extraction robuste des solutions
                fixes_patterns = [
                    r'(?:possible fixes?|repairs?|common repairs?)[^<]*</[^>]+>(.*?)</(?:ul|ol)>',
                    r'<b>Possible Solutions</b><br />(.*?)(?:<b>|$)',
                ]
                for p in fixes_patterns:
                    fixes_sec = re.search(p, html, re.IGNORECASE | re.DOTALL)
                    if fixes_sec:
                        solutions = [re.sub(r'<[^>]+>', '', i).strip()
                                     for i in re.findall(r'<li[^>]*>(.*?)</li>|([^<>\r\n]{15,150})', fixes_sec.group(1), re.DOTALL)
                                     if (i[0] or i[1]).strip() and len((i[0] or i[1]).strip()) > 5][:6]
                        solutions = [s.strip() for s in solutions if s.strip()]
                        if solutions: break

                if meaning or causes:
                    logger.info(f"[DTC Web] {code} trouvé sur obd-codes.com")
                    return {
                        'meaning': meaning or f"Code {code}",
                        'web_causes': causes,
                        'web_solutions': solutions,
                        'web_source': 'obd-codes.com',
                    }
        except Exception as e:
            logger.debug(f"[DTC Web] {code} non accessible sur obd-codes.com: {e}")

        # ── Source 3 : Backup via un autre service ou logique de type ─────────────
        # Si rien n'a été trouvé, on peut tenter une recherche plus générique
        return None
