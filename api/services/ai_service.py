import logging
import json
import re
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
                    causes = ["Pièce gâtée quelque part"]
                if not solutions:
                    solutions = ["Regarder bien partout sur le moteur", "Contrôler les fils de courant"]

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
                            "Capteur (sensor) ou pièce gâtée",
                            "Fils de courant coupés ou fiche rouillée",
                            "Problème de communication entre les ordinateurs (CAN/LIN)",
                        ],
                        'possibleCauses': [
                            "Capteur (sensor) ou pièce gâtée",
                            "Fils de courant coupés ou fiche rouillée",
                            "Problème de communication entre les ordinateurs (CAN/LIN)",
                        ],
                        'suggested_solutions': [
                            "Rechercher le code sur Google avec la marque du véhicule",
                            "Consulter la documentation technique constructeur",
                            "Utiliser un outil de diagnostic spécifique à la marque",
                        ],
                        'suggestedFixes': [
                            "Rechercher le code sur Google avec la marque du véhicule",
                            "Consulter la documentation technique constructeur",
                            "Utiliser un outil de diagnostic spécifique à la marque",
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
                'engine_version': "IA Predict v3.0 (KB + DB + Web)"
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
            repls = [
                (r'défectueux', 'gâté'), (r'défaillant', 'gâté'), (r'défaillance', 'problème'),
                (r'dysfonctionnement', 'problème'), (r'endommagé', 'cassé ou gâté'),
                (r'corrodé', 'rouillé'), (r'obstruction', 'bouché'), (r'obstrué', 'bouché'),
                (r'fuite', 'fuite (ça coule)'), (r'remplacer', 'changer'), (r'inspection', 'regarder bien'),
                (r'inspecter', 'regarder bien'), (r'vérifier', 'contrôler'), (r'contrôle', 'contrôle'),
                (r'nettoyage', 'nettoyer'), (r'nettoyer', 'nettoyer'), (r'ajustement', 'régler'),
                (r'ajuster', 'régler'), (r'réparation', 'réparer'), (r'réparer', 'réparer'),
                (r'faisceau', 'fils de courant'), (r'câblage', 'fils de courant'), (r'connecteur', 'fiche'),
                (r'court-circuit', 'masse (court-circuit)'), (r'circuit ouvert', 'fil coupé'),
                (r'alimentation', 'courant'), (r'tension', 'voltage'), (r'pression', 'pression'),
                (r'capteur', 'capteur (sensor)'), (r'sonde', 'sonde (capteur)'),
                (r'consommation', 'boit le carburant'), (r'perte de puissance', "la voiture n'a plus la force"),
                (r'ralenti instable', 'le moteur tremble au repos'), (r'calage', "le moteur s'éteint"),
                (r'calculateur', 'ordinateur de bord (calculateur)'), (r'insuffisant', 'pas assez'),
                (r'solution', 'ce qu\'il faut faire'), (r'cause', 'pourquoi ça arrive'),
                (r'dû à', 'à cause de'), (r'cause probable', 'ce qui peut envoyer ça')
            ]
            for old, new in repls:
                text = re.sub(old, new, text, flags=re.IGNORECASE)
            return text

        for code in dtc_codes:
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
                merged_causes = [
                    "Pièce gâtée quelque part",
                    "Fils de courant coupés ou fiche rouillée",
                    "Petit problème dans l'ordinateur de bord",
                ]
            if not merged_solutions:
                merged_solutions = [
                    "Regarder bien partout sur le moteur",
                    "Contrôler les fils de courant et les fiches",
                    "Chercher plus de détails sur cette panne",
                ]

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
                    "⚠️ PANNE TRÈS GRAVE — Arrête la voiture tout de suite",
                    "❌ DANGER — Ne roule plus avec la voiture comme ça",
                    "⚠️ ALERTE ROUGE — C'est gâté sérieusement, faut éteindre le moteur"
                ],
                'high': [
                    "🔴 PANNE GRAVE — Faut réparer ça maintenant",
                    "🚫 PROBLÈME SÉRIEUX — Amène la voiture au garage aujourd'hui",
                    "🔴 C'EST GÂTÉ — Si tu laisses, ça va casser autre chose"
                ],
                'medium': [
                    "🟠 PROBLÈME — Faut regarder ça dans les jours qui viennent",
                    "⚠️ ATTENTION — Y'a un truc qui ne va pas bien sur le moteur",
                    "🟠 À CONTRÔLER — Faudra passer voir le mécano bientôt"
                ],
                'low': [
                    "🟢 PETIT PROBLÈME — Faut juste surveiller un peu",
                    "ℹ️ INFO — Y'a une petite fatigue quelque part",
                    "🟡 À SURVEILLER — C'est pas urgent mais garde l'œil dessus"
                ],
            }
            
            # Choix d'un message basé sur le code pour que le même code ait toujours le même message
            # mais que des codes différents puissent avoir des messages différents
            msg_list = severity_messages.get(final_severity, severity_messages['medium'])
            msg_index = sum(ord(char) for char in code) % len(msg_list)
            severity_txt = msg_list[msg_index]

            interpretation = (
                f"{severity_txt}{vehicle_ctx}. "
                f"Le problème c'est : {final_meaning}. "
                f"Pourquoi ça arrive : {merged_causes[0].lower() if merged_causes else 'on ne sait pas trop encore'}."
            )
            if db_tips:
                interpretation += f"💡 {db_tips}"

            # ── 5. Certitude ──────────────────────────────────────────────────────
            certitude = 90 if ref and db_causes else (75 if kb_causes else 40)

            entry = {
                'code': code,
                'description': final_meaning,
                'meaning': final_meaning,
                'severity': final_severity,
                'certitude': certitude,
                'interpretation': interpretation,
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
            verdict = f"🔴 {nb_critical} panne(s) très graves — faut arrêter la voiture maintenant"
        elif nb_high > 0:
            verdict = f"🟠 {nb_high} panne(s) graves — faut prévoir de réparer ça vite"
        elif results:
            verdict = "🟡 Petits problèmes détectés — faut surveiller ça de près"
        else:
            verdict = "🟢 La voiture n'a rien, tout est bon"

        return {
            'diagnostics': results,
            'summary': {
                'verdict': verdict,
                'nb_codes': len(results),
                'nb_critical': nb_critical,
                'nb_high': nb_high,
                'total_estimated_labor': total_labor,
                'engine_version': 'IA Deep DTC v1.0 (DB + KB + Web)',
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
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0B', '0F'],
                    'valeurs': {'charge': load, 'pression_collecteur': map_p, 'temp_air': iat},
                    'dtc_code': 'CORR_TURBO',
                    'label': 'Syndrome turbo défaillant',
                    'severity': 'high',
                    'certitude': 82,
                    'interpretation': (
                        "Le moteur travaille trop fort ({:.0f}%) mais l'air ne rentre pas assez ({:.0f} kPa) "
                        "et l'air qui entre est trop chaud ({:.0f}°C). Ça veut dire que le turbo ne souffle pas bien. "
                        "Ce qui peut envoyer ça : durite de turbo percée, clapet (wastegate) bloqué ouvert, ou radiateur d'air (intercooler) bouché."
                    ).format(load, map_p, iat),
                    'actions': [
                        "Regarder bien les tuyaux du turbo (chercher trou ou si c'est débranché)",
                        "Contrôler le clapet du turbo (wastegate)",
                        "Vérifier si le radiateur d'air n'est pas bouché ou percé",
                        "Mesurer si le turbo souffle bien avec un manomètre",
                    ],
                })

        # Syndrome alternateur défaillant : tension basse + RPM normal + charge élevée
        if volt and rpm and load:
            if volt < 12.5 and rpm > 800 and load > 40:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['42', '0C', '04'],
                    'valeurs': {'tension': volt, 'rpm': rpm, 'charge': load},
                    'dtc_code': 'CORR_ALT',
                    'label': 'Alternateur sous-performant',
                    'severity': 'high',
                    'certitude': 88,
                    'interpretation': (
                        "La batterie donne seulement {:.1f}V alors que le moteur tourne bien ({:.0f} RPM). "
                        "Normalement, l'alternateur doit envoyer entre 13.8V et 14.8V. "
                        "Ce qui peut envoyer ça : alternateur gâté, régulateur de courant mort, ou courroie qui glisse."
                    ).format(volt, rpm, load),
                    'actions': [
                        "Contrôler si l'alternateur charge bien avec un multimètre (chercher 13.8V-14.8V)",
                        "Vérifier si la courroie de l'alternateur est bien serrée",
                        "Regarder les fils et les fiches de la batterie",
                        "Vérifier si la masse du moteur est bien branchée",
                    ],
                })

        # Syndrome refroidissement : température haute + RPM bas + charge faible (thermostat bloqué fermé)
        if temp and rpm and load:
            if temp > 95 and rpm < 1500 and load < 30:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['05', '0C', '04'],
                    'valeurs': {'temp': temp, 'rpm': rpm, 'charge': load},
                    'dtc_code': 'CORR_THERMO',
                    'label': 'Thermostat bloqué fermé (surchauffe au ralenti)',
                    'severity': 'critical',
                    'certitude': 91,
                    'interpretation': (
                        "Le moteur chauffe trop ({:.0f}°C) alors que tu ne roules pas vite ({:.0f} RPM). "
                        "C'est souvent parce que le thermostat (vanne d'eau) est bloqué fermé. "
                        "L'eau ne peut plus aller dans le radiateur pour se refroidir. "
                        "Attention, si tu ne répares pas, tu vas griller le joint de culasse !"
                    ).format(temp, rpm, load),
                    'actions': [
                        "ARRÊTE le moteur tout de suite si ça dépasse 110°C",
                        "Attends que ça refroidisse, puis regarde le niveau de l'eau (liquide)",
                        "Faut changer le thermostat (vanne d'eau) rapidement",
                        "Regarde s'il n'y a pas de bulles dans l'eau (signe de joint de culasse)",
                        "Vérifie si le ventilateur tourne bien",
                    ],
                })

        # Syndrome injection : charge élevée + RPM instable + papillon normal (injecteurs encrassés)
        if load and rpm and tps:
            if load > 70 and rpm < 1000 and tps < 20:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0C', '11'],
                    'valeurs': {'charge': load, 'rpm': rpm, 'tps': tps},
                    'dtc_code': 'CORR_INJECT',
                    'label': 'Injecteurs encrassés ou défaillants',
                    'severity': 'high',
                    'certitude': 79,
                    'interpretation': (
                        "Le moteur travaille trop fort ({:.0f}%) alors que tu n'appuies pas beaucoup sur la pédale ({:.0f}%) et le moteur tremble ({:.0f} RPM). "
                        "L'ordinateur essaie de compenser parce que les injecteurs ne crachent pas bien l'essence. "
                        "Ce qui peut envoyer ça : injecteurs bouchés ou pompe à essence qui fatigue."
                    ).format(load, tps, rpm),
                    'actions': [
                        "Faut nettoyer les injecteurs (avec produit ou machine ultrason)",
                        "Contrôler si la pression de l'essence est bonne",
                        "Vérifier si la pompe à essence travaille bien",
                        "Changer le filtre à essence s'il est vieux",
                    ],
                })

        # Syndrome huile dégradée : température huile élevée + température moteur normale
        if oil_t and temp:
            if oil_t > 120 and temp < 95:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['5C', '05'],
                    'valeurs': {'temp_huile': oil_t, 'temp_moteur': temp},
                    'dtc_code': 'CORR_HUILE',
                    'label': 'Huile moteur dégradée ou niveau bas',
                    'severity': 'high',
                    'certitude': 84,
                    'interpretation': (
                        "L'huile chauffe trop ({:.0f}°C) alors que le moteur lui-même est normal ({:.0f}°C). "
                        "C'est souvent parce que l'huile est vieille, n'a plus de force, ou qu'il n'y en a pas assez. "
                        "Une huile trop chaude ne protège plus le moteur et va tout gâter à l'intérieur."
                    ).format(oil_t, temp),
                    'actions': [
                        "Vérifier tout de suite le niveau de l'huile",
                        "Regarder si l'huile est noire ou trop liquide (si oui, faut faire vidange)",
                        "Faire la vidange rapidement avec une bonne huile",
                        "Vérifier si le refroidisseur d'huile n'est pas bouché",
                    ],
                })

        # Syndrome consommation excessive : charge élevée + vitesse modérée + carburant qui baisse vite
        if load and speed and fuel:
            if load > 80 and speed < 80 and fuel < 30:
                correlation_anomalies.append({
                    'type': 'correlation',
                    'pids_impliques': ['04', '0D', '2F'],
                    'valeurs': {'charge': load, 'vitesse': speed, 'carburant': fuel},
                    'dtc_code': 'CORR_CONSO',
                    'label': 'Consommation carburant anormalement élevée',
                    'severity': 'medium',
                    'certitude': 74,
                    'interpretation': (
                        "Le moteur travaille trop fort ({:.0f}%) alors que tu roules doucement ({:.0f} km/h) et le carburant descend vite ({:.0f}%). "
                        "C'est comme si quelque chose retenait la voiture. "
                        "Ce qui peut envoyer ça : pneus pas bien gonflés, freins qui serrent tout seuls, ou embrayage qui glisse."
                    ).format(load, speed, fuel),
                    'actions': [
                        "Vérifier la pression des pneus (pneu mou = voiture boit trop)",
                        "Vérifier si les freins ne chauffent pas tous seuls (frein qui reste serré)",
                        "Regarder si l'embrayage ne glisse pas",
                        "Changer le filtre à air s'il est trop sale (moteur étouffe)",
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
        nb_critical = sum(1 for r in enriched_results if r['severity'] == 'critical')
        nb_high     = sum(1 for r in enriched_results if r['severity'] == 'high')
        nb_corr     = sum(1 for r in enriched_results if r['type'] == 'correlation')

        if nb_critical > 0:
            verdict = "🔴 DANGER IMMÉDIAT — Arrêt recommandé"
            verdict_detail = (
                f"{nb_critical} anomalie(s) critique(s) détectée(s). "
                "Continuer à rouler risque d'endommager gravement le moteur ou de compromettre la sécurité."
            )
        elif nb_high > 0:
            verdict = "🟠 ATTENTION — Intervention urgente requise"
            verdict_detail = (
                f"{nb_high} anomalie(s) sévère(s) détectée(s). "
                "Planifier une intervention chez un mécanicien dans les 48-72h."
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
                'engine_version': 'IA Deep Analyze v3.0 (Multi-PID Correlation)',
            }
        }

    # ── BASE DE CONNAISSANCES DTC LOCALE (codes les plus fréquents) ──────────
    DTC_KNOWLEDGE_BASE = {
        'P0087': {
            'meaning': "Pression carburant insuffisante dans le rail d'injection — le moteur ne reçoit pas assez de carburant.",
            'web_causes': [
                "Pompe à carburant défaillante ou en fin de vie",
                "Filtre à carburant colmaté (obstruction)",
                "Régulateur de pression carburant défectueux",
                "Fuite sur la ligne d'alimentation carburant",
                "Injecteurs encrassés augmentant la demande de pression",
            ],
            'web_solutions': [
                "Mesurer la pression carburant au rail avec un manomètre (valeur nominale : 3-4 bar)",
                "Remplacer le filtre à carburant (entretien recommandé tous les 30 000 km)",
                "Tester la pompe à carburant (débit et pression à vide)",
                "Inspecter les durites pour fuites ou pincements",
                "Nettoyer ou remplacer les injecteurs si encrassés",
            ],
        },
        'P0101': {
            'meaning': "Débit massique d'air (MAF) hors plage — le capteur de masse d'air envoie des valeurs anormales.",
            'web_causes': [
                "Capteur MAF encrassé (huile, poussière)",
                "Fuite d'air entre le MAF et le papillon des gaz",
                "Filtre à air colmaté réduisant le débit",
                "Câblage ou connecteur MAF endommagé",
                "Capteur MAF défectueux",
            ],
            'web_solutions': [
                "Nettoyer le capteur MAF avec un spray nettoyant spécifique (ne pas toucher le fil)",
                "Inspecter les durites d'admission pour fissures ou déconnexions",
                "Remplacer le filtre à air",
                "Vérifier le câblage et le connecteur du MAF",
                "Remplacer le capteur MAF si le nettoyage ne suffit pas",
            ],
        },
        'P0106': {
            'meaning': "Pression du collecteur d'admission (MAP) hors plage — signal incohérent avec les autres paramètres moteur.",
            'web_causes': [
                "Capteur MAP défectueux ou encrassé",
                "Fuite de dépression sur le collecteur d'admission",
                "Durite de dépression percée ou déconnectée",
                "Court-circuit dans le câblage du capteur MAP",
            ],
            'web_solutions': [
                "Inspecter toutes les durites de dépression (collecteur, servo-frein, régulateur)",
                "Tester le capteur MAP avec un multimètre (tension de sortie 0.5-4.5V)",
                "Remplacer le capteur MAP si hors tolérance",
                "Vérifier l'étanchéité du collecteur d'admission",
            ],
        },
        'P0113': {
            'meaning': "Température de l'air d'admission (IAT) trop élevée — l'air entrant dans le moteur est anormalement chaud.",
            'web_causes': [
                "Capteur IAT défectueux (valeur figée ou dérivée)",
                "Filtre à air colmaté forçant l'aspiration d'air chaud",
                "Intercooler défaillant (turbo) ne refroidissant plus l'air",
                "Recirculation des gaz chauds du compartiment moteur",
            ],
            'web_solutions': [
                "Remplacer le filtre à air",
                "Vérifier et nettoyer l'intercooler (turbo)",
                "Tester le capteur IAT (résistance variable selon température)",
                "Améliorer la ventilation du compartiment moteur si nécessaire",
            ],
        },
        'P0122': {
            'meaning': "Signal du capteur de position du papillon (TPS) trop bas — tension de sortie inférieure à la plage normale.",
            'web_causes': [
                "Capteur TPS défectueux ou mal calibré",
                "Court-circuit dans le câblage du TPS",
                "Connecteur TPS oxydé ou desserré",
                "Corps de papillon encrassé bloquant la rotation",
            ],
            'web_solutions': [
                "Nettoyer le corps de papillon avec un spray dégraissant",
                "Vérifier la tension d'alimentation du TPS (5V référence)",
                "Recalibrer le TPS selon la procédure constructeur",
                "Remplacer le capteur TPS si hors tolérance",
            ],
        },
        'P0190': {
            'meaning': "Capteur de pression du rail carburant — circuit défaillant ou signal hors plage.",
            'web_causes': [
                "Capteur de pression rail défectueux",
                "Pression carburant réellement insuffisante",
                "Câblage endommagé ou connecteur oxydé",
                "Pompe haute pression défaillante (moteur diesel)",
            ],
            'web_solutions': [
                "Mesurer la pression réelle du rail avec un manomètre externe",
                "Vérifier le câblage et le connecteur du capteur",
                "Remplacer le capteur de pression rail",
                "Contrôler la pompe haute pression (diesel)",
            ],
        },
        'P0217': {
            'meaning': "Température du liquide de refroidissement moteur trop élevée — risque de surchauffe imminente.",
            'web_causes': [
                "Niveau de liquide de refroidissement insuffisant (fuite ou évaporation)",
                "Thermostat bloqué en position fermée",
                "Ventilateur de refroidissement défaillant (électrique ou embrayage)",
                "Radiateur obstrué (calcaire, insectes, déformation)",
                "Pompe à eau défectueuse (débit insuffisant)",
                "Joint de culasse percé (mélange eau/huile)",
            ],
            'web_solutions': [
                "Vérifier immédiatement le niveau de liquide de refroidissement (moteur froid)",
                "Tester le thermostat (ouverture à 87-92°C dans l'eau chaude)",
                "Vérifier le fonctionnement du ventilateur (démarrage automatique à chaud)",
                "Nettoyer le radiateur extérieurement (jet d'eau doux)",
                "Contrôler la pompe à eau (jeu axial, fuite sur joint)",
                "Faire un test de combustion dans le liquide de refroidissement (joint de culasse)",
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
            'meaning': "Ratés d'allumage aléatoires détectés sur plusieurs cylindres — combustion irrégulière.",
            'web_causes': [
                "Bougies d'allumage usées ou encrassées",
                "Bobines d'allumage défaillantes",
                "Injecteurs encrassés ou défectueux",
                "Fuite de compression sur un ou plusieurs cylindres",
                "Problème d'alimentation carburant (pression basse)",
                "Capteur de position vilebrequin (CKP) défaillant",
            ],
            'web_solutions': [
                "Remplacer les bougies d'allumage (entretien tous les 30-60 000 km)",
                "Tester les bobines d'allumage (résistance primaire/secondaire)",
                "Nettoyer ou remplacer les injecteurs",
                "Faire un test de compression sur tous les cylindres",
                "Vérifier la pression carburant",
            ],
        },
        'P0500': {
            'meaning': "Capteur de vitesse véhicule (VSS) — signal absent ou hors plage.",
            'web_causes': [
                "Capteur VSS défectueux ou endommagé",
                "Câblage coupé ou connecteur oxydé",
                "Roue phonique endommagée (dents manquantes)",
                "Problème de boîte de vitesses",
            ],
            'web_solutions': [
                "Inspecter le capteur VSS et son câblage",
                "Nettoyer la roue phonique",
                "Remplacer le capteur VSS",
                "Vérifier la boîte de vitesses",
            ],
        },
        'P0524': {
            'meaning': "Pression d'huile moteur trop basse — risque de destruction des coussinets et du vilebrequin.",
            'web_causes': [
                "Niveau d'huile insuffisant (fuite ou consommation)",
                "Pompe à huile défaillante (usure, cavitation)",
                "Huile trop dégradée (viscosité insuffisante)",
                "Clapet de décharge de la pompe bloqué ouvert",
                "Coussinets de vilebrequin usés (jeu excessif)",
                "Capteur de pression d'huile défectueux",
            ],
            'web_solutions': [
                "Arrêter le moteur immédiatement et vérifier le niveau d'huile",
                "Effectuer une vidange si l'huile est dégradée",
                "Mesurer la pression d'huile avec un manomètre mécanique",
                "Remplacer la pompe à huile si débit insuffisant",
                "Inspecter les coussinets de vilebrequin",
            ],
        },
        'P0562': {
            'meaning': "Tension du système électrique trop basse — la batterie ou l'alternateur ne fournit pas assez de tension.",
            'web_causes': [
                "Batterie en fin de vie (capacité réduite)",
                "Alternateur défaillant (charge insuffisante)",
                "Connexions de batterie oxydées ou desserrées",
                "Consommateur parasite déchargeant la batterie",
                "Courroie d'alternateur détendue ou cassée",
            ],
            'web_solutions': [
                "Tester la batterie avec un testeur de charge (capacité réelle)",
                "Mesurer la tension de charge de l'alternateur (13.8-14.8V moteur tournant)",
                "Nettoyer et serrer les bornes de batterie",
                "Rechercher une consommation parasite (test ampèremètre sur borne négative)",
                "Vérifier la tension et l'état de la courroie d'alternateur",
                "Remplacer la batterie si > 4-5 ans ou capacité < 70%",
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
            'meaning': "Mélange air/carburant trop pauvre (banc 1) — le moteur reçoit trop d'air ou pas assez de carburant.",
            'web_causes': [
                "Fuite d'air après le débitmètre MAF (durite fissurée, joint collecteur)",
                "Capteur MAF encrassé donnant une valeur trop basse",
                "Injecteurs encrassés délivrant moins de carburant",
                "Pompe à carburant en fin de vie (pression insuffisante)",
                "Sonde lambda défectueuse (signal figé en pauvre)",
                "Filtre à carburant colmaté",
            ],
            'web_solutions': [
                "Inspecter toutes les durites d'admission pour fuites (spray carburant ou fumée)",
                "Nettoyer le capteur MAF avec un spray spécifique",
                "Vérifier la pression carburant au rail",
                "Nettoyer les injecteurs (additif ou nettoyage ultrason)",
                "Remplacer le filtre à carburant",
                "Tester la sonde lambda amont",
            ],
        },
        'P0172': {
            'meaning': "Mélange air/carburant trop riche (banc 1) — le moteur reçoit trop de carburant ou pas assez d'air.",
            'web_causes': [
                "Injecteurs qui fuient ou restent ouverts",
                "Capteur MAF défectueux (valeur surestimée)",
                "Régulateur de pression carburant bloqué (pression trop haute)",
                "Sonde lambda défectueuse (signal figé en riche)",
                "Filtre à air colmaté réduisant l'air entrant",
            ],
            'web_solutions': [
                "Tester les injecteurs (fuite statique moteur éteint)",
                "Nettoyer ou remplacer le capteur MAF",
                "Vérifier le régulateur de pression carburant",
                "Remplacer le filtre à air",
                "Tester la sonde lambda amont",
            ],
        },
        'P0340': {
            'meaning': "Signal du capteur de position d'arbre à cames (CMP) absent ou incorrect — le calculateur ne peut pas synchroniser l'allumage et l'injection.",
            'web_causes': [
                "Capteur CMP défectueux ou endommagé",
                "Roue phonique de l'arbre à cames endommagée (dents manquantes)",
                "Câblage coupé ou connecteur oxydé",
                "Problème de calage de distribution (chaîne sautée)",
                "Court-circuit dans le circuit du capteur",
            ],
            'web_solutions': [
                "Vérifier le câblage et le connecteur du capteur CMP",
                "Mesurer la résistance du capteur CMP (valeur nominale selon constructeur)",
                "Inspecter la roue phonique de l'arbre à cames",
                "Contrôler le calage de distribution",
                "Remplacer le capteur CMP si défectueux",
            ],
        },
        'P0335': {
            'meaning': "Signal du capteur de position du vilebrequin (CKP) absent ou incorrect — le moteur ne peut pas démarrer ou cale.",
            'web_causes': [
                "Capteur CKP défectueux",
                "Roue phonique du vilebrequin endommagée",
                "Câblage coupé ou connecteur oxydé",
                "Jeu excessif entre le capteur et la roue phonique",
            ],
            'web_solutions': [
                "Vérifier le câblage et le connecteur du capteur CKP",
                "Contrôler le jeu entre le capteur et la roue phonique (0.5–1.5 mm)",
                "Inspecter la roue phonique (dents manquantes ou déformées)",
                "Remplacer le capteur CKP",
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
            'meaning': "Perte de communication avec le calculateur moteur (ECM/PCM) — le réseau CAN ne reçoit plus les données du calculateur principal.",
            'web_causes': [
                "Calculateur moteur (ECM) défaillant ou en court-circuit",
                "Câblage du bus CAN endommagé (coupure, court-circuit)",
                "Connecteur du calculateur oxydé ou desserré",
                "Problème d'alimentation ou de masse du calculateur",
                "Fusible ou relais du calculateur grillé",
            ],
            'web_solutions': [
                "Vérifier l'alimentation et les masses du calculateur moteur",
                "Inspecter le connecteur du calculateur (oxydation, broches pliées)",
                "Contrôler les fusibles et relais associés au calculateur",
                "Vérifier la continuité du bus CAN (résistance terminale : 60 Ω entre CAN-H et CAN-L)",
                "Remplacer le calculateur moteur si défaillant (opération spécialisée)",
            ],
        },
        'P0128': {
            'meaning': "Température du liquide de refroidissement trop basse — le moteur n'atteint pas sa température de fonctionnement normale.",
            'web_causes': [
                "Thermostat bloqué en position ouverte (reste ouvert en permanence)",
                "Capteur de température de liquide de refroidissement défectueux",
                "Trajet trop court ne permettant pas la montée en température",
            ],
            'web_solutions': [
                "Remplacer le thermostat (pièce peu coûteuse, entretien préventif recommandé)",
                "Vérifier le capteur de température (valeur cohérente avec la température réelle)",
                "Effectuer un trajet plus long pour confirmer le diagnostic",
            ],
        },
        'P0016': {
            'meaning': "Désynchronisation entre la position du vilebrequin et de l'arbre à cames (banc 1) — problème de calage de distribution.",
            'web_causes': [
                "Chaîne de distribution étirée ou sautée d'une dent",
                "Tendeur de chaîne défaillant (usure, manque d'huile)",
                "Phaseur d'arbre à cames (VVT) défaillant ou encrassé",
                "Huile moteur dégradée ou niveau insuffisant affectant le VVT",
                "Capteur CKP ou CMP défectueux",
            ],
            'web_solutions': [
                "Vérifier le niveau et la qualité de l'huile moteur (changer si dégradée)",
                "Inspecter le phaseur VVT (nettoyage ou remplacement)",
                "Contrôler le tendeur de chaîne de distribution",
                "Remplacer la chaîne de distribution si étirée (intervention majeure)",
                "Vérifier les capteurs CKP et CMP",
            ],
        },
        'P0157': {
            'meaning': "Tension basse du circuit du capteur d'oxygène (Banque 2, Capteur 2) — mélange trop pauvre ou capteur défectueux.",
            'web_causes': [
                "Fuite d'air à l'admission ou à l'échappement",
                "Capteur d'oxygène (O2) défaillant (sonde aval)",
                "Pression de carburant insuffisante",
                "Injecteur de carburant encrassé ou défectueux",
                "Câblage de la sonde O2 endommagé ou court-circuité",
            ],
            'web_solutions': [
                "Vérifier la pression de carburant (doit être autour de 40-50 psi)",
                "Inspecter l'échappement pour détecter des fuites d'air",
                "Contrôler le câblage et les connecteurs de la sonde O2",
                "Remplacer la sonde O2 Banque 2 Capteur 2",
                "Nettoyer les injecteurs de carburant",
            ],
            'web_symptoms': [
                "Voyant moteur allumé (MIL)",
                "Diminution de la puissance moteur",
                "Ralenti instable ou calages fréquents",
                "Surconsommation de carburant",
            ],
            'web_severity': 'medium',
        },
        'P0274': {
            'meaning': "Circuit de l'injecteur du cylindre 5 trop élevé — problème électrique sur la commande de l'injecteur.",
            'web_causes': [
                "Injecteur de carburant du cylindre 5 défaillant (court-circuit)",
                "Câblage de l'injecteur endommagé ou corrodé",
                "Connecteur de l'injecteur desserré ou broches pliées",
                "Calculateur moteur (PCM/ECM) défectueux",
            ],
            'web_solutions': [
                "Nettoyer l'injecteur et ses connecteurs",
                "Vérifier la résistance de l'injecteur (doit être conforme aux spécifications)",
                "Contrôler la continuité du faisceau électrique jusqu'au calculateur",
                "Remplacer l'injecteur du cylindre 5",
                "Vérifier les mises à jour du logiciel PCM",
            ],
            'web_symptoms': [
                "Moteur qui tourne sur moins de cylindres (ratés)",
                "Diminution de la puissance et de l'accélération",
                "Consommation de carburant en hausse",
                "Voyant moteur qui clignote (danger pour le catalyseur)",
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

                causes_sec = re.search(
                    r'(?:possible causes?)[^<]*</[^>]+>(.*?)</(?:ul|ol)>',
                    html, re.IGNORECASE | re.DOTALL)
                if causes_sec:
                    causes = [re.sub(r'<[^>]+>', '', i).strip()
                              for i in re.findall(r'<li[^>]*>(.*?)</li>', causes_sec.group(1), re.DOTALL)
                              if len(i.strip()) > 5][:6]

                fixes_sec = re.search(
                    r'(?:possible fixes?|repairs?)[^<]*</[^>]+>(.*?)</(?:ul|ol)>',
                    html, re.IGNORECASE | re.DOTALL)
                if fixes_sec:
                    solutions = [re.sub(r'<[^>]+>', '', i).strip()
                                 for i in re.findall(r'<li[^>]*>(.*?)</li>', fixes_sec.group(1), re.DOTALL)
                                 if len(i.strip()) > 5][:6]

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

        return None
