# RIO 음성 인식 수동 테스트 계획 (Voice Test Plan)

> 기준 문서: prd.md, state-machine.md, scenarios.md, configs/triggers.yaml, configs/voice.yaml
> 작성일: 2026-04-17
> 테스트 진입점: `scripts/live_voice_interaction_test.py`
> 대상 기능: `src/app/adapters/audio/live_voice_backend.py` (Silero VAD + faster-whisper + pactl mic gain)

---

## 1. 범위와 전제

### 이번 문서가 다루는 것
- 실제 마이크로 발화 → `voice.intent.*` 이벤트 발행까지의 end-to-end 파이프라인
- VAD/ASR/게인 튜닝 파라미터가 동작에 미치는 영향
- depth=1 동시성 규칙 (Whisper 디코딩 중 신규 발화 drop)
- 환각 차단 (`min_logprob`) 으로 무음/노이즈 입력이 intent 로 이어지지 않는지

### 다루지 않는 것
- **wake word** (구현 안 됨 — 오케스트레이터 측에서 판단하기로 결정)
- 기존 터미널 텍스트 입력 경로 (`manual-test-plan.md` MT-VOICE-* 항목에서 다룸)
- FSM/scene/executor 연쇄 동작 (기존 `manual-test-plan.md` 범위)

---

## 2. 실행 환경

### 필수 하드웨어
- Raspberry Pi (현재 검증: Pi 5)
- USB 웹캠 (카메라용, 기존 요구와 동일)
- USB 마이크 — 현재 검증 완료: **Walmart AB13X USB Headset Adapter**
  - PipeWire source: `alsa_input.usb-Generic_AB13X_USB_Audio_20210926172016-00.mono-fallback`
  - 네이티브 포맷: 48kHz s16le mono → PipeWire 가 자동으로 16kHz 로 리샘플
- 스피커 (3.5mm 또는 HDMI)

### 소프트웨어 의존성 (venv 에 설치됨)
- `sounddevice` ≥ 0.5
- `silero-vad` ≥ 6.2 (ONNX 런타임)
- `onnxruntime` ≥ 1.24
- `faster-whisper` ≥ 1.2 (CTranslate2 백엔드)
- `torch` ≥ 2.0 (CPU 전용, VADIterator 텐서 요구)
- PipeWire / PulseAudio (`pactl` 명령 필요 — mic gain 자동 설정용)

### 실행 명령

```bash
cd ~/RIO
venv/bin/python scripts/live_voice_interaction_test.py
```

옵션:
- `--real-services`: 스마트홈/날씨 실제 HTTP 요청
- `--debug`: 웹캠 인셋 + 상태 사이드바
- `--no-preview`: 창 없이 실행

### 기동 시 확인할 로그 (정상)

```
[voice] starting live mic backend (Silero VAD + faster-whisper)...
mic gain → 25% on 'alsa_input.usb-Generic_AB13X_USB_Audio_...' | Volume: mono: 16384 / 25%
loading silero-vad (threshold=0.85)
loading faster-whisper 'base' (compute_type=int8, device=cpu)...
models ready
opening audio device=<N> rate=16000 blocksize=512 ch=1 dtype=float32
LiveVoiceBackend started
```

로그 중 하나라도 빠지면 **SETUP 실패**로 판정하고 원인 확인 후 재시도.

---

## 3. 테스트 보조 명령 (설정 변경)

파라미터는 `configs/voice.yaml` 에서 변경 후 프로세스 재시작:

| 파라미터 | 기본값 | 변경 시 효과 |
|---------|-------|------------|
| `vad.threshold` | 0.85 | 0.5 = 속삭임도 감지 / 0.95 = 큰 목소리만 |
| `audio.mic_gain_percent` | 25 | 10 = close-talk, 50 = 책상 거리, 100 = 원거리 |
| `asr.model` | `base` | `tiny` 더 빠름 / `small` 더 정확 |
| `asr.min_logprob` | -1.0 | -0.8 엄격 / -1.5 관대 |
| `vad.min_speech_ms` | 150 | 짧은 발화 drop 기준 |
| `concurrency.drop_while_busy` | true | false 로 바꾸면 depth 쌓이기 허용 |

---

## 4. 판정 기준

- **PASS**: 기대 이벤트가 발행되고 기대 payload 가 관찰됨
- **FAIL**: 이벤트 미발행, 오발행, 또는 파이프라인 오류
- **SKIP**: 하드웨어 미지원 (mic 없음 등)

각 테스트 케이스는 실행 중 로그를 `/tmp/rio_run.log` 같은 파일로 받아 두고 PASS/FAIL 근거로 첨부.

