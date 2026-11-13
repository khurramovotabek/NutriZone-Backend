"""core.http_pool: one pooled Session per thread, and patched requests.post/get still intercept the calls."""
import threading
from unittest import mock

from core import http_pool


def test_session_is_reused_within_a_thread_and_separate_per_thread():
    first = http_pool.session()
    assert http_pool.session() is first
    other = []
    t = threading.Thread(target=lambda: other.append(http_pool.session()))
    t.start()
    t.join()
    assert other[0] is not first


def test_patched_requests_post_and_get_still_receive_the_call():
    with mock.patch("requests.post") as post, mock.patch("requests.get") as get:
        http_pool.post("https://api.telegram.org/botX/sendMessage", json={"a": 1}, timeout=5)
        http_pool.get("https://api.telegram.org/botX/getFile", params={"file_id": "f"}, timeout=5)
    post.assert_called_once_with("https://api.telegram.org/botX/sendMessage", json={"a": 1}, timeout=5)
    get.assert_called_once_with("https://api.telegram.org/botX/getFile", params={"file_id": "f"}, timeout=5)


def test_unpatched_call_goes_through_the_pooled_session():
    with mock.patch.object(http_pool.session(), "post") as pooled:
        http_pool.post("https://api.telegram.org/botX/getMe", timeout=5)
    pooled.assert_called_once_with("https://api.telegram.org/botX/getMe", timeout=5)
