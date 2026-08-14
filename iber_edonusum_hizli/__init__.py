# -*- coding: utf-8 -*-
from . import core
from . import models
from .config import INTEGRATOR_DEFAULTS


def post_init_hook(env):
    existing = env["edn.integrator"].search(
        [("code", "=", INTEGRATOR_DEFAULTS["code"])], limit=1
    )
    if not existing:
        integrator = env["edn.integrator"].create(INTEGRATOR_DEFAULTS)
    else:
        existing.write(INTEGRATOR_DEFAULTS)
        integrator = existing

    # Aynı şirketin ayar kaydında henüz bir entegratör seçilmemişse yeni
    # kurulan entegratörü otomatik aktif yap. Aksi halde kullanıcı
    # "Entegratör Kur..." butonuyla modülü kurduktan sonra ayar formuna
    # dönüp "Aktif Entegratör" alanını elle seçmesi gerektiğini fark
    # etmiyor — buton "kaybolmuyor" gibi görünüyor.
    settings = env["ubl21.config.settings"].sudo().search([
        ("company_id", "=", integrator.company_id.id),
        ("integrator_id", "=", False),
    ])
    if settings:
        settings.write({"integrator_id": integrator.id})
