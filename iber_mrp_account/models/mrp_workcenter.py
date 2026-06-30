from odoo import api, fields, models


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    account_721_id = fields.Many2one(
        'account.account',
        string='721 Direkt İşçilik Hesabı',
        check_company=True,
        ondelete='restrict',
        domain="[('active', '=', True)]",
        help="Bu iş merkezindeki işçilik maliyeti bu hesaba alacak kaydedilir. "
             "DR 151 / CR 721",
    )
    costs_hour_721 = fields.Float(
        string='Saatlik İşçilik Maliyeti (721)',
        digits='Product Price',
        help="Saat başına direkt işçilik maliyeti (721 hesabına yansıyacak tutar).",
    )
    account_731_id = fields.Many2one(
        'account.account',
        string='731 Genel Üretim Giderleri Hesabı',
        check_company=True,
        ondelete='restrict',
        domain="[('active', '=', True)]",
        help="Bu iş merkezindeki GÜG maliyeti bu hesaba alacak kaydedilir. "
             "DR 151 / CR 731",
    )
    costs_hour_731 = fields.Float(
        string='Saatlik GÜG Maliyeti (731)',
        digits='Product Price',
        help="Saat başına genel üretim gideri (731 hesabına yansıyacak tutar).",
    )

    @api.constrains('costs_hour_721', 'costs_hour_731', 'costs_hour')
    def _check_costs_consistency(self):
        # Bilgilendirme amaçlı — zorunlu değil, sadece yuvarlama farkına izin ver.
        pass

    def _cal_cost_721(self, duration):
        """721 hesabı için işçilik maliyetini hesapla (dakika cinsinden süre)."""
        self.ensure_one()
        return self.costs_hour_721 * duration / 60.0

    def _cal_cost_731(self, duration):
        """731 hesabı için GÜG maliyetini hesapla (dakika cinsinden süre)."""
        self.ensure_one()
        return self.costs_hour_731 * duration / 60.0
