from django.conf import settings


class DynamicAllowedHostMiddleware:
    """
    Middleware qui lit l'IP stockée dans GlobalSettings (base de données)
    et l'ajoute dynamiquement aux ALLOWED_HOSTS de Django.
    Ainsi, changer l'IP dans l'admin Django suffit — sans modifier settings.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._inject_dynamic_host()
        return self.get_response(request)

    def _inject_dynamic_host(self):
        try:
            from api.models import GlobalSettings
            gs = GlobalSettings.objects.filter(id=1).first()
            if gs and gs.server_ip and gs.server_ip not in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS.append(gs.server_ip)
        except Exception:
            # En cas d'erreur (ex: table pas encore créée), on ignore silencieusement
            pass
