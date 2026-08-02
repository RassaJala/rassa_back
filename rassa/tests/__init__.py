# Python 3.14 + Django 5.0 compatibility patch.
# copy(super()) in Context.__copy__ fails on Python 3.14 because
# super() objects lost __dict__. This patches Context until Django 5.1+.
# Also loaded by conftest.py for pytest — both paths are needed because
# `manage.py test` (Django runner) does NOT load conftest.py.
import django
from django.template.context import Context

if django.VERSION < (5, 1):

    def _safe_context_copy(self):
        duplicate = object.__new__(type(self))
        for k, v in self.__dict__.items():
            setattr(duplicate, k, v[:] if isinstance(v, list) else v)
        return duplicate

    Context.__copy__ = _safe_context_copy
