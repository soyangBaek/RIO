mod audio;
mod config;
mod ipc;
mod vad;

use std::env;
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{Context, Result};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use crossbeam_channel::bounded;
use serde_json::json;

use crate::audio::start_audio_capture;
use crate::config::load_voice_config;
use crate::ipc::{emit, ControlState};
use crate::vad::{RmsVad, VadParams};

fn main() -> Result<()> {
    let config_path = parse_args().context("failed to parse args")?;
    let cfg = load_voice_config(&config_path)?;

    let chunk_ms = ((cfg.audio.blocksize as f64 / cfg.audio.sample_rate as f64) * 1000.0).max(1.0);
    let silence_chunks_to_end = ((cfg.vad.min_silence_duration_ms as f64 / chunk_ms).ceil() as usize).max(1);
    let speech_pad_chunks = (cfg.vad.speech_pad_ms as f64 / chunk_ms).ceil() as usize;

    let vad_params = VadParams {
        threshold: cfg.vad.threshold,
        silence_chunks_to_end,
        speech_pad_chunks,
        min_speech_ms: cfg.vad.min_speech_ms,
        sample_rate: cfg.audio.sample_rate,
    };

    eprintln!(
        "starting rio-audio-worker threshold={} silence_chunks={} pad_chunks={} rate={} blocksize={}",
        cfg.vad.threshold,
        silence_chunks_to_end,
        speech_pad_chunks,
        cfg.audio.sample_rate,
        cfg.audio.blocksize
    );

    let (audio_tx, audio_rx) = bounded::<Vec<f32>>(64);
    let runtime = start_audio_capture(&cfg.audio, audio_tx)?;
    let control = ControlState::new();
    control.spawn_stdin_listener();

    emit(&json!({
        "type": "ready",
        "device": runtime.device_name,
        "sample_rate": cfg.audio.sample_rate,
        "blocksize": cfg.audio.blocksize,
    }))?;

    let mut vad = RmsVad::new(vad_params);
    while !control.is_shutdown() {
        let Ok(chunk) = audio_rx.recv_timeout(Duration::from_millis(100)) else {
            continue;
        };
        if control.is_shutdown() {
            break;
        }
        let decision = vad.process(&chunk);
        if decision.started {
            emit(&json!({
                "type": "speech_started",
                "rms": decision.rms,
            }))?;
        }

        if !decision.ended {
            continue;
        }

        emit(&json!({
            "type": "speech_ended",
            "start_sample": decision.start_sample,
            "end_sample": decision.end_sample,
            "duration_ms": decision.duration_ms,
            "peak": decision.peak,
            "rms": decision.segment_rms,
            "dropped_short": decision.dropped_short,
        }))?;

        if decision.dropped_short {
            continue;
        }

        if cfg.concurrency.drop_while_busy && control.is_asr_busy() {
            emit(&json!({
                "type": "busy_drop",
                "duration_ms": decision.duration_ms,
            }))?;
            continue;
        }

        if let Some(audio) = decision.audio {
            emit(&json!({
                "type": "utterance",
                "sample_rate": cfg.audio.sample_rate,
                "start_sample": decision.start_sample,
                "end_sample": decision.end_sample,
                "duration_ms": decision.duration_ms,
                "peak": decision.peak,
                "rms": decision.segment_rms,
                "pcm_f32_b64": encode_pcm_f32(&audio),
            }))?;
        }
    }

    eprintln!("rio-audio-worker stopped");
    Ok(())
}

fn parse_args() -> Result<PathBuf> {
    let mut args = env::args().skip(1);
    let mut config_path: Option<PathBuf> = None;
    while let Some(arg) = args.next() {
        if arg == "--config" {
            let Some(value) = args.next() else {
                anyhow::bail!("--config requires a path");
            };
            config_path = Some(PathBuf::from(value));
        }
    }
    config_path.ok_or_else(|| anyhow::anyhow!("missing required --config <path>"))
}

fn encode_pcm_f32(audio: &[f32]) -> String {
    let mut bytes = Vec::with_capacity(audio.len() * 4);
    for sample in audio {
        bytes.extend_from_slice(&sample.to_le_bytes());
    }
    BASE64.encode(bytes)
}
