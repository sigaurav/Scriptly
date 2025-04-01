try:
    from django.apps import AppConfig
except ImportError:
    AppConfig = object
from django.conf import settings
from . import settings as scriptly_settings


class ScriptlyConfig(AppConfig):
    name = "scriptly"
    verbose_name = "Scriptly"

    def ready(self):
        from . import signals  # noqa: F401

        if scriptly_settings.SCRIPTLY_ENABLE_API_KEYS:
            new_middleware = []
            for value in settings.MIDDLEWARE:
                new_middleware.append(value)
                if value == "django.contrib.auth.middleware.AuthenticationMiddleware":
                    new_middleware.append("scriptly.middleware.api_key_login")
            settings.MIDDLEWARE = new_middleware
