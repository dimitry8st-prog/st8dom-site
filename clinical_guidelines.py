"""Синхронизация карточек клинических рекомендаций из официальных источников."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from extensions import db
from models import ClinicalGuideline


MINZDRAV_API_URL = (
    "https://apicr.minzdrav.gov.ru/api.ashx?op=GetJsonClinrecsFilterV2"
)
MINZDRAV_VIEW_URL = "https://cr.minzdrav.gov.ru/view-cr/{code_version}"

OFFICIAL_SOURCES = {
    "minzdrav": {
        "name": "Рубрикатор клинических рекомендаций Минздрава России",
        "kind": "russian",
        "domains": {"cr.minzdrav.gov.ru", "apicr.minzdrav.gov.ru"},
    },
    "aan": {
        "name": "American Academy of Neurology",
        "kind": "international",
        "domains": {"aan.com", "www.aan.com"},
    },
    "ean": {
        "name": "European Academy of Neurology",
        "kind": "international",
        "domains": {"ean.org", "www.ean.org"},
    },
    "eso": {
        "name": "European Stroke Organisation",
        "kind": "international",
        "domains": {"eso-stroke.org", "www.eso-stroke.org"},
    },
    "cns": {
        "name": "Congress of Neurological Surgeons",
        "kind": "international",
        "domains": {"cns.org", "www.cns.org"},
    },
    "aans": {
        "name": "American Association of Neurological Surgeons",
        "kind": "international",
        "domains": {"aans.org", "www.aans.org"},
    },
    "nice": {
        "name": "National Institute for Health and Care Excellence",
        "kind": "international",
        "domains": {"nice.org.uk", "www.nice.org.uk"},
    },
    "ahs": {
        "name": "American Headache Society",
        "kind": "international",
        "domains": {"headachejournal.onlinelibrary.wiley.com", "www.neurology.org", "neurology.org"},
    },
    "ihs": {
        "name": "International Headache Society",
        "kind": "international",
        "domains": {"journals.sagepub.com", "ihs-headache.org", "www.ihs-headache.org"},
    },
    "ehf": {
        "name": "European Headache Federation",
        "kind": "international",
        "domains": {"pubmed.ncbi.nlm.nih.gov", "thejournalofheadacheandpain.biomedcentral.com"},
    },
    "bash": {
        "name": "British Association for the Study of Headache",
        "kind": "international",
        "domains": {"bash.org.uk", "www.bash.org.uk"},
    },
    "who": {
        "name": "World Health Organization",
        "kind": "international",
        "domains": {"who.int", "www.who.int"},
    },
    "aha_asa": {
        "name": "American Heart Association / American Stroke Association",
        "kind": "international",
        "domains": {
            "professional.heart.org",
            "ahajournals.org",
            "www.ahajournals.org",
        },
    },
}

# Сначала смотрим на название документа. Это намеренно строже, чем поиск
# любого кода G/F/I в списке МКБ: смежная рекомендация должна быть посвящена
# неврологической/нейрохирургической проблеме, а не просто содержать её как
# сопутствующее состояние.
NEURO_TITLE_TERMS = (
    "неврол",
    "нейрохир",
    "нервной систем",
    "головная боль",
    "мигрень",
    "кластерн",
    "инсульт",
    "инфаркт мозга",
    "церебр",
    "субарахноид",
    "внутричереп",
    "головного мозга",
    "спинного мозга",
    "черепно-мозг",
    "сотрясен",
    "эпилеп",
    "паркинсон",
    "деменц",
    "альцгеймер",
    "рассеянн",
    "миастен",
    "мононевроп",
    "полинейроп",
    "нейропат",
    "радикул",
    "позвоноч",
    "межпозвон",
    "гидроцеф",
    "аневризм",
    "нейроонк",
    "глиом",
    "менингиом",
    "шванном",
    "нейрофибром",
    "менингит",
    "энцефалит",
    "нейроинф",
    "мышечная дистроф",
    "мышечные дистроф",
    "спинальная мышечная атроф",
    "амиотроф",
    "мотонейрон",
    "атакси",
    "дистони",
    "хоре",
    "сирингомиел",
    "церебральный паралич",
    "детский церебральный паралич",
    "болезнь вильсона",
)

# Узкий резервный список кодов для документов, название которых может быть
# коротким, но профиль однозначно нейрохирургический/неврологический.
NEURO_CODE_PREFIXES = (
    "G00", "G01", "G02", "G03", "G04", "G05", "G06", "G08",
    "G10", "G11", "G12", "G20", "G21", "G23", "G24", "G25",
    "G30", "G31", "G35", "G36", "G37", "G40", "G41", "G43", "G44",
    "G50", "G51", "G52", "G53", "G54", "G55", "G56", "G57", "G58", "G59",
    "G60", "G61", "G62", "G63", "G64", "G70", "G71", "G72", "G73",
    "G80", "G81", "G82", "G83", "G90", "G91", "G92", "G93", "G94", "G95", "G96", "G97",
    "I60", "I61", "I62", "I63", "I64", "I65", "I66", "I67", "I68", "I69",
    "S06", "C70", "C71", "C72", "D32", "D33", "Q00", "Q01", "Q02", "Q03", "Q04", "Q05", "Q06",
)

NEURO_DEVELOPER_TERMS = (
    "общество невролог",
    "ассоциация невролог",
    "нейрохирург",
    "нейрорадиолог",
    "нервно-мышеч",
    "клинической нейрофизиолог",
    "головной боли",
)


class GuidelineValidationError(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_hash(data: dict) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise GuidelineValidationError("published_on: ожидается дата ГГГГ-ММ-ДД.")
    raw = value[:10]
    for parser in (
        date.fromisoformat,
        lambda item: datetime.strptime(item, "%d.%m.%Y").date(),
    ):
        try:
            return parser(raw)
        except ValueError:
            continue
    raise GuidelineValidationError("published_on: ожидается дата ГГГГ-ММ-ДД или ДД.ММ.ГГГГ.")


def _clean_text(value, field: str, maximum: int, required: bool = False) -> str | None:
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str):
        raise GuidelineValidationError(f"{field}: ожидается строка.")
    value = " ".join(value.split())
    if required and len(value) < 2:
        raise GuidelineValidationError(f"{field}: значение слишком короткое.")
    if len(value) > maximum:
        raise GuidelineValidationError(f"{field}: превышена длина {maximum} символов.")
    return value


def _official_url(source_key: str, value: str) -> str:
    if not isinstance(value, str) or len(value) > 1000:
        raise GuidelineValidationError("url: нужен полный адрес официального источника.")
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_SOURCES[source_key]["domains"]:
        raise GuidelineValidationError("url: домен не входит в список официальных источников.")
    return value.strip()


def is_neurology_or_neurosurgery(item: dict) -> bool:
    """Отбирает только профильные и действительно смежные рекомендации.

    Не считаем документ неврологическим только потому, что среди множества
    диагнозов встречается один код G/F/I или в МКБ-описании есть слово
    «неврологический». Основной сигнал — название рекомендации.
    """
    title = str(item.get("Name") or "").casefold()
    if any(term in title for term in NEURO_TITLE_TERMS):
        return True

    codes = [
        str(row.get("MkbCode") or "").upper().replace(" ", "")
        for row in item.get("Mkbs") or []
        if row.get("MkbCode")
    ]
    if not codes:
        return False

    neuro_codes = [
        code for code in codes
        if code.startswith(NEURO_CODE_PREFIXES)
    ]
    if not neuro_codes:
        return False

    # Кодовый fallback допускается только при профильном разработчике и когда
    # значимая часть кодов документа относится к неврологии/нейрохирургии.
    developers = " ".join(
        str(row.get("NkoName") or "") for row in item.get("Developers") or []
    ).casefold()
    has_neuro_developer = any(term in developers for term in NEURO_DEVELOPER_TERMS)
    neuro_share = len(neuro_codes) / len(codes)
    return has_neuro_developer and neuro_share >= 0.5


def fetch_minzdrav_page(
    *, current_page: int = 1, timeout: int = 35, page_size: int = 25,
    request_post=requests.post,
) -> dict:
    """Получает одну небольшую страницу, чтобы медленный источник не блокировал сайт."""
    payload = {
            "filters": [
                {
                    "fieldName": "status",
                    "filterType": 1,
                    "filterValueType": 2,
                    "value1": 0,
                    "value2": "",
                    "values": [],
                }
            ],
            "sortOption": {"fieldName": "publishdate", "sortType": 2},
            "pageSize": page_size,
            "currentPage": current_page,
            "useANDoperator": True,
            "columns": [],
        }
    last_error = None
    for _attempt in range(2):
        try:
            response = request_post(
                MINZDRAV_API_URL,
                json=payload,
                headers={"Accept": "application/json", "User-Agent": "DIS-ClinicalGuidelines/1.0"},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data.get("Data"), list):
                raise RuntimeError("Минздрав вернул ответ без списка Data.")
            return data
        except requests.RequestException as exc:
            last_error = exc
    raise last_error or RuntimeError("Официальный источник Минздрава недоступен.")


def fetch_minzdrav_guidelines(
    *, timeout: int = 35, page_size: int = 25, request_post=requests.post
) -> list[dict]:
    """Получает всю историю постранично; предназначено для первичного backfill."""
    records: list[dict] = []
    current_page = 1
    while True:
        data = fetch_minzdrav_page(
            current_page=current_page,
            timeout=timeout,
            page_size=page_size,
            request_post=request_post,
        )
        page = data.get("Data")
        records.extend(page)
        total = int(data.get("TotalRecords") or len(records))
        if not page or len(records) >= total:
            break
        current_page += 1
        if current_page > 20:
            raise RuntimeError("Синхронизация Минздрава остановлена: слишком много страниц.")
    return records


def _minzdrav_payload(item: dict) -> dict:
    code_version = str(item.get("CodeVersion") or "").strip()
    if not code_version:
        raise GuidelineValidationError("Минздрав: отсутствует CodeVersion.")
    developers = ", ".join(
        row.get("NkoName", "").strip()
        for row in item.get("Developers") or []
        if row.get("NkoName")
    )
    codes = ", ".join(
        row.get("MkbCode", "").strip()
        for row in item.get("Mkbs") or []
        if row.get("MkbCode")
    )
    return {
        "source_key": "minzdrav",
        "external_id": code_version,
        "title": str(item.get("Name") or "").strip(),
        "organization": developers,
        "version": str(item.get("Version") or ""),
        "codes": codes,
        "specialties": "Неврология / нейрохирургия",
        "url": MINZDRAV_VIEW_URL.format(code_version=code_version),
        "published_on": str(item.get("PublishDateStr") or "")[:10] or None,
        "status": "active" if int(item.get("Status") or 0) == 0 else "inactive",
    }


def upsert_guideline(payload: dict) -> tuple[ClinicalGuideline, str]:
    """Проверяет и идемпотентно создаёт или обновляет одну карточку."""
    if not isinstance(payload, dict):
        raise GuidelineValidationError("Ожидается JSON-объект.")
    source_key = str(payload.get("source_key") or "").strip().lower()
    if source_key not in OFFICIAL_SOURCES:
        raise GuidelineValidationError("source_key: источник не разрешён.")
    source = OFFICIAL_SOURCES[source_key]
    external_id = _clean_text(payload.get("external_id"), "external_id", 160, True)
    title = _clean_text(payload.get("title"), "title", 500, True)
    url = _official_url(source_key, payload.get("url"))
    normalized = {
        "source_key": source_key,
        "external_id": external_id,
        "title": title,
        "organization": _clean_text(payload.get("organization"), "organization", 2000),
        "version": _clean_text(payload.get("version"), "version", 80),
        "codes": _clean_text(payload.get("codes"), "codes", 2000),
        "specialties": _clean_text(payload.get("specialties"), "specialties", 1000),
        "url": url,
        "published_on": _parse_date(payload.get("published_on")),
        "status": str(payload.get("status") or "active").strip().lower(),
    }
    if normalized["status"] not in {"active", "inactive", "replaced"}:
        raise GuidelineValidationError("status: допустимы active, inactive или replaced.")
    hash_input = {**normalized, "published_on": str(normalized["published_on"] or "")}
    content_hash = _canonical_hash(hash_input)
    record = ClinicalGuideline.query.filter_by(
        source_key=source_key, external_id=external_id
    ).first()
    now = utcnow()
    if record is None:
        record = ClinicalGuideline(
            source_key=source_key,
            source_name=source["name"],
            kind=source["kind"],
            content_hash=content_hash,
            first_seen_at=now,
            last_seen_at=now,
            **{key: value for key, value in normalized.items() if key != "source_key"},
        )
        db.session.add(record)
        return record, "created"
    record.last_seen_at = now
    if record.content_hash == content_hash:
        return record, "unchanged"
    for key, value in normalized.items():
        if key != "source_key":
            setattr(record, key, value)
    record.source_name = source["name"]
    record.kind = source["kind"]
    record.content_hash = content_hash
    return record, "updated"


def sync_minzdrav(items: list[dict] | None = None) -> dict[str, int]:
    """Синхронизирует российские профильные карточки и возвращает статистику."""
    items = fetch_minzdrav_guidelines() if items is None else items
    stats = {"scanned": len(items), "matched": 0, "created": 0, "updated": 0, "unchanged": 0}
    for item in items:
        if not item.get("NPC_approved") or not is_neurology_or_neurosurgery(item):
            continue
        stats["matched"] += 1
        _record, action = upsert_guideline(_minzdrav_payload(item))
        stats[action] += 1
    db.session.commit()
    return stats


def sync_guidelines_registry(path: str | Path) -> dict[str, int]:
    """Загружает в БД публичные карточки из версионируемого GitHub-реестра."""
    registry_path = Path(path)
    if not registry_path.exists():
        return {"scanned": 0, "created": 0, "updated": 0, "unchanged": 0}
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise GuidelineValidationError("Реестр рекомендаций должен содержать список items.")
    stats = {"scanned": len(items), "created": 0, "updated": 0, "unchanged": 0}
    for item in items:
        _record, action = upsert_guideline(item)
        stats[action] += 1
    db.session.commit()
    return stats


def public_guidelines_query():
    return ClinicalGuideline.query.filter(ClinicalGuideline.status == "active")
