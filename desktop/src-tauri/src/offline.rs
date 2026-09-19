//! Local-first storage and a small, content-addressed peer mesh.
//!
//! The local commands keep proofs as blobs addressed by their SHA-256 and keep
//! the exam manifest in a JSON catalog under the application data directory.
//! Nodes discover one another with a LAN UDP broadcast and exchange verified
//! chunks over a short-lived TCP connection. The hybrid build adds the OAuth
//! loopback bridge below, while the local catalog remains usable without an
//! origin or DNS dependency.

use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom, Write};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener, TcpStream, UdpSocket};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const DISCOVERY_PORT: u16 = 48_791;
const CHUNK_SIZE: u64 = 1024 * 1024;
const PROTOCOL: &str = "concurse.mesh.v1";
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

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AssetAdvert {
    asset_id: String,
    size: u64,
    title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DiscoveryMessage {
    kind: String,
    node_id: String,
    tcp_port: u16,
    profile_name: String,
    assets: Vec<AssetAdvert>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PeerRecord {
    node_id: String,
    address: String,
    tcp_port: u16,
    profile_name: String,
    assets: Vec<AssetAdvert>,
    last_seen: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct MeshManifest {
    exam: ExamRecord,
}

struct Runtime {
    root: PathBuf,
    node_id: String,
    tcp_port: u16,
    catalog: Mutex<Catalog>,
    peers: Mutex<HashMap<String, PeerRecord>>,
    oauth_result: Mutex<Option<String>>,
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

fn percent_encode(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .flat_map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                vec![*byte as char]
            }
            _ => format!("%{byte:02X}").chars().collect(),
        })
        .collect()
}

fn percent_decode(value: &str) -> Option<String> {
    let mut bytes = Vec::with_capacity(value.len());
    let raw = value.as_bytes();
    let mut index = 0;
    while index < raw.len() {
        match raw[index] {
            b'+' => bytes.push(b' '),
            b'%' if index + 2 < raw.len() => {
                let high = (raw[index + 1] as char).to_digit(16)? as u8;
                let low = (raw[index + 2] as char).to_digit(16)? as u8;
                bytes.push((high << 4) | low);
                index += 2;
            }
            byte => bytes.push(byte),
        }
        index += 1;
    }
    String::from_utf8(bytes).ok()
}

fn callback_result(request_line: &str) -> Option<String> {
    let target = request_line.split_whitespace().nth(1)?;
    let (path, query) = target.split_once('?')?;
    if path != "/callback" {
        return None;
    }
    query.split('&').find_map(|part| {
        let (key, value) = part.split_once('=')?;
        if key == "code" {
            return percent_decode(value);
        }
        if key == "error" {
            return percent_decode(value).map(|error| format!("__oauth_error__:{error}"));
        }
        None
    })
}

fn normalize_api_origin(value: &str) -> Result<String, String> {
    let origin = value.trim().trim_end_matches('/');
    if origin.is_empty()
        || !(origin.starts_with("https://") || origin.starts_with("http://"))
        || origin
            .chars()
            .any(|character| matches!(character, '?' | '#' | ' ' | '\n' | '\r'))
    {
        return Err("O endereço do serviço de autenticação é inválido.".to_string());
    }
    Ok(origin.to_string())
}

pub fn begin_google_login(api_origin: String, next_path: String) -> Result<Value, String> {
    let runtime = runtime()?;
    let origin = normalize_api_origin(&api_origin)?;
    let next = if next_path.starts_with('/') && !next_path.starts_with("//") {
        next_path.chars().take(500).collect::<String>()
    } else {
        "/".to_string()
    };
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).map_err(|err| err.to_string())?;
    let port = listener.local_addr().map_err(|err| err.to_string())?.port();
    let desktop_return = format!("http://127.0.0.1:{port}/callback");
    let login_url = format!(
        "{origin}/api/v1/auth/google/login?client=desktop&desktop_return={}&next={}",
        percent_encode(&desktop_return),
        percent_encode(&next),
    );
    let result_runtime = runtime.clone();
    thread::spawn(move || {
        let Ok((mut stream, _)) = listener.accept() else { return };
        let mut reader = BufReader::new(&mut stream);
        let mut line = String::new();
        let code = if reader.read_line(&mut line).is_ok() {
            callback_result(&line)
        } else {
            None
        };
        if let Some(code) = code {
            if let Ok(mut result) = result_runtime.oauth_result.lock() {
                *result = Some(code);
            }
        }
        let body = "<html><body>Login concluído. Volte ao aplicativo concurse.io.</body></html>";
        let _ = write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(),
            body,
        );
    });
    #[cfg(target_os = "windows")]
    Command::new("rundll32.exe")
        .args(["url.dll,FileProtocolHandler", &login_url])
        .spawn()
        .map_err(|err| format!("Não foi possível abrir o navegador: {err}"))?;
    #[cfg(not(target_os = "windows"))]
    Command::new("xdg-open")
        .arg(&login_url)
        .spawn()
        .map_err(|err| format!("Não foi possível abrir o navegador: {err}"))?;
    Ok(json!({"started": true, "callback_port": port}))
}

