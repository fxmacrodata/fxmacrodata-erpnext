app_name = "fxmacrodata_erpnext"
app_title = "FXMacroData for ERPNext"
app_publisher = "FXMacroData"
app_description = "Exchange rates for ERPNext from FXMacroData"
app_email = "info@fxmacrodata.com"
app_license = "mit"

required_apps = ["erpnext"]

# Rates requested from transaction forms go through this app first. When the
# integration is disabled, or anything fails, ERPNext's own lookup runs as usual.
override_whitelisted_methods = {
	"erpnext.setup.utils.get_exchange_rate": "fxmacrodata_erpnext.exchange_rate.get_exchange_rate",
}

# Keep Currency Exchange records current for the pairs listed in
# FXMacroData Settings, so server-side lookups see them too.
scheduler_events = {
	"cron": {
		"20 */6 * * *": ["fxmacrodata_erpnext.exchange_rate.sync_configured_pairs"],
	},
}
