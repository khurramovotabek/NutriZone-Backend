"""
Fiscalization: sending a receipt to an OFD / "virtual kassa" provider and storing its fiscal sign + tax-site QR link.

Providers are adapters behind one interface. "none" keeps internal receipts only. "http" is a generic JSON adapter
for a virtual-kassa / OFD gateway: it POSTs the receipt in a neutral structure (requisites, terminal, items with MXIK
and package codes, VAT, payments) and reads {fiscal_number, fiscal_sign, qr_url} back -- the provider-specific field
mapping lives in `_payload` / `_parse`, so a concrete integration (e.g. a soliq.uz virtual kassa) is a small change.
The API token / password is entered on the dashboard and stored encrypted (Fernet, same key as payment secrets);
the server's FISCAL_API_TOKEN is the fallback. It is never shown back, logged or put into a receipt.
"""
from __future__ import annotations

import base64
from decimal import Decimal

import requests
from django.utils import timezone

from apps.receipts.infrastructure.models import Receipt, ReceiptSettings, ReceiptStatus

METHOD = {"cash": "cash", "card": "card", "uzcard": "card", "humo": "card", "payme": "online", "click": "online", "uzum": "online", "mixed": "mixed"}


class FiscalError(Exception):
    pass


def _tiyin(value) -> int:
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1")))


def _payload(r: Receipt, s: ReceiptSettings) -> dict:
    d = r.data
    rate = Decimal(s.vat_rate) if s.vat_payer else Decimal(0)
    items = []
    for i in d.get("items", []):
        total = Decimal(i["line_total"])
        vat = (total * rate / (Decimal(100) + rate)) if rate else Decimal(0)
        items.append({"name": i["name"][:128], "barcode": i.get("sku") or "", "mxik": i.get("mxik") or "", "package_code": i.get("package_code") or "",
                      "quantity": i["quantity"] * 1000, "price": _tiyin(i["unit_price"]), "total": _tiyin(total), "vat_percent": float(rate), "vat": _tiyin(vat)})
    return {
        "receipt_id": r.number, "type": "refund" if r.kind == "refund" else "sale", "terminal_id": s.fiscal_terminal_id, "tin": s.tin,
        "time": r.issued_at.isoformat(), "items": items, "total": _tiyin(r.total), "vat": _tiyin(r.vat_amount),
        "payments": [{"type": METHOD.get(p["method"], "other"), "amount": _tiyin(p["amount"])} for p in d.get("payments", [])],
        "customer_phone": r.customer_phone or None,
    }


EPOS_METHOD = {"cash": "cash", "card": "card", "uzcard": "card", "humo": "card", "payme": "qr", "click": "qr", "uzum": "qr", "mixed": "mixed"}


def _payload_epos(r: Receipt, s: ReceiptSettings) -> dict:
    """E-POS (api.epos.uz/v1/receipts): items in so'm with MXIK (IKPU), package code and VAT; payment + cashier.
    Shape from E-POS's public API page; check field names against docs.epos.uz once the integrator access is issued."""
    d = r.data
    rate = float(s.vat_rate) if s.vat_payer else 0
    pays = d.get("payments") or [{"method": r.payment_method or "cash", "amount": str(r.total)}]
    out = {
        "external_id": r.number, "type": "refund" if r.kind == "refund" else "sale", "cashier_id": s.fiscal_cashier_id or None,
        "terminal_id": s.fiscal_terminal_id or None, "tin": s.tin,
        "items": [{"name": i["name"][:128], "price": float(Decimal(i["unit_price"])), "qty": i["quantity"], "ikpu": i.get("mxik") or "",
                   "package_code": i.get("package_code") or "", "vat_percent": rate, "barcode": i.get("sku") or ""} for i in d.get("items", [])],
        "payment": {"method": EPOS_METHOD.get(pays[0]["method"], "cash"), "provider": pays[0]["method"] if EPOS_METHOD.get(pays[0]["method"]) == "qr" else None,
                    "amount": float(Decimal(str(r.total)))},
        "payments": [{"method": EPOS_METHOD.get(p["method"], "cash"), "amount": float(Decimal(str(p["amount"])))} for p in pays],
        "customer_phone": r.customer_phone or None,
    }
    if r.kind == "refund" and d.get("original_receipt"):
        out["original_receipt_id"] = d["original_receipt"]
    return out


