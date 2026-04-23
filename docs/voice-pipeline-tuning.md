# Voice Pipeline — 모델 선정 및 파라미터 튜닝 기록

RIO 의 음성 입력 파이프라인(마이크 → VAD → ASR → Intent) 에서 내린 선택과
실측 근거를 한곳에 정리한 문서.

- **대상 하드웨어**: Raspberry Pi 5 + USB mic "Generic AB13X" (close-talk)
- **관련 설정 파일**: [configs/voice.yaml](../configs/voice.yaml)
- **관련 코드**:
  [src/app/adapters/audio/live_voice_backend.py](../src/app/adapters/audio/live_voice_backend.py),
  [src/app/domains/speech/intent_parser.py](../src/app/domains/speech/intent_parser.py),
  [src/app/domains/speech/text_normalizer.py](../src/app/domains/speech/text_normalizer.py)

---

## 1. 파이프라인 개요

```
mic (PipeWire/pulse)
  → sounddevice InputStream (16 kHz / mono / float32, blocksize=512 ≈ 32 ms)
  → RMS VAD (_RmsVoiceActivityDetector)
  → 큐 depth=1 (drop_while_busy)
  → faster-whisper (base, int8, CPU)
  → KoreanCommandNormalizer (직접 치환 + jamo fuzzy)
  → intent_parser (단일 공식 발화 매칭)
  → capture → FSM
```

Phase 1 기준으로 **python backend** 와 **Rust worker backend** 두 경로가
공존한다. 본 문서의 VAD DEBUG 로그는 python 경로에서만 출력되므로 튜닝
세션에서는 `--log info` 플래그로 python 경로가 강제된다.

---

## 2. 마이크 & 오디오 캡처

| 파라미터 | 값 | 이유 |
|---|---|---|
| `audio.device` | `"pulse"` | PipeWire 경유. raw ALSA 는 장치/환경 편차가 커서 운영 비추천 |
| `audio.sample_rate` | `16000` | faster-whisper 입력 표준. 상향해도 정확도 이득 없음 |
| `audio.channels` | `1` | close-talk mono |
| `audio.blocksize` | `512` | 약 32 ms. Pi 에서 지연/안정성 균형이 좋은 기본값 |
| `audio.dtype` | `"float32"` | 내부 VAD / whisper 공통 |
| `audio.mic_gain_percent` | `25` | close-talk 기준. 과거 50 이상에서 클리핑 관찰 |
| `audio.gain_target_source` | `"AB13X"` | 부팅/실행 시 이 source 를 default input 으로 고정 |

---

## 3. VAD — RMS 기반 세그멘터

사일런스/사일레로 대신 자체 RMS 세그멘터를 쓴다 (코드:
[`_RmsVoiceActivityDetector`](../src/app/adapters/audio/live_voice_backend.py)).
Silero 대비 Pi CPU 부하가 훨씬 낮고, close-talk 환경에서 RMS 만으로 충분했다.

### 3.1 측정된 RMS 프로파일 (AB13X, 조용한 방)

`--log info` 에서 500 ms 윈도우 min/avg/max 를 샘플링해 관찰:

| 상태 | max 범위 | 특이점 |
|---|---|---|
| 무음 바닥 | 0~60 | 일반 소음 |
| 소음 스파이크 | 100~290 | 책상 진동, 호흡, 팬 등 |
| 간헐 스파이크 | 400~700 | USB noise / pygame 초기화 등 |
| 발화 (정상) | 3000~14000 | "티비 꺼줘" 평균 avg≈2500, max≈8000 |

### 3.2 확정값

| 파라미터 | 초기 → 확정 | 근거 |
|---|---|---|
| `vad.threshold` | 350 → **700** | 350 에서 스파이크 (~600) 를 speech 로 오트리거 → Listening↔Idle 플래핑 + `asr empty` 연쇄. 700 은 스파이크 상단을 차단하면서 발화 RMS 수천에 여유 |
| `vad.min_silence_duration_ms` | 300 → **500** | 300 은 발화 중 짧은 호흡/자음 공백에 조각남. 500 은 2 어절 명령을 한 utterance 로 묶기에 충분. (800 까지 올려봤지만 응답 지연 체감 커서 되돌림) |
| `vad.speech_pad_ms` | **30** | 유지. 프리/포스트 롤 |
| `vad.min_speech_ms` | 150 → **300** | 150 은 320 ms 파편이 whisper 로 유입되어 `asr empty` + 3~4 초 디코딩 낭비. 300 미만은 DROP_SHORT |