pub fn take_oauth_result() -> Result<Option<String>, String> {
    let runtime = runtime()?;
    runtime
        .oauth_result
        .lock()
        .map_err(|_| "Login local ocupado".to_string())
        .map(|mut value| value.take())
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
    runtime.root.join("blobs").join(asset_id.trim_start_matches("sha256:"))
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

fn asset_adverts(catalog: &Catalog) -> Vec<AssetAdvert> {
    catalog
        .exams
        .iter()
        .map(|exam| AssetAdvert {
            asset_id: exam.blob_id.clone(),
            size: exam.blob_size,
            title: exam.title.clone(),
        })
        .collect()
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
    let listener = TcpListener::bind((Ipv4Addr::UNSPECIFIED, 0)).map_err(|err| err.to_string())?;
    let tcp_port = listener.local_addr().map_err(|err| err.to_string())?.port();
    listener
        .set_nonblocking(false)
        .map_err(|err| err.to_string())?;
    let runtime = Arc::new(Runtime {
        root,
        node_id,
        tcp_port,
        catalog: Mutex::new(catalog),
        peers: Mutex::new(HashMap::new()),
        oauth_result: Mutex::new(None),
    });
    RUNTIME
        .set(runtime.clone())
        .map_err(|_| "Armazenamento local já inicializado.".to_string())?;
    start_tcp_server(runtime.clone(), listener);
    start_discovery(runtime);
    Ok(())
}

fn start_tcp_server(runtime: Arc<Runtime>, listener: TcpListener) {
    thread::spawn(move || {
        for stream in listener.incoming().flatten() {
            let runtime = runtime.clone();
            thread::spawn(move || handle_tcp(runtime, stream));
        }
    });
}

fn handle_tcp(runtime: Arc<Runtime>, mut stream: TcpStream) {
    let request = {
        let mut reader = BufReader::new(&mut stream);
        let mut line = String::new();
        if reader.read_line(&mut line).is_err() {
            return;
        }
        serde_json::from_str::<Value>(&line).ok()
    };
    let Some(request) = request else { return };
    match request.get("op").and_then(Value::as_str) {
        Some("manifest") => {
            let Some(asset_id) = request.get("asset_id").and_then(Value::as_str) else { return };
            let catalog = runtime.catalog.lock().ok();
            let exam = catalog.and_then(|catalog| catalog.exams.iter().find(|exam| exam.blob_id == asset_id).cloned());
            let response = exam
                .map(|exam| json!({"ok": true, "manifest": MeshManifest { exam }}))
                .unwrap_or_else(|| json!({"ok": false, "error": "asset_missing"}));
            let _ = writeln!(stream, "{}", response);
        }
        Some("chunk") => {
            let Some(asset_id) = request.get("asset_id").and_then(Value::as_str) else { return };
            let offset = request.get("offset").and_then(Value::as_u64).unwrap_or(0);
            let length = request.get("length").and_then(Value::as_u64).unwrap_or(CHUNK_SIZE).min(CHUNK_SIZE);
            let path = blob_path(&runtime, asset_id);
            let Ok(mut file) = File::open(path) else { let _ = writeln!(stream, "{{\"ok\":false}}"); return };
            if file.seek(SeekFrom::Start(offset)).is_err() { return; }
            let mut bytes = vec![0_u8; length as usize];
            let Ok(read) = file.read(&mut bytes) else { return };
            bytes.truncate(read);
            let header = json!({"ok": true, "length": read});
            if writeln!(stream, "{}", header).is_ok() {
                let _ = stream.write_all(&bytes);
            }
        }
        _ => {
            let _ = writeln!(stream, "{{\"ok\":false,\"error\":\"unknown_operation\"}}");
        }
    }
}

fn start_discovery(runtime: Arc<Runtime>) {
    thread::spawn(move || {
        let Ok(socket) = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, DISCOVERY_PORT)) else { return };
        let _ = socket.set_broadcast(true);
        let _ = socket.set_read_timeout(Some(Duration::from_secs(1)));
        loop {
            let message = {
                let catalog = runtime.catalog.lock().ok();
                let (profile_name, assets) = catalog
                    .map(|catalog| (catalog.profile_name.clone(), asset_adverts(&catalog)))
                    .unwrap_or_else(|| ("Concurseiro local".to_string(), Vec::new()));
                DiscoveryMessage {
                    kind: PROTOCOL.to_string(),
                    node_id: runtime.node_id.clone(),
                    tcp_port: runtime.tcp_port,
                    profile_name,
                    assets,
                }
            };
            if let Ok(payload) = serde_json::to_vec(&message) {
                let _ = socket.send_to(&payload, (Ipv4Addr::BROADCAST, DISCOVERY_PORT));
            }
            let until = now() + 4;
            while now() < until {
                let mut buffer = [0_u8; 65_507];
                match socket.recv_from(&mut buffer) {
                    Ok((size, address)) => {
                        if let Ok(peer) = serde_json::from_slice::<DiscoveryMessage>(&buffer[..size]) {
                            if peer.kind != PROTOCOL || peer.node_id == runtime.node_id { continue; }
                            let ip = match address.ip() {
                                IpAddr::V4(value) => value,
                                IpAddr::V6(_) => continue,
                            };
                            let record = PeerRecord {
                                node_id: peer.node_id.clone(),
                                address: ip.to_string(),
                                tcp_port: peer.tcp_port,
                                profile_name: peer.profile_name,
                                assets: peer.assets,
                                last_seen: now(),
                            };
                            if let Ok(mut peers) = runtime.peers.lock() { peers.insert(record.node_id.clone(), record); }
                        }
                    }
                    Err(_) => break,
                }
            }
            if let Ok(mut peers) = runtime.peers.lock() {
                let cutoff = now().saturating_sub(20);
                peers.retain(|_, peer| peer.last_seen >= cutoff);
            }
        }
    });
}

