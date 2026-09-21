//! Local-first storage for cached proofs and the desktop OAuth bridge.
//!
//! The desktop keeps imported proofs and exam manifests in its application
//! data directory so a user can reopen a synchronized proof without a network
//! connection. Cross-device sharing stays in the central account/library flow.

use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const CATALOG_FILE: &str = "library.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Catalog {
    version: u32,
    node_id: String,
    profile_name: String,
    exams: Vec<ExamRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ExamRecord {
    id: u64,
    title: String,
    status: String,
    filename: String,
    blob_id: String,
    blob_size: u64,
    source_url: Option<String>,
    gabarito_url: Option<String>,
    has_official_answers: bool,
    gabarito_coverage: f64,
    questions: Vec<Value>,
    attempts: Vec<AttemptRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AttemptRecord {
    score: u32,
    total: u32,
    percentage: f64,
    elapsed_seconds: u64,
    created_at: String,
}

struct Runtime {
    root: PathBuf,
    catalog: Mutex<Catalog>,
}

static RUNTIME: OnceLock<Arc<Runtime>> = OnceLock::new();

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn make_node_id() -> String {
    let mut hasher = Sha256::new();
    hasher.update(format!("{}:{}", std::process::id(), now()));
    format!("node-{}", hex::encode(hasher.finalize())[..24].to_string())
}

fn runtime() -> Result<Arc<Runtime>, String> {
    RUNTIME
        .get()
        .cloned()
        .ok_or_else(|| "O armazenamento local ainda não foi inicializado.".to_string())
}

fn load_catalog(root: &Path, node_id: &str) -> Catalog {
    let path = root.join(CATALOG_FILE);
    if let Ok(bytes) = fs::read(&path) {
        if let Ok(mut catalog) = serde_json::from_slice::<Catalog>(&bytes) {
            catalog.node_id = node_id.to_string();
            if catalog.profile_name.trim().is_empty() {
                catalog.profile_name = "Concurseiro local".to_string();
            }
            return catalog;
        }
    }
    Catalog {
        version: 1,
        node_id: node_id.to_string(),
        profile_name: "Concurseiro local".to_string(),
        exams: Vec::new(),
    }
}

fn save_catalog(runtime: &Runtime, catalog: &Catalog) -> Result<(), String> {
    let tmp = runtime.root.join("library.json.tmp");
    let bytes = serde_json::to_vec_pretty(catalog).map_err(|err| err.to_string())?;
    fs::write(&tmp, bytes).map_err(|err| err.to_string())?;
    fs::rename(tmp, runtime.root.join(CATALOG_FILE)).map_err(|err| err.to_string())
}

fn blob_path(runtime: &Runtime, asset_id: &str) -> PathBuf {
    runtime
        .root
        .join("blobs")
        .join(asset_id.trim_start_matches("sha256:"))
}

fn asset_id(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("sha256:{}", hex::encode(hasher.finalize()))
}

fn record_id(blob_id: &str) -> u64 {
    let hex_part = blob_id.trim_start_matches("sha256:");
    u64::from_str_radix(&hex_part[..12.min(hex_part.len())], 16).unwrap_or(1)
}

pub fn init(app: &AppHandle) -> Result<(), String> {
    if RUNTIME.get().is_some() {
        return Ok(());
    }
    let root = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("Não foi possível localizar os dados locais: {err}"))?;
    fs::create_dir_all(root.join("blobs")).map_err(|err| err.to_string())?;
    let node_id_path = root.join("node_id");
    let node_id = fs::read_to_string(&node_id_path)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(make_node_id);
    if !node_id_path.exists() {
        fs::write(&node_id_path, &node_id).map_err(|err| err.to_string())?;
    }
    let catalog = load_catalog(&root, &node_id);
    let runtime = Arc::new(Runtime {
        root,
        catalog: Mutex::new(catalog),
    });
    RUNTIME
        .set(runtime.clone())
        .map_err(|_| "Armazenamento local já inicializado.".to_string())?;
    Ok(())
}