### 3.3 segment_rms 2차 가드 (코드 로직)

VAD END 확정 직후 구간 평균 RMS 가 `< 0.05` (float32 normalized peak
amplitude) 면 whisper 로 보내지 않고 silence 만 feed. 로그:

```
INFO ... drop quiet utterance dur=...ms rms=... (likely noise spike)
```

**이유**: 스파이크로 시작됐지만 실제 발화가 거의 없는 오디오가 whisper 에
들어가면 base 모델이 "자" 같은 단일 글자 hallucination 루프에 빠져
**16 초+** 디코딩하는 케이스가 관찰됐다. 정상 발화는 segment_rms ≈
0.15~0.4 수준이라 0.05 하한은 여유 충분.

---

## 4. ASR — faster-whisper

### 4.1 모델

| 파라미터 | 값 | 이유 |
|---|---|---|
| `asr.model` | `"base"` | Pi 5 CPU 에서 실시간 가능한 한계. `small` 은 decode 2~3 배, `tiny` 는 정확도 과다 손실 |
| `asr.compute_type` | `"int8"` | CPU 에서 속도/정확도 균형. Pi 에 float16 가속 없음 |
| `asr.device` | `"cpu"` | Pi 에 discrete GPU 없음 |
| `asr.language` | `"ko"` | 한국어 고정. 언어 detection 제거로 지연 단축 |
| `asr.beam_size` | `1` | greedy. Pi 에서 5 로 올리면 decode 2 배. 단일 어구 정확도는 초기 프롬프트 편향으로 충분 |

### 4.2 품질/안정성 가드

| 파라미터 | 확정값 | 근거 |
|---|---|---|
| `asr.no_speech_threshold` | 0.6 → **0.8** | 0.6 에서 `text='자' logprob=-1.96 no_speech=0.58` 같은 경계선 디코딩이 16.7 초 decode + BUSY drop 연쇄 유발. 0.8 로 올려 애매 구간은 whisper 가 스스로 드롭. 정상 발화는 no_speech≈0 이라 부작용 없음 |
| `asr.condition_on_previous_text` | true → **false** | 이전 발화 컨텍스트가 base 모델 반복 루프 유발. "티비 꺼줘" 성공 직후 "컴퓨터 켜줘" 가 32 초+ 미응답하는 케이스 관찰. 단발 명령이라 문맥 이득도 없음 |
| `asr.min_logprob` | **-1.0** | 유지. 이보다 낮으면 환각으로 간주해 capture 에 주입 안 함 |
| `compression_ratio_threshold` | **1.8** (코드에서 명시) | faster-whisper 기본 2.4 → 1.8. "X X X..." 반복 생성이 감지되자마자 fallback 경로로 포기 |

### 4.3 initial_prompt

디코더 바이어싱 용도. 주의점 두 가지:

1. **긴 문장 나열은 금물** — 과거에 `"에어컨 켜줘 에어컨 꺼줘 난방 켜줘
   ..."` 식으로 공식 문장 전체를 연결했더니, `"X 켜줘 / X 꺼줘"` 반복
   패턴이 컨텍스트가 되어 base 모델이 반복 루프에 빠짐.
2. **중복 없는 단어 리스트** — 현재는 명사/동사 어휘만 나열:

   ```
   "에어컨 난방 거실 등 간접등 티비 컴퓨터 청소기 공기청정기 음악 사진
    날씨 타이머 켜줘 꺼줘 틀어줘 돌려줘 찍어줘 알려줘 정지 확인 취소"
   ```

   편향 효과는 유지하면서 반복 패턴 미끼를 제거.

### 4.4 동시성

| 파라미터 | 값 | 이유 |
|---|---|---|
| `concurrency.drop_while_busy` | `true` | depth=1. ASR 디코딩 중 새 utterance 는 drop. Pi CPU 보호 + 응답 일관성 |

