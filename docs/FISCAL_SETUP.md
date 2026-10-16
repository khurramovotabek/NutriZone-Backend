# Soliq cheki (fiskal chek) — ishga tushirish

Hammasi dashboard'dan sozlanadi: **Cheklar → Chek sozlamalari**. Kalitlar shifrlangan holda saqlanadi va qayta ko'rsatilmaydi.
Yuqoridagi "Fiskal tayyorlik" ro'yxati nima yetishmayotganini ko'rsatadi.

## 1. Avval (ikkala usul uchun)
1. YaTT yoki MChJ ro'yxatdan o'tgan bo'lishi kerak (soliq cheki shu STIR/JShShIR nomidan chiqadi).
2. "Sotuvchi rekvizitlari": yuridik nom, STIR (JShShIR), manzil; QQS to'lovchisi bo'lsangiz — QQS stavkasi.
3. Har bir sotuvdagi mahsulot kartasida **MXIK (IKPU) kodi** va **qadoq kodi** (tasnif.soliq.uz).

## 2. Payme virtual kassasi (Payme bilan to'langan onlayn buyurtmalar)
1. Payme Business kabinetida kassa uchun fiskalizatsiyani yoqing (Payme menejeri orqali).
2. To'lovlar → To'lov tizimlari → Payme: merchant ID va kalit allaqachon kiritilgan bo'lishi kerak (endpoint o'zgarmaydi).
3. Chek sozlamalari → "Payme orqali fiskal chek" ni yoqing.

Shundan keyin: Payme `CheckPerformTransaction` javobida har bir mahsulotning MXIK, qadoq kodi, QQS va narxi (`detail`) yuboriladi;
Payme chekni soliqqa ro'yxatdan o'tkazib, `SetFiscalData` orqali fiskal belgi va QR havolani qaytaradi — u to'lovda saqlanadi va
buyurtma chekiga (mijozning e-chekiga, `/r/<token>`) avtomatik qo'yiladi. MXIK'i yo'q mahsulot bo'lsa to'lov to'xtamaydi, faqat
`detail` yuborilmaydi (logda sababi yoziladi).

## 3. E-POS (kassa cheklari va boshqa to'lovlar)
1. E-POS bilan shartnoma → integrator kirishi (docs.epos.uz) va API token, terminal ID, kassir ID.
2. Chek sozlamalari → provayder "E-POS", API manzili (bo'sh qoldirilsa `https://api.epos.uz/v1/receipts`), terminal ID, kassir ID,
   avtorizatsiya "Bearer", API kaliti.
3. "Saqlash va ulanishni tekshirish" → ✓ bo'lsa, bitta chekni "Fiskallashtirish" bilan sinang, keyin "Avtomatik fiskallashtirish".

E-POS so'rov maydonlari ularning ochiq API sahifasidagi namunaga asoslangan (`items[name, price (so'm), qty, ikpu,
package_code, vat_percent]`, `payment`, `cashier_id`). Integrator hujjati olingach maydon nomlari solishtiriladi —
moslash `apps/receipts/infrastructure/fiscal.py` dagi `_payload_epos` / `_parse` da.

Boshqa OFD / virtual kassa: provayder "Boshqa (HTTP API)" — umumiy JSON adapter (summalar tiyinda).
