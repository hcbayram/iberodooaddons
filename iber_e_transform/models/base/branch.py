from odoo import models, fields, api


ERP_SYSTEM_SELECTION = [
    ("SAP_B1", "SAP Business One"),
    ("ODOO19", "Odoo 19 Enterprise"),
    ("LOGO", "Logo"),
    ("MIKRO", "Mikro"),
    ("OTHER", "Other"),
]


class AlgebraBaseBranch(models.Model):
    _name = "algebra.base.branch"
    _description = "Branch/Business Place"
    _order = "code"

    code = fields.Char(string="Branch Code", required=True, index=True)
    name = fields.Char(string="Branch Name", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Active", default=True)
    street = fields.Char(string="Street")
    city = fields.Char(string="City")
    county = fields.Char(string="District/County")
    postal_code = fields.Char(string="Postal Code")
    country_code = fields.Char(string="Country Code", default="TR")
    erp_mapping_ids = fields.One2many(
        "algebra.base.branch.erp.mapping",
        "branch_id",
        string="ERP Mappings",
    )

    _sql_constraints = [("code_unique", "UNIQUE(code)", "Branch Code must be unique!")]

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"


class AlgebraBaseBranchERPMapping(models.Model):
    _name = "algebra.base.branch.erp.mapping"
    _description = "ERP Branch Mapping"
    _order = "erp_system, erp_branch_id"

    branch_id = fields.Many2one(
        "algebra.base.branch", string="Branch", required=True, ondelete="cascade", index=True
    )
    erp_system = fields.Selection(
        ERP_SYSTEM_SELECTION, string="ERP System", required=True, default="ODOO19", index=True
    )
    erp_branch_id = fields.Char(string="ERP Branch ID", required=True, index=True)
    erp_branch_name = fields.Char(string="ERP Branch Name")

    _sql_constraints = [
        (
            "erp_mapping_unique",
            "UNIQUE(erp_system, erp_branch_id)",
            "ERP system and branch ID combination must be unique!",
        )
    ]

    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"[{record.erp_system}] {record.erp_branch_id} → {record.branch_id.name}"
            )
