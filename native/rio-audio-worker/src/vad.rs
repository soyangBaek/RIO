use std::collections::VecDeque;

#[derive(Debug, Clone)]
pub struct VadParams {
    pub threshold: u32,
    pub silence_chunks_to_end: usize,
    pub speech_pad_chunks: usize,
    pub min_speech_ms: u64,
    pub sample_rate: u32,
}

#[derive(Debug)]
pub struct VadDecision {
    pub started: bool,
    pub ended: bool,
    pub rms: u32,
    pub start_sample: u64,
    pub end_sample: u64,
    pub duration_ms: u64,
    pub peak: f32,
    pub segment_rms: f32,
    pub dropped_short: bool,
    pub audio: Option<Vec<f32>>,
}

impl Default for VadDecision {
    fn default() -> Self {
        Self {
            started: false,
            ended: false,
            rms: 0,
            start_sample: 0,
            end_sample: 0,
            duration_ms: 0,
            peak: 0.0,
            segment_rms: 0.0,
            dropped_short: false,
            audio: None,
        }
    }
}

pub struct RmsVad {
    params: VadParams,
    active: bool,
    silent_chunks: usize,
    sample_cursor: u64,
    pre_roll: VecDeque<(u64, Vec<f32>)>,
    current_chunks: Vec<(u64, Vec<f32>)>,
    pending_silence: Vec<(u64, Vec<f32>)>,
}

impl RmsVad {
    pub fn new(params: VadParams) -> Self {
        Self {
            pre_roll: VecDeque::with_capacity(params.speech_pad_chunks.max(1)),
            params,
            active: false,
            silent_chunks: 0,
            sample_cursor: 0,
            current_chunks: Vec::new(),
            pending_silence: Vec::new(),
        }
    }

    pub fn process(&mut self, chunk: &[f32]) -> VadDecision {
        let chunk_start = self.sample_cursor;
        self.sample_cursor += chunk.len() as u64;
        let rms = rms_16bit(chunk);
        let voiced = rms >= self.params.threshold;
        let entry = (chunk_start, chunk.to_vec());

        if !self.active {
            if voiced {
                self.active = true;
                self.silent_chunks = 0;
                self.pending_silence.clear();
                self.current_chunks = self.pre_roll.drain(..).collect();
                self.current_chunks.push(entry);
                return VadDecision {
                    started: true,
                    rms,
                    ..VadDecision::default()
                };
            }
            if self.params.speech_pad_chunks > 0 {
                while self.pre_roll.len() >= self.params.speech_pad_chunks {
                    self.pre_roll.pop_front();
                }
                self.pre_roll.push_back(entry);
            }
            return VadDecision {
                rms,
                ..VadDecision::default()
            };
        }

        if voiced {
            if !self.pending_silence.is_empty() {
                self.current_chunks.append(&mut self.pending_silence);
            }
            self.silent_chunks = 0;
            self.current_chunks.push(entry);
            return VadDecision {
                rms,
                ..VadDecision::default()
            };
        }

        self.pending_silence.push(entry);
        self.silent_chunks += 1;
        if self.silent_chunks < self.params.silence_chunks_to_end {
            return VadDecision {
                rms,
                ..VadDecision::default()
            };
        }

        let mut segment_chunks = std::mem::take(&mut self.current_chunks);
        if self.params.speech_pad_chunks > 0 {
            let keep = self.pending_silence.len().min(self.params.speech_pad_chunks);
            let trailing = self.pending_silence[self.pending_silence.len() - keep..].iter().cloned();
            segment_chunks.extend(trailing);
        }

        self.pending_silence.clear();
        self.silent_chunks = 0;
        self.active = false;

        let audio = flatten_chunks(&segment_chunks);
        let start_sample = segment_chunks.first().map(|(start, _)| *start).unwrap_or(0);
        let end_sample = segment_chunks
            .last()
            .map(|(start, chunk)| *start + chunk.len() as u64)
            .unwrap_or(start_sample);
        let duration_ms = ((audio.len() as f64 / self.params.sample_rate as f64) * 1000.0).round() as u64;
        let peak = audio.iter().map(|sample| sample.abs()).fold(0.0_f32, f32::max);
        let segment_rms = rms_float(&audio);
        let dropped_short = duration_ms < self.params.min_speech_ms;

        VadDecision {
            ended: true,
            rms,
            start_sample,
            end_sample,
            duration_ms,
            peak,
            segment_rms,
            dropped_short,
            audio: Some(audio),
            ..VadDecision::default()
        }
    }
}

fn flatten_chunks(chunks: &[(u64, Vec<f32>)]) -> Vec<f32> {
    let total = chunks.iter().map(|(_, chunk)| chunk.len()).sum();
    let mut out = Vec::with_capacity(total);
    for (_, chunk) in chunks {
        out.extend_from_slice(chunk);
    }
    out
}

fn rms_float(chunk: &[f32]) -> f32 {
    if chunk.is_empty() {
        return 0.0;
    }
    let energy = chunk.iter().map(|sample| sample * sample).sum::<f32>() / chunk.len() as f32;
    energy.sqrt()
}

fn rms_16bit(chunk: &[f32]) -> u32 {
    if chunk.is_empty() {
        return 0;
    }
    let energy = chunk
        .iter()
        .map(|sample| {
            let clipped = sample.clamp(-1.0, 1.0);
            clipped * clipped
        })
        .sum::<f32>()
        / chunk.len() as f32;
    (energy.sqrt() * 32768.0).round() as u32
}
