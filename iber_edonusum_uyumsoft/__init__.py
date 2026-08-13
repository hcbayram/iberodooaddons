# -*- coding: utf-8 -*-
from . import models
from .config import INTEGRATOR_DEFAULTS


def post_init_hook(env):
    existing = env["edn.integrator"].search(
        [("code", "=", INTEGRATOR_DEFAULTS["code"])], limit=1
    )
    if not existing:
        env["edn.integrator"].create(INTEGRATOR_DEFAULTS)
    else:
        existing.write(INTEGRATOR_DEFAULTS)