def _parse(body: dict) -> dict:
    data = body.get("data") or body.get("result") or body.get("receipt") or body
    number = data.get("fiscal_number") or data.get("receipt_seq") or data.get("receipt_id") or data.get("number") or data.get("id")
    sign = data.get("fiscal_sign") or data.get("fiscalSign") or data.get("fiscal_mark") or data.get("sign")
    if not (number and sign):
        raise FiscalError(body.get("error") or body.get("message") or "Provayder fiskal belgini qaytarmadi")
    url = data.get("qr_url") or data.get("qr_code_url") or data.get("qrCodeUrl") or data.get("verification_url") or data.get("check_url") or data.get("url") or ""
    return {"number": str(number), "sign": str(sign), "url": url}


def auth_headers(s: ReceiptSettings) -> dict:
    secret = s.fiscal_secret
    if not secret:
        return {}
    if s.fiscal_auth == "basic":
        return {"Authorization": "Basic " + base64.b64encode(f"{s.fiscal_login}:{secret}".encode()).decode()}
    if s.fiscal_auth == "header":
        return {(s.fiscal_auth_header or "X-API-Key").strip(): secret}
    return {"Authorization": f"Bearer {secret}"}


def readiness(s: ReceiptSettings | None = None) -> list[tuple[str, bool, str]]:
    """(label, ok, hint) for each thing fiscalization needs -- shown on the settings page."""
    from apps.products.infrastructure.models import Product

    s = s or ReceiptSettings.get()
    published = Product.objects.filter(status="published")
    no_mxik = published.filter(models_q_empty("mxik_code")).count()
    no_package = published.filter(models_q_empty("package_code")).count()
    checks = [
        ("STIR (INN) / JShShIR", bool(s.tin), "Sotuvchi rekvizitlarida (YaTT yoki MChJ)"),
        ("Yuridik nom", bool(s.legal_name), "Sotuvchi rekvizitlarida"),
        ("Mahsulotlarda MXIK kodi", no_mxik == 0, f"{no_mxik} ta sotuvdagi mahsulotda MXIK yo'q" if no_mxik else "Hammasida bor"),
        ("Mahsulotlarda qadoq kodi", no_package == 0, f"{no_package} ta sotuvdagi mahsulotda qadoq kodi yo'q" if no_package else "Hammasida bor"),
    ]
    if s.payme_fiscal:
        from apps.payment.infrastructure.providers.registry import load

        payme = load("payme")
        checks.append(("Payme ulangan", payme.enabled and payme.configured, "To'lovlar → To'lov tizimlari → Payme (kalitlar)"))
    if s.fiscal_provider != "none":
        checks += [
            ("API manzili", bool(s.fiscal_endpoint), "Provayder bergan URL"),
            ("API kaliti / parol", bool(s.fiscal_secret), "Provayder bergan token yoki parol"),
            ("Terminal (kassa) ID", bool(s.fiscal_terminal_id), "Provayder / soliq bergan ID"),
        ]
        if s.fiscal_provider == "epos":
            checks.append(("Kassir ID", bool(s.fiscal_cashier_id), "E-POS kabinetidan"))
        if s.fiscal_auth == "basic":
            checks.append(("Login", bool(s.fiscal_login), "«Login + parol» turi uchun"))
    if not s.payme_fiscal and s.fiscal_provider == "none":
        checks.insert(0, ("Fiskal usul tanlangan", False, "«Payme orqali fiskal chek»ni yoqing yoki provayder tanlang"))
    return checks


def models_q_empty(field: str):
    from django.db.models import Q

    return Q(**{f"{field}__isnull": True}) | Q(**{field: ""})


