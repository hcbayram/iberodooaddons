# Post-install setup that can't be expressed as plain <record> data:
# switching the main company to the Turkish chart of accounts and flipping
# the Settings checkboxes the demo scenario is meant to showcase. Mirrors
# the pattern used by demoiber/iberdemo/hooks.py in this same addons tree.


def _ensure_turkish_chart(env, company):
    # `account`/`l10n_tr` auto-guess which chart template to apply to the
    # main company right when l10n_tr finishes installing -- but at that
    # point our own data/00_company.xml (which sets the company's country
    # to Türkiye) hasn't run yet, since it's part of *this* module's data
    # and loads later. So the auto-guess falls back to the generic minimal
    # chart instead of the Turkish one. Force the correct chart now.
    company.write({'chart_template': False})
    env['account.account'].search([('company_ids', 'in', [company.id])]).unlink()
    env['account.chart.template'].try_loading('tr', company, install_demo=False)

    # `ir.module.module._register_hook()` runs later, at registry bootstrap,
    # and re-fires the *original* (stale, generic_coa-guessing) auto-install
    # callback recorded before our data set the company's country -- which
    # would immediately re-collide with the correct chart we just loaded.
    # We already did its job properly above, so drop the callback.
    if hasattr(env.registry, '_auto_install_template'):
        del env.registry._auto_install_template


def _account_by_code(env, company, code):
    return env['account.account'].search(
        [('code', '=', code), ('company_ids', 'in', [company.id])], limit=1)


# Category xmlid -> (expense account code, stock valuation account code) on
# the Turkish chart. Mamul (finished goods) posts to the COGS-style 620000
# account; Hammadde (raw materials, purchased and consumed into production,
# never sold directly) posts to the 710000 direct-material-consumption
# account instead -- both AVCO costing + perpetual/automated valuation.
CATEGORY_ACCOUNTS = {
    'iber_demo_civata.product_category_civata': ('620000', '152000'),
    'iber_demo_civata.product_category_hammadde': ('710000', '150000'),
}


def _set_category_accounting(env, company):
    """Point each category's Expense/Stock accounts at the Turkish chart
    instead of the chart's generic defaults. Must run after
    _ensure_turkish_chart, once these account codes actually exist --
    company_dependent fields resolved by account code, same lookup style as
    demoiber/iberdemo/hooks.py's _account_by_code.
    """
    for xmlid, (expense_code, stock_code) in CATEGORY_ACCOUNTS.items():
        category = env.ref(xmlid, raise_if_not_found=False)
        if not category:
            continue
        expense_account = _account_by_code(env, company, expense_code)
        stock_account = _account_by_code(env, company, stock_code)
        category.write({
            'property_cost_method': 'average',
            'property_valuation': 'real_time',
            'property_account_expense_categ_id': expense_account.id if expense_account else False,
            'property_stock_valuation_account_id': stock_account.id if stock_account else False,
        })


# Inventory/Manufacturing feature toggles this demo scenario needs on by
# default, keyed by their technical field name on res.config.settings.
FEATURE_SETTINGS = {
    'group_product_pricelist': True,     # Sales/Inventory: Pricelists
    'group_stock_production_lot': True,  # Inventory: Lots & Serial Numbers
    'group_stock_multi_locations': True, # Inventory: Storage Locations (prerequisite for routes below)
    'group_stock_adv_location': True,    # Inventory: Multi-Step Routes
    'group_mrp_routings': True,          # Manufacturing: Work Orders
}


def _apply_feature_settings(env):
    """Flip the same checkboxes a human would tick in Settings, the same
    way Odoo itself does it: build a res.config.settings record and call
    execute() rather than poking group rows by hand, so the exact same
    implied-group/config-parameter logic runs.
    """
    Settings = env['res.config.settings']
    fields = Settings.fields_get()
    vals = {k: v for k, v in FEATURE_SETTINGS.items() if k in fields}
    Settings.create(vals).execute()


def _set_multi_step_routes(env, company):
    """3-step receipts (Receive, Quality Control, then Store) and 3-step
    deliveries (Pick, Pack, then Deliver) on the main warehouse -- ties the
    already-established quality-control narrative into the receiving flow
    and matches an OEM-grade logistics setup.
    """
    warehouse = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
    if warehouse:
        warehouse.write({
            'reception_steps': 'three_steps',
            'delivery_steps': 'pick_pack_ship',
        })


def post_init_hook(env):
    company = env.ref('base.main_company')
    _ensure_turkish_chart(env, company)
    _set_category_accounting(env, company)
    _apply_feature_settings(env)
    _set_multi_step_routes(env, company)
