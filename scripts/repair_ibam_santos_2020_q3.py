"""Corrige o vazamento do OCR da questão 3 da prova IBAM 2020 de Santos."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.database import Exam, Question, Session


EXAM_ID = 5
QUESTION_NUMBER = "3"

SUPPORT_TEXT = """📖 **Texto de Apoio (Questões 1 a 3):**

> A vida tem duas faces:
> Positiva e negativa
> O passado foi duro
> mas deixou o seu legado
> Saber viver é a grande sabedoria
> Que eu possa dignificar
> Minha condição de mulher,
> Aceitar suas limitações
> E me fazer pedra de segurança
> dos valores que vão desmoronando.
> Nasci em tempos rudes
> Aceitei contradições
> lutas e pedras
> como lições de vida
> e delas me sirvo
> Aprendi a viver
> Assim eu vejo a vida - Cora Coralina"""
QUESTION_ONLY = "Ao lermos o poema podemos tirar algumas conclusões sobre a autora. Uma delas está representada em qual alternativa?"
CORRECT_STATEMENT = f"{SUPPORT_TEXT}\n\n---\n\n{QUESTION_ONLY}"
CORRECT_OPTIONS = {
    "A": "As lutas e contradições por que passou serviram-lhe de lições de vida.",
    "B": "Ela não se orgulha do fato de ser uma mulher.",
    "C": "As pedras em seu caminho foram obstáculos que limitaram o seu aprendizado.",
    "D": "Os tempos rudes em que nasceu a impediram de aceitar contradições.",
}


def repair_question() -> str:
    with Session() as session:
        exam = session.query(Exam).filter(Exam.id == EXAM_ID).one()
        if "2020" not in (exam.title or "") or "SANTOS" not in (exam.title or "").upper():
            raise RuntimeError(f"Exame inesperado para o reparo: {exam.id} / {exam.title}")

        question = (
            session.query(Question)
            .filter(Question.exam_id == exam.id, Question.numero_questao == QUESTION_NUMBER)
            .one()
        )
        current_options = json.loads(question.options or "{}")

        if question.statement == CORRECT_STATEMENT and current_options == CORRECT_OPTIONS:
            return "Questão 3 já estava corrigida; nenhuma alteração foi necessária."

        is_known_ocr_corruption = (
            "MAGALI" in (question.statement or "").upper()
            and current_options.get("A") == "DE PIZZA?!"
        )
        is_missing_support_text = question.statement == QUESTION_ONLY and current_options == CORRECT_OPTIONS
        if not is_known_ocr_corruption and not is_missing_support_text:
            raise RuntimeError("O conteúdo atual não corresponde à corrupção OCR esperada; reparo interrompido.")

        question.statement = CORRECT_STATEMENT
        question.options = json.dumps(CORRECT_OPTIONS, ensure_ascii=False)
        session.commit()
        return "Questão 3 corrigida; gabarito e demais campos foram preservados."


if __name__ == "__main__":
    print(repair_question())
