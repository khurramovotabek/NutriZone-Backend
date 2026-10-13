"""
The catalogue of payment methods: what each one needs from the merchant cabinet, where its callbacks
live, and how "is it usable right now?" is decided. The dashboard renders forms and instructions from
this, checkout lists methods from it, and the protocol handlers read their credentials through it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from apps.payment.infrastructure.crypto import decrypt_secrets
from apps.payment.infrastructure.models import PaymentProvider, PaymentProviderConfig

ACQUIRERS = ("payme", "click", "uzum")
CARD_BRANDS = ("uzcard", "humo")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    help: str = ""
    secret: bool = False
    required: bool = True
    default: str = ""
    choices: tuple = ()
    placeholder: str = ""


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    color: str
    tagline: str
    cabinet_url: str = ""
    docs_url: str = ""
    fields: tuple[Field, ...] = ()
    callbacks: tuple[tuple[str, str], ...] = ()  # (label, path)
    steps: tuple[str, ...] = ()
    online: bool = True  # False for cash
    supports_test: bool = True


SPECS: dict[str, ProviderSpec] = {
    "cash": ProviderSpec(
        key="cash", name=_("Naqd pul"), color="#16a34a", online=False, supports_test=False,
        tagline=_("Kuryerga yoki filialda to'lanadi. Hech qanday sozlash talab qilinmaydi."),
    ),
    "payme": ProviderSpec(
        key="payme", name="Payme", color="#00b2b2",
        tagline=_("Payme Merchant API (JSON-RPC). Uzcard, Humo, Visa va Payme ilovasi orqali to'lov."),
        cabinet_url="https://merchant.paycom.uz", docs_url="https://developer.help.paycom.uz",
        fields=(
            Field("merchant_id", _("Kassa ID (merchant_id)"), _("Payme Business → Kassa → Sozlamalar.")),
            Field("account_field", _("Hisob maydoni"), _("Kassa sozlamalaridagi «Rekvizit» kaliti. Odatda order_id."), default="order_id", placeholder="order_id"),
            Field("key", _("Kalit (production)"), _("Kassa → Kalitlar → «Ключ» (asosiy kalit). Production rejimida majburiy."), secret=True, required=False),
            Field("test_key", _("Test kaliti"), _("«Тестовый ключ». Test rejimida majburiy."), secret=True, required=False),
        ),
        callbacks=((_("Endpoint URL"), "/api/v1/payments/payme"),),
        steps=(
            _("merchant.paycom.uz da kassa yarating va «Sayt» turini tanlang."),
            _("Kassa sozlamalarida Endpoint URL sifatida quyidagi manzilni kiriting."),
            _("«Rekvizitlar» bo'limida bitta maydon qo'shing: order_id (matn)."),
            _("Kassa ID va kalitlarni shu sahifaga kiriting, avval test rejimida sinang."),
            _("Payme Sandbox (test.paycom.uz) dagi barcha testlardan o'tgach, production'ga o'ting."),
        ),
    ),
    "click": ProviderSpec(
        key="click", name="Click", color="#0062ff",
        tagline=_("Click SHOP API: Prepare + Complete, MD5 imzo bilan. Click Up, Uzcard, Humo."),
        cabinet_url="https://merchant.click.uz", docs_url="https://docs.click.uz",
        fields=(
            Field("service_id", _("Service ID"), _("merchant.click.uz → Servislar.")),
            Field("merchant_id", _("Merchant ID"), _("Kabinet → Profil.")),
            Field("merchant_user_id", _("Merchant User ID"), _("API foydalanuvchisi (Merchant API uchun)."), required=False),
            Field("secret_key", _("Secret key"), _("Servis sozlamalaridagi maxfiy kalit (SECRET_KEY)."), secret=True),
        ),
        callbacks=((_("Prepare URL"), "/api/v1/payments/click/prepare"), (_("Complete URL"), "/api/v1/payments/click/complete")),
        steps=(
            _("merchant.click.uz kabinetida servis oching (yoki mavjudini tanlang)."),
            _("Servis sozlamalarida Prepare va Complete URL manzillarini kiriting."),
            _("Service ID, Merchant ID va Secret key ni shu sahifaga kiriting."),
            _("Click texnik qo'llab-quvvatlashidan test to'lovini so'rang va jurnalda Prepare/Complete kelganini tekshiring."),
        ),
    ),
    "uzum": ProviderSpec(
        key="uzum", name="Uzum Bank", color="#7000ff",
        tagline=_("Uzum Bank Merchant API: check / create / confirm / reverse / status (Basic Auth)."),
        cabinet_url="https://business.uzumbank.uz", docs_url="https://developer.uzumbank.uz",
        fields=(
            Field("service_id", _("Service ID"), _("Uzum Bank tomonidan beriladigan servis raqami.")),
            Field("login", _("Login (Basic Auth)"), _("Uzum so'rovlarini tasdiqlash uchun login.")),
            Field("password", _("Parol (Basic Auth)"), secret=True),
            Field("checkout_url", _("To'lov havolasi shabloni"), _("{service_id}, {order}, {amount} (tiyin) almashtiriladi."), required=False,
                  default="https://www.uzumbank.uz/open-service?serviceId={service_id}&order_id={order}&amount={amount}"),
        ),
        callbacks=((_("Base URL"), "/api/v1/payments/uzum/"),),
        steps=(
            _("Uzum Bank bilan merchant shartnomasini tuzing va servis oching."),
            _("Ularga Base URL ni bering: check, create, confirm, reverse, status shu manzil ostida."),
            _("Login/parol va Service ID ni shu sahifaga kiriting."),
            _("Test to'lov bilan jurnalda check → create → confirm ketma-ketligini tekshiring."),
        ),
    ),
    "uzcard": ProviderSpec(
        key="uzcard", name="Uzcard", color="#1a4fa0", supports_test=False,
        tagline=_("Uzcard kartasi bilan to'lov — tanlangan ekvayer (Payme / Click / Uzum) sahifasida."),
        fields=(Field("route", _("Ekvayer"), _("Karta qaysi tizim sahifasida qabul qilinadi."), choices=ACQUIRERS, default="payme"),),
    ),
    "humo": ProviderSpec(
        key="humo", name="Humo", color="#f37021", supports_test=False,
        tagline=_("Humo kartasi bilan to'lov — tanlangan ekvayer (Payme / Click / Uzum) sahifasida."),
        fields=(Field("route", _("Ekvayer"), _("Karta qaysi tizim sahifasida qabul qilinadi."), choices=ACQUIRERS, default="payme"),),
    ),
}

ORDER = ("cash", "payme", "click", "uzum", "uzcard", "humo")


@dataclass
class ProviderState:
    """A provider's live configuration with decrypted secrets -- server-side only, never serialised."""

    key: str
    spec: ProviderSpec
    enabled: bool
    test_mode: bool
    public: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)
    min_amount: Decimal = Decimal("0")
    max_amount: Decimal | None = None
    route: str | None = None  # uzcard / humo → the acquirer they ride on

    def value(self, key: str) -> str:
        spec_field = next((f for f in self.spec.fields if f.key == key), None)
        raw = (self.secrets if spec_field and spec_field.secret else self.public).get(key) or ""
        return raw or (spec_field.default if spec_field else "")

    @property
    def missing(self) -> list[str]:
        out = []
        for f in self.spec.fields:
            if self.key == "payme" and f.key in ("key", "test_key"):
                continue  # Payme: exactly one of the two keys is needed, by mode (below)
            if f.required and not self.value(f.key):
                out.append(f.key)
        if self.key == "payme":
            needed = "test_key" if self.test_mode else "key"
            if not self.value(needed):
                out.append(needed)
        return out

    @property
    def configured(self) -> bool:
        return not self.missing

    @property
    def status(self) -> str:
        """active / disabled / not_configured -- for uzcard & humo also when their acquirer isn't active."""
        if self.key in CARD_BRANDS:
            if not self.enabled:
                return "disabled"
            acquirer = load(self.route or "payme")
            return "active" if acquirer.status == "active" else "not_configured"
        if not self.configured:
            return "not_configured" if self.enabled or self.spec.online else "disabled"
        return "active" if self.enabled else "disabled"


