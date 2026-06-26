from app.services.couple_answer_package_builder import build_couple_answer_package


def test_build_merges_both_sides():
    a = {"self": [{"question_id": "A1-1", "value": 18}],
         "predicted": [{"question_id": "A1-1", "value": 35}], "skipped": []}
    b = {"self": [{"question_id": "A1-1", "value": 72}],
         "predicted": [{"question_id": "A1-1", "value": 60}], "skipped": ["religiosity"]}
    pkg = build_couple_answer_package(a, b)
    assert pkg["A"]["self"]["A1-1"] == 18
    assert pkg["A"]["predicted"]["A1-1"] == 35
    assert pkg["B"]["self"]["A1-1"] == 72
    assert pkg["skipped"]["B"] == ["religiosity"]


def test_missing_predicted_defaults_empty():
    pkg = build_couple_answer_package({"self": [{"question_id": "A1-1", "value": 18}]},
                                      {"self": [{"question_id": "A1-1", "value": 72}]})
    assert pkg["A"]["predicted"] == {}
    assert pkg["skipped"]["A"] == []
