"""Pytest conftest: mock googleapiclient before Django loads.

This prevents ModuleNotFoundError caused by rassa/blueprints/producto_imagen/
which imports googleapiclient at module level. The mock is minimal — enough
for Django's URL resolver to load all blueprints without crashing.

NOTE: The real fix is converting the googleapiclient import in
producto_imagen/ to a lazy import (e.g., inside the view method that
needs it). Until then, this conftest keeps tests running.

Python 3.14 + Django 5.0 Context.__copy__ patch lives in rassa/tests/__init__.py
so it works with both `manage.py test` (Django runner) and pytest.
"""

import sys
from unittest.mock import MagicMock

import pytest


class MockHttpError(Exception):
    """Stand-in for googleapiclient.errors.HttpError for testing.

    The real HttpError accepts (resp, content) where resp has a .status
    attribute. Using a real Exception subclass is critical because:
      - side_effect checks isinstance(exc, BaseException) to decide
        whether to raise or return the value.
      - except HttpError requires isinstance checks to work.
    A bare MagicMock() fails both checks.
    """

    def __init__(self, resp, content=b""):
        super().__init__(content)
        self.resp = resp


# Mock googleapiclient before ANY Django import happens
if "googleapiclient" not in sys.modules:
    googleapiclient = MagicMock()
    googleapiclient.discovery = MagicMock()
    googleapiclient.discovery.build = MagicMock()

    errors_mock = MagicMock()
    errors_mock.HttpError = MockHttpError

    http_mock = MagicMock()

    sys.modules["googleapiclient"] = googleapiclient
    sys.modules["googleapiclient.discovery"] = googleapiclient.discovery
    sys.modules["googleapiclient.errors"] = errors_mock
    sys.modules["googleapiclient.http"] = http_mock


@pytest.fixture(autouse=True)
def _desactivar_rate_limits(monkeypatch):
    """Review 4R R3: los viewsets declaran throttle_classes explícitos (p.ej.
    PagoViewSet con ScopedRateThrottle); el modo test de settings solo limpia
    DEFAULT_THROTTLE_CLASSES, así que los tests pagan 429 según el orden de
    ejecución. Se neutraliza allow_request para que la suite sea reproducible.
    """
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "allow_request", lambda self, request, view: True)
