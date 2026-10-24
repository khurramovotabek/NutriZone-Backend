"""
The starter BCAA entry answered "bcaa nima uchun?" with a dose only. It now says what BCAA does, who benefits and how
to take it. Updated only while the shop hasn't edited the seeded text on the dashboard.
"""
from django.db import migrations

OLD_UZ = "BCAA/EAA mashg'ulot paytida yoki undan keyin 5–10 g ichiladi. Agar kunlik oqsilingiz (ovqat + protein) yetarli bo'lsa, foydasi kichik — avval protein va kreatin, keyin BCAA."
NEW = {
    "answer_uz": "**BCAA** — leysin, izoleysin va valin: mushak oqsilini qurishni boshlab beradigan 3 ta aminokislota. Uzoq, og'ir yoki och qoringa "
                 "qilingan mashg'ulotda mushakni parchalanishdan himoya qiladi va keyingi kunlardagi og'riqni kamaytiradi.\n\n"
                 "_Qanday ichish:_ mashg'ulot oldidan yoki davomida 5–10 g, suv bilan.\n\n"
                 "Kunlik oqsilingiz (ovqat + protein) yetarli bo'lsa, foydasi kichik — avval protein va kreatin, keyin BCAA. To'liq aminokislotalar (EAA) BCAA'dan kuchliroq.",
    "answer_ru": "**BCAA** — лейцин, изолейцин и валин: 3 аминокислоты, которые запускают синтез мышечного белка. На долгих, тяжёлых или тренировках натощак "
                 "защищают мышцы от разрушения и уменьшают крепатуру.\n\n"
                 "_Как принимать:_ 5–10 г до или во время тренировки, с водой.\n\n"
                 "Если белка в рационе (еда + протеин) достаточно, польза небольшая — сначала протеин и креатин, потом BCAA. Полный комплекс EAA сильнее BCAA.",
    "answer_en": "**BCAA** — leucine, isoleucine and valine: the 3 amino acids that switch on muscle protein building. In long, hard or fasted sessions they "
                 "protect muscle from breakdown and ease next-day soreness.\n\n"
                 "_How to take:_ 5–10 g before or during training, with water.\n\n"
                 "If your daily protein (food + powder) is already enough, the benefit is small — protein and creatine first, then BCAA. Full EAAs beat BCAA alone.",
    "questions": "bcaa nima uchun\nbcaa nima uchun kerak\nbcaa nima\nаминокислоты\nзачем bcaa\nbcaa",
}


def forward(apps, schema_editor):
    apps.get_model("assistant", "KnowledgeEntry").objects.filter(title="BCAA / EAA", answer_uz=OLD_UZ).update(**NEW)


class Migration(migrations.Migration):
    dependencies = [("assistant", "0004_seed_knowledge")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
