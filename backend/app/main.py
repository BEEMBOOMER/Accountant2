from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .importers import detect_bank
from .models import AccountCreate, CategoryCreate, CategoryUpdate, RuleCreate, RuleUpdate
from .services import BankingService, NotFoundError, ValidationError


service = BankingService()
app = FastAPI(title="TheAccountant2", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


def _error(exc: Exception):
    if isinstance(exc, NotFoundError):
        raise HTTPException(404, str(exc))
    if isinstance(exc, (ValidationError, ValueError)):
        raise HTTPException(400, str(exc))
    raise exc


def account_json(account):
    return account.model_dump()


def category_json(category):
    return category.model_dump()


def rule_json(rule, categories=None):
    categories = categories or []
    category_id = next((c.id for c in categories if c.name == rule.category), None)
    return {"id": rule.id, "kind": "merchant" if rule.match_type == "exact" else "keyword", "match_type": rule.match_type, "pattern": rule.pattern, "category": rule.category, "category_id": category_id, "enabled": rule.enabled}


def transaction_kind(tx) -> str:
    # A suspected pair remains reviewable through the transfer filter even
    # though its cashflow remains in income/expenditure until confirmed.
    if tx.transfer_status == "suspected":
        return "transfer"
    return service.classification(tx)


def tx_json(tx, categories=None):
    categories = categories or []
    category_id = next((c.id for c in categories if c.name == tx.category), None)
    payload = tx.model_dump(mode="json")
    payload.update({"id": tx.transaction_id, "category_id": category_id, "internal_transfer": tx.internal_transfer, "transfer_status": tx.transfer_status, "amount": float(tx.amount), "balance": float(tx.balance) if tx.balance is not None else None, "type": transaction_kind(tx)})
    return payload


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok", "workbook": str(service.store.path)}


@app.get("/api/accounts")
def accounts():
    return [account_json(a) for a in service.state()[3]]


@app.post("/api/accounts")
async def create_account(request: Request):
    try:
        account = await request.json()
        return account_json(service.create_account(AccountCreate.model_validate(account).model_dump()))
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.patch("/api/accounts/{account_id}")
@app.put("/api/accounts/{account_id}")
async def update_account(account_id: str, request: Request):
    try:
        return account_json(service.update_account(account_id, await request.json()))
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str):
    try:
        service.delete_account(account_id); return {"deleted": True}
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.get("/api/categories")
def categories():
    txs, cats, *_ = service.state()
    counts = {c.name: 0 for c in cats}
    for tx in txs:
        if tx.transfer_status == "confirmed":
            continue
        counts[tx.category] = counts.get(tx.category, 0) + 1
    return [category_json(c) | {"transaction_count": counts.get(c.name, 0)} for c in cats]


@app.post("/api/categories")
async def create_category(request: Request):
    try:
        data = CategoryCreate.model_validate(await request.json())
        return category_json(service.create_category(data.name))
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.patch("/api/categories/{category_id}")
@app.put("/api/categories/{category_id}")
async def update_category(category_id: str, request: Request):
    try:
        data = CategoryUpdate.model_validate(await request.json())
        return category_json(service.update_category(category_id, data.model_dump(exclude_unset=True)))
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.delete("/api/categories/{category_id}")
async def delete_category(category_id: str, request: Request, replacement_category_id: str | None = Query(default=None)):
    try:
        # The UI sends replacement_category_id in JSON; query syntax remains supported for API clients.
        if not replacement_category_id:
            try:
                replacement_category_id = (await request.json()).get("replacement_category_id")
            except Exception:
                replacement_category_id = None
        service.delete_category(category_id, replacement_category_id); return {"deleted": True}
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.get("/api/rules")
def rules():
    txs, cats, rules_data, *_ = service.state()
    return [rule_json(r, cats) for r in rules_data]


