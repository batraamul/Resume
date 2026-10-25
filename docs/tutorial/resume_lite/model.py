"""Step 1 — the data model: what a resume contains, with validation."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

DATE = re.compile(r"^\d{4}(-\d{2})?$")   # "2019" or "2019-04"


class Job(BaseModel):
    title: str
    organisation: str
    start: str
    end: str = ""                                   # empty means "present"
    achievements: list[str] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def check_date(cls, value: str) -> str:
        if value and not DATE.match(value):
            raise ValueError("use YYYY or YYYY-MM, for example 2019-04")
        return value


class Profile(BaseModel):
    name: str
    email: str = ""
    headline: str = ""
    summary: str = ""
    jobs: list[Job] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        if value and "@" not in value:
            raise ValueError("this is not an email address")
        return value
