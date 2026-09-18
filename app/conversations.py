import uuid

from sqlalchemy import text

from app.db import get_engine

HISTORY_LIMIT = 20


def create_conversation(user_id: str) -> str:
    conversation_id = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO shopops_ops.conversations (conversation_id, user_id) VALUES (:id, :user_id)
        """), {"id": conversation_id, "user_id": user_id})
    return conversation_id


def get_conversation_owner(conversation_id: str) -> str | None:
    with get_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT user_id FROM shopops_ops.conversations WHERE conversation_id = :id
        """), {"id": conversation_id}).mappings().first()
    return row["user_id"] if row else None


def load_recent_messages(conversation_id: str) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT role, content FROM shopops_ops.conversation_messages
            WHERE conversation_id = :id ORDER BY turn_index DESC LIMIT :limit
        """), {"id": conversation_id, "limit": HISTORY_LIMIT}).mappings().all()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def append_messages(conversation_id: str, user_message: str, assistant_message: str) -> None:
    with get_engine().begin() as conn:
        next_index = conn.execute(text("""
            SELECT COALESCE(MAX(turn_index), -1) + 1 FROM shopops_ops.conversation_messages
            WHERE conversation_id = :id
        """), {"id": conversation_id}).scalar()
        conn.execute(text("""
            INSERT INTO shopops_ops.conversation_messages (conversation_id, turn_index, role, content)
            VALUES (:id, :idx1, 'user', :user_msg), (:id, :idx2, 'assistant', :assistant_msg)
        """), {
            "id": conversation_id, "idx1": next_index, "user_msg": user_message,
            "idx2": next_index + 1, "assistant_msg": assistant_message,
        })
