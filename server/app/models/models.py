from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, false
from sqlalchemy.orm import relationship
from app.db.database import Base


def _utcnow():
    """Timezone-aware UTC datetime. Replaces deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="student")  # "student" | "curator" | "moderator" | "admin"
    group_number = Column(String, nullable=True)
    # EIOS idGroup of group_number, set only when EIOS itself reported the group; used for the timetable.
    eios_group_id = Column(Integer, nullable=True)
    # Stable user ID returned by EIOS; binds the local account to one EIOS identity.
    sdo_id = Column(String, nullable=True)
    # "eios" for accounts created by EIOS SSO, "local" for the env-configured administrator.
    auth_source = Column(String, nullable=False, default="eios", server_default="eios")
    is_blocked = Column(Boolean, nullable=False, default=False, server_default=false())
    # Profile picture URL reported by EIOS, refreshed on every login.
    avatar_url = Column(String, nullable=True)
    # When the student last agreed to personal data processing at sign-in, and to which text version
    pd_consent_at = Column(DateTime(timezone=True), nullable=True)
    pd_consent_version = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    questions = relationship("ForumQuestion", back_populates="author", cascade="all, delete-orphan")
    answers = relationship("ForumAnswer", back_populates="author", cascade="all, delete-orphan")
    votes = relationship("Vote", back_populates="user", cascade="all, delete-orphan")


class ForumQuestion(Base):
    __tablename__ = "forum_questions"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, index=True, nullable=False)
    category = Column(String, default="Учеба")
    content = Column(Text, nullable=False)
    views_count = Column(Integer, default=0)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    author = relationship("User", back_populates="questions")
    answers = relationship("ForumAnswer", back_populates="question", cascade="all, delete-orphan")
    votes = relationship("Vote", back_populates="question", cascade="all, delete-orphan")


class ForumAnswer(Base):
    __tablename__ = "forum_answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("forum_questions.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_solution = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    question = relationship("ForumQuestion", back_populates="answers")
    author = relationship("User", back_populates="answers")


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("forum_questions.id"), nullable=False)
    vote_type = Column(Integer, nullable=False)  # 1 = upvote, -1 = downvote

    # FIX: Unique constraint prevents duplicate votes (one user — one vote per question)
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_vote_user_question"),
    )

    user = relationship("User", back_populates="votes")
    question = relationship("ForumQuestion", back_populates="votes")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    department = Column(String, nullable=False)
    role = Column(String, nullable=False)
    email = Column(String, nullable=True)
    office = Column(String, default="Б-209")
    hours = Column(String, nullable=True)
    courses = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    is_important = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class FaqItem(Base):
    __tablename__ = "faq_items"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String, nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String, default="Общие")
    order_index = Column(Integer, default=0)


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    subject_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    short_name = Column(String, nullable=False)
    emoji = Column(String, default="📚")
    color = Column(String, default="#007AFF")
    difficulty = Column(Integer, default=3)
    hours = Column(Integer, default=108)
    credits = Column(Integer, default=3)
    semester = Column(Integer, default=1)
    control_type = Column(String, default="Зачет")
    extra_type = Column(String, nullable=True)
    description = Column(Text, nullable=False)
    mascot_hack = Column(Text, nullable=True)
    senior_advice = Column(Text, nullable=True)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, index=True, nullable=False)
    revoked_at = Column(DateTime(timezone=True), default=_utcnow)
