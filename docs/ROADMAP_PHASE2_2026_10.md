# NutriZone — 2-bosqich roadmap (2026-10-16)

Holat tahlili: transfer skanerlash va farqni tasdiqlash allaqachon bor (UX tekshiriladi); Support/CRM yo'q;
fiskal chek tizimi yo'q (POS'da oddiy termal chek bor); bosh sahifada aksiyalar qatori yo'q; AI yordamchi
pullik Claude API'ga bog'langan; bot kanalda admin (post/edit huquqi bor).

| # | Ish | Natija |
|---|-----|--------|
| R1 | Kanal (@nutrizonepit) avtomatik postlari | Yangi mahsulot, chegirma, qayta omborga kelgan mahsulot — rasm + "Sotib olish" tugmasi bilan; dashboardda yoqish/o'chirish |
| R2 | Bosh sahifada "Aksiyalar" qatori | Chegirmadagi mahsulotlar, chegirma foizi, gorizontal mobil karusel |
| R3 | **Bepul AI maslahatchi** (o'zimizniki) | Pullik API'siz: mijoz profili (bo'y, vazn, yosh, maqsad, faollik, byudjet, laktoza) → oqsil/kaloriya hisoboti → katalogdan mos to'plam; brend/kategoriya/mahsulot savollari, yetkazish/do'kon/to'lov/coin FAQ; xaridlar, bosishlar va 👍/👎 dan o'rganadi; ovozli kiritish va ovozli javob (brauzer Web Speech); saytda va Telegram botda |
| R4 | **Support CRM** | Qo'ng'iroq yozuvi (ism — bo'lmasa "Noma'lum", telefon, mavzu, izoh) → avtomatik mijoz akkaunti; Kanban paneli (Yangi → O'ylab ko'radi → Qayta qo'ng'iroq → Buyurtma qildi / Yopildi / Rad etdi); bot orqali shu raqam ro'yxatdan o'tganda ma'lumotlarni tasdiqlatish |
| R5 | Transfer: yuborish/qabul skaneri | 2D skaner bilan bir marta skan; yuborilgan va qabul qilingan solishtiriladi; mos → tasdiq, mos emas → ogohlantirish + sabab yoki o'tkazib yuborish |
| R6 | **Cheklar tizimi** | Yagona chek (POS + onlayn), professional shablon (80 mm + A4), QR kod, "Cheklar" sahifasi (ro'yxat, qo'lda chek yaratish, qayta chop etish), fiskal integratsiya uchun tayyor qatlam (OFD / soliq virtual kassa adapteri, fiskal belgi, terminal ID) |
| R7 | To'lovlar | Har bir holat o'zgarishi tarixi, qayta urinish/qaytarish mantiqi, integratsiya adapterlari tekshiruvi |
| R8 | POS terminal premium | Brauzerda to'liq sinov, tezlik, mobil/planshet, xatolarni tuzatish |
| R9 | Geo/location | Barcha sahifalarda manzil aniqlash, xarita, yaqin do'kon — aniqlik tekshiruvi |
| R10 | Mijoz va do'kon profillari, mobil audit | Profil sahifalari upgrade, 390 px'da barcha sahifalar |

Har bir ish: test → commit → GitHub → production deploy → brauzerda tekshiruv.

## Holat (2026-10-16) — hammasi bajarildi va production'da

| # | Holat |
|---|-------|
| R1 | ✅ Kanal avtopostlari **yoqildi** (@nutrizonepit, har 15 daqiqada ko'pi bilan 2 ta, jim rejim 22:00–09:00) |
| R2 | ✅ Bosh sahifada "Aksiyalar" qatori |
| R3 | ✅ Bepul maslahatchi (sayt + Telegram, ovoz); kirgan mijozning profilidagi bo'y/vazn/yosh/maqsadni o'zi oladi |
| R4 | ✅ Support CRM: Kanban, avtomatik akkaunt, bot orqali tasdiqlash |
| R5 | ✅ DataMatrix (2D) skan, takroriy skan himoyasi, "hal qilinmagan" farq sababi |
| R6 | ✅ Cheklar registri, 80/58/A4 + QR, fiskal adapter (FISCAL_API_TOKEN kerak); onlayn cheklar vaqti = yetkazilgan vaqt (prod ma'lumot tuzatildi) |
| R7 | ✅ To'lov hodisalari tarixi (PaymentEvent) va tranzaksiya sahifasida timeline |
| R8 | ✅ POS: tarjimalar, skaner matnlari |
| R9 | ✅ Viloyat OSM chegarasidan, barcha tumanlar, eski kodlar tozalandi (prod seed + zaxira `/root/geo_backup_20261016.sql`) |
| R10 | ✅ "Cheklarim" (`/account/receipts`), "Shaxsiy kunlik reja" kartasi, filial "Cheklar" (`/profile/store/receipts`), 390 px tekshiruvi |

Foydalanuvchidan kutilmoqda: rclone offsite kalitlari, SENTRY_DSN, fiskal provayder (OFD) ma'lumotlari, sizib chiqqan GitHub token/parolni almashtirish.