```bash
venv/bin/python scripts/live_voice_interaction_test.py 2>&1 | tee /tmp/rio_run.log
```

---

# Tester: 음성 인식 담당

## MT-VOICE-LIVE: 실제 마이크 입력 (12개)

### MT-VOICE-LIVE-01: 기본 intent 매칭 — 스마트홈 조명

| 항목 | 내용 |
|------|------|
| **목적** | 가장 단순한 intent 1건이 end-to-end 로 발행되는지 확인 |
| **전제** | AB13X mic 연결, 조용한 환경, AWAKE/ASLEEP 개념 없음 |
| **절차** | 1. 프로그램 실행 → "models ready" 확인<br>2. mic 에 가까이 대고 또렷하게 **"불 켜줘"** |
| **기대** | 로그에:<br>- `[asr] ... text='불 켜줘' logprob=>-0.5 no_speech=<0.2`<br>- `voice.activity.started` → `voice.intent.detected(intent=smarthome.light.on)` → `voice.activity.ended` |
| **PASS 조건** | `intent=smarthome.light.on` 이 payload 에 포함된 이벤트 발행 |
| **FAIL 예시** | "불 켜줘" 라고 말했는데 `voice.intent.unknown` 으로 발행 → Whisper 전사 실패 or triggers.yaml 매칭 실패 |

---

### MT-VOICE-LIVE-02: Alias 매칭 — 동일 intent 의 다른 표현

| 항목 | 내용 |
|------|------|
| **목적** | `triggers.yaml` 의 여러 alias 가 모두 동일 intent 로 매핑되는지 |
| **절차** | 각각 말하고 각 intent 발행 확인:<br>1. "조명 켜줘" → `smarthome.light.on`<br>2. "춤춰" → `dance.start`<br>3. "사진 찍어줘" → `camera.capture`<br>4. "날씨 알려줘" → `weather.current` |
| **기대** | 네 건 모두 `voice.intent.detected` 로 올바른 intent 발행 |

---

### MT-VOICE-LIVE-03: 미매칭 발화 → `voice.intent.unknown`

| 항목 | 내용 |
|------|------|
| **목적** | triggers.yaml 에 없는 발화가 unknown 으로 처리되는지 + 원본 text 가 payload 에 실리는지 |
| **절차** | "안녕 리오야" 라고 말함 |
| **기대** | `voice.intent.unknown` 이벤트 발행, `payload.text` 에 전사된 텍스트 포함 |
| **PASS 조건** | `voice.intent.unknown` 의 payload 에 발화 텍스트 존재 |

---

### MT-VOICE-LIVE-04: depth=1 동시성 규칙

| 항목 | 내용 |
|------|------|
| **목적** | Whisper 디코딩 중 (~0.5-2s) 에 새 발화가 들어오면 drop 되는지 |
| **절차** | 1. "불 켜줘" 말함<br>2. `[asr] decoding ...` 로그 뜨자마자 **바로 이어서** "에어컨 켜줘" 말함<br>3. 로그 관찰 |
| **기대** | 1번 발화 완료 후 `smarthome.light.on` 발행.<br>2번 발화는 `BUSY drop utterance dur=XXXms` 로그만 남고 `voice.intent.*` **미발행** |
| **PASS 조건** | 두 번째 발화의 intent 가 발행되지 않음 + BUSY drop 로그 존재 |

---

### MT-VOICE-LIVE-05: min_speech_ms 로 짧은 소음 제거

| 항목 | 내용 |
|------|------|
| **목적** | 기침/혀차기/딸꾹질 같은 150ms 미만 소리가 ASR 로 가지 않음 |
| **절차** | 1. mic 근처에서 "쯧" 또는 가벼운 기침<br>2. 로그 관찰 |
| **기대** | `drop short utterance <150ms` 디버그 로그 (또는 조용히 drop), ASR 디코딩 로그 없음, intent 이벤트 없음 |
| **참고** | `vad.min_speech_ms` 값을 300 으로 올리면 더 엄격하게 차단 |

---

### MT-VOICE-LIVE-06: 환각 차단 (logprob 필터)

| 항목 | 내용 |
|------|------|
| **목적** | 무음/노이즈에서 Whisper 가 "감사합니다" 같은 환각을 만들어도 이벤트로 이어지지 않음 |
| **절차** | 1. mic 앞에서 아무 말 없이 30초 대기<br>2. 로그에서 ASR 발화 감지 횟수 관찰 |
| **기대** | VAD 가 어쩌다 speech 로 판정해도 ASR logprob 가 -1.0 미만 → `drop low-confidence utterance` 로그로 차단, intent 이벤트 발행 안 됨 |
| **PASS 조건** | 30초 동안 `voice.intent.*` 이벤트 0건 |
| **FAIL 시** | `voice.intent.unknown(text='감사합니다')` 같은 환각 이벤트가 발행됨 → `asr.min_logprob` 를 -0.8 로 엄격화 or `vad.threshold` 를 0.9 로 올림 |

