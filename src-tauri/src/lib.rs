use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::HashSet,
    env,
    fs,
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::{AppHandle, Manager, RunEvent, State};

const GODOT_PACKAGE_DIRECTORY: &str = "LingMengDesktopPet/godot-resource-package";
const GODOT_EXECUTABLE_RESOURCE: &str = "godot/Godot_v4.7.2-stable_win64.exe";
const GODOT_PROJECT_RESOURCE: &str = "godot/pet_client";
const GATEWAY_EXECUTABLE_RESOURCE: &str = "gateway/desktop-pet-gateway.exe";
const GATEWAY_CONFIG_TEMPLATE_RESOURCE: &str = "gateway/.env.example";
const DESKTOP_RUNTIME_DIRECTORY: &str = "LingMengDesktopPet";
const LEGACY_RUNTIME_DIRECTORY: &str = "AnimeAgentDesktopPet";
const GATEWAY_PORT: u16 = 8000;
const PNG_DATA_URL_PREFIX: &str = "data:image/png;base64,";
const MAX_SPRITE_SHEET_BYTES: usize = 40 * 1024 * 1024;
const PNG_SIGNATURE: [u8; 8] = [137, 80, 78, 71, 13, 10, 26, 10];

struct GodotProcess(Mutex<GodotProcessState>);

struct GodotProcessState {
    child: Option<Child>,
    executable_path: Option<PathBuf>,
    last_error: Option<String>,
}

struct GatewayProcess(Mutex<GatewayProcessState>);

struct GatewayProcessState {
    child: Option<Child>,
    executable_path: Option<PathBuf>,
    reused_existing: bool,
    last_error: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct GodotResourceImage {
    sheet_key: String,
    data_url: String,
}

#[derive(Debug, Deserialize)]
struct GodotResourcePackage {
    manifest: Value,
    images: Vec<GodotResourceImage>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GodotResourceSyncResult {
    manifest_path: String,
    image_count: usize,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct GodotPreviewState {
    action: String,
    mouth_mode: String,
    paused: bool,
    size: u32,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GodotPetStatus {
    running: bool,
    pid: Option<u32>,
    executable_path: Option<String>,
    last_error: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GatewayStatus {
    running: bool,
    pid: Option<u32>,
    executable_path: Option<String>,
    reused_existing: bool,
    last_error: Option<String>,
}

struct GatewayLaunch {
    executable: PathBuf,
    arguments: Vec<String>,
    working_directory: PathBuf,
    config_directory: Option<PathBuf>,
    data_directory: Option<PathBuf>,
    log_directory: PathBuf,
}

fn godot_status(process: &mut GodotProcessState) -> GodotPetStatus {
    let exited = process
        .child
        .as_mut()
        .map(|process| process.try_wait().map(|status| status.is_some()))
        .transpose()
        .ok()
        .flatten()
        .unwrap_or(false);
    if exited {
        process.child = None;
        process.executable_path = None;
        process.last_error = Some("Godot 桌宠进程已退出".to_string());
    }

    GodotPetStatus {
        running: process.child.is_some(),
        pid: process.child.as_ref().map(Child::id),
        executable_path: process
            .executable_path
            .as_ref()
            .map(|path| path.to_string_lossy().to_string()),
        last_error: process.last_error.clone(),
    }
}

fn resolve_godot_paths(app: &AppHandle) -> Result<(PathBuf, PathBuf), String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .ok()
        .map(|path| (path.join(GODOT_EXECUTABLE_RESOURCE), path.join(GODOT_PROJECT_RESOURCE)));
    let candidates = resource_dir
        .into_iter()
        .chain(std::iter::once((
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../tools").join("godot").join("Godot_v4.7.2-stable_win64.exe"),
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../godot/pet_client"),
        )));

    for (executable, project) in candidates {
        if executable.is_file() && project.is_dir() {
            return Ok((executable, project));
        }
    }

    Err("找不到随应用提供的 Godot 运行时或桌宠项目".to_string())
}

fn godot_resource_directory(app: &AppHandle) -> Result<PathBuf, String> {
    if let Some(local_app_data) = env::var_os("LOCALAPPDATA") {
        return Ok(PathBuf::from(local_app_data).join(GODOT_PACKAGE_DIRECTORY));
    }

    app.path()
        .app_local_data_dir()
        .map(|path| path.join("godot-resource-package"))
        .map_err(|error| format!("无法定位本机资源目录: {error}"))
}

fn is_gateway_listening() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], GATEWAY_PORT));
    TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok()
}

