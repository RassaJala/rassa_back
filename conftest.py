"""Pytest conftest: mock googleapiclient before Django loads.

This prevents ModuleNotFoundError caused by rassa/blueprints/producto_imagen/
which imports googleapiclient at module level. The mock is minimal — enough
for Django's URL resolver to load all blueprints without crashing.

NOTE: The real fix is converting the googleapiclient import in
producto_imagen/ to a lazy import (e.g., inside the view method that
needs it). Until then, this conftest keeps tests running.

Monkeypatch for Python 3.14 + Django 5.0: copy(super()) in Context.__copy__
breaks on Python 3.14 because super() objects lost __dict__. This patches
Context until Django is upgraded to 5.1+.
"""

import sys
from unittest.mock import MagicMock


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


# --- Python 3.14 + Django 5.0 compatibility patch ---
# copy(super()) in Context.__copy__ fails on Python 3.14.
# Remove this after upgrading to Django 5.1+.
try:
    import django
    from django.template.context import Context

    if django.VERSION < (5, 1):

        def _safe_copy(self):
            duplicate = object.__new__(type(self))
            for k, v in self.__dict__.items():
                setattr(duplicate, k, v[:] if isinstance(v, list) else v)
            return duplicate

        Context.__copy__ = _safe_copy
except (ImportError, AttributeError):
    pass
