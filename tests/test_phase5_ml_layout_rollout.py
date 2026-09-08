"""Phase-5 dataset, layout-family, ML and rollout contract tests."""

from dataclasses import replace
import io
import json

import fitz
import pytest

from services.pdf_pipeline.structural import (
    BBox,
    BenchmarkCase,
    Candidate,
    CandidateClassifierTrainer,
    DocumentProfile,
    DocumentModel,
    ExamLabelInput,
    FeatureSchemaMismatchError,
    FeatureVector,
    GroupKFoldSplitter,
    LayoutFamilyConfig,
    LayoutFamilyModel,
    ModelRegistry,
    PageModel,
    PhysicalElement,
    ResultArbiter,
    PipelineMode,
    ReliableDatasetBuilder,
    TrainedCandidateClassifier,
    WeakLabelDataset,
    build_legacy_adapter_roles,
    evaluate_exam,
    run_benchmark,
    run_structural_shadow,
)
from services.pdf_pipeline.structural.candidates import StructuralAnalyzer
from services.pdf_pipeline.structural.solver import DocumentParseConfidence


FEATURES = {
    "content.is_integer": 1.0,
    "content.regex_score": 0.9,
    "geometry.x0": 0.1,
    "geometry.y0": 0.2,
    "style.bold": 1.0,
}


def _candidate(exam: str, number: int, *, positive: bool) -> Candidate:
    return Candidate(
        id=f"{exam}:candidate:{number}",
        type="QUESTION_HEADER",
        score=0.85 if positive else 0.2,
        metadata={"question_number": number, "line_text": f"Questão {number}"},
        features=FeatureVector(
            values={
                **FEATURES,
                "content.integer_value_norm": number / 100,
                "content.has_question_token": float(positive),
            }
        ),
    )


def _exam_input(exam: str) -> ExamLabelInput:
    questions = [
        {"numero_questao": "1", "resposta": "A"},
        {"numero_questao": "2", "resposta": "B"},
    ]
    return ExamLabelInput(
        exam_id=exam,
        legacy_questions=questions,
        candidates=[
            _candidate(exam, 1, positive=True),
            _candidate(exam, 2, positive=True),
            _candidate(exam, 99, positive=False),
        ],
        answer_key={1: "A", 2: "B"},
        layout_family="layout-family-1",
    )


def _profile(values, *, reading_order="TWO_COLUMN"):
    return DocumentProfile(
        fingerprint=list(values),
        fingerprint_version="layout-profile-v1",
        reading_order_mode=reading_order,
        question_header_signature={"bold_ratio": 1.0},
        option_signature={"dominant_count": 5},
    )


def test_weak_labels_reject_inconsistent_legacy_and_groupkfold_has_no_exam_leakage():
    builder = ReliableDatasetBuilder()
    rejected = builder.build(
        [
            replace(_exam_input("bad"), answer_key={1: "A"}),
        ]
    )
    assert rejected.records == []
    assert "bad" in rejected.rejected_exams
    assert "legacy_answer_key_number_mismatch" in rejected.rejected_exams["bad"].reasons

    dataset = builder.build([_exam_input(f"exam-{index}") for index in range(4)])
    splits = GroupKFoldSplitter(n_splits=3).split(dataset, holdout_groups={"exam-3"})
    splits.assert_no_leakage()
    assert set(splits.train_groups) | set(splits.validation_groups) == {"exam-0", "exam-1", "exam-2"}
    assert not set(splits.train_groups) & set(splits.validation_groups)
    folds = GroupKFoldSplitter(n_splits=3).kfold(dataset)
    assert all(not set(fold.train_groups) & set(fold.test_groups) for fold in folds)


def test_logistic_training_is_reproducible_and_registry_enforces_schema(tmp_path):
    dataset = ReliableDatasetBuilder().build([_exam_input(f"exam-{index}") for index in range(4)])
    splits = GroupKFoldSplitter(n_splits=3).split(dataset, holdout_groups={"exam-3"})
    trainer = CandidateClassifierTrainer(random_state=7)
    first = trainer.train(dataset, splits=splits)
    second = trainer.train(dataset, splits=splits)
    values = dataset.records[0]
    assert first.predict(values) == second.predict(values)
    assert first.metadata.feature_schema_version == 1
    assert "full_exam_success_rate" in first.metadata.metrics

    model_path = tmp_path / "candidate.joblib"
    manifest_path = tmp_path / "models.json"
    first.save(model_path)
    registry = ModelRegistry(manifest_path)
    registry.register(
        "candidate_classifier",
        path="candidate.joblib",
        version="1",
        feature_schema=1,
        model_version=first.model_version,
        training_dataset_version=dataset.version,
    )
    registry.save()
    loaded = ModelRegistry.load(manifest_path).load_candidate_classifier()
    assert loaded.predict(values) == first.predict(values)

    mismatch = ModelRegistry.load(manifest_path, runtime_feature_schema=2)
    with pytest.raises(FeatureSchemaMismatchError):
        mismatch.resolve("candidate_classifier")