fn migrate_legacy_runtime_if_needed() {
    let Some(local_app_data) = env::var_os("LOCALAPPDATA").map(PathBuf::from) else {
        return;
    };
    let legacy_directory = local_app_data.join(LEGACY_RUNTIME_DIRECTORY);
    let target_directory = local_app_data.join(DESKTOP_RUNTIME_DIRECTORY);
    if !legacy_directory.is_dir() || target_directory.exists() {
        return;
    }

    // 应用正式更名为“灵梦桌宠”后首次启动：把旧版用户数据（接口配置、记忆库、
    // Godot 资源包等）复制到新目录。采用复制而非移动，旧目录保留作为备份。
    if let Err(error) = copy_directory_recursive(&legacy_directory, &target_directory) {
        eprintln!("迁移旧版用户数据失败: {error}");
    }
}

fn copy_directory_recursive(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target)
        .map_err(|error| format!("无法创建目录 {}: {error}", target.display()))?;

    for entry in fs::read_dir(source)
        .map_err(|error| format!("无法读取目录 {}: {error}", source.display()))?
    {
        let entry = entry.map_err(|error| error.to_string())?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() {
            copy_directory_recursive(&source_path, &target_path)?;
        } else {
            fs::copy(&source_path, &target_path)
                .map_err(|error| format!("无法复制 {}: {error}", source_path.display()))?;
        }
    }
    Ok(())
}

fn desktop_runtime_directory(app: &AppHandle) -> Result<PathBuf, String> {
    if let Some(local_app_data) = env::var_os("LOCALAPPDATA") {
        return Ok(PathBuf::from(local_app_data).join(DESKTOP_RUNTIME_DIRECTORY));
    }

    app.path()
        .app_local_data_dir()
        .map_err(|error| format!("无法定位桌面应用数据目录: {error}"))
}

fn env_file_contains_key(config_path: &Path, key: &str) -> bool {
    fs::read_to_string(config_path)
        .map(|contents| {
            contents.lines().any(|line| {
                let trimmed = line.trim();
                let prefix = format!("{key}=");
                if !trimmed.starts_with(&prefix) {
                    return false;
                }
                let value = trimmed[prefix.len()..].trim().trim_matches('"').trim();
                !value.is_empty()
            })
        })
        .unwrap_or(false)
}

fn migrate_development_env_if_available(config_path: &Path, template_path: &Path) -> Result<(), String> {
    if env_file_contains_key(config_path, "SPEECH_API_KEY") {
        return Ok(());
    }

    let project_env = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join(".env");
    if project_env.is_file() && env_file_contains_key(&project_env, "SPEECH_API_KEY") {
        fs::copy(&project_env, config_path)
            .map_err(|error| format!("无法同步开发环境语音配置: {error}"))?;
        return Ok(());
    }

    if !config_path.exists() {
        if !template_path.is_file() {
            return Err("找不到随应用提供的网关配置模板".to_string());
        }
        fs::copy(template_path, config_path)
            .map_err(|error| format!("无法创建本机网关配置文件: {error}"))?;
    }
    Ok(())
}

fn prepare_gateway_runtime(app: &AppHandle, resource_directory: &Path) -> Result<(PathBuf, PathBuf), String> {
    let config_directory = desktop_runtime_directory(app)?;
    let data_directory = config_directory.join("data");
    fs::create_dir_all(&data_directory).map_err(|error| format!("无法创建本机网关数据目录: {error}"))?;

    let config_path = config_directory.join(".env");
    let template_path = resource_directory.join(GATEWAY_CONFIG_TEMPLATE_RESOURCE);
    migrate_development_env_if_available(&config_path, &template_path)?;

    Ok((config_directory, data_directory))
}

