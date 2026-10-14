mod core;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, RunEvent};

fn show_main(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn build_menu(app: &tauri::AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let file = Submenu::with_items(
        app,
        "File",
        true,
        &[
            &MenuItem::with_id(app, "collect", "Collect jobs now", true, Some("CmdOrCtrl+R"))?,
            &MenuItem::with_id(app, "lock", "Lock vault", true, Some("CmdOrCtrl+L"))?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItem::with_id(app, "quit", "Quit Huntly", true, Some("CmdOrCtrl+Q"))?,
        ],
    )?;
    let edit = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, None)?,
            &PredefinedMenuItem::redo(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, None)?,
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::paste(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;
    let go = Submenu::with_items(
        app,
        "Go",
        true,
        &[
            &MenuItem::with_id(app, "nav:/", "Overview", true, Some("CmdOrCtrl+1"))?,
            &MenuItem::with_id(app, "nav:/jobs", "Discover Jobs", true, Some("CmdOrCtrl+2"))?,
            &MenuItem::with_id(app, "nav:/applications", "Applications", true, Some("CmdOrCtrl+3"))?,
            &MenuItem::with_id(app, "nav:/approvals", "Email Approvals", true, Some("CmdOrCtrl+4"))?,
            &MenuItem::with_id(app, "nav:/cv", "CV Library", true, Some("CmdOrCtrl+5"))?,
            &MenuItem::with_id(app, "nav:/sources", "Sources", true, Some("CmdOrCtrl+6"))?,
            &MenuItem::with_id(app, "nav:/analytics", "Analytics", true, Some("CmdOrCtrl+7"))?,
            &MenuItem::with_id(app, "nav:/settings", "Settings", true, Some("CmdOrCtrl+,"))?,
        ],
    )?;
    let help = Submenu::with_items(
        app,
        "Help",
        true,
        &[&MenuItem::with_id(app, "nav:/settings#privacy", "Privacy & security", true, None::<&str>)?],
    )?;
    Menu::with_items(app, &[&file, &edit, &go, &help])
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(core::CoreState::default())
        .invoke_handler(tauri::generate_handler![core::core_connection])
        .setup(|app| {
            let handle = app.handle().clone();
            if let Err(e) = core::start(&handle) {
                *handle.state::<core::CoreState>().error.lock().unwrap() = Some(e);
            }

            // Linux and Windows: no menu bar; every action has an in-app shortcut.
            // macOS keeps a minimal menu because copy/paste shortcuts depend on it there.
            if cfg!(target_os = "macos") {
                let menu = build_menu(&handle)?;
                app.set_menu(menu)?;
            } else {
                app.remove_menu()?;
            }
            app.on_menu_event(|app, event| {
                let id = event.id().as_ref();
                match id {
                    "quit" => app.exit(0),
                    "collect" | "lock" => {
                        let _ = app.emit("menu", id);
                    }
                    other if other.starts_with("nav:") => {
                        show_main(app);
                        let _ = app.emit("navigate", &other[4..]);
                    }
                    _ => {}
                }
            });

            let tray_menu = Menu::with_items(
                app,
                &[
                    &MenuItem::with_id(app, "tray:show", "Show Huntly", true, None::<&str>)?,
                    &MenuItem::with_id(app, "collect", "Collect jobs now", true, None::<&str>)?,
                    &PredefinedMenuItem::separator(app)?,
                    &MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?,
                ],
            )?;
            let mut tray = TrayIconBuilder::with_id("main")
                .tooltip("Huntly")
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "tray:show" => show_main(app),
                    "collect" => {
                        let _ = app.emit("menu", "collect");
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, .. } = event {
                        show_main(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            // A missing tray (e.g. no StatusNotifier host) must not stop the app.
            let _ = tray.build(app);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Huntly")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                core::stop(app);
            }
        });
}
