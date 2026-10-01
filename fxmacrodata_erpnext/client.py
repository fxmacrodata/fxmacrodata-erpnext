"""Small HTTP client for the FXMacroData forex endpoint.

Kept free of Frappe imports so it can be tested without a site.
"""

import datetime
import math

import requests

API_BASE = "https://api.fxmacrodata.com/v1"
TIMEOUT = 10

# Currencies the /forex/{base}/{quote} endpoint accepts.
SUPPORTED_CURRENCIES = frozenset(
	{
		"AUD",
		"BRL",
		"CAD",
		"CHF",
		"CNH",
		"CNY",
		"DKK",
		"EUR",
		"GBP",
		"HUF",
		"ILS",
		"JPY",
		"KRW",
		"MYR",
		"NGN",
		"NOK",
		"NZD",
		"PEN",
		"SEK",
		"THB",
		"TWD",
		"USD",
	}
)


class FXMacroDataError(Exception):
	pass


def is_supported_pair(base: str, quote: str) -> bool:
	return bool(base and quote) and base != quote and {base, quote} <= SUPPORTED_CURRENCIES


def fetch_rate(
	base: str,
	quote: str,
	api_key: str,
	end_date: str | datetime.date | None = None,
	user_agent: str = "fxmacrodata-erpnext",
) -> tuple[str, float] | None:
	"""Return (date, rate) for the newest published rate on or before end_date.

	Returns None when the pair is not covered or no row has a value.
	Raises FXMacroDataError on HTTP or payload errors.
	"""
	base, quote = (base or "").upper(), (quote or "").upper()
	if not is_supported_pair(base, quote):
		return None
	if not api_key:
		raise FXMacroDataError("An FXMacroData API key is required for exchange rates")

	params = {"limit": 5}
	if end_date:
		params["end_date"] = str(end_date)[:10]

	try:
		response = requests.get(
			f"{API_BASE}/forex/{base}/{quote}",
			params=params,
			headers={"X-API-Key": api_key, "Accept": "application/json", "User-Agent": user_agent},
			timeout=TIMEOUT,
		)
	except requests.RequestException as e:
		raise FXMacroDataError(f"Request failed: {e.__class__.__name__}") from e

	if response.status_code != 200:
		raise FXMacroDataError(f"FXMacroData returned HTTP {response.status_code} for {base}/{quote}")

	try:
		payload = response.json()
	except ValueError as e:
		raise FXMacroDataError("FXMacroData returned a non-JSON response") from e

	return newest_rate(payload.get("data") if isinstance(payload, dict) else None)


def newest_rate(rows) -> tuple[str, float] | None:
	"""Pick the newest row with a usable value. Null values are skipped, never read as 0."""
	best = None
	for row in rows or []:
		if not isinstance(row, dict):
			continue
		date, val = row.get("date"), row.get("val")
		if not date or val is None or isinstance(val, bool):
			continue
		try:
			rate = float(val)
		except (TypeError, ValueError):
			continue
		if not math.isfinite(rate) or rate <= 0:
			continue
		date = str(date)[:10]
		if best is None or date > best[0]:
			best = (date, rate)
	return best