---

## 5. 텍스트 정규화 & Intent 파싱

### 5.1 단일 발화 원칙

각 intent 당 **공식 발화 1 개**만 인식한다. 유사 표현/영어/약어는 의도적
으로 제거. 단일 소스 오브 트루스: [docs/user-utterance-scenarios.md](./user-utterance-scenarios.md).

이유: 사용자 멘탈 모델 단순화 + whisper 편향 초기 프롬프트와 alias 테이블
을 동기화하기 쉬움 + 테스트 케이스가 명확.

### 5.2 STT 오인식 보정 (text_normalizer 직접 치환)

Pi 실측에서 반복 관찰된 오인식을
[`KoreanCommandNormalizer._REPLACEMENTS`](../src/app/domains/speech/text_normalizer.py)
에 추가:

| 실제 발화 | whisper 출력 | → 치환 |
|---|---|---|
| 꺼줘 | 고추 / 고중 / 고쳐 | 꺼줘 (ㄲ→ㄱ, ㅓ줘→ㅗ추/ㅗ중/ㅗ쳐) |
| 돌려줘 | 들려줘 | 돌려줘 (ㅗ/ㅡ 혼동) |
| 난방 | 단방 | 난방 (ㄴ/ㄷ 초성 혼동) |
| 간접등 | 간접든 | 간접등 |
| 거실 등 | 거실등 | (공백 유무 흡수) |

**원칙**: 명사 오인식과 의미 보존되는 동사 변형만 보정. 동사 오인식
(`켜줘`↔`꺼줘`) 은 intent 를 뒤집으므로 보정 범위에 넣지 않는다.

### 5.3 fuzzy matcher

한국어 자모 분해 + SequenceMatcher 기반 (`KoreanCommandNormalizer.
_fuzzy_best_candidate`). 명령 컨텍스트(기기명 + 동사 힌트) 에서 임계값을
낮춰 "팁이 켜줘" → "티비 켜줘" 같은 거리 가까운 오인식을 흡수한다.

---

## 6. 튜닝/디버깅 도구

### 6.1 `--log info` CLI 플래그

[scripts/run_rio_app.py](../scripts/run_rio_app.py) 에 추가된 튜닝 전용 모드.

```bash
python scripts/run_rio_app.py --preview --profile app --log info
```

설정 시:
- 환경변수 `RIO_VOICE_DEBUG=1` 주입
- voice backend 로거가 DEBUG + 전용 StreamHandler 부착
- rust backend 강제 해제 (python backend 사용) — rust worker 는 프레임별
  RMS 를 내보내지 않기 때문
- VAD 루프가 500 ms 윈도우로 RMS min/avg/max/threshold 를 한 줄씩 로깅

**기본 실행(플래그 미지정)에는 영향 없다** — voice.yaml 의 logging.level
과 backend.type 이 그대로 존중됨.

### 6.2 관측 가능한 주요 로그

| 로그 | 의미 |
|---|---|
| `vad rms samples=16 min=... avg=... max=... threshold=700` | 프레임 RMS 윈도우 요약 (DEBUG) |
| `asr decode=...ms text='...' logprob=... no_speech=...` | 정상 디코딩 |
| `asr empty (decode=...ms)` | whisper 빈 결과 |
| `drop quiet utterance dur=... rms=...` | segment_rms pre-filter |
| `BUSY drop utterance dur=...ms (ASR working)` | depth=1 보호 |
| `drop low-confidence utterance (logprob=... < ...)` | `min_logprob` 가드 |
| `activity: Idle → Listening` / `→ Idle` | FSM 에서 본 VAD 상태 |

---

## 7. 확정값 요약 (configs/voice.yaml 발췌)