pub fn current_user() -> Result<Value, String> {
    let runtime = runtime()?;
    let name = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?
        .profile_name
        .clone();
    Ok(
        json!({"id": 1, "email": "local@device", "name": name, "picture": "", "is_authenticated": true}),
    )
}

pub fn auth_config() -> Value {
    json!({"google_enabled": false, "offline": true})
}

pub fn library_snapshot() -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?
        .clone();
    let exams: Vec<Value> = catalog.exams.iter().map(summary).collect();
    let folder = json!({"id": "local", "name": "Neste computador", "exams": exams});
    Ok(json!({
        "schema_version": 1,
        "user_id": 1,
        "generated_at": now().to_string(),
        "library_version": now().to_string(),
        "folders": [folder],
        "exams": catalog.exams.iter().map(summary).collect::<Vec<_>>(),
        "asset_manifests": {}
    }))
}

pub fn folders() -> Result<Value, String> {
    let snapshot = library_snapshot()?;
    Ok(snapshot
        .get("folders")
        .cloned()
        .unwrap_or_else(|| json!([])))
}

fn summary(exam: &ExamRecord) -> Value {
    let last = exam.attempts.last();
    let best = exam
        .attempts
        .iter()
        .map(|attempt| attempt.percentage)
        .fold(None, |best: Option<f64>, value| {
            Some(best.map_or(value, |current| current.max(value)))
        });
    json!({
        "id": exam.id,
        "title": exam.title,
        "status": exam.status,
        "question_count": exam.questions.len(),
        "best_score": best,
        "last_score": last.map(|attempt| attempt.percentage),
        "attempt_count": exam.attempts.len(),
        "has_official_answers": exam.has_official_answers,
        "answer_key_source": if exam.has_official_answers { "local" } else { "none" },
        "gabarito_coverage": exam.gabarito_coverage,
        "source_url": exam.source_url,
        "gabarito_url": exam.gabarito_url
    })
}

pub fn get_exam(id: u64) -> Result<Value, String> {
    let runtime = runtime()?;
    let exam = {
        let catalog = runtime
            .catalog
            .lock()
            .map_err(|_| "Catálogo ocupado".to_string())?;
        catalog.exams.iter().find(|exam| exam.id == id).cloned()
    };
    exam.map(|exam| {
        json!({
            "id": exam.id,
            "title": exam.title,
            "status": exam.status,
            "source_url": exam.source_url,
            "gabarito_url": exam.gabarito_url,
            "has_official_answers": exam.has_official_answers,
            "gabarito_coverage": exam.gabarito_coverage,
            "questions": exam.questions
        })
    })
    .ok_or_else(|| "Prova não encontrada neste computador.".to_string())
}

fn normalize_questions(value: &Value) -> Vec<Value> {
    let raw = value
        .get("questions")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    raw.into_iter()
        .enumerate()
        .map(|(index, mut question)| {
            if let Some(object) = question.as_object_mut() {
                let existing_id = object.get("id").and_then(Value::as_i64).unwrap_or(0);
                object.entry("id").or_insert_with(|| json!(0));
                object
                    .entry("numero_questao")
                    .or_insert_with(|| json!((existing_id + 1).to_string()));
                object.entry("statement").or_insert_with(|| json!(""));
                object
                    .entry("options")
                    .or_insert_with(|| json!({"A":"","B":"","C":"","D":"","E":""}));
                object.entry("correct_answer").or_insert_with(|| json!(""));
                object.entry("subject").or_insert_with(|| json!("Geral"));
                object
                    .entry("has_official_answer")
                    .or_insert_with(|| json!(false));
                object
                    .entry("latex_support")
                    .or_insert_with(|| json!(false));
                if object
                    .get("numero_questao")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .is_empty()
                {
                    object.insert("numero_questao".into(), json!((index + 1).to_string()));
                }
            }
            question
        })
        .collect()
}

