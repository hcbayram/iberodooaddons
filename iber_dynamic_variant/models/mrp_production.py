from odoo import models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_confirm(self):
        """Üretim emri onaylandıktan sonra BOM satırlarındaki geçici değişiklikleri sıfırla.

        explode() / _skip_bom_line() sırasında product_id ve product_qty
        geçici olarak değiştirilir. super().action_confirm() bu değerleri
        kullandıktan sonra burası orijinallere geri döner.
        """
        res = super().action_confirm()
        self._reset_dynamic_bom_lines()
        return res

    def _reset_dynamic_bom_lines(self):
        """Dinamik olarak değiştirilmiş BOM satırlarını orijinal değerlerine döndür."""
        for bom_line in self.bom_id.bom_line_ids:
            vals = {}

            if bom_line.iber_dynamic_product_id_backup:
                vals["product_id"] = bom_line.iber_dynamic_product_id_backup.id
                vals["iber_dynamic_product_id_backup"] = False

            # iber_dynamic_product_qty_backup > 0 ise yedek alınmış demektir
            # (product_qty zaten required > 0, bu yüzden 0 güvenli sentinel)
            if bom_line.iber_dynamic_product_qty_backup:
                vals["product_qty"] = bom_line.iber_dynamic_product_qty_backup
                vals["iber_dynamic_product_qty_backup"] = 0.0

            if vals:
                bom_line.write(vals)
