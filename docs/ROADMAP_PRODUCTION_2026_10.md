# NutriZone — production roadmap (2026-10-16)

Manba: nutrizone.uz va api.nutrizone.uz ni jonli tahlil qilish (3 til × barcha ochiq sahifalar,
dashboardning 190 ta sahifasi server ichidan, mahsulot qo'shish formasi Chrome'da, server holati).

## Topilgan muammolar (tahlil natijasi)

### Kritik
| # | Muammo | Sabab |
|---|--------|-------|
| K1 | Til cookie'si bo'lmagan har bir tashrifchi saytni **inglizcha** ko'radi | `frontend/src/i18n/config.ts` `DEFAULT_LOCALE = "en"` |
| K2 | UZ tanlansa ham bosh sahifada "Sports Nutrition / Vitamins / Sports Products" | `QuickNav`, `about` `getCategories()` ni locale'siz chaqiradi → backend inglizcha qaytaradi |
| K3 | Locale berilmagan API so'rovlari doim `en` | `_explicit_locale()` `Accept-Language` ni e'tiborsiz qoldiradi; `common/utils/localization.DEFAULT_LOCALE = "en"` |
| K4 | Dashboard default tili inglizcha (Delete, History, Go, Search...) | `LANGUAGE_CODE = "en"` |
| K5 | Vaqt UTC: dashboardda "Siz server vaqtidan 5 soat oldindasiz", kunlik hisobotlar kun chegarasi noto'g'ri | `TIME_ZONE = "UTC"` |
| K6 | Serverda qo'lda kiritilgan 4 tuzatish repoda yo'q (keyingi deploy ularni o'chirardi) | migration 0011, stores admin formset, celery healthcheck, nginx port/proto |

### Yuqori
| # | Muammo |
|---|--------|
| Y1 | Mahsulot formasi: inglizcha label'lar (Brand, Category, Status, Draft, Sku, Barcode, Is default, Weight value/unit, Package, Flavour, Media role, Sort order, Upload file, Duration seconds, "Product medias") |
| Y2 | Mahsulot formasi: variantlar jadvali gorizontal scroll, SKU input 20px, inputlar kengligi har xil, "Ishlab chiqarilgan davlat" select bo'sh/eni yo'q, checkbox'lar xom |
| Y3 | Analitika va Telegram "Platforma" ichida yashiringan — alohida bo'lim emas |
| Y4 | Analytics bot webhook o'rnatilmagan (bot buyruqlarga javob bermaydi) |
| Y5 | Dashboard bosh sahifasi 2.4 s (sekin) |
| Y6 | "Grid view / List view" aria-label'lari tarjima qilinmagan |

### O'rta
| # | Muammo |
|---|--------|
| O1 | Telegram postlari uchun RichText muharriri yo'q (oddiy textarea) |
| O2 | Zaxira nusxalar faqat shu serverning diskida (server yo'qolsa — hammasi yo'qoladi) |
| O3 | Sentry DSN bo'sh — production xatolari ko'rinmaydi |
| O4 | ANTHROPIC_API_KEY bo'sh — AI yordamchi o'chiq |
| O5 | Excel export barcha ro'yxat sahifalarida bir xil emas |
| O6 | Next.js logida "Server Reference ID" botlar so'rovlari (zararsiz, lekin log shovqini) |

## Holat (2026-10-16 kechqurun)

| Bosqich | Holat |
|---|---|
| 1. Til va vaqt (K1–K6, Y6) | ✅ production'da |
| 2. Dashboard formalari (Y1, Y2) | ✅ production'da — label'lar o'zbekcha, variantlar kartochka, bir xil kengliklar |
| 3. Dashboard tuzilmasi (Y3, Y5, O5) | ✅ Analitika va Telegram bo'limlari; Excel export 21 ta yangi ro'yxatda (jami 30); bosh sahifa "issiq" holatda 0.38 s |
| 4. Telegram premium (O1, Y4) | ✅ RichText muharriri, Telegram postlar, Mijozlarga xabar formatlangan; analytics bot webhook ishlayapti |
| 5. Storefront va Mini App | 🟡 12 sahifa 390px'da toshmaydi; hero savdoga yo'naltirildi; Mini App tilni va rangni Telegramdan oladi |
| 6. Production ishonchliligi | ⏳ offsite backup, Sentry, SSH parolni o'chirish — foydalanuvchi qarori kerak |

Keyingi texnik qarzlar: ruscha dashboard katalogida ~540 satr tarjimasiz; parallel (xdist) test rejimida 1–2 ta tasodifiy yiqilish (umumiy Redis); `products/infrastructure/composition.py` da 3 ta aniqlanmagan nom (wishlist servislari).

## Bosqichlar

### 1-bosqich — Til va vaqt (K1–K6, Y6) ← hozir
- Frontend default til `uz`; har bir server API so'rovi joriy tilni `Accept-Language` bilan yuboradi.
- Backend: locale berilmasa `Accept-Language` → bo'lmasa `uz`.
- Dashboard `LANGUAGE_CODE = "uz"`, `TIME_ZONE = "Asia/Tashkent"`.
- Server tuzatishlarini repoga ko'chirish; deploy skripti.

### 2-bosqich — Dashboard formalari (Y1, Y2)
- Barcha model maydonlariga o'zbekcha `verbose_name` + ru/en tarjima.
- Mahsulot formasi: bir xil grid (2 ustun), variantlar kartochka ko'rinishida (scroll'siz), barcha add/edit formalarni tekshirish.

### 3-bosqich — Dashboard tuzilmasi (Y3, Y5, O5)
- Menyuda alohida **Analitika** (Analitika, Sotuv rejasi, Segmentlar, Filial hisoboti, Qidiruv tahlili) va **Telegram** (Botlar markazi, postlar, kanal sozlamalari, xabar yuborish) bo'limlari.
- Bosh sahifani keshlash (2.4 s → <0.5 s).
- Excel export — barcha ro'yxatlarda bir xil tugma.

### 4-bosqich — Telegram premium (O1, Y4)
- RichText (bold/italic/link/spoiler/quote/emoji) muharriri → Telegram HTML; preview.
- Analytics bot webhook; post shablonlari; mahsulot postlari rasm + tugmalar bilan.

### 5-bosqich — Storefront va Mini App
- Mobil 390px audit (barcha sahifalar), checkout konversiyasi, PDP trust-blok.
- Telegram Mini App: tez kirish, savat, buyurtma holati, MainButton.

### 6-bosqich — Production ishonchliligi (O2, O3, O6)
- Offsite backup, Sentry, uptime monitor, deploy skripti, SSH parol bilan kirishni o'chirish.