fn import_record(filename: &str, title: &str, bytes: &[u8]) -> ExamRecord {
    let blob_id = asset_id(bytes);
    let id = record_id(&blob_id);
    let parsed = serde_json::from_slice::<Value>(bytes).ok();
    let parsed_title = parsed
        .as_ref()
        .and_then(|value| value.get("title"))
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty());
    let questions = parsed.as_ref().map(normalize_questions).unwrap_or_default();
    let has_answers = questions
        .iter()
        .filter(|question| {
            question
                .get("correct_answer")
                .and_then(Value::as_str)
                .map(|answer| !answer.is_empty())
                .unwrap_or(false)
        })
        .count();
    let coverage = if questions.is_empty() {
        0.0
    } else {
        (has_answers as f64 / questions.len() as f64) * 100.0
    };
    ExamRecord {
        id,
        title: parsed_title
            .unwrap_or_else(|| {
                if title.trim().is_empty() {
                    filename
                } else {
                    title
                }
            })
            .to_string(),
        status: if questions.is_empty() {
            "Arquivo local".to_string()
        } else {
            "Aprovada".to_string()
        },
        filename: filename.to_string(),
        blob_id,
        blob_size: bytes.len() as u64,
        source_url: None,
        gabarito_url: None,
        has_official_answers: !questions.is_empty() && has_answers == questions.len(),
        gabarito_coverage: coverage,
        questions,
        attempts: Vec::new(),
    }
}

pub fn import_file(filename: String, data_base64: String, title: String) -> Result<Value, String> {
    let runtime = runtime()?;
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data_base64.as_bytes())
        .map_err(|err| format!("Arquivo inválido: {err}"))?;
    if bytes.is_empty() {
        return Err("O arquivo está vazio.".to_string());
    }
    let record = import_record(&filename, &title, &bytes);
    let blob = blob_path(&runtime, &record.blob_id);
    if !blob.exists() {
        let tmp = blob.with_extension("part");
        fs::write(&tmp, bytes).map_err(|err| err.to_string())?;
        fs::rename(tmp, blob).map_err(|err| err.to_string())?;
    }
    let mut catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?;
    catalog.exams.retain(|exam| exam.blob_id != record.blob_id);
    catalog.exams.push(record.clone());
    save_catalog(&runtime, &catalog)?;
    Ok(
        json!({"exam_id": record.id, "title": record.title, "status": "Aprovada", "progress": 100, "message": if record.questions.is_empty() { "Arquivo guardado localmente; um JSON extraído pode ser importado para abrir as questões." } else { "Prova importada neste computador." }, "reused": false, "already_in_library": false}),
    )
}

pub fn search(query: String) -> Result<Value, String> {
    let runtime = runtime()?;
    let query = query.trim().to_lowercase();
    let catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?;
    let items = catalog.exams.iter().filter(|exam| exam.title.to_lowercase().contains(&query)).map(|exam| json!({"id": exam.id, "title": exam.title, "url": "", "gabarito_url": exam.gabarito_url, "has_gabarito_link": exam.has_official_answers, "match_score": 100, "source": "local", "reuse_available": true})).collect::<Vec<_>>();
    Ok(
        json!({"items": items, "page": 1, "page_size": items.len().max(1), "total": items.len(), "total_pages": if items.is_empty() {0} else {1}, "has_previous": false, "has_next": false}),
    )
}

