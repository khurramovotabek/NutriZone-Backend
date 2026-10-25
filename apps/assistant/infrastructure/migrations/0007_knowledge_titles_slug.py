"""
Knowledge entries become public guides (nutrizone.uz/guides/<slug>): a stable URL slug and the title in Russian and
English (the answers already exist in all three languages). Titles of the seeded entries are filled here; the shop
fills them for its own entries on the dashboard, and a missing slug is made from the Uzbek title on save.
"""
import re

from django.db import migrations, models

TITLES = {
    "Mahsulotlar originalmi?": ("Оригинальные ли товары?", "Are the products genuine?"),
    "Yetkazib berish": ("Доставка", "Delivery"),
    "Qaytarish va almashtirish": ("Возврат и обмен", "Returns and exchanges"),
    "NutriZone Coins": ("NutriZone Coins", "NutriZone Coins"),
    "Kreatin qanday ichiladi": ("Как принимать креатин", "How to take creatine"),
    "Protein (whey) qanday ichiladi": ("Как пить протеин (whey)", "How to take whey protein"),
    "D vitamini: kimga va qancha": ("Витамин D: кому и сколько", "Vitamin D: who needs it and how much"),
    "Geyner kimga kerak": ("Кому нужен гейнер", "Who needs a mass gainer"),
    "Konsentrat, izolyat va gidrolizat farqi": ("Концентрат, изолят и гидролизат: разница", "Concentrate vs isolate vs hydrolysate"),
    "Magniy: uyqu va mushak tortishishi": ("Магний: сон и судороги", "Magnesium: sleep and muscle cramps"),
    "C vitamini": ("Витамин C", "Vitamin C"),
    "Kuniga qancha oqsil kerak": ("Сколько белка нужно в день", "How much protein you need a day"),
    "Temir va kamqonlik": ("Железо и анемия", "Iron and anaemia"),
    "Massa olish uchun ovqatlanish": ("Питание для набора массы", "Eating to build muscle"),
    "To'g'ri ozish: kaloriya va tezlik": ("Правильное похудение: калории и темп", "Losing fat right: calories and pace"),
    "B12 va B guruhi vitaminlari": ("B12 и витамины группы B", "B12 and B vitamins"),
    "Kazein — kechki protein": ("Казеин — протеин на ночь", "Casein — the night-time protein"),
    "Kreatin haqida miflar": ("Мифы о креатине", "Creatine myths"),
    "Pre-workout xavfsiz ishlatish": ("Как безопасно принимать предтрен", "Using a pre-workout safely"),
    "Rux (zinc)": ("Цинк", "Zinc"),
    "Immunitet uchun nima ichish kerak": ("Что пить для иммунитета", "What to take for immunity"),
    "Multivitamin kimga kerak": ("Кому нужны мультивитамины", "Who needs a multivitamin"),
    "Pre-workout tarkibi va xavfsizligi": ("Состав предтрена и безопасность", "What's in a pre-workout and is it safe"),
    "Professional sportchilar va doping nazorati": ("Профессиональные спортсмены и допинг-контроль", "Tested athletes and anti-doping"),
    "Ramazonda mashg'ulot va qo'shimchalar": ("Тренировки и добавки в Рамадан", "Training and supplements in Ramadan"),
    "BCAA / EAA": ("BCAA / EAA", "BCAA / EAA"),
    "BCAA yoki EAA": ("BCAA или EAA", "BCAA or EAA"),
    "Elektrolitlar va suv ichish": ("Электролиты и питьевой режим", "Electrolytes and hydration"),
    "Kalsiy va suyak salomatligi": ("Кальций и здоровье костей", "Calcium and bone health"),
    "Laktoza ko'tarolmasam qaysi protein": ("Какой протеин при непереносимости лактозы", "Which protein if you're lactose intolerant"),
    "L-karnitin": ("L-карнитин", "L-carnitine"),
    "Mashg'ulotdan oldin va keyin ovqatlanish": ("Питание до и после тренировки", "What to eat before and after training"),
    "O'simlik (vegan) protein": ("Растительный (веганский) протеин", "Plant (vegan) protein"),
    "O'smirlar uchun sport ozuqasi": ("Спортивное питание для подростков", "Sports nutrition for teenagers"),
    "Vitaminlarni qachon va qanday birga ichish": ("Когда и с чем принимать витамины", "When to take vitamins and what to combine"),
    "Yog' yoqiruvchilar haqiqatdan ishlaydimi": ("Работают ли жиросжигатели", "Do fat burners really work"),
    "Kofein va energetiklar": ("Кофеин и энергетики", "Caffeine and energy drinks"),
    "Kreatin ayollar uchun": ("Креатин для женщин", "Creatine for women"),
    "Plato: natija to'xtab qoldi": ("Плато: прогресс остановился", "Plateau: progress has stalled"),
    "Testosteron busterlar": ("Тестобустеры", "Testosterone boosters"),
    "Vitamin ortiqcha bo'lishi mumkinmi": ("Бывает ли передозировка витаминов", "Can you overdose on vitamins"),
    "Ayollar: hayz sikli, temir va qo'shimchalar": ("Женщинам: цикл, железо и добавки", "Women: cycle, iron and supplements"),
    "Interval och qolish (intermittent fasting)": ("Интервальное голодание", "Intermittent fasting"),
    "50 yoshdan keyin sport ozuqasi": ("Спортивное питание после 50", "Sports nutrition after 50"),
    "Biotin, soch, teri va tirnoq": ("Биотин, волосы, кожа и ногти", "Biotin, hair, skin and nails"),
    "L-sitrullin va pamp": ("L-цитруллин и памп", "L-citrulline and the pump"),
    "Probiotik va ichak salomatligi": ("Пробиотики и здоровье кишечника", "Probiotics and gut health"),
    "Proteinni sut yoki suv bilan": ("Протеин на молоке или на воде", "Protein with milk or water"),
    "Qo'shimchalarni birga ichish": ("Как сочетать добавки", "Combining supplements"),
    "Uyqu va tiklanish uchun qo'shimchalar": ("Добавки для сна и восстановления", "Supplements for sleep and recovery"),
    "Ayollar uchun protein": ("Протеин для женщин", "Protein for women"),
    "Doimiy charchoq va holsizlik": ("Постоянная усталость и слабость", "Constant tiredness and fatigue"),
    "Glyukozamin va bo'g'imlar": ("Глюкозамин и суставы", "Glucosamine and joints"),
    "Halol sertifikati": ("Сертификат халяль", "Halal certificate"),
    "Mashg'ulot qilmasam protein ichsa bo'ladimi": ("Можно ли пить протеин без тренировок", "Can I take protein without training"),
    "Multivitamin": ("Мультивитамины", "Multivitamins"),
    "Mushak og'rig'i va tiklanish": ("Боль в мышцах и восстановление", "Muscle soreness and recovery"),
    "Omega-3": ("Омега-3", "Omega-3"),
    "Yangi boshlovchilar uchun nima olish kerak": ("Что купить новичку", "What beginners should buy"),
    "Keto parhez va sport": ("Кето-диета и спорт", "Keto diet and training"),
    "Ozish va massa bir vaqtda (rekompozitsiya)": ("Худеть и набирать мышцы одновременно (рекомпозиция)", "Losing fat and gaining muscle at once (recomposition)"),
    "Protein batonchiklar": ("Протеиновые батончики", "Protein bars"),
    "Protein va husnbuzar (akne)": ("Протеин и акне", "Protein and acne"),
    "Spirtli ichimlik va mashg'ulot": ("Алкоголь и тренировки", "Alcohol and training"),
    "Beta-alanin": ("Бета-аланин", "Beta-alanine"),
    "Kollagen": ("Коллаген", "Collagen"),
    "Protein buyrakka zararmi": ("Вредит ли протеин почкам", "Is protein bad for the kidneys"),
    "Saqlash va yaroqlilik muddati": ("Хранение и срок годности", "Storage and shelf life"),
}


def slug_for(title: str) -> str:
    t = re.sub(r"[ʻʼ‘’`´']", "", (title or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:80] or "maslahat"


def fill(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    used = set()
    for e in KnowledgeEntry.objects.order_by("created_at"):
        ru, en = TITLES.get(e.title, ("", ""))
        e.title_ru = e.title_ru or ru
        e.title_en = e.title_en or en
        base = slug_for(e.title)
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        e.slug = slug
        e.save(update_fields=["title_ru", "title_en", "slug"])


class Migration(migrations.Migration):
    dependencies = [("assistant", "0006_expert_knowledge")]
    operations = [
        migrations.AddField("knowledgeentry", "title_ru", models.CharField("Sarlavha (ruscha)", max_length=200, blank=True, default="")),
        migrations.AddField("knowledgeentry", "title_en", models.CharField("Sarlavha (inglizcha)", max_length=200, blank=True, default="")),
        migrations.AddField("knowledgeentry", "slug", models.SlugField("Manzil (URL)", max_length=90, blank=True, default="", db_index=True,
                                                                    help_text="nutrizone.uz/guides/<slug> — bo'sh qoldirilsa sarlavhadan yasaladi.")),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