pub fn current_user() -> Result<Value, String> {
    let runtime = runtime()?;
    let name = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?.profile_name.clone();
    Ok(json!({"id": 1, "email": "local@device", "name": name, "picture": "", "is_authenticated": true}))
}

pub fn auth_config() -> Value {
    json!({"google_enabled": false, "offline": true})
}

pub fn library_snapshot() -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?.clone();
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
    Ok(snapshot.get("folders").cloned().unwrap_or_else(|| json!([])))
}

fn summary(exam: &ExamRecord) -> Value {
    let last = exam.attempts.last();
    let best = exam.attempts.iter().map(|attempt| attempt.percentage).fold(None, |best: Option<f64>, value| {
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
        let catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
        catalog.exams.iter().find(|exam| exam.id == id).cloned()
    };
    exam.map(|exam| json!({
            "id": exam.id,
            "title": exam.title,
            "status": exam.status,
            "source_url": exam.source_url,
            "gabarito_url": exam.gabarito_url,
            "has_official_answers": exam.has_official_answers,
            "gabarito_coverage": exam.gabarito_coverage,
            "questions": exam.questions
        }))
        .ok_or_else(|| "Prova não encontrada neste computador.".to_string())
}

fn normalize_questions(value: &Value) -> Vec<Value> {
    let raw = value.get("questions").and_then(Value::as_array).cloned().unwrap_or_default();
    raw.into_iter().enumerate().map(|(index, mut question)| {
        if let Some(object) = question.as_object_mut() {
            let existing_id = object.get("id").and_then(Value::as_i64).unwrap_or(0);
            object.entry("id").or_insert_with(|| json!(0));
            object.entry("numero_questao").or_insert_with(|| json!((existing_id + 1).to_string()));
            object.entry("statement").or_insert_with(|| json!(""));
            object.entry("options").or_insert_with(|| json!({"A":"","B":"","C":"","D":"","E":""}));
            object.entry("correct_answer").or_insert_with(|| json!(""));
            object.entry("subject").or_insert_with(|| json!("Geral"));
            object.entry("has_official_answer").or_insert_with(|| json!(false));
            object.entry("latex_support").or_insert_with(|| json!(false));
            if object.get("numero_questao").and_then(Value::as_str).unwrap_or("").is_empty() {
                object.insert("numero_questao".into(), json!((index + 1).to_string()));
            }
        }
        question
    }).collect()
}

fn import_record(filename: &str, title: &str, bytes: &[u8]) -> ExamRecord {
    let blob_id = asset_id(bytes);
    let id = record_id(&blob_id);
    let parsed = serde_json::from_slice::<Value>(bytes).ok();
    let parsed_title = parsed.as_ref().and_then(|value| value.get("title")).and_then(Value::as_str).filter(|value| !value.trim().is_empty());
    let questions = parsed.as_ref().map(normalize_questions).unwrap_or_default();
    let has_answers = questions.iter().filter(|question| question.get("correct_answer").and_then(Value::as_str).map(|answer| !answer.is_empty()).unwrap_or(false)).count();
    let coverage = if questions.is_empty() { 0.0 } else { (has_answers as f64 / questions.len() as f64) * 100.0 };
    ExamRecord {
        id,
        title: parsed_title.unwrap_or_else(|| if title.trim().is_empty() { filename } else { title }).to_string(),
        status: if questions.is_empty() { "Arquivo local".to_string() } else { "Aprovada".to_string() },
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
    if bytes.is_empty() { return Err("O arquivo está vazio.".to_string()); }
    let record = import_record(&filename, &title, &bytes);
    let blob = blob_path(&runtime, &record.blob_id);
    if !blob.exists() {
        let tmp = blob.with_extension("part");
        fs::write(&tmp, bytes).map_err(|err| err.to_string())?;
        fs::rename(tmp, blob).map_err(|err| err.to_string())?;
    }
    let mut catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    catalog.exams.retain(|exam| exam.blob_id != record.blob_id);
    catalog.exams.push(record.clone());
    save_catalog(&runtime, &catalog)?;
    Ok(json!({"exam_id": record.id, "title": record.title, "status": "Aprovada", "progress": 100, "message": if record.questions.is_empty() { "Arquivo guardado localmente; um JSON extraído pode ser importado para abrir as questões." } else { "Prova importada neste computador." }, "reused": false, "already_in_library": false}))
}

pub fn mesh_peers() -> Result<Value, String> {
    let runtime = runtime()?;
    let peers = runtime.peers.lock().map_err(|_| "Rede mesh ocupada".to_string())?.values().cloned().collect::<Vec<_>>();
    Ok(json!({"node_id": runtime.node_id, "tcp_port": runtime.tcp_port, "peers": peers}))
}

fn request_manifest(peer: &PeerRecord, asset_id: &str) -> Result<ExamRecord, String> {
    let address = format!("{}:{}", peer.address, peer.tcp_port);
    let mut stream = TcpStream::connect_timeout(&address.parse::<SocketAddr>().map_err(|err| err.to_string())?, Duration::from_secs(4)).map_err(|err| err.to_string())?;
    writeln!(stream, "{}", json!({"op":"manifest", "asset_id": asset_id})).map_err(|err| err.to_string())?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|err| err.to_string())?;
    let response: Value = serde_json::from_str(&line).map_err(|err| err.to_string())?;
    if response.get("ok").and_then(Value::as_bool) != Some(true) { return Err("Manifesto ausente".to_string()); }
    serde_json::from_value(response["manifest"]["exam"].clone()).map_err(|err| err.to_string())
}

fn fetch_chunk(peer: &PeerRecord, asset_id: &str, offset: u64, length: u64) -> Result<Vec<u8>, String> {
    let address = format!("{}:{}", peer.address, peer.tcp_port);
    let mut stream = TcpStream::connect_timeout(&address.parse::<SocketAddr>().map_err(|err| err.to_string())?, Duration::from_secs(8)).map_err(|err| err.to_string())?;
    writeln!(stream, "{}", json!({"op":"chunk", "asset_id": asset_id, "offset": offset, "length": length})).map_err(|err| err.to_string())?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|err| err.to_string())?;
    let header: Value = serde_json::from_str(&line).map_err(|err| err.to_string())?;
    if header.get("ok").and_then(Value::as_bool) != Some(true) { return Err("Bloco não encontrado".to_string()); }
    let size = header.get("length").and_then(Value::as_u64).unwrap_or(0) as usize;
    let mut bytes = vec![0; size];
    reader.read_exact(&mut bytes).map_err(|err| err.to_string())?;
    Ok(bytes)
}

