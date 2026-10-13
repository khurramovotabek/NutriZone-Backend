"""
Replaces the icontains-based search placeholder with a real Postgres
full-text index: a persisted, trigger-maintained `search_vector`
column (GIN-indexed) plus a trigram GIN index on `name` for
typo-tolerant fallback matching. See
`apps/products/infrastructure/selectors.py::DjangoProductSearchBackend`
for the query side.

The trigger (not an application-level signal) is deliberate: it keeps
`search_vector` correct for *every* write path -- ORM `.save()`,
`.update()`/bulk operations, Django admin, direct SQL/data fixes --
without requiring every caller to remember to call `.update_search_vector()`.

Text-search config is chosen per-row from `locale_code` so English and
Russian content get real stemming (search "vitamins" matches
"vitamin"); Uzbek has no Postgres dictionary, so it falls back to
`simple` (exact token matching only, no stemming) -- still correctly
indexed and searchable, just not stemmed.
"""
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models

_CREATE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION catalog_product_translations_search_vector_update()
RETURNS trigger AS $$
DECLARE
    fts_config regconfig;
BEGIN
    fts_config := CASE NEW.locale_code
        WHEN 'en' THEN 'english'::regconfig
        WHEN 'ru' THEN 'russian'::regconfig
        ELSE 'simple'::regconfig
    END;
    NEW.search_vector :=
        setweight(to_tsvector(fts_config, coalesce(NEW.name, '')), 'A') ||
        setweight(to_tsvector(fts_config, coalesce(NEW.description, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS catalog_product_translations_search_vector_trigger
    ON catalog_product_translations;

CREATE TRIGGER catalog_product_translations_search_vector_trigger
    BEFORE INSERT OR UPDATE OF name, description, locale_code
    ON catalog_product_translations
    FOR EACH ROW
    EXECUTE FUNCTION catalog_product_translations_search_vector_update();
"""

_DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS catalog_product_translations_search_vector_trigger
    ON catalog_product_translations;
DROP FUNCTION IF EXISTS catalog_product_translations_search_vector_update();
"""

_BACKFILL_SQL = """
UPDATE catalog_product_translations
SET search_vector =
    setweight(to_tsvector(
        CASE locale_code
            WHEN 'en' THEN 'english'::regconfig
            WHEN 'ru' THEN 'russian'::regconfig
            ELSE 'simple'::regconfig
        END, coalesce(name, '')), 'A') ||
    setweight(to_tsvector(
        CASE locale_code
            WHEN 'en' THEN 'english'::regconfig
            WHEN 'ru' THEN 'russian'::regconfig
            ELSE 'simple'::regconfig
        END, coalesce(description, '')), 'B');
"""

_UNBACKFILL_SQL = "UPDATE catalog_product_translations SET search_vector = NULL;"


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0023_attributevalue_image_storage_path_and_more"),
    ]

    operations = [
        # Enables trigram similarity (typo-tolerant matching + the
        # gin_trgm_ops index class used below). Requires the DB role to
        # be able to CREATE EXTENSION -- standard on RDS/Cloud SQL
        # Postgres 16 superuser-equivalent app roles; if the target
        # environment restricts this, run
        # `CREATE EXTENSION pg_trgm;` once as a superuser before migrating.
        TrigramExtension(),
        migrations.AddField(
            model_name="producttranslation",
            name="search_vector",
            field=SearchVectorField(editable=False, null=True),
        ),
        migrations.RunSQL(sql=_CREATE_TRIGGER_SQL, reverse_sql=_DROP_TRIGGER_SQL),
        migrations.RunSQL(sql=_BACKFILL_SQL, reverse_sql=_UNBACKFILL_SQL),
        migrations.AddIndex(
            model_name="producttranslation",
            index=GinIndex(fields=["search_vector"], name="prod_trans_search_gin"),
        ),
        migrations.AddIndex(
            model_name="producttranslation",
            index=GinIndex(fields=["name"], name="prod_trans_name_trgm_gin", opclasses=["gin_trgm_ops"]),
        ),
    ]
