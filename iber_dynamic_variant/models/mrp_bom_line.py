import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr

_logger = logging.getLogger(__name__)


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    # ── Alan 1: Üst üründen dinamik olarak devralınacak nitelikler ─────────────
    iber_dynamic_attribute_ids = fields.Many2many(
        "product.attribute",
        "iber_dvb_bom_line_attribute_rel",
        "bom_line_id",
        "attribute_id",
        string="Dinamik Nitelikler",
        help=(
            "Bu BOM satırının bileşeni için üst ürün varyantından hangi niteliklerin "
            "değeri alınacağını belirler. Seçilen niteliklerin eşleşen değerleri, "
            "bileşen şablonunun varyantlarında aranır ve uygun product_id otomatik seçilir."
        ),
    )

    # ── Alan 2: Ek sabit nitelik değerleri (bom_product_template_attribute_value_ids gibi) ──
    iber_dynamic_fixed_ptav_ids = fields.Many2many(
        "product.template.attribute.value",
        "iber_dvb_bom_line_ptav_rel",
        "bom_line_id",
        "ptav_id",
        string="Ek Sabit Nitelik Değerleri",
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
        help=(
            "Bileşen varyantı aranırken dinamik niteliklere ek olarak "
            "sabit tutulacak nitelik değerleri. Her iki küme birleştirilerek "
            "uygun varyant bulunur."
        ),
    )

    # ── Alan 3: Miktar formülü ──────────────────────────────────────────────────
    iber_quantity_formula = fields.Text(
        string="Miktar Formülü",
        help=(
            "Bileşen miktarını hesaplamak için çalıştırılacak Python kodu.\n"
            "Kullanılabilir değişkenler:\n"
            "  bom_line  – bu BOM satırı (mrp.bom.line kaydı)\n"
            "  product   – üretilecek nihai ürün varyantı (product.product)\n"
            "Hesaplanan miktarı 'quantity' değişkenine atayın.\n\n"
            "Örnek:\n"
            "  quantity = bom_line.product_qty * 2\n\n"
            "  # Ürünün ağırlık niteliğine göre:\n"
            "  weight = product.weight or 1\n"
            "  quantity = bom_line.product_qty * weight"
        ),
    )

    # ── Teknik yedekleme alanları (explode sonrası sıfırlama için) ──────────────
    iber_dynamic_product_id_backup = fields.Many2one(
        "product.product",
        string="Dynamic Product Backup",
        copy=False,
        help="Teknik alan: explode sırasında değiştirilen product_id'nin orijinal değerini saklar.",
    )
    iber_dynamic_product_qty_backup = fields.Float(
        string="Dynamic Qty Backup",
        digits="Product Unit",
        copy=False,
        help="Teknik alan: explode sırasında değiştirilen product_qty'nin orijinal değerini saklar.",
    )

    # ── Kısıtlama: formül sözdizimi kontrolü ───────────────────────────────────

    @api.constrains("iber_quantity_formula")
    def _check_quantity_formula(self):
        for line in self:
            if not line.iber_quantity_formula:
                continue
            error = test_python_expr(expr=line.iber_quantity_formula, mode="exec")
            if error:
                raise ValidationError(error)

    # ── Yardımcı: dinamik varyantı bul ─────────────────────────────────────────

    def _get_dynamic_variant(self, product):
        """Üst ürün nitelikleri + sabit değerleri birleştirerek bileşen varyantını döndür.

        :param product: Üretilecek nihai ürün (product.product)
        :return: Eşleşen product.product varyantı veya False
        """
        self.ensure_one()
        tmpl = self.product_id.product_tmpl_id
        if not tmpl:
            return False

        # Üst ürün varyantının PTAVları içinden seçili niteliklere ait olanları al
        parent_ptavs = product.product_template_attribute_value_ids.filtered(
            lambda ptav: ptav.attribute_id in self.iber_dynamic_attribute_ids
        )

        # Bu PTAVların karşılığını bileşen şablonunda ara
        tmpl_ptavs = tmpl.attribute_line_ids.product_template_value_ids
        component_ptavs = self.env["product.template.attribute.value"]
        for ptav in parent_ptavs:
            match = tmpl_ptavs.filtered(
                lambda x, _ptav=ptav: (
                    x.attribute_id == _ptav.attribute_id
                    and x.product_attribute_value_id == _ptav.product_attribute_value_id
                )
            )
            component_ptavs |= match

        # Ek sabit değerlerle birleştir (yalnızca bu şablona ait olanlar)
        fixed = self.iber_dynamic_fixed_ptav_ids.filtered(lambda x: x.product_tmpl_id == tmpl)
        combination = component_ptavs | fixed

        if not combination:
            _logger.info(
                "iber_dynamic_variant: %s için eşleşen nitelik kombinasyonu bulunamadı, "
                "satır atlanıyor.",
                tmpl.display_name,
            )
            return False

        variant = tmpl._get_variant_for_combination(combination)
        if variant and variant.active:
            return variant

        _logger.info(
            "iber_dynamic_variant: %s şablonunda kombinasyon için aktif varyant yok, "
            "satır atlanıyor.",
            tmpl.display_name,
        )
        return False

    # ── Yardımcı: miktar formülünü değerlendir ─────────────────────────────────

    def _eval_quantity_formula(self, product):
        """Miktar formülünü çalıştır ve sonucu döndür.

        :param product: Üretilecek nihai ürün (product.product)
        :return: Hesaplanan miktar (float) veya None (formül yoksa)
        """
        self.ensure_one()
        if not self.iber_quantity_formula:
            return None
        ctx = {"bom_line": self, "product": product}
        safe_eval(self.iber_quantity_formula, context=ctx, mode="exec")
        return ctx.get("quantity")

    # ── _skip_bom_line override ─────────────────────────────────────────────────

    def _skip_bom_line(self, product, never_attribute_values=False):
        """product_id ve product_qty'yi manipüle et, ardından super'i çağır.

        1. Dinamik nitelikler tanımlıysa: üst ürün + sabit değerlerden
           bileşen varyantını bul ve product_id'yi güncelle.
           Eşleşen varyant yoksa satırı atla (True döndür).

        2. Miktar formülü varsa: formülü değerlendir ve product_qty'yi güncelle.

        Orijinal değerler action_confirm sonrasında mrp.production tarafından
        geri yüklenir (iber_dynamic_product_id_backup / iber_dynamic_product_qty_backup).
        """
        # ── 1. Dinamik varyant çözümlemesi ──────────────────────────────────
        if self.iber_dynamic_attribute_ids or self.iber_dynamic_fixed_ptav_ids:
            variant = self._get_dynamic_variant(product)
            if variant:
                # İlk değişiklikte orijinali yedekle
                if not self.iber_dynamic_product_id_backup:
                    self.iber_dynamic_product_id_backup = self.product_id
                self.product_id = variant
            else:
                return True  # eşleşme yok → satırı atla

        # ── 2. Dinamik miktar formülü ────────────────────────────────────────
        if self.iber_quantity_formula:
            computed = self._eval_quantity_formula(product)
            if computed is not None:
                # İlk değişiklikte orijinali yedekle
                if not self.iber_dynamic_product_qty_backup:
                    self.iber_dynamic_product_qty_backup = self.product_qty
                self.product_qty = computed

        return super()._skip_bom_line(product, never_attribute_values)
