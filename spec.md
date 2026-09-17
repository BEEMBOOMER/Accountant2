# TheAccountant2 — Specification

## Overview

Build a localhost web application that imports transaction CSVs from two banks, stores processed data in an Excel workbook, and displays monthly financial analytics through a clean UI.

Sample CSVs are in `LearningMaterial/`.

The two banks may use different CSV formats. Inspect the samples and create separate bank importers.

The finished application must work locally with no AI, external APIs, or internet requirement.

## Core Architecture

Preferred stack:

* Python backend
* FastAPI
* React + TypeScript frontend
* `openpyxl` for Excel
* optional `pandas` for CSV processing

Data flow:

```text
Bank CSVs
   ↓
Bank-specific importers
   ↓
Canonical transactions
   ↓
Deduplication
   ↓
Transfer detection
   ↓
Categorisation
   ↓
banking_master.xlsx
   ↓
Analytics
   ↓
Localhost dashboard
```

## Excel

Persistent source of truth:

`data/banking_master.xlsx`

Recommended sheets:

* Transactions
* Categories
* Rules
* Accounts
* Import History
* Monthly Summary

The workbook must be readable and useful independently of the application.

## Transaction Model

Each transaction should include:

* transaction ID/fingerprint
* date
* bank
* account
* original description
* normalised description
* amount
* type
* category
* internal-transfer flag
* savings-transfer flag
* source file
* import timestamp

Use:

* positive amounts = money in
* negative amounts = money out

## Importing

The UI must allow CSV upload.

Import flow:

1. identify/select bank
2. parse CSV
3. validate
4. convert to canonical format
5. generate fingerprints
6. ignore existing transactions
7. detect transfers
8. categorise
9. update workbook
10. refresh dashboard

Show:

* rows processed
* new transactions
* duplicates ignored
* transfers found
* rows needing review
* errors

Overlapping CSV date ranges must not create duplicates.

## Transfers

Transfers between owned accounts must not count as income or expenditure.

Detection may use:

* known account identifiers
* transfer keywords
* equal opposite amounts
* close dates
* account configuration

Example:
`Transfer to xx2990 CommBank app`

Transfers into configured savings accounts must count toward monthly savings.

## Categories

Initial categories:

* Housing
* Groceries
* Eating Out
* Transport
* Phone & Subscriptions
* Health
* Education
* Social
* Roommate Settlement
* Miscellaneous

The user must be able to add, rename, and manage categories.

Categorisation must use deterministic merchant/keyword rules.

Example:

* WOOLWORTHS → Groceries
* TRANSLINK → Transport
* SPOTIFY → Phone & Subscriptions

Manual corrections should optionally create future rules.

## Dashboard

For a selected month, show:

* total income
* total expenditure
* amount moved into savings
* net cashflow
* spending by category
* top 3 spending categories
* top 3 individual expenses
* pie/donut chart of category spending

Internal transfers must be excluded from income and expenditure.

## Transactions Page

Provide:

* transaction table
* month filter
* bank filter
* category filter
* transaction-type filter
* search
* sorting
* manual category editing

## Accounts

Allow configuration of:

* bank
* account name
* account identifier
* savings-account status

Use these values for transfer detection.

## Export

The user must be able to download/export the current Excel workbook from the localhost UI.

## Safety

* Financial data stays local.
* Do not send transaction data externally.
* Do not use AI at runtime.
* Failed imports must not corrupt the workbook.
* Prefer safe temporary-write/replace behaviour.

## Completion Criteria

The project is complete when the user can:

* import both banks' CSVs
* re-import overlapping statements safely
* classify transactions
* identify internal transfers
* track savings
* view monthly analytics
* view category charts
* edit categories
* inspect transactions
* export the standalone Excel workbook
* use the application fully offline
