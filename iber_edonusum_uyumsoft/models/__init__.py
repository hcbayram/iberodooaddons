# -*- coding: utf-8 -*-
from . import ubl_invoice_status_ext
from .uyumsoft_integrator import UyumsoftIntegrator
from odoo.addons.iber_edonusum.models.integrator_factory import register_integrator

register_integrator(UyumsoftIntegrator)