pub fn submit_attempt(exam_id: u64, elapsed_seconds: u64, answers: Value) -> Result<Value, String> {
    let runtime = runtime()?;
    let mut catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?;
    let exam = catalog
        .exams
        .iter_mut()
        .find(|exam| exam.id == exam_id)
        .ok_or_else(|| "Prova não encontrada.".to_string())?;
    let answer_map = answers.as_object().cloned().unwrap_or_default();
    let mut detailed = serde_json::Map::new();
    let mut correct = 0_u32;
    for (index, question) in exam.questions.iter().enumerate() {
        let number = question
            .get("numero_questao")
            .and_then(Value::as_str)
            .unwrap_or_else(|| "");
        let key = if number.is_empty() {
            (index + 1).to_string()
        } else {
            number.to_string()
        };
        let user_answer = answer_map
            .get(&key)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let correct_answer = question
            .get("correct_answer")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let is_correct =
            !correct_answer.is_empty() && user_answer.eq_ignore_ascii_case(&correct_answer);
        if is_correct {
            correct += 1;
        }
        detailed.insert(key.clone(), json!({"question_id": question.get("id").and_then(Value::as_u64).unwrap_or(index as u64 + 1), "user_answer": user_answer, "correct_answer": correct_answer, "is_correct": is_correct, "subject": question.get("subject").and_then(Value::as_str).unwrap_or("Geral")}));
    }
    let total = exam.questions.len() as u32;
    let percentage = if total == 0 {
        0.0
    } else {
        correct as f64 * 100.0 / total as f64
    };
    let attempt = AttemptRecord {
        score: correct,
        total,
        percentage,
        elapsed_seconds,
        created_at: now().to_string(),
    };
    exam.attempts.push(attempt);
    save_catalog(&runtime, &catalog)?;
    Ok(
        json!({"attempt_id": now(), "exam_id": exam_id, "score": correct, "total": total, "percentage": percentage, "elapsed_seconds": elapsed_seconds, "detailed_answers": detailed, "feedback_per_subject": {}}),
    )
}

pub fn stats() -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?;
    let total_questions = catalog
        .exams
        .iter()
        .map(|exam| exam.questions.len() as u64)
        .sum::<u64>();
    let attempts = catalog
        .exams
        .iter()
        .flat_map(|exam| exam.attempts.iter())
        .collect::<Vec<_>>();
    let total_correct = attempts
        .iter()
        .map(|attempt| attempt.score as u64)
        .sum::<u64>();
    let total_answered = attempts
        .iter()
        .map(|attempt| attempt.total as u64)
        .sum::<u64>();
    Ok(
        json!({"total_exams": catalog.exams.len(), "total_questions": total_questions, "total_correct": total_correct, "global_accuracy": if total_answered == 0 {0.0} else {total_correct as f64 * 100.0 / total_answered as f64}, "streak": 0, "study_time": "0 min", "rank": "Local"}),
    )
}

pub fn notebook_stats() -> Result<Value, String> {
    Ok(json!([]))
}
pub fn ranking() -> Result<Value, String> {
    Ok(json!([]))
}
pub fn active_downloads() -> Result<Value, String> {
    Ok(json!([]))
}
pub fn custom_options() -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?;
    let sources = catalog
        .exams
        .iter()
        .map(|exam| json!({"id": exam.id, "title": exam.title, "count": exam.questions.len()}))
        .collect::<Vec<_>>();
    Ok(
        json!({"available_questions": catalog.exams.iter().map(|exam| exam.questions.len()).sum::<usize>(), "subjects": [], "sources": sources}),
    )
}

pub fn custom_exam(count: usize) -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime
        .catalog
        .lock()
        .map_err(|_| "Catálogo ocupado".to_string())?;
    let questions = catalog
        .exams
        .iter()
        .flat_map(|exam| exam.questions.iter().cloned())
        .take(count.max(1))
        .collect::<Vec<_>>();
    Ok(
        json!({"id": 9_000_000_000_u64 + now(), "title": "Teste local", "status": "Sessão", "has_official_answers": true, "gabarito_coverage": 100, "questions": questions}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn asset_id_is_stable_and_content_addressed() {
        assert_eq!(
            asset_id(b"concurse"),
            "sha256:407096e0c1218d1130df71ec78669484f16488c5badba53fdbf89bebd5b1b7a6"
        );
        assert_ne!(asset_id(b"concurse"), asset_id(b"concurse.io"));
    }

    #[test]
    fn json_manifest_keeps_questions_and_answer_key() {
        let value = json!({
            "title": "Prova local",
            "questions": [{"statement": "1 + 1", "options": {"A": "1", "B": "2"}, "correct_answer": "B"}]
        });
        let record = import_record(
            "prova.json",
            "",
            serde_json::to_string(&value).unwrap().as_bytes(),
        );
        assert_eq!(record.questions.len(), 1);
        assert_eq!(record.questions[0]["correct_answer"], "B");
        assert!(record.has_official_answers);
        assert_eq!(record.gabarito_coverage, 100.0);
    }
}