def test_layout_families_are_visual_priors_and_unseen_layout_can_be_noise():
    profiles = [
        _profile([1.0, 0.20, 0.80]),
        _profile([1.0, 0.21, 0.79]),
        _profile([2.0, 0.30, 0.70]),
        _profile([2.0, 0.31, 0.69]),
        _profile([3.0, 0.90, 0.10]),
    ]
    model = LayoutFamilyModel(LayoutFamilyConfig(min_samples=2, max_assignment_distance=1.5))
    assignments = model.fit_predict(profiles, document_ids=[f"exam-{index}" for index in range(5)])
    assert model.algorithm_used in {"HDBSCAN", "DBSCAN"}
    assert len([family for family in model.families.values() if not family.is_noise]) >= 1
    assert assignments["exam-0"].layout_family == assignments["exam-1"].layout_family
    assert assignments["exam-4"].is_noise or assignments["exam-4"].layout_family != assignments["exam-0"].layout_family
    assert model.families[next(iter(model.families))].priors.expected_column_count in {1, 2, 3, None}
    unseen = model.predict(_profile([50.0, -50.0, 50.0]), document_id="unseen")
    assert unseen.is_noise


def test_legacy_adapter_has_evidence_recovery_and_fallback_roles():
    class FakeAdapter:
        name = "fake-bank"

        def supports(self, context):
            return 0.9

        def parse(self, pdf, context):
            return [{"numero_questao": "1", "opcoes": {"A": "x"}}]

        def recover_question(self, region, expected_number):
            return {"id": "recovered", "source_element_ids": ["physical-12"], "score": 0.8}

        def legacy_bank_header_match(self, text, context):
            return 0.91

    roles = build_legacy_adapter_roles(FakeAdapter(), document=DocumentModel(pages=[]))
    assert roles.evidence.legacy_bank_header_match("Questão 1") == 0.91
    context = roles.evidence.context_evidence("Leia o texto e responda às questões")
    assert set(context) >= {
        "legacy_context_pattern",
        "legacy_context_question_range",
        "legacy_context_extractor",
    }
    assert roles.recovery.recover_question(None, 12)["source_element_ids"] == ["physical-12"]
    assert roles.fallback.parse(b"pdf", roles.evidence.context) == [{"numero_questao": "1", "opcoes": {"A": "x"}}]
    assert roles.to_dict()["roles"] == ["evidence", "recovery", "fallback"]


def test_arbiter_promotes_only_safe_results_and_quarantines_divergence():
    legacy = [{"numero_questao": "1", "opcoes": {"A": "x"}}]
    same = [{"numero_questao": "1", "opcoes": {"A": "y"}}]
    different = [{"numero_questao": "2", "opcoes": {"A": "y"}}]
    arbiter = ResultArbiter()
    assert arbiter.arbitrate(legacy_result=legacy, structural_result=same, structural_confidence=0.9).source == "structural"
    medium = arbiter.arbitrate(legacy_result=legacy, structural_result=same, structural_confidence=0.65)
    assert medium.source == "structural" and medium.concordant
    divergent = arbiter.arbitrate(legacy_result=legacy, structural_result=different, structural_confidence=0.65)
    assert divergent.quarantined and divergent.result is None
    assert arbiter.arbitrate(legacy_result=legacy, structural_result=different, structural_confidence=0.2).source == "legacy"
    assert arbiter.arbitrate(legacy_result=[], structural_result=different, structural_confidence=0.2).quarantined


