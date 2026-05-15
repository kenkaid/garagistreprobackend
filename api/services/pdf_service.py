import os
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from django.conf import settings
from django.utils import timezone

class PDFGenerator:
    @staticmethod
    def generate_invoice_pdf(scan_session, is_quote=True):
        """
        Génère un PDF pour un devis (quote) ou une facture (invoice).
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()

        # Styles personnalisés
        styles.add(ParagraphStyle(name='TitleStyle', fontSize=18, leading=22, alignment=1, spaceAfter=20, textColor=colors.HexColor('#1565C0')))
        styles.add(ParagraphStyle(name='SubTitleStyle', fontSize=14, leading=18, spaceAfter=10, textColor=colors.HexColor('#333333')))
        styles.add(ParagraphStyle(name='NormalStyle', fontSize=10, leading=12, spaceAfter=10))
        styles.add(ParagraphStyle(name='BoldStyle', fontSize=10, leading=12, spaceAfter=10, fontName='Helvetica-Bold'))

        elements = []

        # --- Entête : Logo et Infos Garage ---
        mechanic = scan_session.mechanic
        shop_name = mechanic.shop_name if mechanic else "Garage OBD CI"
        location = mechanic.location if mechanic else "Côte d'Ivoire"

        # Titre (Devis ou Facture)
        doc_type = "DEVIS" if is_quote else "FACTURE"
        elements.append(Paragraph(f"{doc_type} #{scan_session.id}", styles['TitleStyle']))

        # Infos Garage vs Infos Client
        data = [
            [Paragraph(f"<b>ÉMETTEUR :</b><br/>{shop_name}<br/>{location}", styles['NormalStyle']),
             Paragraph(f"<b>CLIENT :</b><br/>{scan_session.vehicle.owner_name or 'Client Standard'}<br/>{scan_session.vehicle.owner_phone or ''}", styles['NormalStyle'])]
        ]
        t = Table(data, colWidths=[8*cm, 8*cm])
        elements.append(t)
        elements.append(Spacer(1, 1*cm))

        # --- Infos Véhicule ---
        elements.append(Paragraph("INFORMATIONS VÉHICULE", styles['SubTitleStyle']))
        v = scan_session.vehicle
        v_data = [
            ["Marque / Modèle", f"{v.brand} {v.model}"],
            ["Immatriculation", v.license_plate],
            ["VIN", v.vin or "N/A"],
            ["Kilométrage (ECU)", f"{scan_session.mileage_ecu or 'N/A'} km"],
            ["Date du scan", scan_session.date.strftime('%d/%m/%Y %H:%M')],
        ]
        t_v = Table(v_data, colWidths=[5*cm, 11*cm])
        t_v.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(t_v)
        elements.append(Spacer(1, 1*cm))

        # --- Travaux / Diagnostics ---
        elements.append(Paragraph("DIAGNOSTIC TECHNIQUE", styles['SubTitleStyle']))
        dtcs = scan_session.scan_dtcs.all()
        if dtcs:
            dtc_data = [["Code", "Description", "Gravité"]]
            for sd in dtcs:
                dtc_data.append([sd.dtc.code, sd.dtc.meaning[:100] + '...' if len(sd.dtc.meaning) > 100 else sd.dtc.meaning, sd.dtc.get_severity_display()])

            t_dtc = Table(dtc_data, colWidths=[3*cm, 10*cm, 3*cm])
            t_dtc.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1565C0')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            elements.append(t_dtc)
        else:
            elements.append(Paragraph("Aucun code défaut détecté.", styles['NormalStyle']))
        elements.append(Spacer(1, 1*cm))

        # --- Coûts ---
        elements.append(Paragraph("DÉTAIL DES COÛTS", styles['SubTitleStyle']))
        cost_data = [
            ["Description", "Montant (FCFA)"],
            ["Main d'œuvre estimée", f"{scan_session.actual_labor_cost:,.0f}"],
            ["Pièces de rechange estimées", f"{scan_session.actual_parts_cost:,.0f}"],
            [Paragraph("<b>TOTAL</b>", styles['NormalStyle']), Paragraph(f"<b>{scan_session.total_cost:,.0f} FCFA</b>", styles['NormalStyle'])],
        ]
        t_cost = Table(cost_data, colWidths=[10*cm, 6*cm])
        t_cost.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('LINEABOVE', (0,-1), (-1,-1), 1, colors.black),
        ]))
        elements.append(t_cost)
        elements.append(Spacer(1, 2*cm))

        # --- Bas de page ---
        elements.append(Paragraph("Merci de votre confiance.", styles['NormalStyle']))
        elements.append(Paragraph(f"Généré par OBD CI - {timezone.now().strftime('%d/%m/%Y %H:%M')}", styles['NormalStyle']))

        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf

    @staticmethod
    def generate_invoice_html(scan_session, is_quote=True):
        """
        Génère le HTML pour un devis ou une facture.
        """
        mechanic = scan_session.mechanic
        shop_name = mechanic.shop_name if mechanic else "Garage OBD CI"
        location = mechanic.location if mechanic else "Côte d'Ivoire"
        doc_type = "DEVIS" if is_quote else "FACTURE"
        v = scan_session.vehicle
        dtcs = scan_session.scan_dtcs.all()

        dtc_rows = ""
        if dtcs:
            for sd in dtcs:
                dtc_rows += f"""
                <tr>
                    <td>{sd.dtc.code}</td>
                    <td>{sd.dtc.meaning[:100]}...</td>
                    <td>{sd.dtc.get_severity_display()}</td>
                </tr>
                """
        else:
            dtc_rows = "<tr><td colspan='3'>Aucun code défaut détecté.</td></tr>"

        html = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8"/>
            <title>{doc_type} #{scan_session.id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; color: #212121; padding: 20px; font-size: 13px; }}
                h1 {{ color: #1565C0; border-bottom: 2px solid #1565C0; padding-bottom: 6px; }}
                h2 {{ color: #37474F; margin-top: 20px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
                th {{ background: #1565C0; color: white; padding: 8px 10px; text-align: left; }}
                td {{ padding: 8px 10px; border-bottom: 1px solid #E0E0E0; }}
                tr:nth-child(even) td {{ background: #F5F5F5; }}
                .header-table {{ border: none; }}
                .header-table td {{ border: none; background: none; width: 50%; vertical-align: top; }}
                .footer {{ margin-top: 40px; font-size: 11px; color: #9E9E9E; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }}
                .total {{ font-weight: bold; font-size: 15px; color: #1565C0; text-align: right; }}
            </style>
        </head>
        <body>
            <h1>🔧 {doc_type} #{scan_session.id}</h1>
            
            <table class="header-table">
                <tr>
                    <td>
                        <strong>ÉMETTEUR :</strong><br/>
                        {shop_name}<br/>
                        {location}
                    </td>
                    <td>
                        <strong>CLIENT :</strong><br/>
                        {v.owner_name or 'Client Standard'}<br/>
                        {v.owner_phone or ''}
                    </td>
                </tr>
            </table>

            <h2>🚗 INFORMATIONS VÉHICULE</h2>
            <table>
                <tr><td width="30%">Marque / Modèle</td><td><strong>{v.brand} {v.model}</strong></td></tr>
                <tr><td>Immatriculation</td><td><strong>{v.license_plate}</strong></td></tr>
                <tr><td>VIN</td><td>{v.vin or "N/A"}</td></tr>
                <tr><td>Kilométrage</td><td>{scan_session.mileage_ecu or 'N/A'} km</td></tr>
                <tr><td>Date du scan</td><td>{scan_session.date.strftime('%d/%m/%Y %H:%M')}</td></tr>
            </table>

            <h2>🔍 DIAGNOSTIC TECHNIQUE</h2>
            <table>
                <thead>
                    <tr><th>Code</th><th>Description</th><th>Gravité</th></tr>
                </thead>
                <tbody>
                    {dtc_rows}
                </tbody>
            </table>

            <h2>💰 DÉTAIL DES COÛTS</h2>
            <table>
                <tr><td>Main d'œuvre estimée</td><td align="right">{scan_session.actual_labor_cost:,.0f} FCFA</td></tr>
                <tr><td>Pièces de rechange estimées</td><td align="right">{scan_session.actual_parts_cost:,.0f} FCFA</td></tr>
                <tr class="total"><td>TOTAL</td><td align="right">{scan_session.total_cost:,.0f} FCFA</td></tr>
            </table>

            <div class="footer">
                Merci de votre confiance.<br/>
                Généré par OBD CI le {timezone.now().strftime('%d/%m/%Y %H:%M')}
            </div>
        </body>
        </html>
        """
        return html
