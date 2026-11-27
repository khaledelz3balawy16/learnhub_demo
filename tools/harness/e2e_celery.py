"""HARNESS ONLY: the Celery app for E2E runs, with the same fakes as e2e_wsgi.py.

    celery -A e2e_celery worker      (serve.py starts it; PYTHONPATH has backend/ and this folder)

Syncs run in the worker, so the Breathe HR client must use the local fake here too. The fake
is installed before the worker forks, so every child process inherits it."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django

django.setup()

import fake_breathe
from config.celery import app

fake_breathe.install()

__all__ = ["app"]
