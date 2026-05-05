from odoo import models, fields, api, _
from odoo.exceptions import UserError


class IberEntegraaSyncWizard(models.TransientModel):
    _name = 'iber.entegra.sync.wizard'
    _description = 'Entegra Senkronizasyon Sihirbazı'

    config_id = fields.Many2one('iber.entegra.config', required=True, string='Bağlantı')
    sync_type = fields.Selection([
        ('orders', 'Siparişler'),
        ('products', 'Ürünler'),
        ('reference', 'Referans Veriler (Kategori / Marka / Mağaza)'),
    ], required=True, default='orders', string='Senkronizasyon Türü')

    # Sipariş seçenekleri
    order_supplier = fields.Char(string='Pazaryeri Filtresi (boş = hepsi)')
    order_only_unsynced = fields.Boolean(
        string='Sadece senkronize edilmemişler', default=True)
    order_limit = fields.Integer(string='Limit', default=200)
    order_status_filter = fields.Char(string='Durum Filtresi (örn: 1,2,3)')

    # Ürün seçenekleri
    product_sync_only_changed = fields.Boolean(
        string='Sadece değişenleri çek (sync=0)', default=True)

    # Sonuç
    state = fields.Selection([
        ('draft', 'Hazır'),
        ('done', 'Tamamlandı'),
        ('error', 'Hata'),
    ], default='draft', readonly=True)
    result_message = fields.Text(string='Sonuç', readonly=True)

    def action_run(self):
        self.ensure_one()
        try:
            if self.sync_type == 'orders':
                self._sync_orders()
            elif self.sync_type == 'products':
                self._sync_products()
            elif self.sync_type == 'reference':
                self._sync_reference()
            self.write({'state': 'done'})
        except UserError:
            raise
        except Exception as exc:
            self.write({'state': 'error', 'result_message': str(exc)})
            raise UserError(_('Senkronizasyon hatası: %s') % exc)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Sipariş senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_orders(self):
        client = self.config_id._get_client()
        params = {'limit': min(self.order_limit, 200)}
        if self.order_only_unsynced:
            params['api_sync'] = 0
        if self.order_supplier:
            params['supplier'] = self.order_supplier.strip()
        if self.order_status_filter:
            params['status'] = self.order_status_filter.strip()

        # page path içinde: /order/page=1/?limit=200&api_sync=0...
        data = client.get_orders(page=1, params=params)
        orders = self._extract_list(data, ('orders', 'results', 'data'))

        created = updated = 0
        Order = self.env['iber.entegra.order']
        for raw in orders:
            # API returns id as string; cast to int32 safely
            entegra_id = self._safe_int(raw.get('id'), 0) or None
            if not entegra_id:
                continue
            existing = Order.search([
                ('config_id', '=', self.config_id.id),
                ('entegra_id', '=', entegra_id),
            ], limit=1)
            vals = self._map_order_vals(raw)
            line_data = vals.pop('line_ids', [])
            if existing:
                existing.write(vals)
                # Mevcut kalemleri sil, yeniden yaz (basit strateji)
                existing.line_ids.unlink()
                for ld in line_data:
                    ld[2]['order_id'] = existing.id
                    self.env['iber.entegra.order.line'].create(ld[2])
                updated += 1
            else:
                vals['config_id'] = self.config_id.id
                order = Order.create(vals)
                for ld in line_data:
                    ld[2]['order_id'] = order.id
                    self.env['iber.entegra.order.line'].create(ld[2])
                created += 1

        self.config_id.write({'last_order_sync': fields.Datetime.now()})
        self.result_message = _(
            '%d yeni sipariş oluşturuldu, %d sipariş güncellendi. Toplam: %d'
        ) % (created, updated, created + updated)

    def _map_order_vals(self, o):
        # Order lines are under 'order_product' key in Entegra API
        lines = []
        for d in (o.get('order_product') or []):
            lines.append((0, 0, {
                # product_code: try model (SKU), then store_stock_code, then pov_productCode
                'product_code': (
                    d.get('model') or d.get('store_stock_code')
                    or d.get('pov_productCode') or ''
                ),
                'product_name': d.get('name') or d.get('store_stock_name') or '',
                'quantity': self._safe_int(d.get('quantity'), 1),
                'price': float(d.get('price') or 0.0),
                'first_price': float(d.get('first_price') or 0.0),
            }))

        # supplier_id: API can return string or large number — safe cast
        supplier_id_val = self._safe_int(o.get('supplier_id'), 0)

        # full_name: API has separate firstname/lastname (no full_name field)
        firstname = o.get('firstname') or ''
        lastname = o.get('lastname') or ''
        full_name = f'{firstname} {lastname}'.strip() or o.get('username') or ''

        # Cast id to int — API returns it as a string; clamp to int32
        entegra_id = self._safe_int(o.get('id'), 0)

        return {
            'entegra_id': entegra_id,
            # 'order_number' in API is the marketplace order number
            'order_number': str(o.get('order_number') or ''),
            # 'no' in API is the Entegra internal reference number
            'order_id': o.get('no') or '',
            'supplier': o.get('supplier') or '',
            'supplier_id': supplier_id_val,
            # API uses 'datetime' for order date
            'order_date': o.get('datetime') or False,
            'full_name': full_name,
            'email': o.get('email') or '',
            # API has 'mobil_phone' (typo, missing 'e')
            'mobile_phone': str(o.get('mobil_phone') or ''),
            # API has 'telephone' not 'phone'
            'phone': str(o.get('telephone') or ''),
            'invoice_fullname': o.get('invoice_fullname') or '',
            'invoice_address': o.get('invoice_address') or '',
            'invoice_city': o.get('invoice_city') or '',
            'invoice_district': o.get('invoice_district') or '',
            'invoice_postcode': str(o.get('invoice_postcode') or ''),
            'tax_office': o.get('tax_office') or '',
            'tax_number': o.get('tax_number') or '',
            'tc_id': o.get('tc_id') or '',
            'ship_fullname': o.get('ship_fullname') or '',
            'ship_address': o.get('ship_address') or '',
            'ship_city': o.get('ship_city') or '',
            'ship_district': o.get('ship_district') or '',
            'ship_postcode': str(o.get('ship_postcode') or ''),
            # API has 'paymentType' (camelCase)
            'payment_type': o.get('paymentType') or '',
            # API has 'cargo_company' for the carrier name
            'cargo': o.get('cargo_company') or '',
            'cargo_code': o.get('cargo_code') or '',
            # API has 'cargo_fee_type' not 'cargo_payment_method'
            'cargo_payment_method': o.get('cargo_fee_type') or '',
            'discount': float(o.get('discount') or 0.0),
            'status': str(o.get('status') or '') or False,
            'store_order_status': o.get('store_order_status') or '',
            'sync': self._safe_int(o.get('sync'), 0),
            'api_sync': self._safe_int(o.get('api_sync'), 0),
            'line_ids': lines,
        }

    # ------------------------------------------------------------------
    # Ürün senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_products(self):
        client = self.config_id._get_client()
        params = {}
        if self.product_sync_only_changed:
            params['sync'] = 0
        data = client.get_products(page=1, params=params)
        # API returns 'productList' key (Postman example had typo 'porductList')
        products = self._extract_list(data, ('productList', 'porductList', 'results', 'products', 'data'))

        Product = self.env['iber.entegra.product']
        created = updated = 0
        now = fields.Datetime.now()

        for p in products:
            code = p.get('productCode') or p.get('product_code') or ''
            if not code:
                continue
            try:
                eid = int(float(p.get('id') or 0))
            except (ValueError, TypeError):
                eid = 0

            vals = {
                'config_id': self.config_id.id,
                'entegra_id': eid,
                'product_code': code,
                'name': p.get('name') or code,
                'barcode': p.get('barcode') or '',
                'brand': p.get('brand') or '',
                'status': str(p.get('status') or ''),
                'quantity': float(p.get('quantity') or 0),
                'price1': float(p.get('price1') or 0),
                'price2': float(p.get('price2') or 0),
                'kdv_id': str(p.get('kdv_id') or ''),
                'supplier': p.get('supplier') or '',
                'last_sync': now,
            }
            existing = Product.search([
                ('config_id', '=', self.config_id.id),
                ('product_code', '=', code),
            ], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                Product.create(vals)
                created += 1

        self.config_id.write({'last_product_sync': now})
        self.result_message = _(
            '%d yeni ürün oluşturuldu, %d ürün güncellendi. Toplam: %d'
        ) % (created, updated, created + updated)

    # ------------------------------------------------------------------
    # Referans veri senkronizasyonu
    # ------------------------------------------------------------------

    def _sync_reference(self):
        client = self.config_id._get_client()
        cat_count = self._sync_categories(client)
        brand_count = self._sync_brands(client)
        store_count = self._sync_stores(client)
        self.config_id.write({'last_reference_sync': fields.Datetime.now()})
        self.result_message = _(
            'Referans veriler güncellendi: %d kategori, %d marka, %d mağaza.'
        ) % (cat_count, brand_count, store_count)

    def _sync_categories(self, client):
        try:
            data = client.get_categories(page=1)
        except Exception:
            return 0
        items = self._extract_list(data, ('categories', 'results', 'data'))
        Category = self.env['iber.entegra.category']
        for c in items:
            eid = c.get('id')
            if not eid:
                continue
            existing = Category.search([('entegra_id', '=', eid)], limit=1)
            vals = {'entegra_id': eid, 'name': c.get('name') or str(eid)}
            if existing:
                existing.write(vals)
            else:
                Category.create(vals)
        return len(items)

    def _sync_brands(self, client):
        try:
            data = client.get_brands(page=1)
        except Exception as e:
            # API çağrısı başarısız — hatayı result_message'e ekle
            self.result_message = (self.result_message or '') + _('\nMarka hatası: %s') % e
            return 0
        # API response key bilinmiyor — olası tüm key'leri dene
        # API returns key 'brand' (singular, not 'brands')
        items = self._extract_list(data, ('brand', 'brands', 'brandList', 'results', 'data'))
        if not items and isinstance(data, dict):
            # Bilinmeyen key: hangi key'lerin list döndürdüğünü logla
            list_keys = [k for k, v in data.items() if isinstance(v, list)]
            if list_keys:
                # İlk list key'i kullan
                items = data[list_keys[0]]
                self.result_message = (self.result_message or '') + _(
                    '\nMarka key: %s kullanıldı.') % list_keys[0]
        Brand = self.env['iber.entegra.brand']
        for b in items:
            eid = b.get('id')
            if not eid:
                continue
            existing = Brand.search([('entegra_id', '=', eid)], limit=1)
            vals = {'entegra_id': eid, 'name': b.get('name') or str(eid)}
            if existing:
                existing.write(vals)
            else:
                Brand.create(vals)
        return len(items)

    def _sync_stores(self, client):
        try:
            data = client.get_stores()
        except Exception as e:
            self.result_message = (self.result_message or '') + _('\nMağaza hatası: %s') % e
            return 0
        items = self._extract_list(data, ('stores', 'results', 'data'))
        Store = self.env['iber.entegra.store']
        for s in items:
            eid = s.get('id')
            if not eid:
                continue
            try:
                eid_int = int(eid)
            except (ValueError, TypeError):
                eid_int = 0
            existing = Store.search([
                ('config_id', '=', self.config_id.id),
                ('entegra_id', '=', eid_int),
            ], limit=1)
            vals = {
                'entegra_id': eid_int,
                'name': s.get('name') or str(eid),
                'config_id': self.config_id.id,
            }
            if existing:
                existing.write(vals)
            else:
                Store.create(vals)
        return len(items)

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    _INT32_MAX = 2_147_483_647
    _INT32_MIN = -2_147_483_648

    @staticmethod
    def _safe_int(val, default=0):
        """PostgreSQL integer (32-bit) sınırını aşmayacak şekilde int'e çevirir."""
        try:
            v = int(float(val)) if val not in (None, '', False) else default
            return max(-2_147_483_648, min(2_147_483_647, v))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _extract_list(data, keys):
        if isinstance(data, list):
            return data
        for key in keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
        return []
