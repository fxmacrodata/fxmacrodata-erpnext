// Copyright (c) 2026, FXMacroData and contributors
// For license information, please see license.txt

frappe.ui.form.on("FXMacroData Settings", {
	refresh(frm) {
		if (frm.doc.enabled && !frm.is_dirty()) {
			frm.add_custom_button(__("Sync Now"), () => {
				frappe.call({
					method: "fxmacrodata_erpnext.exchange_rate.sync_now",
					freeze: true,
				});
			});
		}
	},
});