pub fn download_asset(expected_asset_id: String) -> Result<Value, String> {
    let runtime = runtime()?;
    if !expected_asset_id.starts_with("sha256:") { return Err("Identificador de conteúdo inválido.".to_string()); }
    if blob_path(&runtime, &expected_asset_id).exists() { return Ok(json!({"ok": true, "status": "already_present"})); }
    let peers = runtime.peers.lock().map_err(|_| "Rede mesh ocupada".to_string())?.values().filter(|peer| peer.assets.iter().any(|asset| asset.asset_id == expected_asset_id)).cloned().collect::<Vec<_>>();
    let first_peer = peers.first().ok_or_else(|| "Nenhum par online possui esta prova.".to_string())?.clone();
    let exam = request_manifest(&first_peer, &expected_asset_id)?;
    let size = exam.blob_size;
    let temp_path = blob_path(&runtime, &expected_asset_id).with_extension("part");
    let mut file = OpenOptions::new().create(true).write(true).truncate(true).open(&temp_path).map_err(|err| err.to_string())?;
    file.set_len(size).map_err(|err| err.to_string())?;
    let chunk_count = size.div_ceil(CHUNK_SIZE) as usize;
    let chunks: Arc<Mutex<Vec<Option<Vec<u8>>>>> = Arc::new(Mutex::new(vec![None; chunk_count]));
    let next_chunk = Arc::new(AtomicU64::new(0));
    let failure: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));
    let worker_count = (peers.len() * 2).clamp(1, 8);
    let mut workers = Vec::with_capacity(worker_count);
    let peers = Arc::new(peers);
    for _ in 0..worker_count {
        let chunks = chunks.clone();
        let next_chunk = next_chunk.clone();
        let failure = failure.clone();
        let peers = peers.clone();
        let expected_asset_id = expected_asset_id.clone();
        workers.push(thread::spawn(move || loop {
            if failure.lock().ok().and_then(|value| value.clone()).is_some() { break; }
            let index = next_chunk.fetch_add(1, Ordering::Relaxed) as usize;
            if index >= chunk_count { break; }
            let offset = index as u64 * CHUNK_SIZE;
            let length = (size - offset).min(CHUNK_SIZE);
            let peer = &peers[index % peers.len()];
            match fetch_chunk(peer, &expected_asset_id, offset, length) {
                Ok(chunk) if chunk.len() as u64 == length => {
                    if let Ok(mut values) = chunks.lock() { values[index] = Some(chunk); }
                }
                Ok(_) => {
                    if let Ok(mut value) = failure.lock() { *value = Some("O par enviou um bloco incompleto.".to_string()); }
                    break;
                }
                Err(error) => {
                    if let Ok(mut value) = failure.lock() { *value = Some(error); }
                    break;
                }
            }
        }));
    }
    for worker in workers {
        let _ = worker.join();
    }
    if let Some(error) = failure.lock().ok().and_then(|value| value.clone()) {
        let _ = fs::remove_file(&temp_path);
        return Err(error);
    }
    let chunks = chunks.lock().map_err(|_| "Blocos recebidos indisponíveis.".to_string())?;
    for (index, chunk) in chunks.iter().enumerate() {
        let Some(chunk) = chunk else { let _ = fs::remove_file(&temp_path); return Err("A transferência terminou sem todos os blocos.".to_string()); };
        file.seek(SeekFrom::Start(index as u64 * CHUNK_SIZE)).map_err(|err| err.to_string())?;
        file.write_all(chunk).map_err(|err| err.to_string())?;
    }
    file.flush().map_err(|err| err.to_string())?;
    let bytes = fs::read(&temp_path).map_err(|err| err.to_string())?;
    if asset_id(&bytes) != expected_asset_id { let _ = fs::remove_file(&temp_path); return Err("A verificação SHA-256 do conteúdo falhou.".to_string()); }
    fs::rename(temp_path, blob_path(&runtime, &expected_asset_id)).map_err(|err| err.to_string())?;
    let mut catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    catalog.exams.retain(|item| item.blob_id != expected_asset_id);
    catalog.exams.push(exam.clone());
    save_catalog(&runtime, &catalog)?;
    Ok(json!({"ok": true, "status": "downloaded", "exam_id": exam.id, "title": exam.title}))
}

