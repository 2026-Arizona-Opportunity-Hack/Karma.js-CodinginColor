# Import formats (assumed)

**Every column layout below is assumed.** No real Coding in Color export was available this weekend, and neither Zeffy nor Benevity publishes a complete column list that we could read. The layouts are our best reading of what the vendors document; they are the contract between the fixture generator and the import adapters. When CIC sends real header rows, only the adapters and this file change (D-111). Fixtures in `fixtures/` are synthetic and never claim to be a real platform format.

## How sure are we?

| Fact | Status | Source |
|---|---|---|
| Zeffy has a dashboard export of **Payments** and **Itemized Payments**; column order described in prose: Amount, Payment method, Payment status, Payout date, Donation, Refunded amount, Discount, then buyer details | **Documented** (no literal headers) | [Zeffy: export payments](https://support.zeffy.com/export-or-download-all-payments-or-tickets-associated-with-a-specific-form-u0tyj) |
| Zeffy also exports Contacts, Payouts, Tax receipts and Transactions | Documented | [Zeffy: reports and exporting data](https://support.zeffy.com/reports-and-exporting-data-k15ip) |
| Zeffy API payments carry `currency` (`cad`/`usd`), `status` (`succeeded`/`failed`/`pending`), `type` (`online`/`manual`/`imported`), a contact and a campaign; a payment includes line items, refund details, buyer info and a tax receipt link | **Documented** (names of filters, not of every field) | [Zeffy: API](https://support.zeffy.com/get-started-with-the-zeffy-api-yourg) |
| Payment properties `id`, `currency`, `status`, `type`, a date-time, `lineItems`, `refund`, `taxReceiptUrl`; Contact properties `id`, `firstName`, `lastName`, `email`, `address`, `totalContributions`, `communicationPreferences` | **Third-party, unverified** (Zeffy's interactive reference at zeffy.com/api/docs did not render for us) | [apis.io: Zeffy Payments](https://apis.io/apis/zeffy/zeffy-payments-api/), [Contacts](https://apis.io/apis/zeffy/zeffy-contacts-api/) |
| Zeffy amount units (cents or dollars), date format, recurring flag, fees | **Not documented** | n/a |
| Benevity donation reports have a **Company** column (the corporate client the gift came from) and donation types **User Portfolio Donation**, **Match** and **Anonymous Donation**; Reporting Studio fields include `DR Code`, `DR Created Date`, `DR Payment Status` (for example Paid, Partial), `DR_Amount`, `DR_Amount_(With_Fees)`; Causes Portal disbursement reports give payment information for the transfer to the nonprofit's bank | **Secondary**: read from search-result summaries of Benevity's help articles; the articles themselves returned HTTP 403 to automated fetching, so the exact headers are unverified | [Understanding donor reports](https://causeshelp.benevity.org/hc/articles/360056082831-Understanding-donor-reports), [Reporting glossary](https://b-hive.benevity.com/hc/articles/360025663972-Benevity-Reporting-glossary), [Donation Explore glossary](https://b-hive.benevity.com/hc/en-us/articles/52828853696020-Reporting-Studio-Donation-Explore-glossary), [Causes Portal reporting](https://causeshelp.benevity.org/hc/en-ca/categories/35338784218260-Reporting) |
| Benevity literal column headers, donor opt-in fields, file type | **Not verified** | n/a |
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
| `Type` | no | `Individual`, `Organization` or `Funder` (default Individual) |
| `First name`, `Last name` | no | Used when present, otherwise split from `Name` |
| `Organization` | no | Employer, or the organization itself |
| `Email` | no | Primary email (contact detail) |
| `Phone` | no | Primary phone (contact detail) |
| `Notes` | no | Free text |

Identity: `sheet_row` is not a stable platform id, so the adapter records `email` and `name_org` identities; matching follows DED-3.

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

## 3. Benevity donation report (`source = benevity`), assumed

One row per donation line in a disbursement. Built from the documented Company column, donation types and report fields.

| Column | Required | Maps to |
|---|---|---|
| `Transaction ID` | yes | `source_txn_id` |
| `Disbursement ID` | no | kept in the import row's normalized data and the batch summary (counts per disbursement); not stored on the gift |
| `Donation Date` | yes | `gift_date` |
| `Amount` | yes | `gross_cents` |
| `Fee` | no | `fee_cents` (default 0) |
| `Currency` | no | must be USD when present |
| `Company` | no | `payer_name` (the employer) |
| `Donation Type` | no | `User Portfolio Donation`, `Match` or `Anonymous Donation`; `Match` sets `is_matching_gift` |
| `Cause` | no | `campaign_name`, mapped to a program |
| `Donor First Name`, `Donor Last Name`, `Email` | no | donor fields; Benevity can hide them, so empty means anonymous |
| `Benevity Donor ID` | no | `benevity_donor` identity when provided |

Rows typed `Anonymous Donation`, or with no donor fields, become unattributed gifts (DED-8). Employer match rows with a named employee link to that employee; the company is the payer.

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