fn gateway_log_stdio(log_directory: &Path) -> Result<(Stdio, Stdio), String> {
    fs::create_dir_all(log_directory)
        .map_err(|error| format!("无法创建网关日志目录 {}: {error}", log_directory.display()))?;
    let log_path = log_directory.join("gateway.log");
    let stdout = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| format!("无法打开网关日志文件 {}: {error}", log_path.display()))?;
    let stderr = stdout
        .try_clone()
        .map_err(|error| format!("无法复制网关日志文件句柄: {error}"))?;
    Ok((Stdio::from(stdout), Stdio::from(stderr)))
}

fn resolve_gateway_launch(app: &AppHandle) -> Result<GatewayLaunch, String> {
    if let Ok(resource_directory) = app.path().resource_dir() {
        let executable = resource_directory.join(GATEWAY_EXECUTABLE_RESOURCE);
        if executable.is_file() {
            let (config_directory, data_directory) = prepare_gateway_runtime(app, &resource_directory)?;
            return Ok(GatewayLaunch {
                executable,
                arguments: Vec::new(),
                working_directory: config_directory.clone(),
                config_directory: Some(config_directory.clone()),
                data_directory: Some(data_directory),
                log_directory: config_directory.join("logs"),
            });
        }
    }

    let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    if project_root.join("backend/app/main.py").is_file() {
        return Ok(GatewayLaunch {
            executable: PathBuf::from("python"),
            arguments: vec![
                "-m".to_string(),
                "uvicorn".to_string(),
                "backend.app.main:app".to_string(),
                "--host".to_string(),
                "127.0.0.1".to_string(),
                "--port".to_string(),
                GATEWAY_PORT.to_string(),
                "--log-level".to_string(),
                "warning".to_string(),
                "--no-access-log".to_string(),
            ],
            working_directory: project_root.clone(),
            config_directory: None,
            data_directory: None,
            log_directory: project_root.join("runtime").join("logs"),
        });
    }

    Err("找不到随应用提供的本地网关或开发环境后端".to_string())
}

fn gateway_status(process: &mut GatewayProcessState) -> GatewayStatus {
    let exited = process
        .child
        .as_mut()
        .map(|child| child.try_wait().map(|status| status.is_some()))
        .transpose()
        .ok()
        .flatten()
        .unwrap_or(false);
    if exited {
        process.child = None;
        process.executable_path = None;
        process.last_error = Some("本地网关进程已退出".to_string());
    }

    if process.reused_existing && !is_gateway_listening() {
        process.reused_existing = false;
        process.last_error = Some("此前复用的本地网关已退出".to_string());
    }

    GatewayStatus {
        running: process.child.is_some() || process.reused_existing,
        pid: process.child.as_ref().map(Child::id),
        executable_path: process
            .executable_path
            .as_ref()
            .map(|path| path.to_string_lossy().to_string()),
        reused_existing: process.reused_existing,
        last_error: process.last_error.clone(),
    }
}

