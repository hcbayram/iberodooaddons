# -*- coding: utf-8 -*-
"""
Gelen e-Faturayı Odoo sistem faturasına (account.move) dönüştürür.
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class IncomingInvoiceToAccountMove(models.Model):
    _inherit = "l10n_tr.ubl.invoice"

    def _convert_incoming_records(self):
        """Seçili gelen faturaları account.move'a çevirir, oluşan move'ları döner."""
        result_moves = self.env["account.move"]
        for inv in self:
            if inv.invoice_direction != "incoming":
                continue
            if inv.account_move_id:
                raise UserError(
                    _("Invoice %s is already linked to a system invoice: %s")
                    % (inv.id_value, inv.account_move_id.name)
                )
            move = inv._create_account_move()
            inv.account_move_id = move
            result_moves |= move

        if not result_moves:
            raise UserError(_("No processable incoming invoice found among the selected records."))
        return result_moves

    def action_convert_to_account_move_silent(self):
        """Liste ekranı için: dönüştürür, navigasyon yapmadan oluşan fatura sayısını döner."""
        result_moves = self._convert_incoming_records()
        return len(result_moves)

    def action_convert_to_account_move(self):
        """Form butonu için: dönüştürür ve oluşan faturaya yönlendirir."""
        result_moves = self._convert_incoming_records()

        if len(result_moves) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": result_moves.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "domain": [("id", "in", result_moves.ids)],
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "name": _("Created Invoices"),
        }

    def _create_account_move(self):
        self.ensure_one()
        partner = self._find_or_create_partner()
        currency = self.document_currency_id or self.env.company.currency_id
        journal = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal:
            raise UserError(_("No purchase-type accounting journal found."))

        move_vals = {
            "move_type": "in_invoice",
            "partner_id": partner.id if partner else False,
            "invoice_date": self.issue_date,
            "currency_id": currency.id,
            "journal_id": journal.id,
            "ref": self.id_value or self.UUID,
            "narration": _("e-Invoice UUID: %s") % (self.UUID or ""),
            "invoice_line_ids": self._build_invoice_line_vals(partner, currency),
        }
        move = self.env["account.move"].sudo().create(move_vals)
        _logger.info("account.move oluşturuldu: %s ← e-Fatura %s", move.name, self.id_value)
        return move

    def _find_or_create_partner(self):
        """VKN/TCKN ile cari bul; yoksa yeni oluştur."""
        vkn = (self.supplier_vkn_tckn or "").strip()
        name = (self.supplier_name or "").strip() or "Unknown Supplier"
        if vkn:
            partner = self.env["res.partner"].search(
                [("vat", "=", vkn), ("company_type", "=", "company")], limit=1
            )
            if not partner:
                partner = self.env["res.partner"].search(
                    [("vat", "=", vkn)], limit=1
                )
            if partner:
                return partner
            # Yeni cari oluştur
            partner = self.env["res.partner"].sudo().create({
                "name": name,
                "vat": vkn,
                "company_type": "company",
                "supplier_rank": 1,
                "street": self.supplier_street or False,
                "city": self.supplier_city or False,
                "zip": self.supplier_postal_code or False,
                "country_id": self._get_country_id(self.supplier_country_code or "TR"),
            })
            _logger.info("Yeni cari oluşturuldu: %s (VKN: %s)", name, vkn)
            return partner
        # VKN yoksa isimle ara
        if name:
            partner = self.env["res.partner"].search([("name", "ilike", name)], limit=1)
            return partner
        return False

    def _get_country_id(self, code):
        country = self.env["res.country"].search([("code", "=", code.upper())], limit=1)
        return country.id if country else False

    def _build_invoice_line_vals(self, partner, currency):
        """UBL satırlarını account.move.line vals listesine dönüştürür."""
        line_vals = []
        if not self.line_ids:
            # Satır yoksa tek satırlık fatura oluştur
            account = self._default_expense_account()
            tax = self._find_tax(20.0)
            line_vals.append((0, 0, {
                "name": self.id_value or _("e-Invoice"),
                "quantity": 1.0,
                "price_unit": self.payable_amount or 0.0,
                "account_id": account.id if account else False,
                "tax_ids": [(6, 0, tax.ids)] if tax else [],
            }))
            return line_vals

        for line in self.line_ids:
            account = self._default_expense_account()
            tax = self._find_tax(line.tax_percent)
            line_vals.append((0, 0, {
                "name": line.name or _("Product/Service"),
                "quantity": line.quantity,
                "price_unit": line.price_amount,
                "account_id": account.id if account else False,
                "tax_ids": [(6, 0, tax.ids)] if tax else [],
            }))
        return line_vals

    def _default_expense_account(self):
        """Gider hesabı — önce şirkete ait 600/620 gibi hesap, yoksa herhangi bir gider hesabı."""
        account = self.env["account.account"].search([
            ("company_ids", "in", self.env.company.ids),
            ("account_type", "in", ["expense", "expense_direct_cost"]),
        ], limit=1)
        return account

    def action_open_account_move(self):
        self.ensure_one()
        if not self.account_move_id:
            raise UserError(_("This invoice has no linked system invoice."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.account_move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _find_tax(self, percent):
        """Oran bazlı KDV vergisi bul (alış)."""
        if not percent:
            return self.env["account.tax"]
        tax = self.env["account.tax"].search([
            ("type_tax_use", "=", "purchase"),
            ("amount", "=", percent),
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
        ], limit=1)
        return tax
