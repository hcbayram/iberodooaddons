from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberTrendyolListing(models.Model):
    _name = 'iber.marketplace.trendyol.listing'
    _description = 'Trendyol Ürün Listesi'
    _rec_name = 'barcode'

    config_id = fields.Many2one(
        'iber.marketplace.trendyol.config', required=True,
        ondelete='cascade', string='Bağlantı')
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, string='Şirket')

    product_id = fields.Many2one(
        'product.product', required=True, string='Odoo Ürünü')
    barcode = fields.Char(
        required=True, index=True, string='Barkod / SKU')
    active = fields.Boolean(default=True)

    # Trendyol'dan gelen bilgiler
    trendyol_product_name = fields.Char(
        readonly=True, string='Trendyol Ürün Adı')
    trendyol_stock = fields.Integer(
        readonly=True, string='Trendyol Stoku')
    trendyol_price = fields.Float(
        readonly=True, string='Trendyol Fiyatı')
    last_push = fields.Datetime(
        readonly=True, string='Son Stok Gönderimi')

    # Odoo'dan hesaplanan değerler
    odoo_qty = fields.Float(
        compute='_compute_odoo_qty', string='Odoo Stoku')
    sale_price = fields.Float(
        compute='_compute_sale_price', string='Satış Fiyatı')

    # ------------------------------------------------------------------
    # Hesaplanan alanlar
    # ------------------------------------------------------------------

    @api.depends('product_id', 'product_id.qty_available')
    def _compute_odoo_qty(self):
        for rec in self:
            rec.odoo_qty = rec.product_id.qty_available if rec.product_id else 0.0

    @api.depends('product_id', 'product_id.lst_price')
    def _compute_sale_price(self):
        for rec in self:
            rec.sale_price = rec.product_id.lst_price if rec.product_id else 0.0

    # ------------------------------------------------------------------
    # Aksiyonlar
    # ------------------------------------------------------------------

    def action_push_inventory(self):
        """Seçili listingları Trendyol'a stok ve fiyat olarak gönder."""
        # Konfigürasyona göre grupla
        configs = self.mapped('config_id')
        for cfg in configs:
            group_listings = self.filtered(lambda l: l.config_id == cfg)
            client = cfg._get_client()

            # Max 100 item — batch gönder
            all_items = []
            for listing in group_listings:
                all_items.append({
                    'barcode': listing.barcode,
                    'quantity': int(listing.odoo_qty),
                    'salePrice': listing.sale_price,
                    'listPrice': listing.sale_price,
                })

            # Batch işleme (100'er parça)
            errors = []
            for i in range(0, len(all_items), 100):
                batch = all_items[i:i + 100]
                try:
                    client.update_inventory(batch)
                except Exception as exc:
                    errors.append(str(exc))

            if errors:
                raise UserError(
                    _('Stok güncellemesi sırasında hata oluştu:\n%s') % '\n'.join(errors))

        now = fields.Datetime.now()
        self.write({'last_push': now})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('%d ürün için stok/fiyat Trendyol\'a gönderildi.') % len(self),
                'type': 'success',
                'sticky': False,
            },
        }
