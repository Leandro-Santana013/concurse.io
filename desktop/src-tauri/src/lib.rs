mod offline;
#[cfg(desktop)]
mod local_engine;

#[cfg(desktop)]
use tauri::Manager;

#[tauri::command]
fn offline_auth_config() -> serde_json::Value {
    offline::auth_config()
}

#[tauri::command]
fn offline_current_user() -> Result<serde_json::Value, String> {
    offline::current_user()
}

#[tauri::command]
fn offline_library_snapshot() -> Result<serde_json::Value, String> {
    offline::library_snapshot()
}

#[tauri::command]
fn offline_folders() -> Result<serde_json::Value, String> {
    offline::folders()
}

#[tauri::command]
fn offline_get_exam(exam_id: u64) -> Result<serde_json::Value, String> {
    offline::get_exam(exam_id)
}

#[tauri::command]
fn offline_import_file(
    filename: String,
    data_base64: String,
    title: String,
) -> Result<serde_json::Value, String> {
    offline::import_file(filename, data_base64, title)
}

#[tauri::command]
fn offline_search(query: String) -> Result<serde_json::Value, String> {
    offline::search(query)
}

#[tauri::command]
fn offline_submit_attempt(
    exam_id: u64,
    elapsed_seconds: u64,
    answers: serde_json::Value,
) -> Result<serde_json::Value, String> {
    offline::submit_attempt(exam_id, elapsed_seconds, answers)
}

#[tauri::command]
fn offline_stats() -> Result<serde_json::Value, String> {
    offline::stats()
}

#[tauri::command]
fn offline_notebook_stats() -> Result<serde_json::Value, String> {
    offline::notebook_stats()
}

#[tauri::command]
fn offline_ranking() -> Result<serde_json::Value, String> {
    offline::ranking()
}

#[tauri::command]
fn offline_active_downloads() -> Result<serde_json::Value, String> {
    offline::active_downloads()
}

#[tauri::command]
fn offline_custom_options() -> Result<serde_json::Value, String> {
    offline::custom_options()
}

#[tauri::command]
fn offline_custom_exam(count: usize) -> Result<serde_json::Value, String> {
    offline::custom_exam(count)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();

    // Windows and Linux deliver a custom-scheme callback by launching the
    // executable again. The single-instance integration forwards that URL to
    // the existing process, so OAuth never creates a second login window.
    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }));

    let builder = builder
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_opener::init());

    // The mobile build is configured for the Supabase-backed flow
    // (`VITE_OFFLINE_DESKTOP=0`). Initialising the local desktop runtime here
    // can fail before the WebView is created on some Android/MIUI releases,
    // which makes Tauri abort in `__start_app`. Keep that runtime for desktop,
    // where the offline commands are used, and let mobile start directly in
    // the remote mode it was built for.
    #[cfg(desktop)]
    let builder = builder.setup(|app| {
        offline::init(app.handle()).map_err(|error| std::io::Error::other(error))?;
        local_engine::start(app.handle()).map_err(|error| std::io::Error::other(error))?;
        Ok(())
    });

    #[cfg(not(desktop))]
    let builder = builder.setup(|_app| Ok(()));

    let app = builder
        .invoke_handler(tauri::generate_handler![
            offline_auth_config,
            offline_current_user,
            offline_library_snapshot,
            offline_folders,
            offline_get_exam,
            offline_import_file,
            offline_search,
            offline_submit_attempt,
            offline_stats,
            offline_notebook_stats,
            offline_ranking,
            offline_active_downloads,
            offline_custom_options,
            offline_custom_exam,
        ])
        .build(tauri::generate_context!())
        .expect("erro ao construir o aplicativo concurse.io");

    app.run(|_app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            #[cfg(desktop)]
            local_engine::stop();
        }
    });
}
