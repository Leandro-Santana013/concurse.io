from services.crawlers.html_exam_parser import parse_html_exam
from services.gabarito import normalize_answer_or_empty


def test_html_parser_does_not_infer_answer_from_available_options():
    html = """
    <div class="sim-questao">
      <div class="sim-enunciado">Qual e a resposta?</div>
      <div class="btn-sim-alt" data-letra="A">Primeira</div>
      <div class="btn-sim-alt" data-letra="B">Segunda</div>
    </div>
    """

    questions = parse_html_exam(html)

    assert len(questions) == 1
    assert questions[0]["opcoes"] == {"A": "Primeira", "B": "Segunda"}
    assert questions[0]["resposta"] == ""


def test_html_parser_keeps_explicit_answer_key_value():
    html = """
    <script>var simGabaritos = [\"b\"];</script>
    <div class="sim-questao">
      <div class="sim-enunciado">Qual e a resposta?</div>
      <div class="btn-sim-alt" data-letra="A">Primeira</div>
      <div class="btn-sim-alt" data-letra="B">Segunda</div>
    </div>
    """

    questions = parse_html_exam(html)

    assert questions[0]["resposta"] == "B"


def test_normalize_answer_or_empty_has_no_default_answer():
    assert normalize_answer_or_empty(None) == ""
    assert normalize_answer_or_empty("  ") == ""
    assert normalize_answer_or_empty(" b ") == "B"
