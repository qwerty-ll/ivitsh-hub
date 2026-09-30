from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, false, true
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
    # Contacts the student chose to share: seen by leaders of their associations
    # (and, for a leader, by every signed-in student in the catalog)
    vk_url = Column(String, nullable=True)
    max_contact = Column(String, nullable=True)
    # Last request with a valid session, refreshed at most every few minutes ("active this semester")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    # When the SDO (Moodle) course list was last fetched at sign-in
    sdo_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    questions = relationship("ForumQuestion", back_populates="author", cascade="all, delete-orphan")
    answers = relationship("ForumAnswer", back_populates="author", cascade="all, delete-orphan")
    votes = relationship("Vote", back_populates="user", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


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


class Association(Base):
    """A student association of the institute (club, media team, volunteers...)."""
    __tablename__ = "associations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=False, default="", server_default="")
    # Public contact of the association itself: a chat or community link, a room
    contacts = Column(String, nullable=True)
    # Leader's name from the institute's list, shown to the admin until a real account is assigned
    leader_hint = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    memberships = relationship("Membership", back_populates="association", cascade="all, delete-orphan")


class Membership(Base):
    """A student's application to / place in an association. One row per (user, association)."""
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "association_id", name="uq_membership_user_association"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    association_id = Column(Integer, ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False, default="member", server_default="member")  # "member" | "leader"
    status = Column(String, nullable=False, default="pending", server_default="pending")  # "pending" | "approved" | "rejected" | "left"
    # A short note from the applicant to the leader
    message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # When the application was last decided (approved, rejected, left)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="memberships")
    association = relationship("Association", back_populates="memberships")


TASK_STATUSES = ("todo", "in_progress", "review", "done")


class Task(Base):
    """A task of an association (set by its leader) or a personal one (association_id is null)."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    association_id = Column(Integer, ForeignKey("associations.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="", server_default="")
    due_at = Column(DateTime(timezone=True), nullable=True)
    # Personal tasks only: one of the palette names the client knows ("blue", "green", ...)
    color = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    association = relationship("Association")
    created_by = relationship("User")
    assignees = relationship("TaskAssignee", back_populates="task", cascade="all, delete-orphan")
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan",
                            order_by="TaskComment.created_at")
    attachments = relationship("Attachment", back_populates="task", cascade="all, delete-orphan",
                               order_by="Attachment.created_at")


class TaskAssignee(Base):
    """One person's copy of a task: each assignee moves their own card across the board."""
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_assignee"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="todo", server_default="todo")  # see TASK_STATUSES
    status_changed_at = Column(DateTime(timezone=True), default=_utcnow)
    # When the work was handed in ("На проверке" or "Готово"): on time or late against due_at
    completed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="assignees")
    user = relationship("User")


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    task = relationship("Task", back_populates="comments")
    author = relationship("User")


class AssociationPost(Base):
    """An announcement of an association: to all its members or to the chosen ones."""
    __tablename__ = "association_posts"

    id = Column(Integer, primary_key=True, index=True)
    association_id = Column(Integer, ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=False)
    text = Column(Text, nullable=False, default="", server_default="")
    to_all = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    author = relationship("User")
    recipients = relationship("AssociationPostRecipient", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="post", cascade="all, delete-orphan",
                               order_by="Attachment.created_at")


class AssociationPostRecipient(Base):
    __tablename__ = "association_post_recipients"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_recipient"),)

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("association_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class Attachment(Base):
    """A file (stored on disk in UPLOAD_DIR, never in the DB or git) or a link, on a task, a post,
    an event (orders, thanks) or a manual achievement (a scan)."""
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    post_id = Column(Integer, ForeignKey("association_posts.id", ondelete="CASCADE"), nullable=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)
    achievement_id = Column(Integer, ForeignKey("manual_achievements.id", ondelete="CASCADE"), nullable=True, index=True)
    kind = Column(String, nullable=False)  # "file" | "link"
    # The original file name, or the link's caption
    title = Column(String, nullable=False)
    url = Column(String, nullable=True)
    stored_name = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    task = relationship("Task", back_populates="attachments")
    post = relationship("AssociationPost", back_populates="attachments")
    event = relationship("Event", back_populates="attachments")
    achievement = relationship("ManualAchievement", back_populates="attachments")
    uploaded_by = relationship("User")


class SdoCourse(Base):
    """A course the student is enrolled in on SDO (Moodle): refreshed at every EIOS sign-in."""
    __tablename__ = "sdo_courses"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_sdo_course_user"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Moodle course id: the link is SDO_BASE_URL/course/view.php?id=<course_id>
    course_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)


