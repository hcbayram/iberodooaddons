from collections import defaultdict

from odoo import _, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    iber_wip_transfer_move_ids = fields.Many2many(
        'account.move',
        'iber_wip_transfer_production_rel',
        'production_id',
        'move_id',
        string='Üretim Muhasebe Fişleri',
    )

    # ------------------------------------------------------------------ #
    #  Yardımcılar                                                        #
    # ------------------------------------------------------------------ #

    def _get_wip_account(self):
        """151 hesabını döndürür."""
        self.ensure_one()
        wip_acc = self.company_id.account_wip_711_721_731_id
        if not wip_acc:
            production_location = self.product_id.with_company(
                self.company_id
            ).property_stock_production
            wip_acc = production_location.valuation_account_id
        return wip_acc

    @staticmethod
    def _to_balance_vals(vals_list):
        """debit/credit vals listesini balance tabanlı vals listesine dönüştür."""
        result = []
        for vals in vals_list:
            normalized = {k: v for k, v in vals.items() if k not in ('debit', 'credit')}
            debit = vals.get('debit') or 0.0
            credit = vals.get('credit') or 0.0
            normalized['balance'] = debit - credit
            result.append(normalized)
        return result

    # ------------------------------------------------------------------ #
    #  İşçilik/GÜG satır değerlerini hesapla (posting olmadan)           #
    # ------------------------------------------------------------------ #

    def _compute_labour_line_vals(self, wip_acc):
        """
        DR 151 / CR 721 + DR 151 / CR 731 için vals listesi döndürür.
        Posting yapmaz; hem ayrı fiş hem tek fiş modunda kullanılır.
        Returns: (line_vals, total_amount, workorders_by_acc)
        """
        self.ensure_one()
        mo = self
        product_accounts = mo.product_id.product_tmpl_id.get_product_accounts()

        amounts = defaultdict(float)
        workorders_by_acc = defaultdict(mo.env['mrp.workorder'].browse)

        for wo in mo.workorder_ids:
            wc = wo.workcenter_id
            duration = sum(wo.time_ids.mapped('duration'))   # dakika

            if wc.account_721_id and wc.costs_hour_721:
                cost = mo.company_id.currency_id.round(wc._cal_cost_721(duration))
                if not mo.company_id.currency_id.is_zero(cost):
                    amounts[wc.account_721_id] += cost
                    workorders_by_acc[wc.account_721_id] |= wo

            if wc.account_731_id and wc.costs_hour_731:
                cost = mo.company_id.currency_id.round(wc._cal_cost_731(duration))
                if not mo.company_id.currency_id.is_zero(cost):
                    amounts[wc.account_731_id] += cost
                    workorders_by_acc[wc.account_731_id] |= wo

            # 721/731 tanımlı değilse standart expense_account'a
            if not wc.account_721_id and not wc.account_731_id:
                fallback = wc.expense_account_id or product_accounts.get('expense')
                if fallback:
                    cost = mo.company_id.currency_id.round(wo._cal_cost())
                    if not mo.company_id.currency_id.is_zero(cost):
                        amounts[fallback] += cost
                        workorders_by_acc[fallback] |= wo

        total = sum(amounts.values())
        if mo.company_id.currency_id.is_zero(total):
            return [], 0.0, {}

        desc = _('%s - İşçilik/GÜG (721/731)', mo.name)
        line_vals = []

        for acc, amt in amounts.items():
            if mo.company_id.currency_id.is_zero(amt):
                continue
            line_vals.append({
                'name': desc,
                'ref': desc,
                'balance': -amt,        # alacak: 721 / 731
                'account_id': acc.id,
            })

        if wip_acc:
            line_vals.append({
                'name': desc,
                'ref': desc,
                'balance': total,       # borç: 151
                'account_id': wip_acc.id,
            })

        return line_vals, total, workorders_by_acc

    # ------------------------------------------------------------------ #
    #  _post_labour override: DR 151 / CR 721 + DR 151 / CR 731          #
    # ------------------------------------------------------------------ #

    def _post_labour(self):
        """
        Tek fiş modunda çağrılmaz (iber_mrp_skip_labour context).
        Normal modda: DR 151 / CR 721+731 (iş merkezi ayarına göre).
        """
        if self.env.context.get('iber_mrp_skip_labour'):
            return

        for mo in self:
            production_location = mo.product_id.with_company(
                mo.company_id
            ).property_stock_production

            if mo.with_company(mo.company_id).product_id.valuation != 'real_time':
                super(MrpProduction, mo)._post_labour()
                continue

            if not production_location.valuation_account_id:
                super(MrpProduction, mo)._post_labour()
                continue

            has_split = any(
                wo.workcenter_id.account_721_id or wo.workcenter_id.account_731_id
                for wo in mo.workorder_ids
            )
            if not has_split:
                super(MrpProduction, mo)._post_labour()
                continue

            if mo.workorder_ids.time_ids.account_move_line_id:
                continue

            wip_acc = mo._get_wip_account()
            if not wip_acc:
                super(MrpProduction, mo)._post_labour()
                continue

            product_accounts = mo.product_id.product_tmpl_id.get_product_accounts()
            line_vals, total, workorders_by_acc = mo._compute_labour_line_vals(wip_acc)

            if not line_vals or mo.company_id.currency_id.is_zero(total):
                continue

            desc = _('%s - İşçilik/GÜG (721/731)', mo.name)
            account_move = mo.env['account.move'].sudo().create({
                'journal_id': product_accounts['stock_journal'].id,
                'date': fields.Date.context_today(mo),
                'ref': desc,
                'move_type': 'entry',
                'line_ids': [(0, 0, v) for v in line_vals],
            })
            account_move._post()

            for line in account_move.line_ids:
                if line.account_id in workorders_by_acc:
                    workorders_by_acc[line.account_id].time_ids.write(
                        {'account_move_line_id': line.id}
                    )

    # ------------------------------------------------------------------ #
    #  711 → 151 Yansıtma (ayrı fiş modu)                               #
    # ------------------------------------------------------------------ #

    def _get_711_yansitma_amounts(self):
        """
        710'a borç kaydedilen hammadde tutarlarını 711 yansıtma hesabına göre döndürür.
        Returns: dict {acc_711: amount}
        710 ve 711 her ikisi de ürün kategorisinde tanımlı olmalıdır.
        """
        self.ensure_one()
        amounts_by_711 = defaultdict(float)
        for move in self.move_raw_ids.filtered(lambda m: m.state == 'done'):
            acc_710 = move.product_id.categ_id.property_account_710_id
            acc_711 = move.product_id.categ_id.property_account_711_id
            if not acc_710 or not acc_711:
                continue
            amount = abs(move.value)
            if not self.company_id.currency_id.is_zero(amount):
                amounts_by_711[acc_711] += amount
        return amounts_by_711

    def _post_711_to_wip(self):
        """
        Ayrı fiş modunda MO bitiminde DR 151 / CR 711 (yansıtma) fişini oluşturur.
        710 borç tutarları 711 yansıtma hesabına alacak, 151'e borç yazılır.
        Tek fiş modunda bu metot çağrılmaz.
        """
        for mo in self:
            if mo.product_id.valuation != 'real_time':
                continue

            wip_acc = mo._get_wip_account()
            if not wip_acc:
                continue

            product_accounts = mo.product_id.product_tmpl_id.get_product_accounts()
            stock_journal = product_accounts.get('stock_journal')
            if not stock_journal:
                continue

            amounts_by_711 = mo._get_711_yansitma_amounts()
            if not amounts_by_711:
                continue

            total = sum(amounts_by_711.values())
            if mo.company_id.currency_id.is_zero(total):
                continue

            desc = _('%s - Ham Madde Yansıtma (711→151)', mo.name)
            line_vals = []
            for acc_711, amount in amounts_by_711.items():
                line_vals.append({
                    'name': desc, 'ref': desc,
                    'balance': -amount,          # CR 711 yansıtma
                    'account_id': acc_711.id,
                })
            line_vals.append({
                'name': desc, 'ref': desc,
                'balance': total,               # DR 151
                'account_id': wip_acc.id,
            })

            wip_move = mo.env['account.move'].sudo().create({
                'journal_id': stock_journal.id,
                'date': fields.Date.context_today(mo),
                'ref': desc,
                'move_type': 'entry',
                'line_ids': [(0, 0, v) for v in line_vals],
            })
            wip_move._post()
            mo.iber_wip_transfer_move_ids |= wip_move

    # ------------------------------------------------------------------ #
    #  Tek fiş: tüm satırları birleştir                                  #
    # ------------------------------------------------------------------ #

    def _post_single_consolidated_entry(self):
        """
        Tek fiş modunda MO'ya ait tüm muhasebe satırlarını tek bir
        account.move olarak oluşturur ve poste eder.

        Satır sırası:
          1. DR 711 / CR 150  (ham madde tüketimi)
          2. DR 151 / CR 711  (711 yansıtma)
          3. DR 151 / CR 721  (işçilik)
          4. DR 151 / CR 731  (GÜG)
          5. DR 152 / CR 151  (mamul girişi)
        """
        for mo in self:
            if mo.product_id.valuation != 'real_time':
                continue

            wip_acc = mo._get_wip_account()
            product_accounts = mo.product_id.product_tmpl_id.get_product_accounts()
            stock_journal = product_accounts.get('stock_journal')
            if not stock_journal:
                continue

            all_line_vals = []
            raw_moves_done = mo.move_raw_ids.filtered(lambda m: m.state == 'done')
            finished_moves_done = mo.move_finished_ids.filtered(lambda m: m.state == 'done')

            # 1. DR 711 / CR 150 (ham madde tüketim)
            for move in raw_moves_done:
                vals = move._get_account_move_line_vals()
                all_line_vals.extend(mo._to_balance_vals(vals))

            # 2. DR 151 / CR 711 yansıtma (710'a borç yazılan tutarlar 711'e alacak)
            amounts_by_711 = mo._get_711_yansitma_amounts() if wip_acc else {}
            if amounts_by_711 and wip_acc:
                total_711 = sum(amounts_by_711.values())
                desc_711 = _('%s - Ham Madde Yansıtma (711→151)', mo.name)
                for acc_711, amt in amounts_by_711.items():
                    all_line_vals.append({
                        'name': desc_711, 'ref': desc_711,
                        'balance': -amt,             # CR 711 yansıtma
                        'account_id': acc_711.id,
                    })
                all_line_vals.append({
                    'name': desc_711, 'ref': desc_711,
                    'balance': total_711,            # DR 151
                    'account_id': wip_acc.id,
                })

            # 3 & 4. DR 151 / CR 721 + DR 151 / CR 731
            labour_vals, _total, workorders_by_acc = mo._compute_labour_line_vals(wip_acc)
            all_line_vals.extend(labour_vals)

            # 5. DR 152 / CR 151 (mamul girişi)
            for move in finished_moves_done:
                vals = move._get_account_move_line_vals()
                all_line_vals.extend(mo._to_balance_vals(vals))

            if not all_line_vals:
                continue

            desc_main = _('%s - Üretim Yevmiyesi', mo.name)
            consolidated = mo.env['account.move'].sudo().create({
                'journal_id': stock_journal.id,
                'date': fields.Date.context_today(mo),
                'ref': desc_main,
                'move_type': 'entry',
                'line_ids': [(0, 0, v) for v in all_line_vals],
            })
            consolidated._post()

            # Stok hareketlerini konsolide fişe bağla
            (raw_moves_done | finished_moves_done).account_move_id = consolidated.id

            # İşçilik time satırlarını bağla
            for line in consolidated.line_ids:
                if line.account_id in workorders_by_acc:
                    workorders_by_acc[line.account_id].time_ids.write(
                        {'account_move_line_id': line.id}
                    )

            mo.iber_wip_transfer_move_ids |= consolidated

    # ------------------------------------------------------------------ #
    #  _post_inventory hook                                               #
    # ------------------------------------------------------------------ #

    def _post_inventory(self, cancel_backorder=False):
        if self.company_id.iber_mrp_single_entry:
            # İşçilik fişini ertele; tek fişe dahil edilecek
            res = super(
                MrpProduction, self.with_context(iber_mrp_skip_labour=True)
            )._post_inventory(cancel_backorder=cancel_backorder)
            self.filtered(lambda mo: mo.state == 'done')._post_single_consolidated_entry()
        else:
            res = super()._post_inventory(cancel_backorder=cancel_backorder)
            self.filtered(lambda mo: mo.state == 'done')._post_711_to_wip()
        return res

    # ------------------------------------------------------------------ #
    #  UI aksiyon                                                         #
    # ------------------------------------------------------------------ #

    def action_view_wip_transfer_moves(self):
        self.ensure_one()
        return {
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'name': _('Üretim Muhasebe Fişleri (%s)', self.name),
            'domain': [('id', 'in', self.iber_wip_transfer_move_ids.ids)],
            'view_mode': 'list,form',
            'views': [(self.env.ref('account.view_move_tree').id, 'list')],
        }
