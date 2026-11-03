"""Imports every model module in this package so `Base.metadata` is complete (Alembic needs it).

New model files are picked up automatically; nothing to register.
"""
import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