def test_ml_disabled_keeps_geometric_scores_and_enabled_adds_model_evidence():
    page = PageModel(
        page_index=0,
        width=600,
        height=800,
        elements=[
            PhysicalElement(
                id="q1",
                page_index=0,
                kind="text",
                bbox=BBox.from_absolute(50, 50, 150, 70, 600, 800),
                text="Questão 1",
                bold=True,
                font_size=12,
            ),
            PhysicalElement(
                id="body1",
                page_index=0,
                kind="text",
                bbox=BBox.from_absolute(50, 90, 500, 115, 600, 800),
                text="Escolha a alternativa correta.",
                font_size=10,
            ),
        ],
    )
    document = __import__("services.pdf_pipeline.structural", fromlist=["DocumentModel"]).DocumentModel(pages=[page])

    class AlwaysPositive:
        metadata = type("Metadata", (), {"model_version": "test-model"})()

        def score_candidate(self, candidate):
            return 1.0

    disabled = StructuralAnalyzer(candidate_classifier=AlwaysPositive(), ml_enabled=False).analyze(document)
    enabled = StructuralAnalyzer(candidate_classifier=AlwaysPositive(), ml_enabled=True).analyze(document)
    assert disabled.question_candidates
    assert all("ml_candidate_probability" not in item.evidence for item in disabled.question_candidates)
    assert any("ml_candidate_probability" in item.evidence for item in enabled.question_candidates)


def test_benchmark_reports_all_kpis_and_legacy_structural_comparison():
    case = BenchmarkCase(
        exam_id="holdout-1",
        expected_numbers=[1, 2],
        structural_result=[
            {"numero_questao": "1", "opcoes": {"A": "x", "B": "y"}},
            {"numero_questao": "2", "opcoes": {"A": "x", "B": "y"}},
        ],
        legacy_result=[
            {"numero_questao": "1", "opcoes": {"A": "x"}},
            {"numero_questao": "2", "opcoes": {"A": "x"}},
        ],
        expected_options={1: ["A", "B"], 2: ["A", "B"]},
        banca="IBAM",
        layout_family="layout-family-1",
        split="holdout",
    )
    metrics = evaluate_exam(case)
    report = run_benchmark([case])
    assert metrics.full_exam_success is True
    assert report.generalization_rate == 1.0
    payload = report.to_dict()
    assert set(payload["metrics"]) >= {
        "question_detection_precision",
        "question_detection_recall",
        "option_extraction_accuracy",
        "image_ownership_accuracy",
        "question_ordering_accuracy",
        "full_exam_success_rate",
        "zero_modification_success_rate",
        "generalization_rate",
    }
    assert payload["legacy_vs_structural"]["cases_with_changes"] == 1


def test_trained_classifier_artifact_has_versioned_metadata(tmp_path):
    dataset = ReliableDatasetBuilder().build([_exam_input(f"exam-{index}") for index in range(3)])
    model = CandidateClassifierTrainer().train(dataset)
    path = model.save(tmp_path / "candidate.joblib")
    loaded = TrainedCandidateClassifier.load(path)
    assert json.loads(json.dumps(loaded.metadata.to_dict()))["feature_schema_version"] == 1


def test_shadow_preserves_legacy_and_preferred_uses_arbiter():
    pdf = fitz.open()
    page = pdf.new_page(width=300, height=400)
    page.insert_text((30, 50), "Questao 1", fontname="hebo", fontsize=12)
    page.insert_text((30, 80), "Escolha uma alternativa.", fontsize=10)
    page.insert_text((30, 120), "A) uma", fontsize=10)
    page.insert_text((30, 145), "B) duas", fontsize=10)
    page.insert_text((30, 170), "C) tres", fontsize=10)
    page.insert_text((30, 195), "D) quatro", fontsize=10)
    stream = io.BytesIO()
    pdf.save(stream)
    pdf.close()
    legacy = [{"numero_questao": "1", "opcoes": {"A": "uma", "B": "duas", "C": "tres", "D": "quatro"}}]

    shadow = run_structural_shadow(
        stream.getvalue(),
        mode=PipelineMode.STRUCTURAL_SHADOW,
        legacy_result=legacy,
        answer_key={1: "A"},
    )
    preferred = run_structural_shadow(
        stream.getvalue(),
        mode=PipelineMode.STRUCTURAL_PREFERRED,
        legacy_result=legacy,
        answer_key={1: "A"},
    )
    assert shadow.user_result == legacy
    assert shadow.structural_result
    assert preferred.arbitration is not None
    assert preferred.arbitration.source == "structural"
    assert preferred.user_result == preferred.structural_result
