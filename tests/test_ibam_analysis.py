from types import SimpleNamespace

from services.ibam_analysis import analyze_ibam_exams


def _exam(exam_id: int, year: int):
    return SimpleNamespace(
        id=exam_id,
        title=f"[{year}] PREFEITURA DE SANTOS - OFICIAL DE ADMINISTRA\ufffdO",
        source_url=None,
        gabarito_url=None,
    )


def _questions(count: int):
    return [
        SimpleNamespace(id=index, numero_questao=str(index), question_index=index - 1, subject="Geral")
        for index in range(1, count + 1)
    ]


def _by_name(items, name):
    return next(item for item in items if item["name"] == name)


def test_known_ibam_profiles_are_indexed_by_documented_ranges():
    result = analyze_ibam_exams(
        [_exam(5, 2020), _exam(6, 2016)],
        {5: _questions(40), 6: _questions(50)},
    )

    assert result["available"] is True
    assert result["exam_count"] == 2
    assert result["question_count"] == 90
    assert result["classified_question_count"] == 90
    assert result["coverage_percentage"] == 100.0

    exam_2020 = next(item for item in result["exams"] if item["exam_id"] == 5)
    assert exam_2020["top_category"]["name"] == "Informática"
    assert exam_2020["top_category"]["question_count"] == 14
    assert exam_2020["top_category"]["percentage"] == 35.0
    assert _by_name(exam_2020["categories"], "Administração")["question_range"] == "33–35, 39"
    assert _by_name(exam_2020["categories"], "Redação Oficial")["question_count"] == 3
    assert _by_name(exam_2020["categories"], "Arquivologia")["question_count"] == 1

    exam_2016 = next(item for item in result["exams"] if item["exam_id"] == 6)
    assert exam_2016["top_category"]["name"] == "Informática"
    assert exam_2016["top_category"]["question_count"] == 15
    assert exam_2016["top_category"]["percentage"] == 30.0
    assert _by_name(exam_2016["categories"], "Administração")["question_range"] == "26–29"
    assert _by_name(exam_2016["categories"], "Arquivologia")["question_range"] == "30–32"
    assert _by_name(exam_2016["categories"], "Redação Oficial")["question_range"] == "33–35"
    assert _by_name(exam_2016["categories"], "História local / Patrimônio de Santos")["question_count"] == 1
    assert len(exam_2016["categories"]) == 8


def test_category_average_includes_zero_weight_when_category_is_absent():
    result = analyze_ibam_exams(
        [_exam(5, 2020), _exam(6, 2016)],
        {5: _questions(40), 6: _questions(50)},
    )

    informatics = _by_name(result["category_averages"], "Informática")
    administration = _by_name(result["category_averages"], "Administração")
    portuguese = _by_name(result["category_averages"], "Língua Portuguesa")
    math = _by_name(result["category_averages"], "Matemática e Raciocínio Lógico")

    assert informatics["average_weight_percentage"] == 32.5
    assert informatics["aggregate_percentage"] == 32.2
    assert administration["average_weight_percentage"] == 9.0
    assert administration["aggregate_percentage"] == 8.9
    assert portuguese["average_question_count"] == 10.0
    assert portuguese["average_weight_percentage"] == 22.5
    assert math["average_weight_percentage"] == 11.3


def test_unknown_ibam_exam_falls_back_to_persisted_subject():
    exam = SimpleNamespace(
        id=9,
        title="[2024] Prefeitura Municipal — Analista (IBAM)",
        source_url="https://example.test/ibam/prova.pdf",
        gabarito_url=None,
    )
    questions = [
        SimpleNamespace(id=1, numero_questao="1", question_index=0, subject="Língua Portuguesa"),
        SimpleNamespace(id=2, numero_questao="2", question_index=1, subject="Geral"),
    ]

    result = analyze_ibam_exams([exam], {9: questions})

    assert result["exam_count"] == 1
    assert result["classified_question_count"] == 1
    assert result["unclassified_question_count"] == 1
    assert result["exams"][0]["categories"][0]["name"] == "Língua Portuguesa"
