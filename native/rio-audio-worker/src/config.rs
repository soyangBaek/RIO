use std::fs;
use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use serde::Deserialize;
use serde_yaml::Value;

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
    let raw_cfg = load_voice_config_value(path)?;
    let cfg: VoiceConfig = serde_yaml::from_value(raw_cfg)
        .with_context(|| format!("failed to parse YAML config: {}", path.display()))?;
    Ok(cfg)
}

fn load_voice_config_value(path: &Path) -> anyhow::Result<Value> {
    let raw = fs::read_to_string(path)
        .with_context(|| format!("failed to read config file: {}", path.display()))?;
    let cfg: Value = serde_yaml::from_str(&raw)
        .with_context(|| format!("failed to parse YAML config: {}", path.display()))?;

    let Some(extends) = extract_extends(&cfg) else {
        return Ok(cfg);
    };

    let base_path = resolve_extends_path(path, &extends);
    let base_cfg = load_voice_config_value(&base_path)?;
    Ok(deep_merge(base_cfg, strip_extends(cfg)))
}

fn extract_extends(cfg: &Value) -> Option<String> {
    let Value::Mapping(mapping) = cfg else {
        return None;
    };
    mapping
        .get(&Value::String("extends".to_string()))
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

fn strip_extends(cfg: Value) -> Value {
    match cfg {
        Value::Mapping(mut mapping) => {
            mapping.remove(&Value::String("extends".to_string()));
            Value::Mapping(mapping)
        }
        other => other,
    }
}

fn resolve_extends_path(path: &Path, extends: &str) -> PathBuf {
    let relative = PathBuf::from(extends);
    if relative.is_absolute() {
        return relative;
    }

    let sibling = path
        .parent()
        .map(|parent| parent.join(&relative))
        .unwrap_or_else(|| relative.clone());
    if sibling.exists() {
        return sibling;
    }

    let repo_relative = path
        .parent()
        .and_then(Path::parent)
        .map(|root| root.join(&relative));
    if let Some(candidate) = repo_relative {
        if candidate.exists() {
            return candidate;
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        let candidate = cwd.join(&relative);
        if candidate.exists() {
            return candidate;
        }
    }

    sibling
}

fn deep_merge(base: Value, override_value: Value) -> Value {
    match (base, override_value) {
        (Value::Mapping(mut base_map), Value::Mapping(override_map)) => {
            for (key, value) in override_map {
                let merged = match base_map.remove(&key) {
                    Some(existing) => deep_merge(existing, value),
                    None => value,
                };
                base_map.insert(key, merged);
            }
            Value::Mapping(base_map)
        }
        (_, value) => value,
    }
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

#[cfg(test)]
mod tests {
    use super::load_voice_config;
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root() -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time went backwards")
            .as_nanos();
        std::env::temp_dir().join(format!("rio-audio-worker-config-{unique}"))
    }

    #[test]
    fn load_voice_config_merges_extended_yaml() {
        let root = temp_root();
        let configs_dir = root.join("configs");
        fs::create_dir_all(&configs_dir).expect("create temp config dir");

        let base_path = configs_dir.join("voice.yaml");
        fs::write(
            &base_path,
            r#"
audio:
  sample_rate: 16000
vad:
  threshold: 700
  min_silence_duration_ms: 500
concurrency:
  drop_while_busy: false
"#,
        )
        .expect("write base config");

        let child_path = configs_dir.join("voice_sandbox.yaml");
        fs::write(
            &child_path,
            r#"
extends: "configs/voice.yaml"
vad:
  min_speech_ms: 300
"#,
        )
        .expect("write child config");

        let cfg = load_voice_config(&child_path).expect("load merged config");
        assert_eq!(cfg.audio.sample_rate, 16_000);
        assert_eq!(cfg.vad.threshold, 700);
        assert_eq!(cfg.vad.min_silence_duration_ms, 500);
        assert_eq!(cfg.vad.min_speech_ms, 300);
        assert!(!cfg.concurrency.drop_while_busy);

        fs::remove_dir_all(root).expect("cleanup temp config dir");
    }
}
