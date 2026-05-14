"""
WSGI config for core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

_application = get_wsgi_application()

def application(environ, start_response):
    # Apache/mod_wsgi supprime l'en-tête Authorization par défaut.
    # On le récupère depuis HTTP_X_AUTHORIZATION (header personnalisé)
    # ou depuis REDIRECT_HTTP_AUTHORIZATION (mod_rewrite).
    if 'HTTP_AUTHORIZATION' not in environ:
        if 'HTTP_X_AUTHORIZATION' in environ:
            environ['HTTP_AUTHORIZATION'] = environ['HTTP_X_AUTHORIZATION']
        elif 'REDIRECT_HTTP_AUTHORIZATION' in environ:
            environ['HTTP_AUTHORIZATION'] = environ['REDIRECT_HTTP_AUTHORIZATION']
    return _application(environ, start_response)
