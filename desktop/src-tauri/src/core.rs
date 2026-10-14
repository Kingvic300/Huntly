//! Supervises the local Python core service.
//!
//! The core listens on 127.0.0.1 only, on a free port chosen at launch, and
//! requires a random bearer token generated fresh for every launch. The token
//! is passed through the child's environment (never the command line, which
//! other local users could read from /proc) and handed to the UI over IPC.

use std::net::TcpListener;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Manager};

#[derive(Clone, Serialize)]
pub struct CoreConnection {
    pub base_url: String,
    pub token: String,
    pub mode: &'static str,
}

pub enum CoreChild {
    #[allow(dead_code)]
    Dev(std::process::Child),
    #[allow(dead_code)]
    Sidecar(tauri_plugin_shell::process::CommandChild),
}

pub struct CoreState {
    pub connection: Mutex<Option<CoreConnection>>,
    pub child: Mutex<Option<CoreChild>>,
    pub error: Mutex<Option<String>>,
}

impl Default for CoreState {
    fn default() -> Self {
        Self { connection: Mutex::new(None), child: Mutex::new(None), error: Mutex::new(None) }
    }
}

fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    Ok(listener.local_addr()?.port())
}

fn random_token() -> String {
    let mut buf = [0u8; 32];
    getrandom::getrandom(&mut buf).expect("OS random source unavailable");
    hex::encode(buf)
}

pub fn start(app: &AppHandle) -> Result<(), String> {
    let port = free_port().map_err(|e| format!("no free port: {e}"))?;
    let token = random_token();
    let state = app.state::<CoreState>();

    // Allow an externally started core (e.g. `python -m huntly`) during development.
    if let (Ok(url), Ok(tok)) = (std::env::var("HUNTLY_CORE_URL"), std::env::var("HUNTLY_CORE_TOKEN")) {
        *state.connection.lock().unwrap() = Some(CoreConnection { base_url: url, token: tok, mode: "external" });
        return Ok(());
    }

    let child = if cfg!(debug_assertions) { spawn_dev(port, &token)? } else { spawn_sidecar(app, port, &token)? };
    *state.child.lock().unwrap() = Some(child);
    *state.connection.lock().unwrap() = Some(CoreConnection {
        base_url: format!("http://127.0.0.1:{port}"),
        token,
        mode: if cfg!(debug_assertions) { "dev" } else { "bundled" },
    });
    Ok(())
}

fn spawn_dev(port: u16, token: &str) -> Result<CoreChild, String> {
    let manifest = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let repo = manifest.join("../..");
    let python = std::env::var("HUNTLY_PYTHON").unwrap_or_else(|_| repo.join(".venv/bin/python").to_string_lossy().into_owned());
    std::process::Command::new(python)
        .args(["-m", "huntly", "--port", &port.to_string()])
        .current_dir(repo.join("core"))
        .env("HUNTLY_API_TOKEN", token)
        .spawn()
        .map(CoreChild::Dev)
        .map_err(|e| format!("failed to start dev core (set HUNTLY_PYTHON or create .venv): {e}"))
}

fn spawn_sidecar(app: &AppHandle, port: u16, token: &str) -> Result<CoreChild, String> {
    use tauri_plugin_shell::process::CommandEvent;
    use tauri_plugin_shell::ShellExt;

    let (mut rx, child) = app
        .shell()
        .sidecar("huntly-core")
        .map_err(|e| format!("core binary missing: {e}"))?
        .args(["--port", &port.to_string()])
        .env("HUNTLY_API_TOKEN", token)
        .spawn()
        .map_err(|e| format!("failed to start core: {e}"))?;

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if let CommandEvent::Terminated(payload) = event {
                let msg = format!("Core service stopped (exit code {:?})", payload.code);
                *handle.state::<CoreState>().error.lock().unwrap() = Some(msg);
            }
        }
    });
    Ok(CoreChild::Sidecar(child))
}

pub fn stop(app: &AppHandle) {
    let state = app.state::<CoreState>();
    let taken = state.child.lock().unwrap().take();
    match taken {
        Some(CoreChild::Dev(mut c)) => {
            let _ = c.kill();
            let _ = c.wait();
        }
        Some(CoreChild::Sidecar(c)) => {
            let _ = c.kill();
        }
        None => {}
    }
}

#[tauri::command]
pub fn core_connection(state: tauri::State<'_, CoreState>) -> Result<CoreConnection, String> {
    if let Some(err) = state.error.lock().unwrap().clone() {
        return Err(err);
    }
    state.connection.lock().unwrap().clone().ok_or_else(|| "Core service not started".into())
}