---

### MT-VOICE-LIVE-07: mic_gain 자동 설정 검증

| 항목 | 내용 |
|------|------|
| **목적** | 프로그램 시작 시 `configs/voice.yaml` 의 `mic_gain_percent` 값이 실제 시스템에 적용됨 |
| **절차** | 1. 실행 전: `pactl get-source-volume alsa_input.usb-Generic_AB13X_...` 로 현재 값 기록<br>2. 프로그램 실행<br>3. 기동 로그에서 `mic gain → 25% on '...'` 확인<br>4. 실행 중: 다시 `pactl get-source-volume` 실행해서 25% 여부 확인 |
| **기대** | 로그에 설정 성공 메시지, pactl 명령 결과 25% |
| **PASS 조건** | pactl 이 25% 를 반환 |

---

### MT-VOICE-LIVE-08: 거리/gain 반응 (close-talk 전제)

| 항목 | 내용 |
|------|------|
| **목적** | 현재 튜닝(gain=25%, VAD threshold=0.85) 이 close-talk 최적화 되었음을 검증 — 멀리서 말하면 인식 안 됨 |
| **절차** | 1. mic 에서 5 cm 거리 — "불 켜줘" (PASS 기대)<br>2. mic 에서 30 cm 거리 — "불 켜줘" (VAD 감지 안 되거나 logprob 낮음 기대)<br>3. mic 에서 1 m 거리 — "불 켜줘" (감지 안 됨 기대) |
| **기대** | 1번만 intent 발행, 2/3번은 무시 또는 unknown |
| **의미** | 이 거동은 의도된 설계. 환경에 따라 mic_gain_percent 와 vad.threshold 를 조정 |

---

### MT-VOICE-LIVE-09: 연속 명령 (ASR 완료 대기 후)

| 항목 | 내용 |
|------|------|
| **목적** | 한 발화가 끝나고 충분한 간격 (>2s) 을 두면 다음 발화도 정상 처리 |
| **절차** | 1. "불 켜줘" → ASR done 로그 확인 (~1s)<br>2. 2초 대기<br>3. "에어컨 켜줘" |
| **기대** | 두 발화 모두 `voice.intent.detected` 발행 (첫 번째 smarthome.light.on, 두 번째 smarthome.aircon.on) |
| **PASS 조건** | 두 intent 모두 payload 에 포함 |

---

### MT-VOICE-LIVE-10: 터미널 입력 경로와 공존

| 항목 | 내용 |
|------|------|
| **목적** | live voice 를 켠 상태에서도 기존 터미널 텍스트 입력이 여전히 동작 |
| **절차** | 1. 프로그램 실행<br>2. 터미널에 `불 켜줘` 타이핑 후 Enter<br>3. mic 에 "에어컨 켜줘" 말함 |
| **기대** | 두 경로 모두 `voice.intent.detected` 발행. 두 개의 normalizer 인스턴스 (스크립트의 `terminal_voice` + `rio.audio_worker.normalizer`) 가 각자 동작하지만 bus 에는 이벤트가 정상 축적 |

---

### MT-VOICE-LIVE-11: 종료 시 자원 정리

| 항목 | 내용 |
|------|------|
| **목적** | Ctrl+C 로 종료 시 backend 스레드가 모두 정리되어 hang 없음 |
| **절차** | 1. 프로그램 실행 후 10초 대기<br>2. Ctrl+C<br>3. 프로세스 종료 확인 |
| **기대** | 3초 이내에 `LiveVoiceBackend stopped` 로그 + 프로세스 exit |
| **FAIL 시** | `pgrep -af python` 로 잔여 프로세스 확인. 있으면 `kill -9` 필요 → `live_voice_backend.stop()` 버그 |

---

### MT-VOICE-LIVE-12: 오디오 장치 부재 시 우아한 실패

| 항목 | 내용 |
|------|------|
| **목적** | mic 이 뽑혀 있거나 PipeWire default source 가 없을 때 크래시 없이 처리 |
| **절차** | 1. mic 을 뽑음<br>2. `pactl set-default-source ''` (빈 값 시도)<br>3. 프로그램 실행 |
| **기대** | backend start 실패 로그, 하지만 프로그램 전체는 계속 동작 (터미널 입력/비전은 정상) |
| **PASS 조건** | 프로세스 크래시 없음, 다른 기능 정상 |

---

## 5. 통합 시나리오 (PRD 기반)

