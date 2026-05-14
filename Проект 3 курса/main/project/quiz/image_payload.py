"""Сбор URL изображений вопроса (legacy + галерея) для HTTP и WebSocket."""

MAX_QUESTION_IMAGES = 4


def media_url_for_client(scope, storage_url):
    if not storage_url:
        return None
    s = str(storage_url).strip()
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    headers = {k.decode().lower(): v.decode() for k, v in (scope.get("headers") or [])}
    host = headers.get("host") or "127.0.0.1:8000"
    xf = (headers.get("x-forwarded-proto") or "").lower()
    if xf in ("http", "https"):
        scheme = xf
    else:
        asg_scheme = (scope.get("scheme") or "").lower()
        scheme = "https" if asg_scheme in ("https", "wss") else "http"
    if not s.startswith("/"):
        s = "/" + s
    return f"{scheme}://{host}{s}"


def iter_question_image_relative_urls(question):
    """Относительные URL; не более MAX_QUESTION_IMAGES штук (сначала устаревшее поле, затем галерея по id)."""
    n = 0
    if getattr(question, "image", None) and getattr(question.image, "name", None):
        try:
            yield question.image.url
            n += 1
        except ValueError:
            pass
    rel = getattr(question, "gallery_images", None)
    if rel is None:
        return
    for gi in rel.all().order_by("id"):
        if n >= MAX_QUESTION_IMAGES:
            break
        if gi.image and getattr(gi.image, "name", None):
            try:
                yield gi.image.url
                n += 1
            except ValueError:
                continue


def question_image_urls_for_scope(scope, question):
    return [media_url_for_client(scope, u) for u in iter_question_image_relative_urls(question)]


def question_image_urls_for_request(request, question):
    return [request.build_absolute_uri(u) for u in iter_question_image_relative_urls(question)]
