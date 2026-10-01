# Copyright (c) 2026, FXMacroData and contributors
# For license information, please see license.txt

from unittest import mock

import frappe

from fxmacrodata_erpnext import client, exchange_rate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

PAIRS = (("EUR", "USD"), ("USD", "JPY"))


def api_response(rows, status_code=200):
	resp = mock.Mock()
	resp.status_code = status_code
	resp.json.return_value = {"data": rows}
	return resp


class TestFXMacroDataSettings(IntegrationTestCase):
	def setUp(self):
		for from_currency, to_currency in PAIRS:
			frappe.db.delete(
				"Currency Exchange", {"from_currency": from_currency, "to_currency": to_currency}
			)
			frappe.db.set_value("Currency", from_currency, "enabled", 1)
			frappe.db.set_value("Currency", to_currency, "enabled", 1)
		frappe.db.set_single_value("Accounts Settings", "allow_stale", 1)
		frappe.clear_document_cache("Accounts Settings", "Accounts Settings")
		self.configure(enabled=1)

	def tearDown(self):
		self.configure(enabled=0)
		frappe.db.rollback()

	def configure(self, enabled=1, cache_minutes=60, pairs=()):
		settings = frappe.get_doc("FXMacroData Settings")
		settings.enabled = enabled
		settings.api_key = "test-key" if enabled else None
		settings.cache_minutes = cache_minutes
		settings.set("currency_pairs", [])
		for from_currency, to_currency in pairs:
			settings.append("currency_pairs", {"from_currency": from_currency, "to_currency": to_currency})
		settings.save()
		return settings

	def patch_api(self, rows=None, status_code=200):
		return mock.patch.object(client.requests, "get", return_value=api_response(rows or [], status_code))

	def test_override_is_registered(self):
		self.assertEqual(
			frappe.override_whitelisted_method("erpnext.setup.utils.get_exchange_rate"),
			"fxmacrodata_erpnext.exchange_rate.get_exchange_rate",
		)

	def test_desk_call_is_routed_through_the_app(self):
		from frappe.handler import execute_cmd

		frappe.local.form_dict = frappe._dict(
			from_currency="EUR", to_currency="USD", transaction_date="2021-03-05"
		)
		with (
			self.patch_api([{"date": "2021-03-05", "val": 1.1912}]) as get,
			mock.patch.object(frappe.local, "request", frappe._dict(method="POST"), create=True),
		):
			rate = execute_cmd("erpnext.setup.utils.get_exchange_rate")

		get.assert_called_once()
		self.assertEqual(rate, 1.1912)

	def test_rate_is_stored_as_currency_exchange_and_used_by_erpnext(self):
		rows = [{"date": "2021-03-05", "val": None}, {"date": "2021-03-04", "val": 1.1934}]
		with self.patch_api(rows) as get:
			rate = exchange_rate.get_exchange_rate("EUR", "USD", "2021-03-05")

		self.assertEqual(rate, 1.1934)
		self.assertEqual(get.call_args.kwargs["headers"]["X-API-Key"], "test-key")
		self.assertEqual(get.call_args.kwargs["params"]["end_date"], "2021-03-05")
		record = frappe.get_all(
			"Currency Exchange",
			filters={"from_currency": "EUR", "to_currency": "USD"},
			fields=["date", "exchange_rate", "for_buying", "for_selling"],
		)
		self.assertEqual(len(record), 1)
		self.assertEqual(str(record[0].date), "2021-03-04")
		self.assertEqual(record[0].exchange_rate, 1.1934)
		self.assertEqual((record[0].for_buying, record[0].for_selling), (1, 1))

	def test_existing_record_is_left_alone(self):
		frappe.get_doc(
			{
				"doctype": "Currency Exchange",
				"date": "2021-03-05",
				"from_currency": "EUR",
				"to_currency": "USD",
				"exchange_rate": 1.25,
				"for_buying": 1,
				"for_selling": 1,
			}
		).insert()

		with self.patch_api([{"date": "2021-03-05", "val": 1.19}]) as get:
			rate = exchange_rate.get_exchange_rate("EUR", "USD", "2021-03-05")

		get.assert_not_called()
		self.assertEqual(rate, 1.25)

	def test_falls_back_to_erpnext_on_api_error(self):
		with (
			self.patch_api(status_code=500),
			mock.patch("erpnext.setup.utils.get_exchange_rate", return_value=0.5) as erpnext_rate,
		):
			rate = exchange_rate.get_exchange_rate("EUR", "USD", "2021-03-08", "for_selling")

		self.assertEqual(rate, 0.5)
		erpnext_rate.assert_called_once_with("EUR", "USD", "2021-03-08", "for_selling")
		self.assertFalse(
			frappe.db.exists("Currency Exchange", {"from_currency": "EUR", "to_currency": "USD"})
		)

	def test_disabled_does_not_call_api(self):
		self.configure(enabled=0)
		with (
			self.patch_api([{"date": "2021-03-04", "val": 1.19}]) as get,
			mock.patch("erpnext.setup.utils.get_exchange_rate", return_value=0.5),
		):
			rate = exchange_rate.get_exchange_rate("EUR", "USD", "2021-03-05")

		get.assert_not_called()
		self.assertEqual(rate, 0.5)

	def test_unsupported_pair_does_not_call_api(self):
		with self.patch_api() as get:
			self.assertIsNone(exchange_rate.ensure_rate("INR", "USD", "2021-03-05"))
		get.assert_not_called()

	def test_missing_rate_is_cached(self):
		with self.patch_api([]) as get:
			self.assertIsNone(exchange_rate.ensure_rate("EUR", "USD", "2021-03-09"))
			self.assertIsNone(exchange_rate.ensure_rate("EUR", "USD", "2021-03-09"))
		self.assertEqual(get.call_count, 1)

	def test_cache_can_be_turned_off(self):
		self.configure(enabled=1, cache_minutes=0)
		with self.patch_api([]) as get:
			exchange_rate.ensure_rate("EUR", "USD", "2021-03-10")
			exchange_rate.ensure_rate("EUR", "USD", "2021-03-10")
		self.assertEqual(get.call_count, 2)

	def test_sync_configured_pairs(self):
		self.configure(enabled=1, pairs=PAIRS)
		today = frappe.utils.nowdate()
		with self.patch_api([{"date": today, "val": 150.25}]) as get:
			created = exchange_rate.sync_configured_pairs()
			again = exchange_rate.sync_configured_pairs()

		self.assertEqual(len(created), 2)
		self.assertEqual(again, [])
		self.assertEqual(get.call_count, 2)
		self.assertTrue(
			frappe.db.exists(
				"Currency Exchange", {"from_currency": "USD", "to_currency": "JPY", "date": today}
			)
		)

	def test_rejects_unsupported_or_duplicate_pairs(self):
		with self.assertRaises(frappe.ValidationError):
			self.configure(enabled=1, pairs=[("INR", "USD")])
		with self.assertRaises(frappe.ValidationError):
			self.configure(enabled=1, pairs=[("EUR", "USD"), ("EUR", "USD")])
