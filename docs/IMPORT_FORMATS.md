# Import formats (assumed)

**File layouts below are only as certain as their labels say.** No real Coding in Color export was available this weekend. Zeffy's **API** (section 2b) and Benevity's **disbursement report columns** (section 3) are documented by the vendors; Zeffy's dashboard export, the exact header text and file type of Benevity's export, and our own spreadsheet layouts are assumed. The layouts are our best reading of what the vendors document; they are the contract between the fixture generator and the import adapters. When CIC sends real header rows, only the adapters and this file change (D-111). Fixtures in `fixtures/` are synthetic and never claim to be a real platform format.

## How sure are we?

| Fact | Status | Source |
|---|---|---|
| Zeffy has a dashboard export of **Payments** and **Itemized Payments**; column order described in prose: Amount, Payment method, Payment status, Payout date, Donation, Refunded amount, Discount, then buyer details | **Documented** (no literal headers) | [Zeffy: export payments](https://support.zeffy.com/export-or-download-all-payments-or-tickets-associated-with-a-specific-form-u0tyj) |
| Zeffy also exports Contacts, Payouts, Tax receipts and Transactions | Documented | [Zeffy: reports and exporting data](https://support.zeffy.com/reports-and-exporting-data-k15ip) |
| **Zeffy API v1** objects and fields: Payment, Contact, Campaign, User, error format, cursor pagination (`has_more`, `next_cursor`, `limit` up to 100), rate limits (100 per minute, 20 per second per organization), webhooks. Amounts are **integer cents**, dates are **Unix timestamps**, `currency` is `cad` or `usd` | **Documented**: Zeffy's own OpenAPI 3.1 document, copied from the interactive reference by a team member on 2026-11-14. We do not store the vendor's file in the repo | [Zeffy API reference](https://www.zeffy.com/api/docs) |
| Zeffy API payments carry `currency` (`cad`/`usd`), `status` (`succeeded`/`failed`/`pending`), `type` (`online`/`manual`/`imported`), `refund_status` (`none`/`partial`/`full`), a contact and a campaign | **Documented** | [Zeffy API reference](https://www.zeffy.com/api/docs), [Zeffy: API](https://support.zeffy.com/get-started-with-the-zeffy-api-yourg) |
| Zeffy dashboard CSV/XLSX column headers, amount units and date format in the file export | **Not documented** (only the prose order above) | n/a |
| Zeffy fees and tips as fields | **Not documented** in the Payment object (tips are mentioned for webhooks only) | n/a |
| **Benevity Causes Portal reporting glossary** (the nonprofit-side disbursement report): 36 columns in four groups, Disbursement and Organization Details (Nonprofit Name, Nonprofit ID, Disbursement ID, Disbursement Date, Bank Date, Bank Reference ID, Payment Method, Disbursement From (Grantor)), Project and Campaign Information (Company Name, Corporate / Peer Campaign, Project Name, Project ID, Project External ID, Grant Requirements), Donation and Fee Breakdown (Transaction ID, Donation Date, Donation Amount, Match Amount, Donation Currency, Foreign Exchange Rate, Cause Support Fee, Merchant Fee, Disbursement Check Fee, Fee Comment) and Donor Information (Donation Frequency, Donation Method, Donation Type, Donor First Name, Donor Last Name, Donor Email, Donor Address, Donor City, Original Donor State / Province, Donor Zip / Postal Code, Donor Country, Donor Comment). A company **code** such as A1234 in Company Name means the client chose to stay anonymous; donor details are visible only if the donor opted to share, except the postal code, which defaults to visible | **Documented**: Benevity's article, printed to PDF by a teammate on 2026-11-14 | [Reporting glossary](https://causeshelp.benevity.org/hc/en-us/articles/47969079553300-Reporting-glossary) |
| Benevity Reporting Studio fields (`Donation_Type`, `Donation_Reversal`, `DR_Amount`, and so on) and the Causes glossary of terms | **Documented but not used**: these describe the *corporate client's* reporting tool and Benevity's legal terms, not the file a nonprofit receives | [B-Hive Reporting glossary](https://b-hive.benevity.com/hc/en-us/articles/360025663972-Benevity-Reporting-glossary), [Donation Explore glossary](https://b-hive.benevity.com/hc/en-us/articles/52828853696020-Reporting-Studio-Donation-Explore-glossary) |
| Benevity exact header text, file type (CSV or XLSX), date format, reversal and negative-amount rows | **Not verified**: the glossary lists terms, not a sample file; the article "Why is there a negative amount on my report?" was not available | n/a |
| AZ Gives (runs on MightyCause) and United Way export formats | **Not documented** publicly; they use the generic template | [AZ Gives](https://azgives.org), [United Way](https://www.unitedway.org) |

**To close the gaps** (a human task, five minutes): ask CIC for one real header row from each of Zeffy, Benevity and the donor spreadsheet, or open the Benevity help articles above in a browser and copy the report glossary.

## Shared rules for every adapter

- Files: `.csv` (UTF-8, with or without BOM; comma delimited) or `.xlsx` (first sheet). Maximum 5 MB, checked by extension and content (ING-1).
- Header matching: case-insensitive, trimmed, spaces, underscores and hyphens treated alike (`Donation Date` = `donation_date`). Extra columns are ignored; a missing **required** column rejects the file with a message naming it.
- Normalization (DATA_MODEL 3.2): money to integer cents, rounded half up, `$1,234.50` and `1234.5` accepted, negatives rejected; dates ISO, `MM/DD/YYYY`, `M/D/YY` or Excel serial; emails lower-cased; phones to E.164 when parseable.
- Only USD gifts are accepted; any other currency is an `invalid` row with a reason (ING-6).
- A row we cannot use is never dropped: it is listed as `invalid` with a reason, and the preview totals must reconcile (ING-5).

## 1. CIC donor spreadsheet (`source = spreadsheet`)

One row per donor, people, organizations and funders. Creates or updates **donors only**; it never creates gifts (ING-8).

| Column | Required | Meaning |
|---|---|---|
| `Name` | yes | Full name, or organization name for organizations and funders |
| `Contact ID` | no | Existing Zeffy contact identity, when known; never synthesized from a name |
| `Type` | no | `Individual`, `Organization` or `Funder` (default Individual) |
| `First name`, `Last name` | no | Used when present, otherwise split from `Name` |
| `Organization` | no | Employer, or the organization itself |
| `Email` | no | Primary email (contact detail) |
| `Phone` | no | Primary phone (contact detail) |
| `Notes` | no | Free text |

Identity: `sheet_row` is not a stable platform id, so the adapter records `email` and `name_org` identities; matching follows DED-3.

An existing donor matched by Contact ID, a remembered review or email without a
name conflict is never silently overwritten. Different name, organization, email,
phone and notes values appear as donor updates in preview. The uploader chooses
each field in a review dialog; every checkbox starts unchecked. Commit applies
only selected fields and never changes ownership. Old values are hidden when
the uploader cannot see that donor's contacts (DON-3). Missing optional columns
preserve existing values; an explicitly empty supplied cell proposes clearing
the field. Repeated rows must agree on each supplied field. Name alone never
matches an existing donor. These donor-only rows add no gifts or cents, and the
`donor_updates` row class participates in summary reconciliation (D-130).

## 2. Zeffy payments export (`source = zeffy`), assumed

One row per payment. Built from the documented export order (Amount, Payment method, Payment status, Payout date, Donation, Refunded amount, Discount, buyer details) and the API's documented status, type, contact and campaign.

| Column | Required | Maps to |
|---|---|---|
| `Payment ID` | yes | `source_txn_id` (makes `row_key` stable, DATA_MODEL 3.1) |
| `Date` | yes | `gift_date` |
| `Amount` | yes | `gross_cents` (dollars with decimals assumed) |
| `Currency` | no | must be `USD`/`usd` when present |
| `Payment status` | no | only `succeeded` rows become gifts; `failed` and `pending` rows are `invalid` ("payment not succeeded") |
| `Refunded amount` | no | any amount above zero makes the row `invalid` ("refunded"; refunds are out of scope for the MVP) |
| `Campaign` | no | `campaign_name`, mapped to a program through `source_program_map` (ING-7) |
| `Contact ID` | no | `zeffy_contact` identity |
| `First name`, `Last name`, `Email`, `Phone` | no | donor fields; a row with no name and no email is an anonymous gift |

Fee is 0 (Zeffy charges nonprofits no platform fee; optional donor tips are not modelled). Monthly recurring gifts are simply repeated payments with distinct `Payment ID`s.

## 2b. Zeffy API payments (documented), for the later API pull job

Not used by the MVP importer, which reads files. Recorded now because the field names are documented and the pull job (SRS 3.2, item 3) is the planned replacement for manual Zeffy uploads. Source: [Zeffy API reference](https://www.zeffy.com/api/docs). `GET https://api.zeffy.com/api/v1/payments` with `Authorization: Bearer <key>`; cursor pagination (`limit` 1 to 100, `starting_after` = previous `next_cursor`); `created[gte]`/`created[lte]` filter by Unix time.

| Zeffy field | Type and units | Maps to |
|---|---|---|
| `id` | UUID | `source_txn_id` |
| `created` | Unix seconds | `gift_date`, converted to a date in America/Phoenix |
| `amount` | **integer cents** | `gross_cents` (no parsing needed) |
| `eligible_amount` | integer cents | not stored |
| `currency` | `cad` or `usd` | only `usd` becomes a gift; `cad` is `invalid` ("not USD") |
| `status` | `succeeded`, `failed`, `pending` | only `succeeded`; others are `invalid` ("payment not succeeded") |
| `refund_status`, `refunds[]` | `none`, `partial`, `full` | anything other than `none` is `invalid` ("refunded") for the MVP |
| `type` | `online`, `manual`, `imported` | kept as information; all three count as gifts |
| `campaign_id`, `description` | UUID, campaign title | `campaign_name` = `description`, mapped to a program (ING-7) |
| `contact` | UUID | `zeffy_contact` identity |
| `buyer.first_name`, `buyer.last_name`, `buyer.email` | strings or null | donor fields; all three null means an anonymous gift |
| `buyer.is_corporate`, `buyer.company_name` | boolean, string or null | `is_corporate` true makes the donor an organization named `company_name`; otherwise `company_name` is the employer for matching |
| `recurring.is_recurring`, `recurring.interval` | boolean, string | informational |
| `fund`, `receipt_url`, `items[]`, `buyer_questions[]` | various | not stored |

Contacts (`GET /v1/contacts`) add `phone_number` (E.164 in their examples) and `address`, which we do not store (NFR-3). Not documented in the Payment object: platform fees and tips, so `fee_cents` stays 0.

Operational notes from the reference: 100 requests per minute and 20 per second per organization (a pull job must back off on `429` using `Retry-After`); an API key is created by the organization owner under Settings → Integrations; the same key can also **write** (create and delete payments and contacts), so the pull job must only ever call `GET` endpoints and the key belongs in an environment variable, never in git (D-113, least privilege). The fixtures in `fixtures/` imitate the dashboard-style file in section 2, not this JSON; an API adapter needs its own fixtures.

## 3. Benevity disbursement report (`source = benevity`)

Column names are **documented** (Causes Portal Reporting glossary, see the table above); the header text in a real file, its file type and the date format are not verified. One row per donation (`Transaction ID`) inside a disbursement (`Disbursement ID`). The fixture uses all 36 names so the adapter's header matching is exercised on a realistic, wide file. Columns not listed below are ignored.

| Column | Required | Maps to |
|---|---|---|
| `Transaction ID` | yes | `source_txn_id` for the donation gift; the match gift uses `<id>:match` so both keep a stable `row_key` |
| `Donation Date` | yes | `gift_date` (the date the gift was processed or submitted for a match) |
| `Donation Amount` | yes | `gross_cents`: the gross amount contributed by the donor |
| `Match Amount` | no | when above zero, a **second gift** on the same row: `is_matching_gift = true`, `payer_name` = company, source transaction ID suffixed `:match` before row-key hashing. Retain the donation's donor linkage for traceability; the match is org revenue, excluded from employee giving (D-127) |
| `Donation Currency` | yes | must be `USD`; anything else is `invalid` ("not USD"). `Foreign Exchange Rate` is ignored |
| `Cause Support Fee`, `Merchant Fee` | no | summed into `fee_cents` of the donation gift (`net = gross - fees`); `Disbursement Check Fee` is per disbursement and not stored |
| `Company Name` | no | `payer_name` and the employer used for name-and-employer matching. A code of the form `A1234` means the company is anonymous: kept as the payer text, not used for matching |
| `Project Name` | no | `campaign_name`, mapped to a program (ING-7); `Corporate / Peer Campaign` is ignored |
| `Disbursement ID`, `Disbursement Date` | no | kept in the import row's normalized data and the batch summary (counts per disbursement); not stored on the gift |
| `Donor First Name`, `Donor Last Name`, `Donor Email` | no | donor fields. They are present only if the donor opted to share: **all three empty means an anonymous gift** (DED-8) |
| `Donation Frequency`, `Donation Method`, `Donation Type` | no | informational (`One-Time` or `Recurring`; payroll, card or match request) |
| `Donor Zip / Postal Code` and other address fields | no | not stored (NFR-3); the postal code is visible even when everything else is hidden, so it never identifies a donor |

Rules that follow from the glossary:

- **There is no donor id** in the report, so Benevity donors are recognised by email (DED-3), then by name plus employer (a review item). The `benevity_donor` identity kind in the schema stays unused until a real file shows an id.
- A **match** is employer money. Per CIC's decision D-127 (superseding employee credit in D-125), the employee is credited only for `Donation Amount`. Keep the separate match gift and donor relationship for traceability, but exclude it from donor totals, lifetime giving, retention classes and every amount pre-filled in message templates. Include it in org revenue. If the donor is hidden, both gifts are unattributed. Board members use donation-only data on the dashboard or reminders and edit message amounts by hand; no automatic donor send is introduced.
- **Preview accounting:** classification counts are physical source rows. Each class reports `donation_cents`, `match_cents`, combined `cents`, and a separate `gift_count`. `anonymous` is a subset of new rows. Reconcile source rows across new/already-imported/review/invalid, and reconcile donation plus match cents across those same classes. Invalid rows contribute no accepted gifts or cents. The Benevity fixture remains 80 source rows and 91 valid gifts, including matches. Fees affect net revenue, not this gross-cents reconciliation.
- **Anonymous means the donor opted out.** Benevity hides name and email only when the donor chooses to, so an anonymous Benevity gift is never attached to a donor record (D-131): the attribute action refuses it with 409. It still counts in org revenue and reports.
- **Negative amounts** (the glossary links an article about them, which we could not read) are probably reversals. The importer lists them as `invalid` ("non-positive amount") so a person can look; reversal handling is not built.
- `Donation Currency` can differ from the disbursement currency; only USD rows are imported.

## 4. Generic gifts template (`source = generic`)

Used for AZ Gives, United Way and anything else. This one is **ours**, so it is not assumed: it is the format we ask CIC to fill when a platform has no adapter, and the file we publish as a downloadable template.

| Column | Required | Meaning |
|---|---|---|
| `Date` | yes | gift date |
| `Amount` | yes | dollars |
| `Platform` | yes | `azgives`, `united_way` or `other`; stored in `source_platform` |
| `Donor name` | no | person or organization |
| `Email`, `Phone` | no | contact details |
| `Organization` | no | employer or giving organization |
| `Campaign` | no | mapped to a program |
| `Transaction ID` | no | when present it makes the `row_key` stable |
| `Fee` | no | default 0 |
| `Notes` | no | free text, not stored on the gift |

Known limit (DATA_MODEL 3.1): without a `Transaction ID`, two identical gifts split across different files can be under-counted, because the `occurrence` counter only sees one file. Ask for transaction ids when a platform has them.