pub fn search(query: String) -> Result<Value, String> {
    let runtime = runtime()?;
    let query = query.trim().to_lowercase();
    let catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    let items = catalog.exams.iter().filter(|exam| exam.title.to_lowercase().contains(&query)).map(|exam| json!({"id": exam.id, "title": exam.title, "url": "", "gabarito_url": exam.gabarito_url, "has_gabarito_link": exam.has_official_answers, "match_score": 100, "source": "local", "reuse_available": true})).collect::<Vec<_>>();
    Ok(json!({"items": items, "page": 1, "page_size": items.len().max(1), "total": items.len(), "total_pages": if items.is_empty() {0} else {1}, "has_previous": false, "has_next": false}))
}

pub fn submit_attempt(exam_id: u64, elapsed_seconds: u64, answers: Value) -> Result<Value, String> {
    let runtime = runtime()?;
    let mut catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    let exam = catalog.exams.iter_mut().find(|exam| exam.id == exam_id).ok_or_else(|| "Prova não encontrada.".to_string())?;
    let answer_map = answers.as_object().cloned().unwrap_or_default();
    let mut detailed = serde_json::Map::new();
    let mut correct = 0_u32;
    for (index, question) in exam.questions.iter().enumerate() {
        let number = question.get("numero_questao").and_then(Value::as_str).unwrap_or_else(|| "");
        let key = if number.is_empty() { (index + 1).to_string() } else { number.to_string() };
        let user_answer = answer_map.get(&key).and_then(Value::as_str).unwrap_or("").to_string();
        let correct_answer = question.get("correct_answer").and_then(Value::as_str).unwrap_or("").to_string();
        let is_correct = !correct_answer.is_empty() && user_answer.eq_ignore_ascii_case(&correct_answer);
        if is_correct { correct += 1; }
        detailed.insert(key.clone(), json!({"question_id": question.get("id").and_then(Value::as_u64).unwrap_or(index as u64 + 1), "user_answer": user_answer, "correct_answer": correct_answer, "is_correct": is_correct, "subject": question.get("subject").and_then(Value::as_str).unwrap_or("Geral")}));
    }
    let total = exam.questions.len() as u32;
    let percentage = if total == 0 { 0.0 } else { correct as f64 * 100.0 / total as f64 };
    let attempt = AttemptRecord { score: correct, total, percentage, elapsed_seconds, created_at: now().to_string() };
    exam.attempts.push(attempt);
    save_catalog(&runtime, &catalog)?;
    Ok(json!({"attempt_id": now(), "exam_id": exam_id, "score": correct, "total": total, "percentage": percentage, "elapsed_seconds": elapsed_seconds, "detailed_answers": detailed, "feedback_per_subject": {}}))
}

