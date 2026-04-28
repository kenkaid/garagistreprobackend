"""
Commande Django pour scraper les codes DTC depuis outilsobdfacile.fr
et les importer dans la base de données DTCReference.

Usage:
    python manage.py scrape_dtcs
    python manage.py scrape_dtcs --dry-run
    python manage.py scrape_dtcs --verbose
"""

import re
import time
import requests
from django.core.management.base import BaseCommand
from api.models import DTCReference

BASE_URL = "https://www.outilsobdfacile.fr/code-defaut-standard-obd.php"

# Plages de codes disponibles sur le site avec descriptions complètes
RANGES = [
    "p0000-p0299",
    "p0300-p0399",
    "p0400-p0499",
    "p0500-p0599",
    "p0600-p0699",
    "p0700-p0999",
]

# Codes constructeurs spécifiques par marque (codes P1xxx)
BRAND_URLS = {
    "Renault":    "https://www.outilsobdfacile.fr/code-defaut-renault.php",
    "Peugeot":    "https://www.outilsobdfacile.fr/code-defaut-peugeot.php",
    "Citroen":    "https://www.outilsobdfacile.fr/code-defaut-citroen.php",
    "Volkswagen": "https://www.outilsobdfacile.fr/code-defaut-volkswagen.php",
    "Audi":       "https://www.outilsobdfacile.fr/code-defaut-audi.php",
    "BMW":        "https://www.outilsobdfacile.fr/code-defaut-bmw.php",
    "Toyota":     "https://www.outilsobdfacile.fr/code-defaut-toyota.php",
    "Ford":       "https://www.outilsobdfacile.fr/code-defaut-ford.php",
    "Opel":       "https://www.outilsobdfacile.fr/code-defaut-opel.php",
    "Mercedes":   "https://www.outilsobdfacile.fr/code-defaut-mercedes.php",
}

# Sévérité automatique basée sur les mots-clés dans la description
SEVERITY_KEYWORDS = {
    "critical": [
        "airbag", "srs", "frein", "abs", "crash", "collision",
        "direction", "sécurité", "incendie", "explosion",
    ],
    "high": [
        "catalyseur", "injection", "allumage", "raté", "turbo",
        "suralimentation", "vilebrequin", "arbre à cames",
        "pression huile", "température moteur", "surchauffe",
    ],
    "medium": [
        "sonde lambda", "capteur", "circuit", "panne", "signal",
        "performance", "plage de mesure", "régulateur",
    ],
    "low": [
        "intermittent", "aucune panne", "information",
    ],
}


def detect_severity(description: str) -> str:
    """Détecte la sévérité d'un code DTC à partir de sa description."""
    desc_lower = description.lower()
    for severity, keywords in SEVERITY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return severity
    return "medium"


def clean_description(raw: str) -> str:
    """Nettoie la description en supprimant les liens Markdown et espaces superflus."""
    # Supprime les liens Markdown [texte](/url) → texte
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', raw)
    # Supprime les balises HTML résiduelles
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    return cleaned.strip()


def parse_dtc_table(content: str) -> list:
    """
    Parse le HTML d'une page outilsobdfacile.fr et extrait les paires (code, description).
    Format HTML : <tr><td>P0300</td><td>Description...</td></tr>
    """
    results = []
    # Regex pour les lignes de tableau HTML : <tr><td>CODE</td><td>Description</td></tr>
    pattern = re.compile(
        r'<tr>\s*<td>\s*([A-Z][0-9A-Z]{3,6})\s*</td>\s*<td>(.*?)</td>\s*</tr>',
        re.IGNORECASE | re.DOTALL
    )
    for match in pattern.finditer(content):
        code = match.group(1).strip().upper()
        description = clean_description(match.group(2).strip())
        # Ignore les descriptions vides
        if description:
            results.append((code, description))
    return results