fn start_gateway_process(app: &AppHandle, process: &mut GatewayProcessState) -> Result<GatewayStatus, String> {
    let current = gateway_status(process);
    if current.running {
        return Ok(current);
    }

    if is_gateway_listening() {
        process.reused_existing = true;
        process.last_error = None;
        return Ok(gateway_status(process));
    }

    let launch = match resolve_gateway_launch(app) {
        Ok(launch) => launch,
        Err(message) => {
            process.last_error = Some(message.clone());
            return Err(message);
        }
    };
    let mut command = Command::new(&launch.executable);
    let (gateway_stdout, gateway_stderr) = gateway_log_stdio(&launch.log_directory)?;
    command
        .args(&launch.arguments)
        .current_dir(&launch.working_directory)
        .stdin(Stdio::null())
        .stdout(gateway_stdout)
        .stderr(gateway_stderr);
    if let Some(config_directory) = launch.config_directory {
        command.env("DESKTOP_PET_CONFIG_DIR", config_directory);
    }
    if let Some(data_directory) = launch.data_directory {
        command.env("DESKTOP_PET_DATA_DIR", data_directory);
    }

    match command.spawn() {
        Ok(child) => {
            process.child = Some(child);
            process.executable_path = Some(launch.executable);
            process.reused_existing = false;
            process.last_error = None;
            Ok(gateway_status(process))
        }
        Err(error) => {
            let message = format!("无法启动本地网关: {error}");
            process.last_error = Some(message.clone());
            Err(message)
        }
    }
}

fn stop_gateway_process(process: &mut GatewayProcessState) -> GatewayStatus {
    if let Some(child) = process.child.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    process.child = None;
    process.executable_path = None;
    process.reused_existing = false;
    gateway_status(process)
}

fn decode_png_data_url(data_url: &str) -> Result<Vec<u8>, String> {
    let encoded = data_url
        .strip_prefix(PNG_DATA_URL_PREFIX)
        .ok_or_else(|| "仅支持 PNG Data URL".to_string())?;
    let image = BASE64_STANDARD
        .decode(encoded)
        .map_err(|_| "PNG 数据无法解码".to_string())?;

    if image.len() > MAX_SPRITE_SHEET_BYTES {
        return Err("单张 SpriteSheet 不能超过 40 MB".to_string());
    }
    if !image.starts_with(&PNG_SIGNATURE) {
        return Err("资源不是有效的 PNG 图片".to_string());
    }
    Ok(image)
}

fn package_manifest_with_fixed_files(package: &GodotResourcePackage) -> Result<Value, String> {
    let mut manifest = package.manifest.clone();
    let sheets = manifest
        .get_mut("sprite_sheets")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| "资源包缺少 sprite_sheets".to_string())?;

    if sheets.len() != package.images.len() {
        return Err("SpriteSheet 清单与图片数量不一致".to_string());
    }

    let mut seen_sheet_keys = HashSet::new();
    for (index, image) in package.images.iter().enumerate() {
        if !seen_sheet_keys.insert(&image.sheet_key) {
            return Err("SpriteSheet 不能重复同步".to_string());
        }
        let sheet = sheets
            .get_mut(&image.sheet_key)
            .and_then(Value::as_object_mut)
            .ok_or_else(|| format!("找不到 SpriteSheet: {}", image.sheet_key))?;
        sheet.insert("file".to_string(), Value::String(format!("sheet-{index}.png")));
    }

    Ok(manifest)
}

fn replace_file(from: &Path, to: &Path) -> Result<(), String> {
    if to.exists() {
        fs::remove_file(to).map_err(|error| format!("无法更新资源文件: {error}"))?;
    }
    fs::rename(from, to).map_err(|error| format!("无法提交资源文件: {error}"))
}

fn write_godot_resource_package(
    directory: &Path,
    package: GodotResourcePackage,
) -> Result<GodotResourceSyncResult, String> {
    let manifest = package_manifest_with_fixed_files(&package)?;
    let decoded_images = package
        .images
        .iter()
        .map(|image| decode_png_data_url(&image.data_url))
        .collect::<Result<Vec<_>, _>>()?;

    fs::create_dir_all(directory).map_err(|error| format!("无法创建本机资源目录: {error}"))?;

    for (index, image) in decoded_images.iter().enumerate() {
        let temporary_path = directory.join(format!(".sheet-{index}.tmp"));
        let destination_path = directory.join(format!("sheet-{index}.png"));
        fs::write(&temporary_path, image).map_err(|error| format!("无法写入 SpriteSheet: {error}"))?;
        replace_file(&temporary_path, &destination_path)?;
    }

    let manifest_path = directory.join("manifest.json");
    let temporary_manifest_path = directory.join(".manifest.tmp");
    let manifest_bytes = serde_json::to_vec_pretty(&manifest)
        .map_err(|error| format!("无法序列化资源清单: {error}"))?;
    fs::write(&temporary_manifest_path, manifest_bytes)
        .map_err(|error| format!("无法写入资源清单: {error}"))?;
    replace_file(&temporary_manifest_path, &manifest_path)?;

    Ok(GodotResourceSyncResult {
        manifest_path: manifest_path.to_string_lossy().to_string(),
        image_count: decoded_images.len(),
    })
}

