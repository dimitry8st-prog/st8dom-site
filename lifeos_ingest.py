"""Контракт приёма анонсов MIT. Ссылки сохраняются, сервер их не загружает."""
from urllib.parse import urlsplit

from lifeos_workspace import SCIENCE_STREAMS, normalize_url


def validate_mit_batch(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("materials"), list):
        raise ValueError("Нужен объект materials со списком материалов.")
    if len(payload["materials"]) > 100:
        raise ValueError("Не более 100 материалов в пакете.")
    records = []
    for row in payload["materials"]:
        if not isinstance(row, dict):
            raise ValueError("Материал должен быть объектом.")
        fields = {}
        for key, maximum in (("title", 500), ("source_url", 1500), ("summary", 2000), ("published_date", 100)):
            value = row.get(key, "")
            if not isinstance(value, str) or len(value) > maximum:
                raise ValueError(f"Некорректное поле {key}.")
            fields[key] = value.strip()
        if not fields["title"]:
            raise ValueError("Нужен заголовок.")
        url = normalize_url(fields["source_url"])
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "news.mit.edu":
            raise ValueError("Допустим только источник https://news.mit.edu/.")
        fields["source_url"] = url
        stream = row.get("stream")
        if not isinstance(stream, str) or stream not in SCIENCE_STREAMS:
            raise ValueError("Неизвестный научный поток.")
        fields.update(stream=stream, evidence="Анонс MIT News — требует проверки")
        records.append(fields)
    return records
