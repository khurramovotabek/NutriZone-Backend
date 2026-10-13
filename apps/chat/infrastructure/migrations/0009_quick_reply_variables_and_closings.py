"""
The starter quick replies learn the variables ({ism}, {buyurtma_raqami}, {yetkazish_sanasi}, ...) -- only the ones
still worded exactly as seeded, an edited reply is left alone -- and support chats already closed before the
operator report existed get one closing each (credited to the operator they were assigned to).
"""
from __future__ import annotations

from django.db import migrations

UPGRADE = {  # title -> (seeded text, text with variables)
    "Salomlashish": ("Assalomu alaykum! NutriZone qo'llab-quvvatlash xizmati. Sizga qanday yordam bera olaman?",
                     "Assalomu alaykum, {ism}! NutriZone qo'llab-quvvatlash xizmati, {operator}. Sizga qanday yordam bera olaman?"),
    "Buyurtma yo'lda": ("Buyurtmangiz yo'lda, kuryer tez orada siz bilan bog'lanadi.",
                        "{ism}, {buyurtma_raqami} buyurtmangiz yo'lda — taxminan {yetkazish_sanasi} yetkaziladi. Kuryer siz bilan bog'lanadi."),
    "Xayrlashish": ("Murojaatingiz uchun rahmat! Yana savollar bo'lsa, yozing.",
                    "Murojaatingiz uchun rahmat, {ism}! Yana savollar bo'lsa, yozing."),
}
NEW = ("Buyurtma holati", "{ism}, {buyurtma_raqami} buyurtmangiz holati: {buyurtma_holati}. Taxminiy yetkazish: {yetkazish_sanasi}.")


def forwards(apps, schema_editor):
    QuickReply = apps.get_model("chat", "ChatQuickReply")
    for title, (old, new) in UPGRADE.items():
        QuickReply.objects.filter(title=title, text=old).update(text=new)
    if not QuickReply.objects.filter(title=NEW[0]).exists():
        QuickReply.objects.create(title=NEW[0], text=NEW[1], sort_order=3)
    Conversation = apps.get_model("chat", "ConversationModel")
    Closing = apps.get_model("chat", "ConversationClosing")
    closed = Conversation.objects.filter(status__in=("closed", "archived")).exclude(conversation_type="customer_sales").exclude(closings__isnull=False)
    Closing.objects.bulk_create([Closing(conversation_id=c.id, operator_id=c.assigned_operator_id, closed_at=c.updated_at) for c in closed])


def backwards(apps, schema_editor):
    QuickReply = apps.get_model("chat", "ChatQuickReply")
    for title, (old, new) in UPGRADE.items():
        QuickReply.objects.filter(title=title, text=new).update(text=old)


class Migration(migrations.Migration):
    dependencies = [("chat", "0008_support_desk_v2")]
    operations = [migrations.RunPython(forwards, backwards)]
