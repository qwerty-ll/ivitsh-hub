import re
from datetime import date, datetime, timezone
from typing import Annotated, Any, Dict, Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator


# --- Contacts a student shares with association leaders ---
# VK is accepted as a link or a bare name and stored as the bare name ("id12345", "ivan.petrov").
_VK_PREFIX = re.compile(r"^(?:https?://)?(?:m\.|www\.)?vk\.(?:com|ru)/|^@", re.IGNORECASE)
_VK_NAME = re.compile(r"^[A-Za-z0-9_.]{2,50}$")
_UNSAFE_TEXT = re.compile(r"[<>\x00-\x1f]")


def normalize_vk(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = _VK_PREFIX.sub("", value.strip()).strip("/")
    if not value:
        return ""
    if not _VK_NAME.match(value):
        raise ValueError("ВКонтакте: укажите ссылку на страницу, например vk.com/id12345")
    return value


def normalize_max(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if _UNSAFE_TEXT.search(value):
        raise ValueError("Max: недопустимые символы")
    return value

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
    # None leaves a contact as is, "" clears it
    vk_url: Optional[str] = Field(None, max_length=100)
    max_contact: Optional[str] = Field(None, max_length=64)

    @field_validator("vk_url")
    @classmethod
    def clean_vk(cls, v: Optional[str]) -> Optional[str]:
        return normalize_vk(v)

    @field_validator("max_contact")
    @classmethod
    def clean_max(cls, v: Optional[str]) -> Optional[str]:
        return normalize_max(v)

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
    vk_url: Optional[str] = None
    max_contact: Optional[str] = None
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


# --- Associations ---
class PersonContacts(BaseModel):
    """A person as shown in association pages; contacts are empty for viewers not allowed to see them."""
    user_id: int
    full_name: str
    group_number: Optional[str] = None
    vk_url: Optional[str] = None
    max_contact: Optional[str] = None


class MemberItem(PersonContacts):
    role: Literal["member", "leader"]
    status: Literal["pending", "approved", "rejected", "left"]
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None


class AssociationItem(BaseModel):
    id: int
    name: str
    description: str = ""
    contacts: Optional[str] = None
    leaders: List[PersonContacts] = []
    listed_leader: Optional[str] = None
    member_count: int = 0
    # The viewer's own place in it (None for guests and non-members)
    my_role: Optional[str] = None
    my_status: Optional[str] = None


class AssociationDetail(AssociationItem):
    can_manage: bool = False
    # Filled only for its leaders and administrators
    members: List[MemberItem] = []
    applications: List[MemberItem] = []


class AssociationApply(BaseModel):
    message: Optional[str] = Field(None, max_length=300)

    @field_validator("message")
    @classmethod
    def clean_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if _UNSAFE_TEXT.search(v.replace("\n", " ")):
            raise ValueError("Недопустимые символы в сообщении")
        return v or None


class MembershipDecision(BaseModel):
    approve: bool


class AssociationLeaderEdit(BaseModel):
    description: str = Field("", max_length=3000)
    contacts: Optional[str] = Field(None, max_length=200)


class AssociationAdminIn(AssociationLeaderEdit):
    name: str = Field(..., min_length=2, max_length=100)
    leader_hint: Optional[str] = Field(None, max_length=200)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Название слишком короткое")
        return v


class UserBrief(BaseModel):
    id: int
    full_name: str
    group_number: Optional[str] = None


class AssociationAdminItem(BaseModel):
    id: int
    name: str
    description: str = ""
    contacts: Optional[str] = None
    leader_hint: Optional[str] = None
    is_active: bool = True
    leaders: List[UserBrief] = []
    member_count: int = 0
    pending_count: int = 0
    # Signed-in users whose name matches leader_hint, for a one-click assignment
    hint_matches: List[UserBrief] = []


class MyMembership(BaseModel):
    association_id: int
    association_name: str
    role: str
    status: str
    created_at: Optional[datetime] = None


# --- Tasks ---
def as_utc(value: datetime) -> datetime:
    # SQLite gives back naive datetimes; everything is stored in UTC
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# A datetime sent to the client always carries its offset, so the browser shows local (Moscow) time
UtcDateTime = Annotated[datetime, PlainSerializer(lambda v: as_utc(v).isoformat(), return_type=str)]

TaskStatus = Literal["todo", "in_progress", "review", "done"]
TaskColor = Literal["blue", "green", "amber", "pink", "violet", "slate"]


def _clean_title(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("Введите название")
    return value


def _utc_or_none(value: Optional[datetime]) -> Optional[datetime]:
    return as_utc(value).astimezone(timezone.utc) if value else None


class AssociationRef(BaseModel):
    id: int
    name: str


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=5000)
    due_at: Optional[datetime] = None
    # Personal task when absent; then color applies
    association_id: Optional[int] = None
    color: Optional[TaskColor] = None
    # Association tasks: everyone in it, or the listed members
    to_all: bool = False
    assignee_ids: List[int] = Field(default_factory=list, max_length=500)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean_title(v)

    @field_validator("due_at")
    @classmethod
    def aware_due(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _utc_or_none(v)


class TaskEdit(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=5000)
    due_at: Optional[datetime] = None
    color: Optional[TaskColor] = None
    # Association tasks: members to add (existing assignees keep their progress)
    add_assignee_ids: List[int] = Field(default_factory=list, max_length=500)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean_title(v)

    @field_validator("due_at")
    @classmethod
    def aware_due(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _utc_or_none(v)


class TaskStatusIn(BaseModel):
    status: TaskStatus
    # A leader moves someone else's card; omitted = my own
    user_id: Optional[int] = None


class TaskCard(BaseModel):
    """A card on my board: the task and where my copy of it is."""
    id: int
    title: str
    due_at: Optional[UtcDateTime] = None
    color: Optional[str] = None
    association: Optional[AssociationRef] = None
    my_status: TaskStatus
    comments_count: int = 0
    attachments_count: int = 0
    assignees_count: int = 1


class AssigneeItem(BaseModel):
    user_id: int
    full_name: str
    group_number: Optional[str] = None
    status: TaskStatus
    status_changed_at: Optional[UtcDateTime] = None
    completed_at: Optional[UtcDateTime] = None
    vk_url: Optional[str] = None
    max_contact: Optional[str] = None


class ManagedTask(BaseModel):
    """A task a leader set: how far the assignees got."""
    id: int
    title: str
    due_at: Optional[UtcDateTime] = None
    association: AssociationRef
    counts: Dict[str, int]
    total: int
    created_at: Optional[UtcDateTime] = None


class CommentItem(BaseModel):
    id: int
    author_id: int
    author_name: str
    text: str
    created_at: Optional[UtcDateTime] = None
    can_delete: bool = False


class AttachmentItem(BaseModel):
    id: int
    kind: Literal["file", "link"]
    title: str
    url: Optional[str] = None
    size: Optional[int] = None
    uploaded_by: Optional[str] = None
    created_at: Optional[UtcDateTime] = None
    can_delete: bool = False


class TaskDetail(BaseModel):
    id: int
    title: str
    description: str = ""
    due_at: Optional[UtcDateTime] = None
    color: Optional[str] = None
    association: Optional[AssociationRef] = None
    created_by: Optional[str] = None
    created_at: Optional[UtcDateTime] = None
    can_manage: bool = False
    my_status: Optional[TaskStatus] = None
    # All of them for its managers, only mine for an assignee
    assignees: List[AssigneeItem] = []
    comments: List[CommentItem] = []
    attachments: List[AttachmentItem] = []


class CommentIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def clean_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Пустой комментарий")
        return v


class LinkIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=1000)
    title: str = Field("", max_length=200)

    @field_validator("url")
    @classmethod
    def http_only(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^https?://[^\s<>\"]+$", v, re.IGNORECASE):
            raise ValueError("Ссылка должна начинаться с http:// или https://")
        return v


# --- Association announcements ---
class PostIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    text: str = Field("", max_length=5000)
    to_all: bool = True
    recipient_ids: List[int] = Field(default_factory=list, max_length=500)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean_title(v)


class PostItem(BaseModel):
    id: int
    title: str
    text: str = ""
    to_all: bool = True
    author: Optional[str] = None
    created_at: Optional[UtcDateTime] = None
    attachments: List[AttachmentItem] = []
    # Only for its association's leaders
    recipients: List[UserBrief] = []
    can_manage: bool = False
