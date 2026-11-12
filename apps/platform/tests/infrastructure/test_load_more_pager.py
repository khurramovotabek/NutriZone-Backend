"""Every Dashboard list pager offers "Yana ko'rsatish" (nz-load-more.js appends the next page under the rows shown)."""
from types import SimpleNamespace

from django.core.paginator import Paginator

from apps.platform.templatetags.nzi import nz_pager


def _cl(count, page, per_page=25):
    pag = Paginator(range(count), per_page)
    return SimpleNamespace(page_num=page, paginator=pag, list_per_page=per_page, result_count=count,
                           get_query_string=lambda d: f"?p={d['p']}")


def test_more_is_the_rows_the_next_page_adds():
    assert nz_pager(_cl(60, 1), [1, 2, 3])["more"] == 25
    assert nz_pager(_cl(60, 2), [1, 2, 3])["more"] == 10
    last = nz_pager(_cl(60, 3), [1, 2, 3])
    assert last["more"] == 0 and last["next"] is None


def test_pager_template_has_the_load_more_link():
    from django.template.loader import render_to_string

    cl = _cl(60, 1)
    cl.opts = SimpleNamespace(verbose_name="post", verbose_name_plural="posts")
    cl.formset = None
    html = render_to_string("admin/pagination.html", {"cl": cl, "page_range": [1, 2, 3], "pagination_required": True})
    assert 'data-nz-more' in html and 'href="?p=2"' in html and "+25" in html and "data-nz-from-cell" in html
    last = _cl(60, 3)
    last.opts, last.formset = cl.opts, None
    assert "data-nz-more" not in render_to_string("admin/pagination.html", {"cl": last, "page_range": [1, 2, 3], "pagination_required": True})
    cl.formset = object()  # an editable list (list_editable) keeps plain paging: appended rows would break its formset
    assert "data-nz-more" not in render_to_string("admin/pagination.html", {"cl": cl, "page_range": [1, 2, 3], "pagination_required": True})