@app.post("/api/rules")
async def create_rule(request: Request):
    try:
        raw = await request.json()
        data = {"match_type": "exact" if raw.get("kind") == "merchant" else raw.get("match_type", raw.get("kind", "keyword")), "pattern": raw.get("pattern", ""), "category": raw.get("category", "")}
        if raw.get("category_id"):
            data["category"] = next((c.name for c in service.state()[1] if c.id == raw["category_id"]), data["category"])
        data["enabled"] = raw.get("enabled", True)
        return rule_json(service.create_rule(RuleCreate.model_validate(data).model_dump()), service.state()[1])
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.patch("/api/rules/{rule_id}")
@app.put("/api/rules/{rule_id}")
async def update_rule(rule_id: str, request: Request):
    try:
        raw = await request.json(); data = dict(raw)
        if "kind" in data: data["match_type"] = "exact" if data.pop("kind") == "merchant" else "keyword"
        if "category_id" in data:
            category_id = data.pop("category_id"); data["category"] = next((c.name for c in service.state()[1] if c.id == category_id), "")
        return rule_json(service.update_rule(rule_id, RuleUpdate.model_validate(data).model_dump(exclude_unset=True)), service.state()[1])
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: str):
    try:
        service.delete_rule(rule_id); return {"deleted": True}
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


async def _import_payload(request: Request) -> tuple[str, str | None, str | None, str]:
    max_upload_bytes = 10 * 1024 * 1024
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
        except AssertionError as exc:
            raise HTTPException(400, "multipart uploads require python-multipart") from exc
        upload = form.get("file") or form.get("csv")
        if upload is None: raise HTTPException(400, "file is required")
        raw = await upload.read(max_upload_bytes + 1)
        if len(raw) > max_upload_bytes:
            raise HTTPException(413, "CSV files must be 10 MB or smaller")
        source_file = getattr(upload, "filename", None) or "upload.csv"
        bank = str(form.get("bank") or "") or None
        account = str(form.get("account") or form.get("account_id") or "") or None
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "CSV files must use UTF-8 encoding") from exc
        return text, bank, account, source_file
    payload = await request.json()
    text = payload.get("csv_text") or payload.get("text") or ""
    if not text and payload.get("rows") is not None: text = "\n".join(payload["rows"])
    return text, str(payload.get("bank") or "") or None, payload.get("account") or payload.get("account_id"), str(payload.get("source_file") or "upload.csv")


@app.post("/api/imports/detect")
async def import_detect(request: Request):
    text, _, _, _ = await _import_payload(request)
    try:
        bank = detect_bank(text)
        return {"bank": bank, "account_required": bank == "CommBank"}
    except ValueError as exc:
        _error(exc)


