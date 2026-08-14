from odoo import models, fields, api


ERP_SYSTEM_SELECTION = [
    ("SAP_B1", "SAP Business One"),
    ("ODOO19", "Odoo 19 Enterprise"),
    ("LOGO", "Logo"),
    ("MIKRO", "Mikro"),
    ("OTHER", "Other"),
]


class AlgebraBaseDocumentUnit(models.Model):
    _name = "algebra.base.document.unit"
    _description = "UBL Document Unit Codes"
    _order = "code"

    code = fields.Char(string="UBL Unit Code", required=True, index=True)
    name = fields.Char(string="Unit Name", required=True)
    description = fields.Text(string="Description")
    erp_mapping_ids = fields.One2many(
        "algebra.base.document.unit.erp.mapping",
        "unit_id",
        string="ERP Mappings",
    )

    _sql_constraints = [("code_unique", "UNIQUE(code)", "UBL Unit Code must be unique!")]

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"


class AlgebraBaseDocumentUnitERPMapping(models.Model):
    _name = "algebra.base.document.unit.erp.mapping"
    _description = "ERP Unit Code Mapping"
    _order = "erp_system, erp_code"

    unit_id = fields.Many2one(
        "algebra.base.document.unit", string="UBL Unit", required=True, ondelete="cascade", index=True
    )
    erp_system = fields.Selection(
        ERP_SYSTEM_SELECTION, string="ERP System", required=True, default="ODOO19", index=True
    )
    erp_code = fields.Char(string="ERP Unit Code", required=True, index=True)
    erp_description = fields.Char(string="ERP Description")

    _sql_constraints = [
        (
            "erp_mapping_unique",
            "UNIQUE(erp_system, erp_code)",
            "ERP system and code combination must be unique!",
        )
    ]

    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"[{record.erp_system}] {record.erp_code} → {record.unit_id.code}"
            )
