# -*- coding: utf-8 -*-
from . import edn_integrator_hizli_ext
from . import edn_document_manager_hizli_ext
from .hizli_integrator import HizliIntegrator
from odoo.addons.iber_edonusum.models.integrator_factory import register_integrator

register_integrator(HizliIntegrator)
