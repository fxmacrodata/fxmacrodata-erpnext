## FXMacroData for ERPNext

A Frappe app that lets ERPNext pull exchange rates from
[FXMacroData](https://fxmacrodata.com/?utm_source=github&utm_medium=referral&utm_campaign=fxmacrodata-erpnext&utm_content=readme).
The API key is sent in an `X-API-Key` header, so it never ends up in a URL or
in ERPNext's Currency Exchange Settings request parameters.

FXMacroData is a commercial API. Exchange rates need a paid key; plans are on
the [subscribe page](https://fxmacrodata.com/subscribe?utm_source=github&utm_medium=referral&utm_campaign=fxmacrodata-erpnext&utm_content=readme).

### How it works

ERPNext looks for a rate in two places: the newest matching **Currency
Exchange** record, and then the provider set in **Currency Exchange
Settings**. This app adds a step in front of that.

When a transaction form asks for a rate, the app fetches the latest published
rate for the pair on or before the transaction date and saves it as a normal
Currency Exchange record (dated with the rate's own date, for buying and
selling). It then hands the request back to ERPNext's own
`get_exchange_rate`, which finds that record. Stale-rate settings, pegged
currencies and buying/selling filters behave exactly as they did before.

The app never overwrites a Currency Exchange record that already exists for
that pair and date, including ones you enter by hand. If the integration is
disabled, the pair isn't covered, or the API call fails for any reason, ERPNext
falls back to its own provider as if the app weren't installed.

The hook used is `override_whitelisted_methods` on
`erpnext.setup.utils.get_exchange_rate`, which covers rates fetched from the
desk (sales and purchase documents, Payment Entry, Dunning, Opportunity,
Timesheet).
Server-side code that reads rates directly, such as reports and Exchange Rate
Revaluation, uses Currency Exchange records, so list the pairs you need under
**Scheduled Sync** and the app keeps those records current every six hours.

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/fxmacrodata/fxmacrodata-erpnext
bench --site your-site install-app fxmacrodata_erpnext
```

Tested on ERPNext v15 and v16.

### Setup

Open **FXMacroData Settings** and fill in:

| Field | |
| --- | --- |
| Enabled | Turns the integration on |
| API Key | Your FXMacroData key (stored as a password field) |
| Cache Minutes | How long a fetched rate, or a miss, is reused before the API is asked again. Default 60 |
| Currency Pairs | Optional. Pairs to refresh on a schedule |

Saving with Enabled checked makes one test request to confirm the key works.
The **Sync Now** button runs the scheduled sync straight away.

Supported currencies: AUD, BRL, CAD, CHF, CNH, CNY, DKK, EUR, GBP, HUF, ILS,
JPY, KRW, MYR, NGN, NOK, NZD, PEN, SEK, THB, TWD, USD. Pairs outside that list
are passed straight to ERPNext without an API call.

Rates are daily reference rates from official sources. The request is
`GET /v1/forex/{base}/{quote}?limit=5&end_date=<transaction date>`, and the
newest row with a value is used; rows with a null value are skipped. See the
[API reference](https://fxmacrodata.com/documentation/reference?utm_source=github&utm_medium=referral&utm_campaign=fxmacrodata-erpnext&utm_content=readme)
for the response format.

### Tests

The HTTP client tests need no site:

```bash
python -m unittest fxmacrodata_erpnext.tests.test_client
```

The rest run against a test site with ERPNext installed. All HTTP calls are
mocked:

```bash
bench --site test_site set-config allow_tests true
bench --site test_site run-tests --app fxmacrodata_erpnext
```

### License

MIT
