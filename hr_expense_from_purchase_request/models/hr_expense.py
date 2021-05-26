# Copyright 2021 Ecosoft Co., Ltd. (http://ecosoft.co.th)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    employee_user_id = fields.Many2one(
        related="employee_id.user_id",
        readonly=True,
    )
    purchase_request_id = fields.Many2one(
        comodel_name="purchase.request",
        string="Purchase Request",
        ondelete="restrict",
        copy=False,
        index=True,
        help="Select purchase request of this employee, to create expense lines",
    )
    pr_for = fields.Selection(
        selection=[("expense", "Expense")],
        string="Use PR for",
        default="expense",
        required=True,
    )
    pr_line_ids = fields.One2many(
        comodel_name="hr.expense.sheet.prline",
        inverse_name="sheet_id",
        copy=False,
    )

    @api.onchange("employee_id")
    def _onchange_purchase_request_employee(self):
        self.purchase_request_id = False

    @api.onchange("purchase_request_id")
    def _onchange_purchase_request_id(self):
        SheetPRLine = self.env["hr.expense.sheet.prline"]
        self.pr_line_ids = False
        for line in self.purchase_request_id.line_ids:
            sheet_prline = self._prepare_sheet_prline(line)
            self.pr_line_ids += SheetPRLine.new(sheet_prline)

    def _prepare_sheet_prline(self, line):
        """ Prepare data, to create hr.expense. All must be hr.expense's fields """
        unit_amount = (
            line.estimated_cost / line.product_qty if line.product_qty > 0 else 0
        )
        return {
            "name": line.name,
            "product_id": line.product_id.id,
            "product_uom_id": line.product_uom_id.id,
            "unit_amount": unit_amount,
            "quantity": line.product_qty,
            "company_id": line.company_id.id,
            "currency_id": line.currency_id.id,
            "analytic_account_id": line.analytic_account_id.id,
            "analytic_tag_ids": line.analytic_tag_ids.ids,
            "description": line.description,
            "reference": line.specifications,
        }

    @api.model
    def create(self, vals):
        sheet = super().create(vals)
        if vals.get("purchase_request_id"):
            sheet.mapped("expense_line_ids").unlink()
            sheet._do_process_from_purchase_request()
            sheet.pr_line_ids.unlink()  # clean after use
        return sheet

    def write(self, vals):
        res = super().write(vals)
        if vals.get("purchase_request_id"):
            self.mapped("expense_line_ids").unlink()
            self._do_process_from_purchase_request()
            self.mapped("pr_line_ids").unlink()  # clean after use
        return res

    def _do_process_from_purchase_request(self):
        """ Hook method """
        sheets = self.filtered(lambda l: l.pr_for == "expense")
        sheets._create_expenses_from_prlines()

    def _create_expenses_from_prlines(self):
        for sheet in self:
            expenses_list = []
            sheet.pr_line_ids.mapped("employee_id")  # Force prefetch
            for pr_line in sheet.pr_line_ids:
                expense_line = pr_line._convert_to_write(pr_line._cache)
                expenses_list.append(expense_line)
            self.env["hr.expense"].create(expenses_list)


class HrExpenseSheetPRLine(models.Model):
    _name = "hr.expense.sheet.prline"
    _description = "Temp Holder of PR Lines data, used to create hr.expense"

    sheet_id = fields.Many2one(
        comodel_name="hr.expense.sheet",
        string="Expense Report",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        related="sheet_id.employee_id",
        store=True,
    )
    name = fields.Char(
        string="Description",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        required=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
        required=True,
    )
    unit_amount = fields.Monetary(
        string="Unit Price",
    )
    quantity = fields.Float(
        string="Quantity",
        digits="Product Unit of Measure",
    )
    total_amount = fields.Monetary(
        string="Total",
        compute="_compute_total_amount",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Analytic Account",
        check_company=True,
    )
    analytic_tag_ids = fields.Many2many(
        comodel_name="account.analytic.tag",
        string="Analytic Tags",
    )
    description = fields.Text(
        string="Notes...",
    )
    reference = fields.Char(
        string="Bill Reference",
    )

    @api.depends("unit_amount", "quantity")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = rec.unit_amount * rec.quantity

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.product_uom_id = self.product_id.uom_id