#[tauri::command]
fn sync_godot_resource_package(
    app: AppHandle,
    package: GodotResourcePackage,
) -> Result<GodotResourceSyncResult, String> {
    let directory = godot_resource_directory(&app)?;
    write_godot_resource_package(&directory, package)
}

#[tauri::command]
fn get_godot_pet_status(state: State<'_, GodotProcess>) -> Result<GodotPetStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "无法读取 Godot 进程状态".to_string())?;
    Ok(godot_status(&mut process))
}

#[tauri::command]
fn start_godot_pet(
    app: AppHandle,
    state: State<'_, GodotProcess>,
) -> Result<GodotPetStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "无法读取 Godot 进程状态".to_string())?;
    let current = godot_status(&mut process);
    if current.running {
        return Ok(current);
    }
    let (executable, project) = match resolve_godot_paths(&app) {
        Ok(paths) => paths,
        Err(message) => {
            process.last_error = Some(message.clone());
            return Err(message);
        }
    };
    let child_process = match Command::new(&executable)
        .arg("--path")
        .arg(&project)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(error) => {
            let message = format!("无法启动 Godot 桌宠: {error}");
            process.last_error = Some(message.clone());
            return Err(message);
        }
    };
    process.child = Some(child_process);
    process.executable_path = Some(executable);
    process.last_error = None;
    Ok(godot_status(&mut process))
}

#[tauri::command]
fn stop_godot_pet(state: State<'_, GodotProcess>) -> Result<GodotPetStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "无法读取 Godot 进程状态".to_string())?;
    if let Some(child) = process.child.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    process.child = None;
    process.executable_path = None;
    process.last_error = None;
    Ok(godot_status(&mut process))
}

#[tauri::command]
fn get_gateway_status(state: State<'_, GatewayProcess>) -> Result<GatewayStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "无法读取本地网关状态".to_string())?;
    Ok(gateway_status(&mut process))
}

#[tauri::command]
fn start_gateway(
    app: AppHandle,
    state: State<'_, GatewayProcess>,
) -> Result<GatewayStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "无法读取本地网关状态".to_string())?;
    start_gateway_process(&app, &mut process)
}

#[tauri::command]
fn stop_gateway(state: State<'_, GatewayProcess>) -> Result<GatewayStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "无法读取本地网关状态".to_string())?;
    Ok(stop_gateway_process(&mut process))
}

