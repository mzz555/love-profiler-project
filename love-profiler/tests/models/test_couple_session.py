def test_couple_session_model_fields():
    from app.models.couple_session import CoupleSession
    assert CoupleSession.__tablename__ == "couple_sessions"
    cols = set(CoupleSession.__table__.columns.keys())
    assert {"session_id", "pairing_token", "initiator_user_id", "partner_user_id",
            "a_answers_json", "b_answers_json", "a_status", "b_status",
            "briefing_json", "report_json", "status"} <= cols
