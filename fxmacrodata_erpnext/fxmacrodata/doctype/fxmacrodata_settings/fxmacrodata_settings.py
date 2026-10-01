# Copyright (c) 2026, FXMacroData and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from fxmacrodata_erpnext.client import (
	SUPPORTED_CURRENCIES,
	FXMacroDataError,
	fetch_rate,
	is_supported_pair,
)


class FXMacroDataSettings(Document):
	def validate(self):
		self.validate_currency_pairs()
		if cint(self.enabled) and not self.in_test_or_install():
			self.check_api_key()

	def on_update(self):
		frappe.cache().delete_keys("fxmacrodata_erpnext:rate:")

	def validate_currency_pairs(self):
		seen = set()
		for row in self.get("currency_pairs") or []:
			pair = (row.from_currency, row.to_currency)
			if row.from_currency == row.to_currency:
				frappe.throw(_("Row {0}: From Currency and To Currency cannot be the same").format(row.idx))
			if not is_supported_pair(*pair):
				frappe.throw(
					_("Row {0}: {1}/{2} is not available from FXMacroData. Supported currencies: {3}").format(
						row.idx, row.from_currency, row.to_currency, ", ".join(sorted(SUPPORTED_CURRENCIES))
					)
				)
			if pair in seen:
				frappe.throw(_("Row {0}: {1}/{2} is listed twice").format(row.idx, *pair))
			seen.add(pair)

	def check_api_key(self):
		api_key = self.get_password("api_key", raise_exception=False)
		if not api_key:
			frappe.throw(_("API Key is required when FXMacroData is enabled"))
		try:
			fetch_rate("EUR", "USD", api_key)
		except FXMacroDataError as e:
			frappe.throw(_("Could not fetch a test rate from FXMacroData: {0}").format(str(e)))

	@staticmethod
	def in_test_or_install():
		return bool(getattr(frappe, "in_test", False) or frappe.flags.in_test or frappe.flags.in_install)
