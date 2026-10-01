# These tests need neither a Frappe site nor network access:
#   python -m unittest fxmacrodata_erpnext.tests.test_client

import unittest
from unittest import mock

import requests

from fxmacrodata_erpnext import client


def response(status_code=200, payload=None):
	resp = mock.Mock()
	resp.status_code = status_code
	resp.json.return_value = payload if payload is not None else {}
	return resp


class TestFetchRate(unittest.TestCase):
	def test_sends_key_in_header_and_reads_newest_value(self):
		payload = {
			"data": [
				{"date": "2026-09-30", "val": None},
				{"date": "2026-09-29", "val": 1.0712},
				{"date": "2026-09-28", "val": 1.0699},
			]
		}
		with mock.patch.object(client.requests, "get", return_value=response(payload=payload)) as get:
			result = client.fetch_rate("eur", "usd", "test-key", end_date="2026-09-30")

		self.assertEqual(result, ("2026-09-29", 1.0712))
		url = get.call_args.args[0]
		kwargs = get.call_args.kwargs
		self.assertEqual(url, "https://api.fxmacrodata.com/v1/forex/EUR/USD")
		self.assertEqual(kwargs["headers"]["X-API-Key"], "test-key")
		self.assertEqual(kwargs["params"], {"limit": 5, "end_date": "2026-09-30"})
		self.assertNotIn("api_key", kwargs["params"])
		self.assertTrue(kwargs["timeout"])

	def test_row_order_does_not_matter(self):
		rows = [{"date": "2026-09-25", "val": 1.1}, {"date": "2026-09-29", "val": 1.2}]
		self.assertEqual(client.newest_rate(rows), ("2026-09-29", 1.2))

	def test_null_zero_and_bad_values_are_skipped(self):
		rows = [
			{"date": "2026-09-30", "val": None},
			{"date": "2026-09-29", "val": 0},
			{"date": "2026-09-28", "val": "n/a"},
			{"date": "2026-09-27", "val": float("nan")},
			{"date": "2026-09-26", "val": True},
			{"val": 1.5},
			"junk",
		]
		self.assertIsNone(client.newest_rate(rows))
		self.assertIsNone(client.newest_rate(None))

	def test_unsupported_pair_makes_no_request(self):
		with mock.patch.object(client.requests, "get") as get:
			self.assertIsNone(client.fetch_rate("INR", "USD", "test-key"))
			self.assertIsNone(client.fetch_rate("USD", "USD", "test-key"))
			self.assertIsNone(client.fetch_rate("", "USD", "test-key"))
		get.assert_not_called()

	def test_missing_key_raises(self):
		with mock.patch.object(client.requests, "get") as get:
			with self.assertRaises(client.FXMacroDataError):
				client.fetch_rate("EUR", "USD", "")
		get.assert_not_called()

	def test_http_error_raises(self):
		with mock.patch.object(client.requests, "get", return_value=response(401, {"detail": "no"})):
			with self.assertRaises(client.FXMacroDataError) as ctx:
				client.fetch_rate("EUR", "USD", "test-key")
		self.assertIn("401", str(ctx.exception))

	def test_network_error_raises(self):
		with mock.patch.object(client.requests, "get", side_effect=requests.ConnectionError("down")):
			with self.assertRaises(client.FXMacroDataError):
				client.fetch_rate("EUR", "USD", "test-key")

	def test_non_json_response_raises(self):
		resp = response()
		resp.json.side_effect = ValueError("not json")
		with mock.patch.object(client.requests, "get", return_value=resp):
			with self.assertRaises(client.FXMacroDataError):
				client.fetch_rate("EUR", "USD", "test-key")

	def test_empty_data_returns_none(self):
		with mock.patch.object(client.requests, "get", return_value=response(payload={"data": []})):
			self.assertIsNone(client.fetch_rate("EUR", "USD", "test-key"))


if __name__ == "__main__":
	unittest.main()
