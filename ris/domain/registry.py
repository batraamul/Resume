"""Registry of record kinds: payload model, allowed parents, defaults and form metadata."""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel

from ris.domain import models as m
from ris.domain.enums import Confidentiality, Origin, RecordKind


@dataclass(frozen=True)
class KindInfo:
    kind: RecordKind
    model: type[m.RecordData]
    parents: tuple[RecordKind, ...] = ()
    singleton: bool = False
    #: Default classification for manually created records of this kind.
    default_confidentiality: Confidentiality = Confidentiality.REVIEW
    is_fact: bool = True


REGISTRY: dict[RecordKind, KindInfo] = {
    RecordKind.PERSONAL: KindInfo(RecordKind.PERSONAL, m.PersonalInfo, singleton=True,
                                  default_confidentiality=Confidentiality.APPROVED),
    RecordKind.SUMMARY: KindInfo(RecordKind.SUMMARY, m.Summary, default_confidentiality=Confidentiality.APPROVED),
    RecordKind.POSITION: KindInfo(RecordKind.POSITION, m.Position),
    RecordKind.ASSIGNMENT: KindInfo(RecordKind.ASSIGNMENT, m.Assignment, parents=(RecordKind.POSITION,)),
    RecordKind.BULLET: KindInfo(
        RecordKind.BULLET, m.Bullet,
        parents=(RecordKind.POSITION, RecordKind.ASSIGNMENT, RecordKind.PROJECT, RecordKind.ACTIVITY),
    ),
    RecordKind.EDUCATION: KindInfo(RecordKind.EDUCATION, m.Education, default_confidentiality=Confidentiality.APPROVED),
    RecordKind.PUBLICATION: KindInfo(RecordKind.PUBLICATION, m.Publication,
                                     default_confidentiality=Confidentiality.APPROVED),
    RecordKind.PROJECT: KindInfo(RecordKind.PROJECT, m.Project),
    RecordKind.SKILL: KindInfo(RecordKind.SKILL, m.Skill, default_confidentiality=Confidentiality.APPROVED),
    RecordKind.ACTIVITY: KindInfo(RecordKind.ACTIVITY, m.Activity),
    RecordKind.CUSTOM_SECTION: KindInfo(RecordKind.CUSTOM_SECTION, m.CustomSection,
                                        default_confidentiality=Confidentiality.APPROVED, is_fact=False),
    RecordKind.CUSTOM_ENTRY: KindInfo(RecordKind.CUSTOM_ENTRY, m.CustomEntry, parents=(RecordKind.CUSTOM_SECTION,)),
    RecordKind.CAREER_TARGET: KindInfo(RecordKind.CAREER_TARGET, m.CareerTarget,
                                       default_confidentiality=Confidentiality.APPROVED, is_fact=False),
    RecordKind.VACANCY: KindInfo(RecordKind.VACANCY, m.Vacancy, default_confidentiality=Confidentiality.APPROVED,
                                 is_fact=False),
    RecordKind.VARIANT: KindInfo(RecordKind.VARIANT, m.Variant, default_confidentiality=Confidentiality.APPROVED,
                                 is_fact=False),
    RecordKind.CLAIM: KindInfo(RecordKind.CLAIM, m.Claim, parents=(RecordKind.VARIANT,),
                               default_confidentiality=Confidentiality.APPROVED, is_fact=False),
    RecordKind.APPLICATION: KindInfo(RecordKind.APPLICATION, m.Application,
                                     default_confidentiality=Confidentiality.APPROVED, is_fact=False),
    RecordKind.COVER_LETTER: KindInfo(RecordKind.COVER_LETTER, m.CoverLetter,
                                      default_confidentiality=Confidentiality.APPROVED, is_fact=False),
    RecordKind.EXPERTISE: KindInfo(RecordKind.EXPERTISE, m.Expertise),
    RecordKind.REFERENCE: KindInfo(RecordKind.REFERENCE, m.Reference, default_confidentiality=Confidentiality.APPROVED),
}


def info(kind: RecordKind | str) -> KindInfo:
    return REGISTRY[RecordKind(kind)]


def model_for(kind: RecordKind | str) -> type[m.RecordData]:
    return info(kind).model


def validate_payload(kind: RecordKind | str, data: dict[str, Any] | BaseModel) -> m.RecordData:
    model = model_for(kind)
    if isinstance(data, model):
        return data
    if isinstance(data, BaseModel):
        data = data.model_dump()
    return model.model_validate(data)


def default_confidentiality(kind: RecordKind | str, origin: Origin | str) -> Confidentiality:
    """Classification for a new record.

    Imported and pre-populated information is uncertain, so it defaults to
    *Requires review* whatever the kind. Manually entered records use the
    kind default (work-related records default to *Requires review*).
    """
    origin = Origin(origin)
    if origin in (Origin.IMPORTED, Origin.PRELOADED):
        return Confidentiality.REVIEW
    if origin == Origin.SAMPLE:
        return Confidentiality.APPROVED
    return info(kind).default_confidentiality


# --------------------------------------------------------------------------- form metadata


@dataclass
class FieldMeta:
    name: str
    title: str
    widget: str
    help: str = ""
    group: str = "Details"
    private: bool = False
    hidden: bool = False
    placeholder: str = ""
    ref_kind: str | None = None
    enum_type: type[Enum] | None = None
    optional_enum: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _unwrap_enum(annotation: Any) -> tuple[type[Enum] | None, bool]:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        optional = len(args) < len(typing.get_args(annotation))
        if len(args) == 1 and isinstance(args[0], type) and issubclass(args[0], Enum):
            return args[0], optional
        return None, optional
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation, False
    return None, False


def field_metas(model: type[BaseModel], include_hidden: bool = False) -> list[FieldMeta]:
    """Ordered UI metadata for a payload model's fields."""
    out: list[FieldMeta] = []
    for name, fi in model.model_fields.items():
        extra = dict(fi.json_schema_extra or {}) if isinstance(fi.json_schema_extra, dict) else {}
        hidden = bool(extra.get("hidden"))
        if hidden and not include_hidden:
            continue
        enum_type, optional = _unwrap_enum(fi.annotation)
        widget = str(extra.get("widget", "line"))
        if enum_type is not None:
            widget = "choice"
        out.append(
            FieldMeta(
                name=name,
                title=fi.title or name.replace("_", " ").capitalize(),
                widget=widget,
                help=fi.description or "",
                group=str(extra.get("group", "Details")),
                private=bool(extra.get("private", False)),
                hidden=hidden,
                placeholder=str(extra.get("placeholder", "")),
                ref_kind=extra.get("ref_kind"),
                enum_type=enum_type,
                optional_enum=optional,
                extra=extra,
            )
        )
    # Custom fields always last.
    out.sort(key=lambda f: f.name == "custom")
    return out


def private_fields(model: type[BaseModel]) -> set[str]:
    return {f.name for f in field_metas(model, include_hidden=True) if f.private}
