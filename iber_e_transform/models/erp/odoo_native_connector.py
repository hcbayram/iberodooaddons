"""
Odoo 19 Enterprise Native Connector
-------------------------------------
Provides invoice and delivery note data directly from Odoo ORM.
No external HTTP calls — uses self.env to access account.move and stock.picking.
"""
import logging
from typing import List

_logger = logging.getLogger(__name__)


class OdooNativeConnector:
    """
    Connector for Odoo 19 Enterprise as the source ERP.
    Fetches account.move (invoices) and stock.picking (delivery notes)
    that are ready for e-transformation.
    """

    def __init__(self, env):
        self.env = env

    def fetch_invoices(self, last_sync_datetime=None) -> List:
        """
        Fetch customer invoices from Odoo that are posted and not yet UBL-synced.

        Returns:
            List of account.move recordsets
        """
        domain = [
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "=", "posted"),
        ]
        if last_sync_datetime:
            domain.append(("write_date", ">=", last_sync_datetime))

        # Exclude moves that already have a UBL invoice linked
        already_synced = self.env["l10n_tr.ubl.invoice"].search(
            [("account_move_id", "!=", False)]
        ).mapped("account_move_id.id")

        if already_synced and not last_sync_datetime:
            domain.append(("id", "not in", already_synced))

        moves = self.env["account.move"].search(domain, order="invoice_date desc", limit=500)
        _logger.info("OdooNativeConnector: %d fatura çekildi", len(moves))
        return moves

    def fetch_delivery_notes(self, last_sync_datetime=None) -> List:
        """
        Fetch outgoing delivery orders (stock.picking) from Odoo.

        Returns:
            List of stock.picking recordsets
        """
        domain = [
            ("picking_type_code", "=", "outgoing"),
            ("state", "=", "done"),
        ]
        if last_sync_datetime:
            domain.append(("write_date", ">=", last_sync_datetime))

        already_synced = self.env["l10n_tr.ubl.delivery.note"].search(
            [("stock_picking_id", "!=", False)]
        ).mapped("stock_picking_id.id")

        if already_synced and not last_sync_datetime:
            domain.append(("id", "not in", already_synced))

        pickings = self.env["stock.picking"].search(domain, order="date_done desc", limit=500)
        _logger.info("OdooNativeConnector: %d irsaliye çekildi", len(pickings))
        return pickings
