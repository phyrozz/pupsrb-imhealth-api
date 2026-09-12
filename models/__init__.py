from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Profile:
    id: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    is_student: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class PersonalDetails:
    user_id: str
    email: str
    first_name: str
    last_name: str
    student_number: str
    birth_date: str
    year: int
    middle_name: Optional[str] = None
    name_suffix: Optional[str] = None
    program_id: Optional[int] = None
    marital_status_id: Optional[int] = None
    is_working_student: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Assessment:
    id: Optional[int] = None
    user_id: Optional[str] = None
    responses: list = field(default_factory=list)
    created_at: Optional[datetime] = None


@dataclass
class AprioriResult:
    id: Optional[int] = None
    assessment_id: Optional[int] = None
    user_id: Optional[str] = None
    apriori_result: Optional[int] = None
    counseling_status_id: Optional[int] = None
    created_at: Optional[datetime] = None