class Meeting(Base):
    """A meeting of an association: in the calendar of its members, with a summary afterwards."""
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    association_id = Column(Integer, ForeignKey("associations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    place = Column(String, nullable=False, default="", server_default="")
    # What it is about (before) and what was decided (after)
    agenda = Column(Text, nullable=False, default="", server_default="")
    summary = Column(Text, nullable=False, default="", server_default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    association = relationship("Association")
    created_by = relationship("User")
    attendance = relationship("MeetingAttendance", cascade="all, delete-orphan")


class MeetingAttendance(Base):
    """Who was at a meeting, marked by a leader: a row means present."""
    __tablename__ = "meeting_attendance"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_meeting_attendance"),)

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class GroupHomework(Base):
    """Homework, a deadline or a note inside an academic group: every student of the group sees it."""
    __tablename__ = "group_homework"

    id = Column(Integer, primary_key=True, index=True)
    # Normalized group name (lower case, ё→е, no spaces): SQLite cannot fold Cyrillic case itself
    group_key = Column(String, nullable=False, index=True)
    group_number = Column(String, nullable=False)
    subject = Column(String, nullable=False, default="", server_default="")
    text = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    created_by = relationship("User")


class Event(Base):
    """An event: of an association (its members see it) or of the institute (everyone; set by administrators)."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    # "association" | "institute"
    scope = Column(String, nullable=False, default="association", server_default="association")
    # The organizing association; for institute events optional (null = the administration)
    association_id = Column(Integer, ForeignKey("associations.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="", server_default="")
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    place = Column(String, nullable=False, default="", server_default="")
    # None = no limit
    participant_limit = Column(Integer, nullable=True)
    # None = volunteers are not needed
    volunteer_limit = Column(Integer, nullable=True)
    registration_open = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    association = relationship("Association")
    created_by = relationship("User")
    registrations = relationship("EventRegistration", back_populates="event", cascade="all, delete-orphan")
    feedback = relationship("EventFeedback", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="event", cascade="all, delete-orphan",
                               order_by="Attachment.created_at")


class EventRegistration(Base):
    __tablename__ = "event_registrations"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_registration"),)

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False, default="participant", server_default="participant")  # participant | volunteer
    # self | leader | admin | admin_group
    source = Column(String, nullable=False, default="self", server_default="self")
    # Marked by the organizers after the start: True came, False did not, None not marked
    attended = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    event = relationship("Event", back_populates="registrations")
    user = relationship("User")


class EventFeedback(Base):
    """The short survey after an event: a 1–5 rating and a comment, one per student."""
    __tablename__ = "event_feedback"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_feedback"),)

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    text = Column(Text, nullable=False, default="", server_default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user = relationship("User")


class ManualAchievement(Base):
    """An event the student took part in outside the portal, for the ПГАС summary; a scan can be attached."""
    __tablename__ = "manual_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    organizer = Column(String, nullable=False, default="", server_default="")
    day = Column(Date, nullable=False)
    # "Участник", "Волонтёр", "Призёр (2 место)"...
    role = Column(String, nullable=False, default="", server_default="")
    description = Column(Text, nullable=False, default="", server_default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    attachments = relationship("Attachment", back_populates="achievement", cascade="all, delete-orphan",
                               order_by="Attachment.created_at")


BOOKING_ZONES = ("top", "bottom", "whole")


class Booking(Base):
    """A booking of coworking room 108 ("8 бит": the upper or lower part, or all of it) or of laptops.

    Confirmed at once; an administrator may cancel it. Cancelled rows stay for the history.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    resource = Column(String, nullable=False)  # "room" | "laptops"
    zone = Column(String, nullable=True)  # room: see BOOKING_ZONES
    laptops = Column(Integer, nullable=True)  # laptops: how many
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    purpose = Column(String, nullable=False, default="", server_default="")
    association_id = Column(Integer, ForeignKey("associations.id", ondelete="SET NULL"), nullable=True, index=True)
    booked_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancel_reason = Column(String, nullable=True)

    association = relationship("Association")
    booked_by = relationship("User", foreign_keys=[booked_by_id])
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
