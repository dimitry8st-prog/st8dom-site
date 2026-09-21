"""Модели SQLAlchemy: пользователи, заявки и редакционные публикации."""

import re
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class AdminUser(UserMixin, db.Model):
    """Единственная роль входа — администратор сайта."""

    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Inquiry(db.Model):
    """Обращение с публичной формы. Телефон и компания могут быть пустыми."""

    __tablename__ = "inquiries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    company = db.Column(db.String(160), nullable=True)
    topic = db.Column(db.String(80), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    ip_hash = db.Column(db.String(64), nullable=True)

    def mark_read(self) -> None:
        self.is_read = True


article_tags = db.Table(
    "article_tags",
    db.Column(
        "article_id",
        db.Integer,
        db.ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "tag_id",
        db.Integer,
        db.ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Rubric(db.Model):
    """Редакционная рубрика внутри одного из четырёх разделов портала."""

    __tablename__ = "rubrics"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    section = db.Column(db.String(40), nullable=False, index=True)
    description = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    articles = db.relationship("Article", back_populates="rubric", lazy="dynamic")


class Tag(db.Model):
    """Тема для поиска и формирования связанных материалов."""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)


class Article(db.Model):
    """Самостоятельная публикация с управляемым редакционным статусом."""

    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(220), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    summary = db.Column(db.String(600), nullable=False)
    body = db.Column(db.Text, nullable=False)
    section = db.Column(db.String(40), nullable=False, index=True)
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubrics.id"), nullable=False)
    content_type = db.Column(db.String(40), nullable=False, index=True)
    status = db.Column(db.String(24), default="draft", nullable=False, index=True)
    author = db.Column(db.String(120), nullable=False, default="Степанов Д.А.")
    medical_reviewer = db.Column(db.String(120), nullable=True)
    disclaimer = db.Column(db.Text, nullable=True)
    revision_note = db.Column(db.String(500), nullable=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    reviewed_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True, index=True)

    rubric = db.relationship("Rubric", back_populates="articles")
    tags = db.relationship(
        "Tag",
        secondary=article_tags,
        lazy="selectin",
        backref=db.backref("articles", lazy="dynamic"),
    )
    sources = db.relationship(
        "ArticleSource",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="ArticleSource.id",
    )

    @property
    def is_medical(self) -> bool:
        return self.section == "medicine"

    @property
    def is_public(self) -> bool:
        return self.status == "published" and self.published_at is not None

    @property
    def tag_names(self) -> list[str]:
        return [tag.name for tag in self.tags]

    @property
    def cover_image(self) -> str | None:
        return {
            "nighteagle-vredonos-pod-vidom-1c-adobe": "images/material-nighteagle.svg",
            "ne-anthropic-vzlomala-openai-claude-hacktron": "images/material-openai-claude-security.svg",
            "pochemu-ai-agentam-nuzhna-pesochnitsa": "images/material-ai-agent-sandbox.svg",
            "tihokhodki-i-predely-vyzhivaniya": "images/material-tardigrades.svg",
        }.get(self.slug)

    @property
    def cover_display_mode(self) -> str:
        """Return the presentation mode for an article cover."""
        if self.slug == "pochemu-ai-agentam-nuzhna-pesochnitsa":
            return "contain"
        return "cover"

    @property
    def body_paragraphs(self) -> list[str]:
        return [part.strip() for part in self.body.split("\n\n") if part.strip()]

    @property
    def body_blocks(self) -> list[dict]:
        """Разбирает небольшой безопасный поднабор Markdown без сырого HTML."""
        lines = self.body.splitlines()
        blocks = []
        index = 0

        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue

            if line.startswith("### "):
                blocks.append({"type": "heading", "level": 3, "text": line[4:]})
                index += 1
                continue
            if line.startswith("## "):
                blocks.append({"type": "heading", "level": 2, "text": line[3:]})
                index += 1
                continue

            if line.startswith("- "):
                items = []
                while index < len(lines) and lines[index].strip().startswith("- "):
                    items.append(lines[index].strip()[2:].strip())
                    index += 1
                blocks.append({"type": "list", "items": items})
                continue

            if line.startswith("|") and index + 1 < len(lines):
                header = [cell.strip() for cell in line.strip("|").split("|")]
                separator = [
                    cell.strip() for cell in lines[index + 1].strip().strip("|").split("|")
                ]
                if len(header) == len(separator) and all(
                    re.fullmatch(r":?-{3,}:?", cell) for cell in separator
                ):
                    index += 2
                    rows = []
                    while index < len(lines) and lines[index].strip().startswith("|"):
                        row = [
                            cell.strip()
                            for cell in lines[index].strip().strip("|").split("|")
                        ]
                        if len(row) == len(header):
                            rows.append(row)
                        index += 1
                    blocks.append({"type": "table", "header": header, "rows": rows})
                    continue

            paragraph = [line]
            index += 1
            while index < len(lines):
                next_line = lines[index].strip()
                if not next_line:
                    break
                if next_line.startswith(("## ", "### ", "- ", "|")):
                    break
                paragraph.append(next_line)
                index += 1
            blocks.append({"type": "paragraph", "text": " ".join(paragraph)})

        return blocks

    def publication_errors(self) -> list[str]:
        """Возвращает причины, по которым материал нельзя публиковать."""
        errors = []
        required = {
            "заголовок": self.title,
            "адрес": self.slug,
            "краткое описание": self.summary,
            "текст": self.body,
            "раздел": self.section,
            "рубрика": self.rubric_id,
            "тип материала": self.content_type,
            "автор": self.author,
        }
        errors.extend(name for name, value in required.items() if not value)
        if not self.tags:
            errors.append("минимум один тег")
        if self.is_medical:
            if not self.sources:
                errors.append("источник медицинского материала")
            if not self.medical_reviewer:
                errors.append("медицинский редактор")
            if not self.reviewed_at:
                errors.append("дата медицинской проверки")
            if not self.disclaimer:
                errors.append("медицинское предупреждение")
        return errors

    def publish(self) -> list[str]:
        errors = self.publication_errors()
        if errors:
            return errors
        self.status = "published"
        if self.published_at is None:
            self.published_at = utcnow()
        return []

    def unpublish(self) -> None:
        self.status = "ready"


class ArticleSource(db.Model):
    """Проверяемый источник, приложенный к публикации."""

    __tablename__ = "article_sources"
    __table_args__ = (
        db.UniqueConstraint("article_id", "url", name="uq_article_source_url"),
    )

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer,
        db.ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    accessed_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    article = db.relationship("Article", back_populates="sources")


class ImportPackage(db.Model):
    """Журнал идемпотентного импорта черновиков из Life-OS."""

    __tablename__ = "import_packages"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    checksum = db.Column(db.String(64), nullable=False, index=True)
    generator_version = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="imported", index=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    article = db.relationship("Article")


class ClinicalGuideline(db.Model):
    """Метаданные клинической рекомендации из официального источника.

    В таблице хранится только библиографическая карточка и ссылка на оригинал.
    Медицинский пересказ остаётся отдельной редакционной публикацией Article.
    """

    __tablename__ = "clinical_guidelines"
    __table_args__ = (
        db.UniqueConstraint(
            "source_key", "external_id", name="uq_guideline_source_external_id"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(40), nullable=False, index=True)
    source_name = db.Column(db.String(180), nullable=False)
    external_id = db.Column(db.String(160), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    organization = db.Column(db.Text, nullable=True)
    version = db.Column(db.String(80), nullable=True)
    codes = db.Column(db.Text, nullable=True)
    specialties = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(1000), nullable=False)
    published_on = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    content_hash = db.Column(db.String(64), nullable=False, index=True)
    first_seen_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def is_russian(self) -> bool:
        return self.kind == "russian"
