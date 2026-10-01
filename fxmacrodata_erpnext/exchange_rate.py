"""Supply ERPNext exchange rates from FXMacroData.

ERPNext resolves a rate by reading the newest matching Currency Exchange record
and only calls its configured provider when none is found. This app writes the
FXMacroData rate into a Currency Exchange record first, then hands the call
back to ERPNext, so stale-rate rules, pegged currencies and buying/selling
filters all keep working as before. Any failure falls through to ERPNext's own
behaviour.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

import fxmacrodata_erpnext
from fxmacrodata_erpnext.client import FXMacroDataError, fetch_rate, is_supported_pair

SETTINGS_DOCTYPE = "FXMacroData Settings"
CACHE_PREFIX = "fxmacrodata_erpnext:rate"
NO_RATE = "none"


@frappe.whitelist()
def get_exchange_rate(
	from_currency: str,
	to_currency: str,
	transaction_date: str | None = None,
	args: str | None = None,
):
	"""Drop-in replacement for erpnext.setup.utils.get_exchange_rate (wired in hooks.py)."""
	from erpnext.setup.utils import get_exchange_rate as erpnext_get_exchange_rate

	try:
		ensure_rate(from_currency, to_currency, transaction_date)
	except Exception:
		frappe.log_error(title="FXMacroData exchange rate", message=frappe.get_traceback())

	return erpnext_get_exchange_rate(from_currency, to_currency, transaction_date, args)


def get_settings():
	"""Return (api_key, cache_minutes) when the integration is enabled, else None."""
	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	if not cint(settings.enabled):
		return None
	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		return None
	return api_key, max(cint(settings.cache_minutes), 0)


def ensure_rate(from_currency, to_currency, transaction_date=None):
	"""Make sure a Currency Exchange record from FXMacroData exists for the pair.

	Returns the name of the record that was created, or None when nothing was
	written (disabled, unsupported pair, record already there, no rate).
	"""
	if not is_supported_pair(from_currency, to_currency):
		return None

	settings = get_settings()
	if not settings:
		return None
	api_key, cache_minutes = settings

	end_date = min(getdate(transaction_date or nowdate()), getdate(nowdate()))
	if record_exists(from_currency, to_currency, end_date):
		return None

	result = get_rate(from_currency, to_currency, end_date, api_key, cache_minutes)
	if not result:
		return None

	rate_date, rate = result
	if record_exists(from_currency, to_currency, rate_date):
		return None
	return make_currency_exchange(from_currency, to_currency, rate_date, rate)


def get_rate(from_currency, to_currency, end_date, api_key, cache_minutes):
	"""Fetch a rate, cached for cache_minutes. Misses and errors are cached too."""
	key = f"{CACHE_PREFIX}:{from_currency}:{to_currency}:{end_date}"
	cache = frappe.cache()
	if cache_minutes:
		cached = cache.get_value(key, expires=True)
		if cached == NO_RATE:
			return None
		if cached:
			return tuple(cached)

	try:
		result = fetch_rate(
			from_currency,
			to_currency,
			api_key,
			end_date=end_date,
			user_agent=f"fxmacrodata-erpnext/{fxmacrodata_erpnext.__version__}",
		)
	except FXMacroDataError as e:
		frappe.log_error(title="FXMacroData exchange rate", message=str(e))
		result = None

	if cache_minutes:
		cache.set_value(key, list(result) if result else NO_RATE, expires_in_sec=cache_minutes * 60)
	return result


def record_exists(from_currency, to_currency, date):
	return frappe.db.exists(
		"Currency Exchange",
		{"from_currency": from_currency, "to_currency": to_currency, "date": getdate(date)},
	)


def make_currency_exchange(from_currency, to_currency, date, rate):
	doc = frappe.get_doc(
		{
			"doctype": "Currency Exchange",
			"date": getdate(date),
			"from_currency": from_currency,
			"to_currency": to_currency,
			"exchange_rate": rate,
			"for_buying": 1,
			"for_selling": 1,
		}
	)
	# The user asking for a rate on a transaction may not be allowed to create
	# Currency Exchange records themselves.
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# Another request wrote the same record first.
		return None
	return doc.name


def sync_configured_pairs():
	"""Scheduled job: refresh today's rate for every pair listed in the settings."""
	if not get_settings():
		return []

	created = []
	for row in frappe.get_cached_doc(SETTINGS_DOCTYPE).get("currency_pairs") or []:
		try:
			if name := ensure_rate(row.from_currency, row.to_currency):
				created.append(name)
		except Exception:
			frappe.log_error(title="FXMacroData exchange rate sync", message=frappe.get_traceback())
	return created


@frappe.whitelist()
def sync_now():
	frappe.only_for("System Manager")
	created = sync_configured_pairs()
	if created:
		frappe.msgprint(_("Created {0} Currency Exchange record(s)").format(len(created)))
	else:
		frappe.msgprint(_("No new rates to add"))
	return created