def _row(key: str) -> PaymentProviderConfig | None:
    return PaymentProviderConfig.objects.filter(provider=key).first()


def load(key: str) -> ProviderState:
    spec = SPECS[key]
    row = _row(key)
    if row is None:
        return ProviderState(key=key, spec=spec, enabled=key == "cash", test_mode=True)
    public = dict(row.settings_public or {})
    return ProviderState(
        key=key, spec=spec, enabled=row.is_enabled, test_mode=row.is_test_mode and spec.supports_test,
        public=public, secrets=decrypt_secrets(row.secrets_encrypted), min_amount=row.min_amount, max_amount=row.max_amount,
        route=public.get("route") or (spec.fields[0].default if key in CARD_BRANDS else None),
    )


def all_states() -> list[ProviderState]:
    return [load(k) for k in ORDER]


def provider_label(key: str) -> str:
    spec = SPECS.get(key)
    return str(spec.name) if spec else key


def acquirer_for(method: str) -> str:
    """The protocol that actually moves the money for a checkout method (uzcard → its route)."""
    if method in CARD_BRANDS:
        return load(method).route or "payme"
    return method


__all__ = ["ACQUIRERS", "CARD_BRANDS", "ORDER", "SPECS", "PaymentProvider", "ProviderState", "acquirer_for", "all_states", "load", "provider_label"]
