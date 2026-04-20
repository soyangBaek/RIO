use std::fs;
use std::path::Path;

use anyhow::Context;
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct VoiceConfig {
    #[serde(default)]
    pub audio: AudioConfig,
    #[serde(default)]
    pub vad: VadConfig,
    #[serde(default)]
    pub concurrency: ConcurrencyConfig,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
pub struct AudioConfig {
    #[serde(default = "default_device")]
    pub device: Option<String>,
    #[serde(default = "default_sample_rate")]
    pub sample_rate: u32,
    #[serde(default = "default_channels")]
    pub channels: u16,
    #[serde(default = "default_blocksize")]
    pub blocksize: u32,
    #[serde(default = "default_dtype")]
    pub dtype: String,
    #[serde(default)]
    pub mic_gain_percent: Option<u8>,
    #[serde(default)]
    pub gain_target_source: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct VadConfig {
    #[serde(default = "default_vad_threshold")]
    pub threshold: u32,
    #[serde(default = "default_min_silence_ms")]
    pub min_silence_duration_ms: u64,
    #[serde(default = "default_speech_pad_ms")]
    pub speech_pad_ms: u64,
    #[serde(default = "default_min_speech_ms")]
    pub min_speech_ms: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ConcurrencyConfig {
    #[serde(default = "default_drop_while_busy")]
    pub drop_while_busy: bool,
}

impl Default for VoiceConfig {
    fn default() -> Self {
        Self {
            audio: AudioConfig::default(),
            vad: VadConfig::default(),
            concurrency: ConcurrencyConfig::default(),
        }
    }
}

impl Default for AudioConfig {
    fn default() -> Self {
        Self {
            device: default_device(),
            sample_rate: default_sample_rate(),
            channels: default_channels(),
            blocksize: default_blocksize(),
            dtype: default_dtype(),
            mic_gain_percent: None,
            gain_target_source: None,
        }
    }
}

impl Default for VadConfig {
    fn default() -> Self {
        Self {
            threshold: default_vad_threshold(),
            min_silence_duration_ms: default_min_silence_ms(),
            speech_pad_ms: default_speech_pad_ms(),
            min_speech_ms: default_min_speech_ms(),
        }
    }
}

impl Default for ConcurrencyConfig {
    fn default() -> Self {
        Self {
            drop_while_busy: default_drop_while_busy(),
        }
    }
}

pub fn load_voice_config(path: &Path) -> anyhow::Result<VoiceConfig> {
    let raw = fs::read_to_string(path)
        .with_context(|| format!("failed to read config file: {}", path.display()))?;
    let cfg: VoiceConfig = serde_yaml::from_str(&raw)
        .with_context(|| format!("failed to parse YAML config: {}", path.display()))?;
    Ok(cfg)
}

fn default_device() -> Option<String> {
    Some("pulse".to_string())
}

fn default_sample_rate() -> u32 {
    16_000
}

fn default_channels() -> u16 {
    1
}

fn default_blocksize() -> u32 {
    512
}

fn default_dtype() -> String {
    "float32".to_string()
}

fn default_vad_threshold() -> u32 {
    350
}

fn default_min_silence_ms() -> u64 {
    300
}

fn default_speech_pad_ms() -> u64 {
    30
}

fn default_min_speech_ms() -> u64 {
    150
}

fn default_drop_while_busy() -> bool {
    true
}
