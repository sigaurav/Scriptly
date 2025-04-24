__author__ = "chris"

import os
import tempfile

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from celery import app

celery_app = app.app_or_default()


def get(key, default):
    return getattr(settings, key, default)


IS_WINDOWS = os.name == "nt"

# AUTH based settings
SCRIPTLY_ALLOW_ANONYMOUS = get("SCRIPTLY_ALLOW_ANONYMOUS", True)
SCRIPTLY_AUTH = get("SCRIPTLY_AUTH", True)
SCRIPTLY_LOGIN_URL = get("SCRIPTLY_LOGIN_URL", settings.LOGIN_URL)
SCRIPTLY_REGISTER_URL = get("SCRIPTLY_REGISTER_URL", "/accounts/register/")
SCRIPTLY_ENABLE_API_KEYS = get("SCRIPTLY_ENABLE_API_KEYS", False)

# Celery and job queue settings
# SCRIPTLY_CELERY = get("SCRIPTLY_CELERY", True)
SCRIPTLY_CELERY_TASKS = get("SCRIPTLY_CELERY_TASKS", "scriptly.tasks")
SCRIPTLY_CELERY_STOPPABLE_JOBS = "amqp" in str(
    celery_app.conf.get("CELERY_BROKER_URL", celery_app.conf.get("broker_url") or "")
)

SCRIPTLY_CELERY = False


# Site setup settings
SCRIPTLY_DEFAULT_SCRIPT_GROUP = get("SCRIPTLY_DEFAULT_SCRIPT_GROUP", _("Scripts"))
SCRIPTLY_EPHEMERAL_FILES = get("SCRIPTLY_EPHEMERAL_FILES", False)
SCRIPTLY_FILE_DIR = get("SCRIPTLY_FILE_DIR", "scriptly_files")
SCRIPTLY_JOB_EXPIRATION = get("SCRIPTLY_JOB_EXPIRATION", {"anonymous": None, "users": None})
SCRIPTLY_REALTIME_CACHE = get("SCRIPTLY_REALTIME_CACHE", None)
SCRIPTLY_SCRIPT_DIR = get("SCRIPTLY_SCRIPT_DIR", "scriptly_scripts")

# User interface settings
SCRIPTLY_SHOW_LOCKED_SCRIPTS = get("SCRIPTLY_SHOW_LOCKED_SCRIPTS", True)
SCRIPTLY_SITE_NAME = get("SCRIPTLY_SITE_NAME", _("Scriptly!"))
SCRIPTLY_SITE_TAG = get("SCRIPTLY_SITE_TAG", _("A web UI for Python scripts"))

# Virtual Environment Settings
SCRIPTLY_VIRTUAL_ENVIRONMENT_DIRECTORY = get(
    "SCRIPTLY_VIRTUAL_ENVIRONMENT_DIRECTORY", tempfile.gettempdir()
)
