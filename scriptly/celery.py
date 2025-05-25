from __future__ import absolute_import
import os
from celery import Celery

# ✅ Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")


app = Celery("scriptly")

# ✅ Load settings from Django settings, using a namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# ✅ Autodiscover tasks in all installed apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f"🔧 DEBUG TASK: Request: {self.request!r}")