#[tauri::command]
fn sync_godot_preview_state(
    app: AppHandle,
    state: GodotPreviewState,
) -> Result<(), String> {
    let directory = godot_resource_directory(&app)?;
    fs::create_dir_all(&directory).map_err(|error| format!("无法创建 Godot 控制目录: {error}"))?;
    let path = directory.join("preview.json");
    let temporary_path = directory.join(".preview.tmp");
    let bytes = serde_json::to_vec_pretty(&state)
        .map_err(|error| format!("无法序列化 Godot 预览状态: {error}"))?;
    fs::write(&temporary_path, bytes).map_err(|error| format!("无法写入 Godot 预览状态: {error}"))?;
    replace_file(&temporary_path, &path)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(GodotProcess(Mutex::new(GodotProcessState {
            child: None,
            executable_path: None,
            last_error: None,
        })))
        .manage(GatewayProcess(Mutex::new(GatewayProcessState {
            child: None,
            executable_path: None,
            reused_existing: false,
            last_error: None,
        })))
        .setup(|app| {
            migrate_legacy_runtime_if_needed();
            let app_handle = app.handle().clone();
            let gateway = app.state::<GatewayProcess>();
            if let Ok(mut process) = gateway.0.lock() {
                let _ = start_gateway_process(&app_handle, &mut process);
            }

            let godot = app.state::<GodotProcess>();
            if let Ok(mut process) = godot.0.lock() {
                let current = godot_status(&mut process);
                if !current.running {
                    match resolve_godot_paths(&app_handle) {
                        Ok((executable, project)) => match Command::new(&executable)
                            .arg("--path")
                            .arg(&project)
                            .stdin(Stdio::null())
                            .stdout(Stdio::null())
                            .stderr(Stdio::null())
                            .spawn()
                        {
                            Ok(child) => {
                                process.child = Some(child);
                                process.executable_path = Some(executable);
                                process.last_error = None;
                            }
                            Err(error) => {
                                process.last_error = Some(format!("无法启动 Godot 桌宠: {error}"));
                            }
                        },
                        Err(message) => {
                            process.last_error = Some(message);
                        }
                    }
                };
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sync_godot_resource_package,
            get_godot_pet_status,
            start_godot_pet,
            stop_godot_pet,
            get_gateway_status,
            start_gateway,
            stop_gateway,
            sync_godot_preview_state
        ])
        .build(tauri::generate_context!())
        .expect("构建灵梦桌宠应用失败")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                let gateway = app_handle.state::<GatewayProcess>();
                if let Ok(mut process) = gateway.0.lock() {
                    let _ = stop_gateway_process(&mut process);
                }
                let godot = app_handle.state::<GodotProcess>();
                if let Ok(mut process) = godot.0.lock() {
                    if let Some(child) = process.child.as_mut() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                    process.child = None;
                    process.executable_path = None;
                };
            }
        });
}

#[cfg(test)]
mod tests {
    use super::{
        decode_png_data_url, write_godot_resource_package, GodotResourceImage,
        GodotResourcePackage,
    };
    use serde_json::json;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

    #[test]
    fn accepts_a_png_data_url() {
        let image = decode_png_data_url("data:image/png;base64,iVBORw0KGgo=").unwrap();
        assert_eq!(image.len(), 8);
    }

    #[test]
    fn rejects_non_png_data() {
        assert!(decode_png_data_url("data:image/png;base64,AAAA").is_err());
        assert!(decode_png_data_url("data:image/jpeg;base64,iVBORw0KGgo=").is_err());
    }

    #[test]
    fn writes_portable_manifest_after_sprite_sheets() {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let directory = std::env::temp_dir().join(format!(
            "canvas-pet-lab-godot-resource-test-{}-{timestamp}",
            std::process::id()
        ));
        let package = GodotResourcePackage {
            manifest: json!({
                "sprite_sheets": {
                    "idle": { "file": "untrusted-name.png" }
                },
                "actions": {
                    "idle": { "sheet": "idle" }
                }
            }),
            images: vec![GodotResourceImage {
                sheet_key: "idle".to_string(),
                data_url: "data:image/png;base64,iVBORw0KGgo=".to_string(),
            }],
        };

        let result = write_godot_resource_package(&directory, package).unwrap();
        let written_manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(directory.join("manifest.json")).unwrap()).unwrap();

        assert_eq!(result.image_count, 1);
        assert_eq!(result.manifest_path, directory.join("manifest.json").to_string_lossy());
        assert_eq!(
            written_manifest["sprite_sheets"]["idle"]["file"],
            "sheet-0.png"
        );
        assert_eq!(
            fs::read(directory.join("sheet-0.png")).unwrap(),
            vec![137, 80, 78, 71, 13, 10, 26, 10]
        );

        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn godot_status_reports_a_stopped_process() {
        let mut process = super::GodotProcessState {
            child: None,
            executable_path: None,
            last_error: None,
        };
        let status = super::godot_status(&mut process);
        assert!(!status.running);
        assert_eq!(status.pid, None);
    }
}
