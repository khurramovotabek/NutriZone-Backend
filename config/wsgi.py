"""
WSGI entrypoint.

Serves the synchronous DRF/HTTP surface via Gunicorn, deployed and
scaled as a separate worker pool from the ASGI/Channels pool (Django
Implementation Blueprint §9) -- see docker/compose/ for the two
distinct service definitions.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{os.environ.get('DJANGO_ENV', 'development')}")

application = get_wsgi_application()
