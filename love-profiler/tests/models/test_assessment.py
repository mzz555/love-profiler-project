from app.models.assessment import Assessment


def test_assessment_has_new_json_fields(db_session):
    a = Assessment(
        user_id=1,
        session_id="sess-model-test",
        mode="quick",
        status="pending",
        signals="{}",
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    assert a.answers_json is None
    assert a.diagnosis_json is None
    assert a.report_json is None


def test_assessment_json_fields_persist(db_session):
    a = Assessment(
        user_id=1,
        session_id="sess-model-test2",
        mode="quick",
        status="analyzed",
        signals="{}",
        answers_json='[{"question_id":"D1-Q01","chosen_option":"a"}]',
        diagnosis_json='{"type_code":"S-CL-H"}',
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    assert a.answers_json is not None
    assert "D1-Q01" in a.answers_json
    assert a.diagnosis_json is not None
    assert "S-CL-H" in a.diagnosis_json
    assert a.report_json is None