pub fn stats() -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    let total_questions = catalog.exams.iter().map(|exam| exam.questions.len() as u64).sum::<u64>();
    let attempts = catalog.exams.iter().flat_map(|exam| exam.attempts.iter()).collect::<Vec<_>>();
    let total_correct = attempts.iter().map(|attempt| attempt.score as u64).sum::<u64>();
    let total_answered = attempts.iter().map(|attempt| attempt.total as u64).sum::<u64>();
    Ok(json!({"total_exams": catalog.exams.len(), "total_questions": total_questions, "total_correct": total_correct, "global_accuracy": if total_answered == 0 {0.0} else {total_correct as f64 * 100.0 / total_answered as f64}, "streak": 0, "study_time": "0 min", "rank": "Local"}))
}

pub fn notebook_stats() -> Result<Value, String> { Ok(json!([])) }
pub fn ranking() -> Result<Value, String> { Ok(json!([])) }
pub fn active_downloads() -> Result<Value, String> { Ok(json!([])) }
pub fn custom_options() -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    let sources = catalog.exams.iter().map(|exam| json!({"id": exam.id, "title": exam.title, "count": exam.questions.len()})).collect::<Vec<_>>();
    Ok(json!({"available_questions": catalog.exams.iter().map(|exam| exam.questions.len()).sum::<usize>(), "subjects": [], "sources": sources}))
}

