from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    # ------------------------------------------------------------------ #
    #  711 hesabını kullan: DR 711 / CR 150  (üretim tüketim hareketi)   #
    # ------------------------------------------------------------------ #

    def _get_account_move_line_vals(self):
        """Ham madde tüketim hareketleri için 711 hesabını kullan."""
        self.ensure_one()

        production = self.raw_material_production_id
        if not production:
            return super()._get_account_move_line_vals()

        if self.product_id.valuation != 'real_time':
            return super()._get_account_move_line_vals()

        # 710 borç (maliyet hesabı) — her ikisi de tanımlı olmalı
        account_710 = self.product_id.categ_id.property_account_710_id
        if not account_710:
            return super()._get_account_move_line_vals()

        # Sadece stoktan üretim lokasyonuna giden hareketler (alacak tarafı 150)
        if self.location_id.valuation_account_id:
            return super()._get_account_move_line_vals()

        product_accounts = self.product_id._get_product_accounts()
        credit_acc = product_accounts.get('stock_valuation')   # 150
        if not credit_acc:
            return super()._get_account_move_line_vals()

        value = self._get_aml_value()
        ref = (self.reference or '') + ' - ' + (self.product_id.display_name or '')
        return [
            {
                'account_id': credit_acc.id,     # CR 150
                'name': ref,
                'debit': 0.0,
                'credit': value,
                'product_id': self.product_id.id,
            },
            {
                'account_id': account_710.id,    # DR 710
                'name': ref,
                'debit': value,
                'credit': 0.0,
                'product_id': self.product_id.id,
            },
        ]

    # ------------------------------------------------------------------ #
    #  Tek fiş modu: MO hareketlerinin bireysel fişini oluşturma         #
    # ------------------------------------------------------------------ #

    def _should_create_account_move(self):
        """
        Tek fiş parametresi aktifse MO'ya bağlı hareketler için
        bireysel fiş oluşturmayı ertele; tüm satırlar MO bitiminde
        tek bir fişte birleştirilir.
        """
        if (self.company_id.iber_mrp_single_entry
                and (self.raw_material_production_id or self.production_id)
                and self.product_id.valuation == 'real_time'):
            return False
        return super()._should_create_account_move()
