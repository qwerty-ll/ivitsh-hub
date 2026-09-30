from datetime import date, datetime
from typing import Any, Dict, Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- User & Auth Schemas ---
class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=128)

class EiosLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=128)
    group_number: Optional[str] = Field(None, max_length=50)
    # The "I agree to personal data processing" box at sign-in; nothing is sent to EIOS without it
    consent: bool = False

class UserUpdateProfile(BaseModel):
    group_number: Optional[str] = Field(None, max_length=50)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    group_number: Optional[str] = None
    eios_group_id: Optional[int] = None
    email: Optional[str] = None
    userpictureurl: Optional[str] = None
    auth_source: str = "eios"
    is_blocked: bool = False
    created_at: datetime

class LoginResponse(BaseModel):
    # The JWT is only delivered as an httpOnly cookie so page scripts can never read it.
    user: UserResponse

class RoleUpdateSchema(BaseModel):
    role: Literal["student", "curator", "moderator", "admin"]

class BlockUpdateSchema(BaseModel):
    blocked: bool

# --- Forum Schemas ---
class ForumAnswerCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)

class ForumAnswerResponse(BaseModel):
    id: int
    question_id: int
    author_id: int
    author_name: str
    content: str
    is_solution: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ForumQuestionCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    category: str = Field("Учеба", max_length=100)
    content: str = Field(..., min_length=10, max_length=20000)

class ForumQuestionResponse(BaseModel):
    id: int
    author_id: int
    author_name: str
    title: str
    category: str
    content: str
    views_count: int
    votes_count: int
    answers_count: int
    user_vote: Optional[int] = 0
    is_pinned: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class VoteRequest(BaseModel):
    vote_type: int

    # FIX: Only allow valid vote values: 1 (upvote) or -1 (downvote)
    @field_validator("vote_type")
    @classmethod
    def validate_vote_type(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("vote_type must be 1 (upvote) or -1 (downvote)")
        return v

# --- Admin Content Schemas ---
class TeacherCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    department: str = Field(..., max_length=200)
    role: str = Field(..., max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    office: Optional[str] = Field("Б-209", max_length=50)
    hours: Optional[str] = Field(None, max_length=200)
    courses: Optional[str] = Field(None, max_length=500)
    photo_url: Optional[str] = Field(None, max_length=500)

class TeacherResponse(TeacherCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1, max_length=5000)
    is_important: Optional[bool] = False

class AnnouncementResponse(AnnouncementCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FaqItemCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=5000)
    category: Optional[str] = Field("Общие", max_length=100)
    order_index: Optional[int] = 0

class FaqItemResponse(FaqItemCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

class SubjectCreate(BaseModel):
    subject_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=300)
    short_name: str = Field(..., min_length=1, max_length=100)
    emoji: Optional[str] = Field("📚", max_length=10)
    color: Optional[str] = Field("#007AFF", max_length=20)
    difficulty: Optional[int] = Field(3, ge=1, le=5)
    hours: Optional[int] = Field(108, ge=1)
    credits: Optional[int] = Field(3, ge=1)
    semester: Optional[int] = Field(1, ge=1, le=12)
    control_type: Optional[str] = Field("Зачет", max_length=50)
    extra_type: Optional[str] = Field(None, max_length=50)
    description: str = Field(..., min_length=1, max_length=5000)
    mascot_hack: Optional[str] = Field(None, max_length=2000)
    senior_advice: Optional[str] = Field(None, max_length=2000)

class SubjectResponse(SubjectCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

# --- Chatbot Schemas ---
class ChatMessageTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=2000)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    history: Optional[List[ChatMessageTurn]] = Field(default_factory=list, max_length=20)
    # Group picked in the dashboard schedule; used when the student's own group is unknown
    group: Optional[str] = Field(None, max_length=50)

class ChatAction(BaseModel):
    label: str
    to: str  # an in-portal path such as "/map?room=Б-407"

class ChatResponse(BaseModel):
    reply: str
    actions: List[ChatAction] = Field(default_factory=list)
    # A document ВИТШик prepared: {"kind", "fields", "options"}, shown as a card to check and download
    document: Optional[Dict[str, Any]] = None


# --- Documents (explanatory note, retake request) ---
_PERSON_NAME = r"^[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z' .-]*$"


class DocumentPerson(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=120, pattern=_PERSON_NAME)
    group: str = Field(..., min_length=1, max_length=50)
    course: Optional[int] = Field(None, ge=1, le=6)

    @field_validator("full_name")
    @classmethod
    def _two_words(cls, value: str) -> str:
        if len(value.split()) < 2:
            raise ValueError("Укажите фамилию и имя")
        return value


class MissedPairIn(BaseModel):
    start: str = Field(..., pattern=r"^\d{1,2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{1,2}:\d{2}$")
    discipline: str = Field(..., min_length=1, max_length=200)
    kind: str = Field("", max_length=40)
    teacher: str = Field("", max_length=100)


class ExplanatoryIn(DocumentPerson):
    date_from: date
    date_to: Optional[date] = None
    reason: str = Field(..., min_length=2, max_length=300)
    pairs: List[MissedPairIn] = Field(default_factory=list, max_length=12)
    attachment: str = Field("", max_length=200)


class RetakeIn(DocumentPerson):
    discipline: str = Field(..., min_length=2, max_length=200)
    control: Literal["экзамен", "зачёт", "дифференцированный зачёт"]
    teacher: str = Field("", max_length=100)
    reason: str = Field(..., min_length=3, max_length=300)
