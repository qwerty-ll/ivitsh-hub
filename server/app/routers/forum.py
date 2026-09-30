from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
import app.models as models
import app.schemas as schemas
import app.core.security as security
from app.core import rate_limit

router = APIRouter(prefix="/api/v1/forum", tags=["Forum"])

# Max search query length to prevent DB abuse
_MAX_SEARCH_LEN = 200


@router.get("/questions", response_model=List[schemas.ForumQuestionResponse])
def get_forum_questions(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=_MAX_SEARCH_LEN),
    author_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Optional[models.User] = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    # FIX: Use joinedload to avoid N+1 queries when accessing q.author.full_name
    query = db.query(models.ForumQuestion).options(joinedload(models.ForumQuestion.author))
    if category and category != "Все":
        query = query.filter(models.ForumQuestion.category == category)
    if author_id is not None:
        query = query.filter(models.ForumQuestion.author_id == author_id)
    if search:
        safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(
            (models.ForumQuestion.title.ilike(f"%{safe_search}%", escape="\\")) |
            (models.ForumQuestion.content.ilike(f"%{safe_search}%", escape="\\"))
        )

    questions = (
        query
        .order_by(models.ForumQuestion.is_pinned.desc(), models.ForumQuestion.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    q_ids = [q.id for q in questions]
    votes_dict = {}
    answers_dict = {}
    user_votes_dict = {}

    if q_ids:
        votes_query = (
            db.query(models.Vote.question_id, models.Vote.vote_type, func.count(models.Vote.id))
            .filter(models.Vote.question_id.in_(q_ids))
            .group_by(models.Vote.question_id, models.Vote.vote_type)
            .all()
        )
        for q_id, v_type, count in votes_query:
            if q_id not in votes_dict:
                votes_dict[q_id] = 0
            votes_dict[q_id] += count if v_type == 1 else -count

        answers_query = (
            db.query(models.ForumAnswer.question_id, func.count(models.ForumAnswer.id))
            .filter(models.ForumAnswer.question_id.in_(q_ids))
            .group_by(models.ForumAnswer.question_id)
            .all()
        )
        answers_dict = {q_id: count for q_id, count in answers_query}

        if current_user:
            u_votes = (
                db.query(models.Vote.question_id, models.Vote.vote_type)
                .filter(models.Vote.question_id.in_(q_ids), models.Vote.user_id == current_user.id)
                .all()
            )
            user_votes_dict = {q_id: v_type for q_id, v_type in u_votes}

    result = []
    for q in questions:
        result.append(schemas.ForumQuestionResponse(
            id=q.id,
            author_id=q.author_id,
            author_name=q.author.full_name if q.author else "Студент",
            title=q.title,
            category=q.category,
            content=q.content,
            views_count=q.views_count,
            votes_count=votes_dict.get(q.id, 0),
            answers_count=answers_dict.get(q.id, 0),
            user_vote=user_votes_dict.get(q.id, 0),
            is_pinned=q.is_pinned,
            created_at=q.created_at
        ))
    return result


@router.post("/questions", response_model=schemas.ForumQuestionResponse)
def create_question(
    q_in: schemas.ForumQuestionCreate,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db)
):
    rate_limit.check_posting(current_user)
    new_q = models.ForumQuestion(
        author_id=current_user.id,
        title=q_in.title,
        category=q_in.category,
        content=q_in.content
    )
    db.add(new_q)
    db.commit()
    db.refresh(new_q)

    return schemas.ForumQuestionResponse(
        id=new_q.id,
        author_id=new_q.author_id,
        author_name=current_user.full_name,
        title=new_q.title,
        category=new_q.category,
        content=new_q.content,
        views_count=0,
        votes_count=0,
        answers_count=0,
        user_vote=0,
        is_pinned=False,
        created_at=new_q.created_at
    )


@router.get("/questions/{question_id}", response_model=schemas.ForumQuestionResponse)
def get_question_detail(
    question_id: int,
    current_user: Optional[models.User] = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    q = (
        db.query(models.ForumQuestion)
        .options(joinedload(models.ForumQuestion.author))
        .filter(models.ForumQuestion.id == question_id)
        .first()
    )
    if not q:
        raise HTTPException(status_code=404, detail="Вопрос не найден")

    # FIX: Use SQL-level update to avoid lost-update race condition on views_count
    db.query(models.ForumQuestion).filter(models.ForumQuestion.id == question_id).update(
        {models.ForumQuestion.views_count: models.ForumQuestion.views_count + 1}
    )
    db.commit()
    db.refresh(q)

    upvotes = db.query(models.Vote).filter(models.Vote.question_id == q.id, models.Vote.vote_type == 1).count()
    downvotes = db.query(models.Vote).filter(models.Vote.question_id == q.id, models.Vote.vote_type == -1).count()
    answers_count = db.query(models.ForumAnswer).filter(models.ForumAnswer.question_id == q.id).count()

    user_vote = 0
    if current_user:
        v = db.query(models.Vote).filter(models.Vote.question_id == q.id, models.Vote.user_id == current_user.id).first()
        if v:
            user_vote = v.vote_type

    return schemas.ForumQuestionResponse(
        id=q.id,
        author_id=q.author_id,
        author_name=q.author.full_name if q.author else "Студент",
        title=q.title,
        category=q.category,
        content=q.content,
        views_count=q.views_count,
        votes_count=upvotes - downvotes,
        answers_count=answers_count,
        user_vote=user_vote,
        is_pinned=q.is_pinned,
        created_at=q.created_at
    )


@router.get("/questions/{question_id}/answers", response_model=List[schemas.ForumAnswerResponse])
def get_question_answers(
    question_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    answers = (
        db.query(models.ForumAnswer)
        .options(joinedload(models.ForumAnswer.author))
        .filter(models.ForumAnswer.question_id == question_id)
        .order_by(models.ForumAnswer.created_at.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        schemas.ForumAnswerResponse(
            id=a.id,
            question_id=a.question_id,
            author_id=a.author_id,
            author_name=a.author.full_name if a.author else "Студент",
            content=a.content,
            is_solution=a.is_solution,
            created_at=a.created_at
        )
        for a in answers
    ]


@router.post("/questions/{question_id}/answers", response_model=schemas.ForumAnswerResponse)
def post_answer(
    question_id: int,
    ans_in: schemas.ForumAnswerCreate,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db)
):
    q = db.query(models.ForumQuestion).filter(models.ForumQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Вопрос не найден")
    rate_limit.check_posting(current_user)

    new_ans = models.ForumAnswer(
        question_id=question_id,
        author_id=current_user.id,
        content=ans_in.content
    )
    db.add(new_ans)
    db.commit()
    db.refresh(new_ans)

    return schemas.ForumAnswerResponse(
        id=new_ans.id,
        question_id=new_ans.question_id,
        author_id=new_ans.author_id,
        author_name=current_user.full_name,
        content=new_ans.content,
        is_solution=False,
        created_at=new_ans.created_at
    )


@router.post("/questions/{question_id}/vote")
def vote_question(
    question_id: int,
    req: schemas.VoteRequest,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db)
):
    # Check question exists
    q = db.query(models.ForumQuestion).filter(models.ForumQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Вопрос не найден")

    vote = db.query(models.Vote).filter(
        models.Vote.question_id == question_id,
        models.Vote.user_id == current_user.id
    ).first()
    if vote:
        if vote.vote_type == req.vote_type:
            db.delete(vote)
        else:
            vote.vote_type = req.vote_type
    else:
        new_vote = models.Vote(user_id=current_user.id, question_id=question_id, vote_type=req.vote_type)
        db.add(new_vote)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"status": "ok"}


@router.delete("/questions/{question_id}", status_code=200)
def delete_question(
    question_id: int,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db)
):
    q = db.query(models.ForumQuestion).filter(models.ForumQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Вопрос не найден")
    
    if q.author_id != current_user.id and not security.is_moderator(current_user):
        raise HTTPException(status_code=403, detail="Недостаточно прав для удаления этого вопроса")
    
    db.delete(q)
    db.commit()
    return {"status": "deleted"}


@router.post("/questions/{question_id}/pin")
def toggle_pin(
    question_id: int,
    current_user: models.User = Depends(security.require_moderator),
    db: Session = Depends(get_db)
):
    q = db.query(models.ForumQuestion).filter(models.ForumQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Вопрос не найден")
    q.is_pinned = not q.is_pinned
    db.commit()
    return {"id": q.id, "is_pinned": q.is_pinned}


def _get_answer_or_404(db: Session, answer_id: int) -> models.ForumAnswer:
    answer = (
        db.query(models.ForumAnswer)
        .options(joinedload(models.ForumAnswer.question))
        .filter(models.ForumAnswer.id == answer_id)
        .first()
    )
    if not answer:
        raise HTTPException(status_code=404, detail="Ответ не найден")
    return answer


@router.delete("/answers/{answer_id}", status_code=200)
def delete_answer(
    answer_id: int,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db)
):
    answer = _get_answer_or_404(db, answer_id)
    if answer.author_id != current_user.id and not security.is_moderator(current_user):
        raise HTTPException(status_code=403, detail="Недостаточно прав для удаления этого ответа")
    db.delete(answer)
    db.commit()
    return {"status": "deleted"}


@router.post("/answers/{answer_id}/solution")
def toggle_solution(
    answer_id: int,
    current_user: models.User = Depends(security.require_current_user),
    db: Session = Depends(get_db)
):
    """The question author or a moderator marks (or unmarks) the answer that solved the question."""
    answer = _get_answer_or_404(db, answer_id)
    if answer.question.author_id != current_user.id and not security.is_moderator(current_user):
        raise HTTPException(status_code=403, detail="Отметить решение может только автор вопроса или модератор")
    if answer.author_id == answer.question.author_id:
        # Bits are paid for solutions: an answer to one's own question is never one
        raise HTTPException(status_code=400, detail="Свой ответ на свой вопрос нельзя отметить решением")
    mark = not answer.is_solution
    if mark:
        db.query(models.ForumAnswer).filter(
            models.ForumAnswer.question_id == answer.question_id,
            models.ForumAnswer.id != answer.id,
        ).update({models.ForumAnswer.is_solution: False}, synchronize_session=False)
    answer.is_solution = mark
    db.commit()
    return {"id": answer.id, "question_id": answer.question_id, "is_solution": answer.is_solution}
