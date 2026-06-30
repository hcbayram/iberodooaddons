from odoo import models, fields
from odoo.exceptions import UserError


class UBL21ConfigSettingsSAPB1(models.Model):
    """
    iber_e_transform ayarlarına SAP B1 bağlantı bilgilerini ekler.
    Bu modül kurulduğunda ayarlar formuna SAP B1 sekmesi eklenir.
    """
    _inherit = "ubl21.config.settings"

    # active_erp seçimine sap_b1 seçeneği eklenir
    active_erp = fields.Selection(
        selection_add=[("sap_b1", "SAP Business One")],
        ondelete={"sap_b1": "set default"},
    )

    # === SAP B1 SERVICE LAYER ===
    sap_service_layer_url = fields.Char(
        string="Service Layer URL",
        placeholder="https://server:50000/b1s/v1",
        help="SAP Business One Service Layer URL adresi",
    )
    sap_company_db = fields.Char(
        string="Company Database",
        placeholder="SBODEMOUS",
        help="SAP B1 şirket veritabanı adı",
    )
    sap_username = fields.Char(string="Kullanıcı Adı", help="SAP B1 kullanıcı adı")
    sap_password = fields.Char(string="Şifre", help="SAP B1 şifresi")

    # === SQL SERVER (Opsiyonel) ===
    sql_server = fields.Char(string="SQL Server", placeholder="localhost")
    sql_database = fields.Char(string="Database", placeholder="SBODEMOUS")
    sql_username = fields.Char(string="SQL Kullanıcı Adı")
    sql_password = fields.Char(string="SQL Şifre")
    sql_port = fields.Integer(string="Port", default=1433)

    def action_sync_branches_from_sap(self):
        """SAP BusinessPlaces verilerini Odoo şubelere senkronize et."""
        self.ensure_one()
        from .sap_b1_connector import SAPB1Connector

        if not self.sap_service_layer_url:
            raise UserError("SAP Service Layer URL tanımlı değil!")

        try:
            connector = SAPB1Connector(self, env=self.env)
            with connector:
                synced_count = connector.sync_branches_to_odoo()

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Başarılı",
                    "message": f"{synced_count} şube SAP'den senkronize edildi.",
                    "type": "success",
                    "sticky": True,
                },
            }
        except Exception as e:
            raise UserError(f"Şube senkronizasyon hatası: {str(e)}")