def check_connection(s: ReceiptSettings | None = None) -> tuple[bool, str]:
    """Reach the provider without sending a receipt: is the URL up and is the key accepted? Saves the result."""
    s = s or ReceiptSettings.get()
    if not s.fiscal_endpoint:
        ok, text = False, "API manzili kiritilmagan."
    else:
        try:
            resp = requests.get(s.fiscal_endpoint, headers=auth_headers(s), timeout=min(s.fiscal_timeout or 20, 15), allow_redirects=False)
            code = resp.status_code
            if code in (401, 403):
                ok, text = False, f"Server javob berdi ({code}), lekin kalit qabul qilinmadi — token / login / parolni tekshiring."
            elif code >= 500:
                ok, text = False, f"Provayder serverida xato ({code}). Keyinroq qayta tekshiring."
            else:
                ok, text = True, f"Ulanish bor (HTTP {code}). Kalit rad etilmadi."
        except requests.RequestException as exc:
            ok, text = False, f"Serverga ulanib bo'lmadi: {type(exc).__name__}"
    ReceiptSettings.objects.filter(pk=s.pk).update(fiscal_checked_at=timezone.now(), fiscal_check_result=("✓ " if ok else "✗ ") + text[:250])
    return ok, text


def fiscalize(receipt: Receipt) -> Receipt:
    s = ReceiptSettings.get()
    if receipt.status == ReceiptStatus.FISCALIZED:
        return receipt
    if receipt.source == "online" and receipt.payment_method == "payme" and s.payme_fiscal:
        from apps.receipts.infrastructure.payme_fiscal import apply_to_receipt

        if apply_to_receipt(receipt.order_id):
            receipt.refresh_from_db()
            return receipt
        raise FiscalError("Bu buyurtma Payme orqali to'langan: soliq chekini Payme virtual kassasi chiqaradi (SetFiscalData hali kelmagan).")
    if s.fiscal_provider == "none":
        raise FiscalError("Fiskal provayder ulanmagan (Chek sozlamalari).")
    if not (s.fiscal_endpoint and s.fiscal_terminal_id and s.tin):
        raise FiscalError("Chek sozlamalarida API manzili, terminal ID va STIR to'ldirilishi kerak.")
    if not s.fiscal_secret:
        raise FiscalError("Chek sozlamalarida provayder API kaliti (token / parol) kiritilmagan.")
    missing = [i["name"] for i in receipt.data.get("items", []) if not i.get("mxik")]
    if missing:
        raise FiscalError("MXIK kodi yo'q: " + ", ".join(missing[:5]) + " (mahsulot kartasida to'ldiring).")
    Receipt.objects.filter(pk=receipt.pk).update(fiscal_attempts=receipt.fiscal_attempts + 1, status=ReceiptStatus.FISCAL_PENDING)
    try:
        body_out = _payload_epos(receipt, s) if s.fiscal_provider == "epos" else _payload(receipt, s)
        resp = requests.post(s.fiscal_endpoint, json=body_out, timeout=s.fiscal_timeout or 20, headers=auth_headers(s))
        body = resp.json()
        if resp.status_code >= 400:
            raise FiscalError(str(body.get("error") or body.get("message") or resp.status_code))
        result = _parse(body)
    except (requests.RequestException, ValueError, FiscalError) as exc:
        Receipt.objects.filter(pk=receipt.pk).update(status=ReceiptStatus.FISCAL_FAILED, fiscal_error=str(exc)[:1000])
        raise FiscalError(str(exc)) from exc
    Receipt.objects.filter(pk=receipt.pk).update(
        status=ReceiptStatus.FISCALIZED, fiscal_provider=s.fiscal_provider, fiscal_terminal_id=s.fiscal_terminal_id, fiscal_number=result["number"],
        fiscal_sign=result["sign"], fiscal_url=result["url"][:500], fiscalized_at=timezone.now(), fiscal_error="")
    receipt.refresh_from_db()
    return receipt
