"""Pytest conftest: mock googleapiclient before Django loads.

This prevents ModuleNotFoundError caused by rassa/blueprints/producto_imagen/
which imports googleapiclient at module level. The mock is minimal — enough
for Django's URL resolver to load all blueprints without crashing.
"""

import sys
from unittest.mock import MagicMock

# Mock googleapiclient before ANY Django import happens
if "googleapiclient" not in sys.modules:
    googleapiclient = MagicMock()
    googleapiclient.discovery = MagicMock()
    googleapiclient.discovery.build = MagicMock()
    sys.modules["googleapiclient"] = googleapiclient
    sys.modules["googleapiclient.discovery"] = googleapiclient.discovery
    sys.modules["googleapiclient.http"] = MagicMock()
    sys.modules["googleapiclient.errors"] = MagicMock()