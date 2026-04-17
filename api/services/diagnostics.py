from api.models import ScanSession, Vehicle, DTCReference
from api.services.ai_service import DTCModelAI

class DiagnosticService:
    @staticmethod
    def record_scan(mechanic, vehicle_data, dtc_codes, notes="", mileage_data=None, safety_data=None, scan_type='DIAGNOSTIC'):
        """
        Enregistre une session de diagnostic avec expertise optionnelle.
        """
        if not vehicle_data:
            vehicle_data = {'license_plate': 'INCONNU'}

        license_plate = vehicle_data.get('license_plate', 'INCONNU')
        brand = vehicle_data.get('brand', 'Inconnue')

        # Mise à jour ou création du véhicule
        vehicle, created = Vehicle.objects.update_or_create(
            license_plate=license_plate,
            defaults={
                'brand': brand,
                'model': vehicle_data.get('model', 'Inconnu'),
                'year': vehicle_data.get('year'),
                'vin': vehicle_data.get('vin', ''),
                'owner_name': vehicle_data.get('owner_name', ''),
                'owner_phone': vehicle_data.get('owner_phone', ''),
            }
        )

        # Ajout des codes DTC s'ils ne sont pas en base
        if not dtc_codes:
            dtc_codes = []

        for code in dtc_codes:
            # On cherche d'abord si un code générique existe
            generic_ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()

            # Si le code n'existe ni en générique ni spécifique à la marque, on le crée
            DTCReference.objects.get_or_create(
                code=code,
                brand=brand,
                defaults={
                    'description': generic_ref.description if generic_ref else f'Code défaut {code} détecté sur {brand}',
                    'meaning': generic_ref.meaning if generic_ref else f"Le système a détecté un dysfonctionnement lié au code {code} sur ce véhicule {brand}. Une inspection approfondie des composants associés est recommandée pour confirmer la panne.",
                    'severity': generic_ref.severity if generic_ref else 'medium',
                }
            )

        # Prédiction des coûts via l'IA (On ignore les coûts si c'est une expertise pour ne pas fausser les stats)
        predictions = DTCModelAI.predict_costs(dtc_codes, brand=brand) if scan_type != 'EXPERT' else {'estimated_labor': 0, 'estimated_parts_min': 0}

        # Extraction des données de kilométrage
        mileage_ecu = mileage_data.get('mileage_ecu') if mileage_data else None
        mileage_abs = mileage_data.get('mileage_abs') if mileage_data else None
        mileage_dashboard = mileage_data.get('mileage_dashboard') if mileage_data else None

        scan_session = ScanSession.objects.create(
            mechanic=mechanic,
            vehicle=vehicle,
            notes=notes,
            actual_labor_cost=predictions.get('estimated_labor', 0),
            actual_parts_cost=predictions.get('estimated_parts_min', 0),
            mileage_ecu=mileage_ecu,
            mileage_abs=mileage_abs,
            mileage_dashboard=mileage_dashboard,
            scan_type=scan_type
        )

        # Enregistrement des données de sécurité si présentes
        if safety_data:
            from api.models import SafetyCheck
            SafetyCheck.objects.create(
                scan_session=scan_session,
                is_airbag_deployed=safety_data.get('is_airbag_deployed', False),
                crash_data_present=safety_data.get('crash_data_present', False),
                srs_module_status=safety_data.get('srs_module_status', 'OK'),
                notes=safety_data.get('notes', '')
            )

        # On lie les DTC (Priorité au spécifique marque, sinon générique)
        dtc_refs = []
        for code in dtc_codes:
            ref = DTCReference.objects.filter(code=code, brand=brand).first()
            if not ref:
                ref = DTCReference.objects.filter(code=code, brand__isnull=True).first()
            if ref:
                dtc_refs.append(ref)

        scan_session.found_dtcs.set(dtc_refs)

        return scan_session

    @staticmethod
    def get_vehicle_history(license_plate):
        return ScanSession.objects.filter(vehicle__license_plate=license_plate).order_by('-date')
