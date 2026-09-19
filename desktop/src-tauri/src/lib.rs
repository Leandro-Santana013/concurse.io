mod offline;

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
fn desktop_begin_google_login(
    api_origin: String,
    next_path: String,
) -> Result<serde_json::Value, String> {
    offline::begin_google_login(api_origin, next_path)
}

#[tauri::command]
fn desktop_take_oauth_result() -> Result<Option<String>, String> {
    offline::take_oauth_result()
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
    tauri::Builder::default()
        .setup(|app| {
            offline::init(app.handle()).map_err(|error| std::io::Error::other(error))?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            offline_auth_config,
            offline_current_user,
            offline_library_snapshot,
            offline_folders,
            offline_get_exam,
            offline_import_file,
            desktop_begin_google_login,
            desktop_take_oauth_result,
            offline_search,
            offline_submit_attempt,
            offline_stats,
            offline_notebook_stats,
            offline_ranking,
            offline_active_downloads,
            offline_custom_options,
            offline_custom_exam,
        ])
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o aplicativo concurse.io");
}
