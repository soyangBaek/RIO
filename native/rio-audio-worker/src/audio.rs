use anyhow::{anyhow, Context};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{BufferSize, Device, SampleFormat, SampleRate, Stream, StreamConfig, SupportedStreamConfigRange};
use crossbeam_channel::Sender;

use crate::config::AudioConfig;

pub struct AudioRuntime {
    _stream: Stream,
    pub device_name: String,
}

pub fn start_audio_capture(audio_cfg: &AudioConfig, tx: Sender<Vec<f32>>) -> anyhow::Result<AudioRuntime> {
    let host = cpal::default_host();
    let device = resolve_input_device(&host, audio_cfg.device.as_deref())?;
    let device_name = device
        .name()
        .unwrap_or_else(|_| "unknown-input-device".to_string());
    let (stream_config, sample_format) = select_stream_config(&device, audio_cfg)?;
    let channels = stream_config.channels as usize;
    let err_fn = |err| eprintln!("cpal stream error: {err}");

    let stream = match sample_format {
        SampleFormat::F32 => build_stream_f32(&device, &stream_config, channels, tx, err_fn)?,
        SampleFormat::I16 => build_stream_i16(&device, &stream_config, channels, tx, err_fn)?,
        SampleFormat::U16 => build_stream_u16(&device, &stream_config, channels, tx, err_fn)?,
        other => return Err(anyhow!("unsupported sample format: {other:?}")),
    };

    stream.play().context("failed to start input stream")?;
    Ok(AudioRuntime {
        _stream: stream,
        device_name,
    })
}

fn resolve_input_device(host: &cpal::Host, hint: Option<&str>) -> anyhow::Result<Device> {
    if let Some(raw_hint) = hint {
        let lowered = raw_hint.trim().to_lowercase();
        if !lowered.is_empty() {
            let devices = host
                .input_devices()
                .context("failed to enumerate input devices")?;
            for (idx, device) in devices.enumerate() {
                let Ok(name) = device.name() else {
                    continue;
                };
                let name_lc = name.to_lowercase();
                if lowered == idx.to_string() || name_lc.contains(&lowered) {
                    return Ok(device);
                }
            }
        }
    }

    host.default_input_device()
        .ok_or_else(|| anyhow!("no usable microphone input device found"))
}

fn select_stream_config(device: &Device, audio_cfg: &AudioConfig) -> anyhow::Result<(StreamConfig, SampleFormat)> {
    let ranges = device
        .supported_input_configs()
        .context("failed to query supported input configs")?;
    let dtype_hint = audio_cfg.dtype.to_lowercase();
    let mut best: Option<(SupportedStreamConfigRange, i64)> = None;

    for range in ranges {
        let mut score = 0_i64;
        if range.channels() == audio_cfg.channels {
            score += 1000;
        } else {
            score -= ((range.channels() as i64 - audio_cfg.channels as i64).abs()) * 100;
        }

        score -= (range.min_sample_rate().0 as i64 - audio_cfg.sample_rate as i64).abs();
        let desired_format = matches!(
            (dtype_hint.as_str(), range.sample_format()),
            ("float32", SampleFormat::F32) | ("int16", SampleFormat::I16) | ("uint16", SampleFormat::U16)
        );
        if desired_format {
            score += 500;
        }

        if range.min_sample_rate().0 <= audio_cfg.sample_rate && range.max_sample_rate().0 >= audio_cfg.sample_rate {
            score += 750;
        }

        match &best {
            Some((_, best_score)) if *best_score >= score => {}
            _ => best = Some((range, score)),
        }
    }

    let (range, _) = best.ok_or_else(|| anyhow!("no supported input configuration found"))?;
    let sample_rate = if range.min_sample_rate().0 <= audio_cfg.sample_rate && range.max_sample_rate().0 >= audio_cfg.sample_rate {
        SampleRate(audio_cfg.sample_rate)
    } else {
        let min_diff = (range.min_sample_rate().0 as i64 - audio_cfg.sample_rate as i64).abs();
        let max_diff = (range.max_sample_rate().0 as i64 - audio_cfg.sample_rate as i64).abs();
        if min_diff <= max_diff {
            range.min_sample_rate()
        } else {
            range.max_sample_rate()
        }
    };

    let mut stream_config = range.with_sample_rate(sample_rate).config();
    stream_config.channels = audio_cfg.channels.max(1);
    stream_config.buffer_size = BufferSize::Fixed(audio_cfg.blocksize.max(1));
    Ok((stream_config, range.sample_format()))
}

fn build_stream_f32(
    device: &Device,
    config: &StreamConfig,
    channels: usize,
    tx: Sender<Vec<f32>>,
    err_fn: impl FnMut(cpal::StreamError) + Send + 'static,
) -> anyhow::Result<Stream> {
    let stream = device.build_input_stream(
        config,
        move |data: &[f32], _| {
            let _ = tx.send(extract_first_channel_f32(data, channels));
        },
        err_fn,
        None,
    )?;
    Ok(stream)
}

fn build_stream_i16(
    device: &Device,
    config: &StreamConfig,
    channels: usize,
    tx: Sender<Vec<f32>>,
    err_fn: impl FnMut(cpal::StreamError) + Send + 'static,
) -> anyhow::Result<Stream> {
    let stream = device.build_input_stream(
        config,
        move |data: &[i16], _| {
            let normalized: Vec<f32> = if channels <= 1 {
                data.iter().map(|sample| *sample as f32 / 32768.0).collect()
            } else {
                data.chunks(channels)
                    .map(|frame| frame[0] as f32 / 32768.0)
                    .collect()
            };
            let _ = tx.send(normalized);
        },
        err_fn,
        None,
    )?;
    Ok(stream)
}

fn build_stream_u16(
    device: &Device,
    config: &StreamConfig,
    channels: usize,
    tx: Sender<Vec<f32>>,
    err_fn: impl FnMut(cpal::StreamError) + Send + 'static,
) -> anyhow::Result<Stream> {
    let stream = device.build_input_stream(
        config,
        move |data: &[u16], _| {
            let normalized: Vec<f32> = if channels <= 1 {
                data.iter().map(|sample| (*sample as f32 - 32768.0) / 32768.0).collect()
            } else {
                data.chunks(channels)
                    .map(|frame| (frame[0] as f32 - 32768.0) / 32768.0)
                    .collect()
            };
            let _ = tx.send(normalized);
        },
        err_fn,
        None,
    )?;
    Ok(stream)
}

fn extract_first_channel_f32(data: &[f32], channels: usize) -> Vec<f32> {
    if channels <= 1 {
        return data.to_vec();
    }
    data.chunks(channels).map(|frame| frame[0]).collect()
}
