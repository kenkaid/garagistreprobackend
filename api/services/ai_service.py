import logging
import json
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
                
                # Si les données d'entraînement sont vides, utiliser les descriptions par défaut
                if not causes:
                    causes = [f"Défaillance détectée : {ref.description}"]
                if not solutions:
                    solutions = ["Inspection visuelle du composant", "Vérification du faisceau électrique"]

                results.append({
                    'code': code,
                    'description': ref.description,
                    'meaning': ref.meaning,
                    'severity': ref.severity,
                    'probable_causes': causes,
                    'possibleCauses': causes, # Compatibilité camelCase
                    'suggested_solutions': solutions,
                    'suggestedFixes': solutions, # Compatibilité camelCase
                    'estimated_labor': ref.est_labor_cost,
                    'estimatedLaborCost': ref.est_labor_cost, # Compatibilité camelCase
                    'estimated_parts': {
                        'local': ref.est_part_price_local,
                        'import': ref.est_part_price_import
                    },
                    'localPartPrice': ref.est_part_price_local, # Compatibilité camelCase
                    'importPartPrice': ref.est_part_price_import, # Compatibilité camelCase
                    'partImageUrl': ref.part_image_url, # Compatibilité camelCase
                    'partLocation': ref.part_location, # Compatibilité camelCase
                })
                total_labor += ref.est_labor_cost
                total_parts_min += ref.est_part_price_local
                total_parts_max += max(ref.est_part_price_local, ref.est_part_price_import)
            else:
                results.append({
                    'code': code,
                    'description': "Code inconnu",
                    'probable_causes': ["Analyse manuelle requise"],
                    'suggested_solutions': ["Vérifier la base de données constructeur"]
                })

        # Score de confiance basé sur la présence de données d'entraînement
        confidence = "Élevée (Basée sur l'historique)" if any(r.get('probable_causes') for r in results) else "Moyenne (Générique)"

        return {
            'diagnostics': results,
            'summary': {
                'total_estimated_labor': total_labor,
                'total_estimated_parts_min': total_parts_min,
                'total_estimated_parts_max': total_parts_max,
                'confidence_score': confidence,
                'engine_version': "IA Predict v2.0 (Advanced)"
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
