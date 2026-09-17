# AGENTS.md

## Project

Build a localhost personal banking dashboard.

Read `SPEC.md` before making changes.

AI is used only to build the application. The finished application must use no AI, external APIs, cloud services, or internet-dependent financial logic.

## Agent Model

Use GPT-5.6 Sol as the orchestrator.

Sol should:

* plan the work
* define architecture
* delegate bounded implementation tasks to Luna
* review subagent changes
* run tests
* integrate the final system

Use Luna for isolated coding, testing, UI, refactoring, and debugging tasks.

Sol owns all final architectural and financial-logic decisions.

## Source of Truth

`data/banking_master.xlsx` is the persistent data store.

Do not introduce another database unless explicitly requested.

The application must read from and write to this workbook.

## Core Rules

* Financial calculations must be deterministic.
* Internal account transfers are not income or expenditure.
* Savings transfers must be tracked separately.
* Re-importing the same or overlapping CSVs must not create duplicates.
* Preserve original bank transaction descriptions.
* Never silently delete financial data.
* Keep bank-specific CSV parsing isolated.
* Do not hard-code sample CSV structure without inspecting `LearningMaterial/`.

## Categorisation

Use local deterministic rules only.

Priority:

1. exact merchant rule
2. keyword/pattern rule
3. Miscellaneous / manual review

Manual category changes must persist.

Users must be able to add, rename, and manage categories.

## Engineering

Prefer:

* simple modules
* clear interfaces
* type hints
* useful errors
* reusable components
* testable financial logic

Avoid unnecessary abstraction.

## Testing

Tests must cover:

* both bank importers
* duplicate imports
* overlapping date ranges
* transaction fingerprints
* transfer detection
* savings detection
* categorisation
* monthly analytics
* Excel read/write integrity

Financial correctness has priority over UI polish.

## Development Order

1. inspect sample CSVs
2. define canonical transaction model
3. define workbook schema
4. build both importers
5. implement deduplication
6. implement transfer/savings detection
7. implement categorisation
8. implement analytics
9. implement Excel persistence
10. build backend
11. build frontend
12. integration testing
13. UI polish

## Delegation

Delegated tasks must specify:

* objective
* files to modify
* interfaces
* constraints
* acceptance criteria

Subagents should make narrowly scoped changes.

Sol must review all delegated work before integration.