pub fn custom_exam(count: usize) -> Result<Value, String> {
    let runtime = runtime()?;
    let catalog = runtime.catalog.lock().map_err(|_| "Catálogo ocupado".to_string())?;
    let questions = catalog.exams.iter().flat_map(|exam| exam.questions.iter().cloned()).take(count.max(1)).collect::<Vec<_>>();
    Ok(json!({"id": 9_000_000_000_u64 + now(), "title": "Teste local", "status": "Sessão", "has_official_answers": true, "gabarito_coverage": 100, "questions": questions}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn asset_id_is_stable_and_content_addressed() {
        assert_eq!(asset_id(b"concurse"), "sha256:407096e0c1218d1130df71ec78669484f16488c5badba53fdbf89bebd5b1b7a6");
        assert_ne!(asset_id(b"concurse"), asset_id(b"concurse.io"));
    }

    #[test]
    fn json_manifest_keeps_questions_and_answer_key() {
        let value = json!({
            "title": "Prova local",
            "questions": [{"statement": "1 + 1", "options": {"A": "1", "B": "2"}, "correct_answer": "B"}]
        });
        let record = import_record("prova.json", "", serde_json::to_string(&value).unwrap().as_bytes());
        assert_eq!(record.questions.len(), 1);
        assert_eq!(record.questions[0]["correct_answer"], "B");
        assert!(record.has_official_answers);
        assert_eq!(record.gabarito_coverage, 100.0);
    }
}
