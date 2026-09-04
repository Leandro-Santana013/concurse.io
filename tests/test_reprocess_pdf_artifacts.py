import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database import Base, Exam, User
from services.gabarito import AnswerKeyMatchResult
from services.exam_files import (
    canonical_answer_key_pdf_path,
    canonical_exam_pdf_path,
    ensure_canonical_exam_pdf,
    find_local_exam_artifacts,
)


class ReprocessPdfArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        Base.metadata.create_all(bind=self.engine)
        with self.session_factory() as session:
            session.add(
                User(id=1, google_id="artifact-test-user", email="artifact@example.com")
            )
            session.commit()
        import app_core.async_worker  # noqa: F401
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp_dir.cleanup()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_worker_reuses_local_answer_key_when_database_url_is_missing(self):
        pdf_dir = Path(self.temp_dir.name) / "pdfs"
        pdf_dir.mkdir()
        proof_path = pdf_dir / "42_1700000000.pdf"
        answer_key_path = pdf_dir / "42_gab_1700000000.pdf"
        pdf_bytes = b"%PDF-1.7\n" + (b"fixture\n" * 1000)
        proof_path.write_bytes(pdf_bytes)
        answer_key_path.write_bytes(pdf_bytes)

        with self.session_factory() as session:
            session.add(
                Exam(
                    id=42,
                    title="Prova local sem URL de gabarito",
                    source_url="https://example.test/prova-42.pdf",
                    gabarito_url=None,
                    status="Processando",
                    user_id=1,
                )
            )
            session.commit()

        profile = Mock()
        profile.to_dict.return_value = {}

        def fake_match(path, *_args, **_kwargs):
            if "_gab_" in os.fspath(path):
                return AnswerKeyMatchResult(
                    answers={1: "A", 2: "B"},
                    accepted=True,
                    status="accepted",
                    confidence=1.0,
                    method="local_fixture",
                    profile=profile,
                )
            return AnswerKeyMatchResult(profile=profile, status="not_found")

        with patch("app_core.async_worker.Session", self.session_factory), patch(
            "app_core.async_worker.inspect_pdf_document",
            return_value={"is_valid_exam": True, "doc_type": "EXAM", "reason": ""},
        ), patch(
            "app_core.async_worker.parse_exam_document",
            return_value=[
                {
                    "enunciado": "Questão 1",
                    "opcoes": {"A": "A", "B": "B"},
                    "numero_questao": "1",
                    "question_index": 0,
                    "disciplina": "Geral",
                },
                {
                    "enunciado": "Questão 2",
                    "opcoes": {"A": "A", "B": "B"},
                    "numero_questao": "2",
                    "question_index": 1,
                    "disciplina": "Geral",
                },
            ],
        ), patch(
            "app_core.async_worker.extract_exam_code_ranges_from_pdf", return_value=[]
        ), patch(
            "app_core.async_worker.build_exam_answer_key_profile",
            return_value=profile,
        ), patch(
            "app_core.async_worker.match_gabarito_from_pdf", side_effect=fake_match
        ), patch(
            "app_core.async_worker.merge_exam_with_gabarito",
            side_effect=lambda questions, answers, strict=False: (
                [
                    dict(
                        question,
                        resposta={1: "A", 2: "B"}[int(question["numero_questao"])],
                    )
                    for question in questions
                ],
                {
                    "has_official_answers": bool(answers),
                    "coverage_pct": 100.0 if answers else 0.0,
                    "integrity_conflicts": [],
                },
            ),
        ):
            from app_core.async_worker import process_exam_async

            process_exam_async(42)

        with self.session_factory() as session:
            exam = session.get(Exam, 42)
            self.assertEqual(exam.status, "Aprovada")
            self.assertEqual(exam.answer_key_source, "attached_pdf")
            self.assertEqual(exam.gabarito_coverage, 100.0)

    def test_local_artifacts_are_paired_by_exam_id(self):
        pdf_dir = Path(self.temp_dir.name) / "pdfs"
        pdf_dir.mkdir()
        pdf_bytes = b"%PDF-1.7\n" + (b"fixture\n" * 1000)
        for name in ("7_1700000000.pdf", "7_gab_1700000000.pdf", "8_gab_1700000000.pdf"):
            (pdf_dir / name).write_bytes(pdf_bytes)

        proof, answer_key = find_local_exam_artifacts(7, str(pdf_dir))

        self.assertEqual(Path(proof).name, "7_1700000000.pdf")
        self.assertEqual(Path(answer_key).name, "7_gab_1700000000.pdf")
        self.assertEqual(canonical_exam_pdf_path(7, str(pdf_dir)), str(pdf_dir / "7_prova.pdf"))
        self.assertEqual(
            canonical_answer_key_pdf_path(7, str(pdf_dir)),
            str(pdf_dir / "7_gab.pdf"),
        )

    def test_legacy_exam_artifact_is_materialized_with_canonical_name(self):
        pdf_dir = Path(self.temp_dir.name) / "pdfs"
        pdf_dir.mkdir()
        legacy_path = pdf_dir / "80_1788542391.pdf"
        legacy_path.write_bytes(b"%PDF-1.7\n" + (b"fixture\n" * 1000))

        canonical_path = ensure_canonical_exam_pdf(80, str(legacy_path), str(pdf_dir))

        self.assertEqual(canonical_path, str(pdf_dir / "80_prova.pdf"))
        self.assertTrue((pdf_dir / "80_prova.pdf").is_file())

    def test_explicit_answer_key_url_replaces_stale_local_file(self):
        pdf_dir = Path(self.temp_dir.name) / "pdfs"
        pdf_dir.mkdir()
        proof_path = pdf_dir / "42_1700000000.pdf"
        stale_key_path = pdf_dir / "42_gab_1700000000.pdf"
        pdf_bytes = b"%PDF-1.7\n" + (b"fixture\n" * 1000)
        proof_path.write_bytes(pdf_bytes)
        stale_key_path.write_bytes(pdf_bytes)

        official_url = "https://arq.example/33695083/gabarito.pdf"
        with self.session_factory() as session:
            session.add(
                Exam(
                    id=42,
                    title="Nova Prova de Concurso",
                    source_url="https://arq.example/33695083/prova.pdf",
                    gabarito_url=official_url,
                    status="Processando",
                    user_id=1,
                )
            )
            session.commit()

        profile = Mock()
        profile.to_dict.return_value = {}
        downloads = []

        def fake_download(url, destination):
            downloads.append((url, Path(destination).name))
            Path(destination).write_bytes(pdf_bytes)
            return True

        def fake_match(path, *_args, **_kwargs):
            if Path(path).name == "42_gab.pdf":
                return AnswerKeyMatchResult(
                    answers={1: "A", 2: "B"},
                    accepted=True,
                    status="accepted",
                    confidence=1.0,
                    method="explicit_url",
                    profile=profile,
                )
            return AnswerKeyMatchResult(profile=profile, status="not_found")

        with patch("app_core.async_worker.Session", self.session_factory), patch(
            "app_core.async_worker.inspect_pdf_document",
            return_value={"is_valid_exam": True, "doc_type": "EXAM", "reason": ""},
        ), patch(
            "app_core.async_worker.parse_exam_document",
            return_value=[
                {"enunciado": "Questão 1", "opcoes": {"A": "A", "B": "B"}, "numero_questao": "1", "question_index": 0, "disciplina": "Geral"},
                {"enunciado": "Questão 2", "opcoes": {"A": "A", "B": "B"}, "numero_questao": "2", "question_index": 1, "disciplina": "Geral"},
            ],
        ), patch(
            "app_core.async_worker.extract_exam_code_ranges_from_pdf", return_value=[]
        ), patch(
            "app_core.async_worker.build_exam_answer_key_profile", return_value=profile
        ), patch(
            "app_core.async_worker.download_pdf_file", side_effect=fake_download
        ), patch(
            "app_core.async_worker.match_gabarito_from_pdf", side_effect=fake_match
        ), patch(
            "app_core.async_worker.merge_exam_with_gabarito",
            side_effect=lambda questions, answers, strict=False: (
                [dict(question, resposta="A") for question in questions],
                {"has_official_answers": True, "coverage_pct": 100.0, "integrity_conflicts": []},
            ),
        ):
            from app_core.async_worker import process_exam_async

            process_exam_async(42)

        self.assertEqual(downloads, [(official_url, "42_gab.pdf")])
        with self.session_factory() as session:
            exam = session.get(Exam, 42)
            self.assertEqual(exam.answer_key_source, "attached_pdf")
            self.assertEqual(exam.gabarito_coverage, 100.0)
