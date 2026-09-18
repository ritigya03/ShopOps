import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


def test_conversation_and_message_round_trip(engine):
    conversation_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO shopops_ops.conversations (conversation_id, user_id) VALUES (:id, :user_id)
        """), {"id": conversation_id, "user_id": "test-user"})
        conn.execute(text("""
            INSERT INTO shopops_ops.conversation_messages (conversation_id, turn_index, role, content)
            VALUES (:id, 0, 'user', 'hello'), (:id, 1, 'assistant', 'hi there')
        """), {"id": conversation_id})

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT role, content FROM shopops_ops.conversation_messages
            WHERE conversation_id = :id ORDER BY turn_index
        """), {"id": conversation_id}).mappings().all()

    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert [r["content"] for r in rows] == ["hello", "hi there"]


def test_message_role_check_constraint_rejects_bad_role(engine):
    conversation_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO shopops_ops.conversations (conversation_id, user_id) VALUES (:id, :user_id)
        """), {"id": conversation_id, "user_id": "test-user"})
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO shopops_ops.conversation_messages (conversation_id, turn_index, role, content)
                VALUES (:id, 0, 'system', 'not allowed')
            """), {"id": conversation_id})
