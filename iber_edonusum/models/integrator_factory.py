# -*- coding: utf-8 -*-
import importlib
import pkgutil
import inspect
from .integrator_base import IntegratorBase
from . import integrators as _integrators_pkg

_integrator_registry: dict[str, type[IntegratorBase]] = {}


def _discover_integrators():
    """iber_edonusum/models/integrators/ altındaki tüm entegratörleri otomatik bulur."""
    for _, module_name, _ in pkgutil.iter_modules(_integrators_pkg.__path__):
        module = importlib.import_module(f"{_integrators_pkg.__name__}.{module_name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, IntegratorBase) and obj is not IntegratorBase:
                code = getattr(obj, "code", None)
                if code:
                    _integrator_registry[str(code).upper()] = obj


def register_integrator(cls: type[IntegratorBase]) -> None:
    """
    Dışarıdan (başka bir addon'dan) entegratör kaydeder.

    Kullanım — iber_uyumsoft gibi ayrı bir addon'un __init__.py'ında:

        from iber_edonusum.models.integrator_factory import register_integrator
        from .integrators.uyumsoft_integrator import UyumsoftIntegrator
        register_integrator(UyumsoftIntegrator)

    Bu sayede iber_edonusum'a dokunmadan yeni entegratör eklenebilir.
    """
    if not issubclass(cls, IntegratorBase):
        raise TypeError(f"{cls} must derive from IntegratorBase.")
    code = getattr(cls, "code", None)
    if not code:
        raise ValueError(f"{cls} class is missing the 'code' class attribute.")
    _integrator_registry[str(code).upper()] = cls


def refresh_registry():
    """Yerel integrators/ klasörünü yeniden tarar (hot-reload senaryoları için)."""
    _discover_integrators()


def get_integrator(code: str, settings: dict) -> IntegratorBase:
    if not code:
        raise ValueError("Integrator code cannot be empty.")
    cls = _integrator_registry.get(code.upper())
    if not cls:
        registered = ", ".join(sorted(_integrator_registry.keys())) or "—"
        raise ValueError(
            f"Unsupported integrator: '{code}'. Registered: {registered}"
        )
    return cls(settings)


def list_integrators() -> list[str]:
    return sorted(_integrator_registry.keys())


# Modül yüklenirken yerel integrators/ klasörünü tara
_discover_integrators()
