use std::env;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{AppHandle, Manager};

const LOCAL_ENGINE_PORT: u16 = 45873;

static ENGINE_CHILD: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

fn child_slot() -> &'static Mutex<Option<Child>> {
    ENGINE_CHILD.get_or_init(|| Mutex::new(None))
}

fn packaged_candidates(app: &AppHandle) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("concurse-engine-x86_64-pc-windows-msvc.exe"));
        candidates.push(resource_dir.join("concurse-engine.exe"));
        candidates.push(resource_dir.join("binaries/concurse-engine-x86_64-pc-windows-msvc.exe"));
        candidates.push(resource_dir.join("binaries/concurse-engine.exe"));
    }
    candidates
}

fn command_spec(app: &AppHandle, data_dir: &Path) -> Result<(PathBuf, Vec<String>), String> {
    let args = vec![
        "--host".to_string(),
        "127.0.0.1".to_string(),
        "--port".to_string(),
        LOCAL_ENGINE_PORT.to_string(),
        "--data-dir".to_string(),
        data_dir.to_string_lossy().to_string(),
    ];

    if let Ok(command) = env::var("CONCURSE_ENGINE_COMMAND") {
        let command = PathBuf::from(command.trim());
        if command.as_os_str().is_empty() {
            return Err("CONCURSE_ENGINE_COMMAND está vazio.".to_string());
        }
        let mut full_args = Vec::new();
        if command.extension().and_then(|value| value.to_str()) == Some("py") {
            let python = env::var("CONCURSE_ENGINE_PYTHON").unwrap_or_else(|_| "python".to_string());
            full_args.push(command.to_string_lossy().to_string());
            full_args.extend(args);
            return Ok((PathBuf::from(python), full_args));
        }
        full_args.extend(args);
        return Ok((command, full_args));
    }

    for candidate in packaged_candidates(app) {
        if candidate.is_file() {
            return Ok((candidate, args));
        }
    }

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let script = repo_root.join("desktop/engine/server.py");
    let python_candidates = [
        repo_root.join("venv/Scripts/python.exe"),
        repo_root.join(".venv/Scripts/python.exe"),
    ];
    if script.is_file() {
        for python in python_candidates {
            if python.is_file() {
                let mut dev_args = vec![script.to_string_lossy().to_string()];
                dev_args.extend(args);
                return Ok((python, dev_args));
            }
        }
    }

    Err("Motor local não encontrado. Gere o sidecar concurse-engine antes de compilar o instalador.".to_string())
}

pub fn start(app: &AppHandle) -> Result<(), String> {
    let slot = child_slot();
    let mut guard = slot.lock().map_err(|_| "Motor local ocupado.".to_string())?;
    if guard.is_some() {
        return Ok(());
    }

    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Não foi possível localizar os dados do desktop: {error}"))?;
    std::fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
    let (program, args) = command_spec(app, &data_dir)?;
    let mut command = Command::new(&program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(0x08000000); // CREATE_NO_WINDOW

    let mut child = command
        .spawn()
        .map_err(|error| format!("Não foi possível iniciar o motor local: {error}"))?;

    // The frozen OCR sidecar must unpack its bundled ONNX/PDF dependencies on
    // the first launch. On slower Windows disks this can take over 30 seconds.
    for _ in 0..480 {
        if TcpStream::connect(("127.0.0.1", LOCAL_ENGINE_PORT)).is_ok() {
            *guard = Some(child);
            return Ok(());
        }
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            return Err(format!("O motor local encerrou durante a inicialização ({status})."));
        }
        thread::sleep(Duration::from_millis(250));
    }

    let _ = child.kill();
    let _ = child.wait();
    Err("O motor local não respondeu no tempo esperado.".to_string())
}

pub fn stop() {
    if let Some(slot) = ENGINE_CHILD.get() {
        if let Ok(mut guard) = slot.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}