def fetch_page(url: str, verbose: bool = False) -> str:
    """Récupère le contenu d'une page web."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        if verbose:
            print(f"  → {url} [{response.status_code}] ({len(response.text)} chars)")
        return response.text
    except requests.RequestException as e:
        print(f"  ✗ Erreur lors du chargement de {url}: {e}")
        return ""


class Command(BaseCommand):
    help = "Scrape les codes DTC depuis outilsobdfacile.fr et les importe dans DTCReference"

    def add_arguments(self, parser):
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
        parser.add_argument(
            "--brands-only",
            action="store_true",
            help="Importe uniquement les codes constructeurs (pas les génériques)",
        )
        parser.add_argument(
            "--generic-only",
            action="store_true",
            help="Importe uniquement les codes génériques (pas les constructeurs)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Délai en secondes entre chaque requête (défaut: 1.0)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verbose = options["verbose"]
        brands_only = options["brands_only"]
        generic_only = options["generic_only"]
        delay = options["delay"]

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Mode DRY-RUN activé — aucune écriture en base"))

        total_created = 0
        total_updated = 0
        total_skipped = 0

        # === 1. Codes génériques (toutes familles P) ===
        if not brands_only:
            self.stdout.write(self.style.SUCCESS("\n📥 Scraping des codes génériques OBD..."))
            for range_param in RANGES:
                url = f"{BASE_URL}?dtc={range_param}#dtc"
                self.stdout.write(f"  Chargement: {range_param}...")
                content = fetch_page(url, verbose)
                if not content:
                    continue

                dtcs = parse_dtc_table(content)
                self.stdout.write(f"  → {len(dtcs)} codes trouvés dans {range_param}")

                for code, description in dtcs:
                    created, updated, skipped = self._save_dtc(
                        code=code,
                        description=description,
                        brand=None,
                        dry_run=dry_run,
                        verbose=verbose,
                    )
                    total_created += created
                    total_updated += updated
                    total_skipped += skipped

                time.sleep(delay)

        # === 2. Codes constructeurs ===
        if not generic_only:
            self.stdout.write(self.style.SUCCESS("\n🏭 Scraping des codes constructeurs..."))
            for brand, url in BRAND_URLS.items():
                self.stdout.write(f"  Chargement: {brand}...")
                content = fetch_page(url, verbose)
                if not content:
                    self.stdout.write(f"  ⚠️  Page {brand} non disponible, ignorée.")
                    time.sleep(delay)
                    continue

                dtcs = parse_dtc_table(content)
                self.stdout.write(f"  → {len(dtcs)} codes trouvés pour {brand}")

                for code, description in dtcs:
                    created, updated, skipped = self._save_dtc(
                        code=code,
                        description=description,
                        brand=brand,
                        dry_run=dry_run,
                        verbose=verbose,
                    )
                    total_created += created
                    total_updated += updated
                    total_skipped += skipped

                time.sleep(delay)

        # === Résumé final ===
        self.stdout.write("\n" + "=" * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"🔍 DRY-RUN terminé : {total_created + total_updated} codes seraient importés "
                f"({total_created} nouveaux, {total_updated} mis à jour, {total_skipped} ignorés)"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Import terminé : {total_created} nouveaux codes, "
                f"{total_updated} mis à jour, {total_skipped} ignorés"
            ))

    def _save_dtc(
        self,
        code: str,
        description: str,
        brand: str | None,
        dry_run: bool,
        verbose: bool,
    ) -> tuple[int, int, int]:
        """
        Sauvegarde un code DTC en base.
        Retourne (created, updated, skipped).
        """
        if not description:
            return 0, 0, 1

        severity = detect_severity(description)

        if verbose:
            brand_label = brand or "Générique"
            self.stdout.write(f"    [{brand_label}] {code}: {description[:60]}... [{severity}]")

        if dry_run:
            return 1, 0, 0

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
                return 1, 0, 0
            else:
                return 0, 1, 0
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    ✗ Erreur pour {code}: {e}"))
            return 0, 0, 1
