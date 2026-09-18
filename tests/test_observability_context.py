from app.observability.context import request_id_var, user_id_var


def test_request_id_var_defaults_to_none():
    assert request_id_var.get() is None


def test_user_id_var_defaults_to_none():
    assert user_id_var.get() is None


def test_request_id_var_can_be_set_and_reset():
    token = request_id_var.set("req-1")
    assert request_id_var.get() == "req-1"
    request_id_var.reset(token)
    assert request_id_var.get() is None
