use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;

use anyhow::Context;
use serde::Serialize;
use serde_json::Value;

#[derive(Clone)]
pub struct ControlState {
    asr_busy: Arc<AtomicBool>,
    shutdown: Arc<AtomicBool>,
}

impl ControlState {
    pub fn new() -> Self {
        Self {
            asr_busy: Arc::new(AtomicBool::new(false)),
            shutdown: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn is_asr_busy(&self) -> bool {
        self.asr_busy.load(Ordering::SeqCst)
    }

    pub fn is_shutdown(&self) -> bool {
        self.shutdown.load(Ordering::SeqCst)
    }

    pub fn spawn_stdin_listener(&self) {
        let this = self.clone();
        thread::spawn(move || {
            let stdin = io::stdin();
            let reader = io::BufReader::new(stdin.lock());
            for line in reader.lines() {
                let Ok(raw) = line else {
                    break;
                };
                let trimmed = raw.trim();
                if trimmed.is_empty() {
                    continue;
                }
                let Ok(value) = serde_json::from_str::<Value>(trimmed) else {
                    eprintln!("invalid control json: {trimmed}");
                    continue;
                };
                let kind = value.get("type").and_then(Value::as_str).unwrap_or_default();
                match kind {
                    "asr_busy" => this.asr_busy.store(true, Ordering::SeqCst),
                    "asr_idle" => this.asr_busy.store(false, Ordering::SeqCst),
                    "shutdown" => {
                        this.shutdown.store(true, Ordering::SeqCst);
                        break;
                    }
                    _ => {}
                }
            }
            this.shutdown.store(true, Ordering::SeqCst);
        });
    }
}

pub fn emit<T: Serialize>(value: &T) -> anyhow::Result<()> {
    let stdout = io::stdout();
    let mut lock = stdout.lock();
    serde_json::to_writer(&mut lock, value).context("failed to serialize worker message")?;
    lock.write_all(b"\n").context("failed to write newline")?;
    lock.flush().context("failed to flush stdout")?;
    Ok(())
}