실제 제품 사용 흐름 검증. `manual-test-plan.md` MT-VOICE-* 와 유사하지만 **mic 발화로 수행**.

### MT-VOICE-LIVE-SCN-01: 스마트홈 제어

1. "불 켜줘" → 조명 on 실행 시퀀스 관찰
   - `voice.intent.detected(smarthome.light.on)`
   - Activity FSM: `Listening` → `Executing`
   - home_client HTTP 호출 (--real-services 일 경우) 또는 mock 응답
   - 성공 scene 렌더 (표정 + 효과음)
2. "불 꺼줘" → off
3. 동일 패턴으로 `에어컨 켜줘/꺼줘`, `티비 켜줘`, `음악 틀어줘`, `청소기 돌려줘`

### MT-VOICE-LIVE-SCN-02: 타이머

1. "1분 있다 알려줘" (자연어 파싱 의존)
2. 기대: `voice.intent.detected(timer.create)`, payload 에 duration_ms 파싱 결과
3. 현재 timer 파서 수준에서 파싱 가능한 표현 확인

### MT-VOICE-LIVE-SCN-03: 카메라 촬영

1. "사진 찍어줘"
2. 기대: `voice.intent.detected(camera.capture)` → photo service 실행 → 카운트다운 → 촬영 → 저장

### MT-VOICE-LIVE-SCN-04: 날씨

1. "날씨 알려줘"
2. 기대: `voice.intent.detected(weather.current)` → weather client HTTP (real-services) 또는 mock

### MT-VOICE-LIVE-SCN-05: 시스템 명령

1. "알겠어" → `voice.intent.detected(system.ack)` — ack scene
2. "취소" → `voice.intent.detected(system.cancel)` — 현재 실행 중인 task 취소 시도

---

## 6. 알려진 한계 / 주의

1. **Wake word 없음**: 모든 발화가 ASR 을 거쳐 bus 에 이벤트를 발행. 주변 대화가 `triggers.yaml` alias 와 우연히 매칭되면 의도치 않은 intent 발생 가능. **오케스트레이터 측에서 wake 상태를 판단하도록 설계됨** — 이 테스트 계획은 backend 수준까지만 다룸.
2. **첫 실행 시 모델 다운로드**: ~145MB (Whisper base). 인터넷 연결 필요. 이후 `~/.cache/huggingface/` 에 캐시.
3. **Pi 4 에서 decode 1-2s**: Pi 5 기준 0.5s. 지연이 체감되면 `asr.model: "tiny"` 고려 (정확도 ↓).
4. **Whisper 텍스트 구두점**: "불 켜줘." 처럼 마침표 붙을 수 있음. `intent_parser` 가 허용하지 않으면 매칭 실패 가능. 재발 시 발견된 케이스를 issue 에 기록.
5. **mic 볼륨 전역 변경**: `mic_gain_percent` 는 시스템 mic 게인을 바꾸므로 종료 후 다른 앱에도 영향. 필요 시 `pactl set-source-volume <source> 100%` 로 복원.
6. **vision_worker 카메라 중복 오픈**: `rio.pump_workers()` 가 `vision_worker.run_once()` 도 호출하는데, 스크립트는 자체 `process_frame()` 에서 같은 카메라를 이미 읽음. 이중 오픈으로 인한 성능 저하/오동작 가능. 발견 시 별도 이슈로 등록.

---

## 7. 체크리스트 (요약)

실행 후 아래를 체크:

- [ ] SETUP: mic gain, Silero, Whisper, stream 로그 모두 OK
- [ ] LIVE-01: "불 켜줘" → `smarthome.light.on`
- [ ] LIVE-02: alias 4건 모두 매핑 OK
- [ ] LIVE-03: 비-intent 발화 → `voice.intent.unknown`
- [ ] LIVE-04: depth=1 규칙 — 연속 발화 중 두 번째 drop
- [ ] LIVE-05: 짧은 기침 drop
- [ ] LIVE-06: 30초 무음 동안 환각 이벤트 0
- [ ] LIVE-07: pactl 값이 25% 로 변경됨
- [ ] LIVE-08: 원거리 발화 무시
- [ ] LIVE-09: 2초 간격 연속 2 intent 발행
- [ ] LIVE-10: 터미널/mic 병행 동작
- [ ] LIVE-11: Ctrl+C 깨끗한 종료
- [ ] LIVE-12: mic 없을 때 graceful 실패
- [ ] SCN-01~05: PRD 시나리오 5건 mic 발화로 통과

---

*이 문서는 `configs/voice.yaml` 과 `src/app/adapters/audio/live_voice_backend.py` 구현을 기준으로 작성. 파라미터 변경 시 본 문서의 기본값 표도 함께 업데이트.*