```yaml
audio:
  device: "pulse"
  sample_rate: 16000
  channels: 1
  blocksize: 512
  dtype: "float32"
  mic_gain_percent: 25
  gain_target_source: "AB13X"

vad:
  threshold: 700
  min_silence_duration_ms: 500
  speech_pad_ms: 30
  min_speech_ms: 300

asr:
  model: "base"
  language: "ko"
  beam_size: 1
  compute_type: "int8"
  device: "cpu"
  no_speech_threshold: 0.8
  condition_on_previous_text: false
  min_logprob: -1.0
  initial_prompt: "에어컨 난방 거실 등 간접등 티비 컴퓨터 청소기 공기청정기 음악 사진 날씨 타이머 켜줘 꺼줘 틀어줘 돌려줘 찍어줘 알려줘 정지 확인 취소"

concurrency:
  drop_while_busy: true

logging:
  level: "INFO"   # --log info 로 런타임에 DEBUG 오버라이드
```

코드에서 명시하는 파라미터 (voice.yaml 밖):

```python
# src/app/adapters/audio/live_voice_backend.py
self._whisper.transcribe(
    ...,
    compression_ratio_threshold=1.8,  # 기본 2.4 → 1.8
)

# VAD 루프
if decision.segment_rms < 0.05:
    # drop quiet utterance (likely noise spike)
```

---

## 7.1 전처리 (시끄러운 환경 옵션, 기본 OFF)

`preprocess` 섹션. VAD 가 끝난 utterance 세그먼트에 한해 ASR 투입 직전
적용한다. per-utterance 라 스테이트/클릭 아티팩트 없음. 조용한 방 close-talk
기본 프로파일에서는 **기본 OFF**. 팬/에어컨/배경 음성 등 SNR 이 나빠지는
환경에서만 `enabled: true` 로 올린다.

| 파라미터 | 기본값 | 의미 |
|---|---|---|
| `preprocess.enabled` | `false` | 전체 on/off |
| `preprocess.apply_highpass` | `true` | 1차 IIR HPF, 저주파 험/팬 제거 |
| `preprocess.highpass_cutoff` | `0.01` | ≈ cutoff_freq / sample_rate. 16k 에서 0.01 → ~160Hz |
| `preprocess.apply_gate` | `true` | \|x\| ≤ threshold 를 0 으로 |
| `preprocess.gate_threshold` | `0.01` | float32 peak 기준. 너무 높이면 어두운 음절 깎임 |
| `preprocess.apply_normalize` | `true` | RMS 정규화 (target_rms 로 맞춤, 게인 ≤10x, ±1 클리핑) |
| `preprocess.target_rms` | `0.1` | 정규화 타겟. 정상 발화 segment_rms 0.15~0.4 에 근접하게 |

구현: [src/app/adapters/audio/preprocessor.py](../src/app/adapters/audio/preprocessor.py),
호출 지점: `_WhisperBridgeBackend._transcribe_and_feed`.

Rust backend 경로에서도 whisper 는 Python 이 돌리므로 동일하게 적용됨.

주의점:
- VAD threshold 자체는 raw 신호 기준. preprocess 는 VAD END 이후에 적용되므로
  VAD 튜닝값과 독립적. 시끄러운 환경에서 VAD 플래핑이 본질 원인이라면
  `vad.threshold` 를 먼저 올린다.
- `segment_rms < 0.05` 2차 가드는 preprocess 이전 값 기준. 순서대로:
  raw → VAD END → segment_rms 가드 → preprocess → whisper.

---

## 8. 알려진 한계 & 다음 단계 후보

- **base 모델 한국어 오인식 롱테일**: STT 오인식 치환은 관찰될 때마다
  `_REPLACEMENTS` 에 추가하는 점진 방식. 자주 반복되는 것만 커버.
- **단발 명령 외 대화 불가**: `condition_on_previous_text=false` 로 끄는
  순간 대화형 발화(이전 문맥 의존) 는 포기. RIO 는 단발 명령만 지원하는
  전제라 맞는 선택.
- **근본 개선 방향**: 오인식 롱테일이 문제라면 `model: small` 승급 검토.
  Pi 5 에서 decode ~6~8 초로 예상, 응답성과 정확도의 트레이드오프.
- **Rust worker 경로의 튜닝 로그 부재**: 프레임별 RMS 이벤트가 stdin
  protocol 에 없어 현재는 python backend 로만 튜닝 가능. 필요 시
  `trace` 이벤트 타입 확장.