@app.post("/api/imports/preview")
async def import_preview(request: Request):
    text, bank, account, source_file = await _import_payload(request)
    try:
        detected_bank = detect_bank(text)
        txs, errors, categories_for, duplicates, suspected, transfer_groups, review = service.preview_csv(text, bank=bank, account=account, source_file=source_file)
        cats = service.state()[1]
        structured_errors = [{"row": int(item.split(":", 1)[0].split()[-1]) if item.startswith("row ") and item.split(":", 1)[0].split()[-1].isdigit() else None, "message": item} for item in errors]
        return {"bank": detected_bank, "account": account, "source_file": source_file, "processed": len(txs) + len(errors), "inserted": len(txs) - duplicates, "new_transactions": len(txs) - duplicates, "duplicates": duplicates, "suspected_transfers": suspected, "transfers": transfer_groups, "review_required": review, "latest_month": max((tx.date for tx in txs), default=None).strftime("%Y-%m") if txs else None, "rows": [tx_json(tx, cats) | {"suggested_category": category} for tx, category in zip(txs, categories_for)], "errors": structured_errors, "rejected": len(errors)}
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.post("/api/imports")
async def import_transactions(request: Request):
    text, bank, account, source_file = await _import_payload(request)
    try:
        result = service.import_csv(text, bank=bank, account=account, source_file=source_file).model_dump(mode="json")
        result["transfers"] = result.get("transfers", 0)
        result["errors"] = [{"row": int(item.split(":", 1)[0].split()[-1]) if item.startswith("row ") and item.split(":", 1)[0].split()[-1].isdigit() else None, "message": item} for item in result.get("errors", [])]
        return result
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.get("/api/transactions")
def transactions(month: str | None = None, bank: str | None = None, category: str | None = None, category_id: str | None = None, transaction_type: str | None = None, metric: str | None = None, review_required: bool | None = None, search: str | None = None, sort_by: str = "date", sort_order: str = "desc", limit: int = Query(default=1000, ge=1, le=10000), offset: int = Query(default=0, ge=0)):
    txs, cats, *_ = service.state()
    if metric:
        try:
            txs = service.metric_transactions(metric, month)
        except ValidationError as exc:
            _error(exc)
    category_from_id = next((c.name for c in cats if c.id == category_id), None) if category_id else None
    filtered = [t for t in txs if (not month or t.date.strftime("%Y-%m") == month) and (not bank or t.bank.lower() == bank.lower()) and (not category and not category_from_id or t.category == (category_from_id or category)) and (review_required is None or t.review_required == review_required) and (not transaction_type or transaction_kind(t) == transaction_type or (transaction_type == "transfer" and t.internal_transfer)) and (not search or search.lower() in t.original_description.lower())]
    key_map = {"date": lambda t: t.date, "amount": lambda t: t.amount, "description": lambda t: t.original_description.lower(), "category": lambda t: t.category.lower(), "bank": lambda t: t.bank.lower()}
    filtered.sort(key=key_map.get(sort_by, key_map["date"]), reverse=sort_order.lower() != "asc")
    return {"transactions": [tx_json(t, cats) for t in filtered[offset:offset + limit]], "total": len(filtered)}


@app.patch("/api/transactions/{transaction_id}/category")
async def set_transaction_category(transaction_id: str, request: Request):
    try:
        raw = await request.json(); category = raw.get("category")
        if raw.get("category_id"):
            category = next((c.name for c in service.state()[1] if c.id == raw["category_id"]), category)
        return tx_json(service.set_category(transaction_id, category, bool(raw.get("create_rule") or raw.get("create_exact_rule"))), service.state()[1])
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.patch("/api/transactions/{transaction_id}/transfer")
async def set_transaction_transfer(transaction_id: str, request: Request):
    try:
        raw = await request.json(); return tx_json(service.set_transfer(transaction_id, raw.get("status", "")), service.state()[1])
    except (ValidationError, NotFoundError) as exc: _error(exc)


@app.patch("/api/transactions/{transaction_id}/classification")
async def set_transaction_classification(transaction_id: str, request: Request):
    try:
        raw = await request.json()
        category = raw.get("category")
        if raw.get("category_id"):
            category = next((c.name for c in service.state()[1] if c.id == raw["category_id"]), None)
            if category is None:
                raise ValidationError("unknown category")
        return tx_json(service.set_classification(transaction_id, raw.get("classification", ""), category), service.state()[1])
    except (ValidationError, NotFoundError, ValueError) as exc: _error(exc)


@app.get("/api/analytics/months")
def analytics_months():
    months = service.available_months()
    return {"months": months, "latest": months[0] if months else None}


@app.get("/api/analytics")
def analytics(month: str | None = None):
    result = service.analytics(month)
    for key in ("income", "expenditure", "net_cashflow", "savings", "investments"):
        result[key] = float(result[key])
    for key in ("spending_by_category", "top_categories", "top_expenses"):
        for item in result[key]:
            item["amount"] = float(item["amount"])
    return result


@app.get("/api/export")
def export_workbook():
    service.store.ensure()
    return FileResponse(service.store.path, filename="banking_master.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _spa_page():
    index = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
    if not index.exists():
        raise HTTPException(404, "frontend build not found")
    return FileResponse(index)


@app.get("/dashboard", include_in_schema=False)
@app.get("/transactions", include_in_schema=False)
@app.get("/import", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
def spa_deep_links():
    return _spa_page()


# The static mount comes after all /api routes, so it cannot shadow the API.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
