# ASR `initial_prompt` 도입 가이드

> 목적: Whisper 디코더에 도메인 어휘를 편향(bias) 으로 주입해 한국어 스마트홈 명령 인식률을 올린다.
> 벤치 근거: `artifacts/voice_bench/` (48 샘플 / 3 화자) — baseline 35.4% → +prompt 47.9% (+12.5%p).
> 변경 범위: 코드 3파일 + 설정 1파일. 기존 동작과 하위 호환 (값 없으면 `None`).

---

## 1. 무엇을 바꾸는가

Whisper 디코딩 호출에 `initial_prompt` 파라미터 하나 추가. 이 파라미터는 **"직전 세그먼트가 이런 문장이었다고 가정하고 디코딩 시작"** 하는 텍스트 힌트.

여기에 우리가 실제로 받고 싶은 명령어 단어들을 넣으면, 같은 오디오라도 그 방향으로 디코딩이 기울어진다.

### 벤치 결과 (48샘플)

| 설정 | 정확도 | p50 decode |
|---|---|---|
| baseline (현행) | 35.4% | 1647ms |
| baseline + `initial_prompt` | **47.9%** | 1116ms |

정확도만 오르는 게 아니라 디코드 시간도 오히려 약간 줄었다. **실행 시간 비용 거의 0**.

---

## 2. 수정해야 할 파일

### 2.1 [configs/voice.yaml](../configs/voice.yaml)

`asr` 섹션에 아래 키 추가.

**변경 전:**

```yaml
asr:
  model: "base"
  language: "ko"
  beam_size: 1
  compute_type: "int8"
  device: "cpu"
  no_speech_threshold: 0.6
  condition_on_previous_text: true
  min_logprob: -1.0
```

**변경 후:**

```yaml
asr:
  model: "base"
  language: "ko"
  beam_size: 1
  compute_type: "int8"
  device: "cpu"
  no_speech_threshold: 0.6
  condition_on_previous_text: true
  min_logprob: -1.0

  # Whisper 디코더 바이어싱. 도메인 어휘를 가짜 직전 문맥으로 주입해
  # "티비/에어컨/꺼줘/켜줘" 같은 명령어 방향으로 디코딩을 기울인다.
  # 공백 구분 문장이면 충분. 길이는 수십~100자 수준 권장.
  # null 또는 빈 문자열이면 바이어싱 없음(현행 동작과 동일).
  initial_prompt: "티비 에어컨 조명 불 청소기 댄스 타이머 날씨 사진 음악 켜줘 꺼줘 틀어줘 맞춰줘 찍어줘 알려줘 취소 그만 확인 알겠어"
```

### 2.2 [src/app/adapters/audio/live_voice_backend.py](../src/app/adapters/audio/live_voice_backend.py)

두 군데 수정.

**(a) `ASRParams` 에 필드 추가** ([live_voice_backend.py:68-77](../src/app/adapters/audio/live_voice_backend.py#L68-L77))

```python
@dataclass
class ASRParams:
    model: str = "base"
    language: str = "ko"
    beam_size: int = 1
    compute_type: str = "int8"
    device: str = "cpu"
    no_speech_threshold: float = 0.6
    condition_on_previous_text: bool = True
    min_logprob: float = -1.0
    initial_prompt: Optional[str] = None   # ← 추가. None = 바이어싱 없음
```

> `Optional` 은 파일 상단 import 에 이미 있으면 OK. 없으면 `from typing import Optional` 추가.

**(b) `transcribe()` 호출에 파라미터 전달** ([live_voice_backend.py:394-400](../src/app/adapters/audio/live_voice_backend.py#L394-L400))

```python
segments, _info = self._whisper.transcribe(
    audio,
    language=self.cfg.asr.language,
    beam_size=self.cfg.asr.beam_size,
    no_speech_threshold=self.cfg.asr.no_speech_threshold,
    condition_on_previous_text=self.cfg.asr.condition_on_previous_text,
    initial_prompt=self.cfg.asr.initial_prompt,   # ← 추가
)
```

### 2.3 [src/app/main.py](../src/app/main.py)

YAML 로더에서 값을 읽어 `ASRParams` 로 전달. [main.py:128-137](../src/app/main.py#L128-L137)

```python
asr=ASRParams(
    model=str(asr.get("model", "base")),
    language=str(asr.get("language", "ko")),
    beam_size=int(asr.get("beam_size", 1)),
    compute_type=str(asr.get("compute_type", "int8")),
    device=str(asr.get("device", "cpu")),
    no_speech_threshold=float(asr.get("no_speech_threshold", 0.6)),
    condition_on_previous_text=bool(asr.get("condition_on_previous_text", True)),
    min_logprob=float(asr.get("min_logprob", -1.0)),
    initial_prompt=asr.get("initial_prompt") or None,   # ← 추가. 빈 문자열도 None 으로 정규화
),
```

> `asr.get("initial_prompt") or None` — YAML 에서 `null`, 빈 문자열, 키 없음 모두 `None` 으로 떨어뜨려 기존 경로를 그대로 탄다.

### 2.4 (선택) [scripts/voice_sandbox/pipeline.py](../scripts/voice_sandbox/pipeline.py)

샌드박스 파이프라인도 같은 설정을 쓰려면 동일하게 반영. 현재 샌드박스는 `configs/voice_sandbox.yaml` → `configs/voice.yaml` 을 `extends` 하므로 **2.1 만 고쳐도 자동 반영됨**. `asr_whisper.py` 쪽에서 `transcribe()` 에 파라미터를 실제로 넘기는지는 확인 필요.

---

## 3. 프롬프트 문자열 선정 근거

```
티비 에어컨 조명 불 청소기 댄스 타이머 날씨 사진 음악 켜줘 꺼줘 틀어줘 맞춰줘 찍어줘 알려줘 취소 그만 확인 알겠어
```

- `docs/user-manual.md §4` 의 16개 명령어에서 쓰이는 **명사 + 동사** 어휘만 뽑아 공백으로 나열
- 조사/숫자 제외 (Whisper 가 자체적으로 넣을 수 있음)
- 길이 ~60자 — 권장 범위 내 (너무 길면 오히려 다른 문맥으로 흐름)
- 실패 케이스 보고 어휘 추가는 이후 튜닝에서

### 추가 후보 (필요 시)

- 지역 명칭: `거실 침실 안방 주방`
- 영문 혼용 대응: `tv music light timer` (지금은 넣지 않음 — 한국어 유도가 목적)

---

## 4. 동작 검증

적용 후 아래 4 가지를 확인.

### 4.1 로그 확인 (1 회)

`live_voice_backend` 부팅 시 로그에 `initial_prompt` 가 찍히면 좋음.
`_load_models` 끝나고 `_LOGGER.info("models ready")` 근처에 한 줄 추가하는 걸 권장:

```python
_LOGGER.info(
    "asr initial_prompt: %s",
    (self.cfg.asr.initial_prompt[:60] + "...")
    if self.cfg.asr.initial_prompt and len(self.cfg.asr.initial_prompt) > 60
    else self.cfg.asr.initial_prompt,
)
```

### 4.2 회귀 테스트

- `initial_prompt: null` 로 설정 → 기존 동작과 동일해야 함 (문자열 전달이 None 일 때 `WhisperModel.transcribe` 가 정상 동작해야 함)
- `initial_prompt: ""` (빈 문자열) → `None` 으로 정규화되어 기존 동작

### 4.3 벤치 재실행

```
python -m scripts.voice_bench.run_audio_bench --run-name post_change_baseline
python -m scripts.voice_bench.run_audio_bench --run-name post_change_biased \
    --initial-prompt "티비 에어컨 조명 불 청소기 댄스 타이머 날씨 사진 음악 켜줘 꺼줘 틀어줘 맞춰줘 찍어줘 알려줘 취소 그만 확인 알겠어"
```

둘 정확도 차이가 벤치 결과와 **비슷한 폭(+10%p 이상)** 으로 재현되는지 확인.

### 4.4 Pi 에서 실제 발화 테스트

`docs/manual-test/voice-test-plan.md` 의 MT-VOICE-LIVE-01/02 발화 몇 건 돌려서:
- 기존에 자주 실패하던 "에어컨 꺼줘", "티비 켜줘", "불 켜줘" 가 잡히는지
- 반대로 **엉뚱한 발화 (예: "어제 뭐 먹었지")가 `smarthome.*` 으로 잘못 잡히는 false positive 증가**는 없는지

---

## 5. 주의 / 제한

1. **환각이 도메인 쪽으로 쏠릴 수 있음**. 무음/노이즈에서 Whisper 가 "에어컨 켜줘" 같은 환각을 더 잘 만들 수 있다. 기존의 `asr.min_logprob: -1.0` + `asr.no_speech_threshold: 0.6` 두 장벽이 여전히 걸러주긴 하지만, Pi 발화 테스트에서 **무음 30초 동안 `voice.intent.*` 이벤트 0건** 이 유지되는지 재확인 필요 (MT-VOICE-LIVE-06).
2. **사용자 발화가 도메인 밖일 때 오히려 낮아질 수 있음**. 예: "안녕 리오야" 같은 비명령 발화. 우리 매뉴얼 §4 범위만 지원한다는 제품 정의를 감안하면 허용.
3. **프롬프트를 너무 길게 쓰면 역효과**. 100~150자 넘어가면 Whisper 가 해당 분포로 너무 기울어져 일반 한국어 인식이 떨어짐. 현재 60자 전후가 적정.
4. **`condition_on_previous_text=true` 와 상호작용**. 직전 디코딩 결과가 다음 프롬프트로 누적되는데, `initial_prompt` 는 그와 별개로 매 디코딩에 재주입된다. 환각 누적이 문제로 드러나면 `condition_on_previous_text=false` 로 내리는 걸 고려.

---

## 6. Rollback

`configs/voice.yaml` 의 `initial_prompt` 를 주석 처리하거나 `null` 로 바꾸면 기존 동작으로 즉시 복귀. 코드 변경은 default `None` 이라 무해.

---

## 7. 이 변경 이후 다음 단계

- `beam_size: 5` 도 정확도 +4%p 를 추가로 확인했으나 **Pi 에서 디코드 시간 증가폭 재측정 필요** → 별도 PR 에서 다룰 예정
- 지금 프롬프트 적용 후 여전히 실패하는 케이스 (`text_normalizer._REPLACEMENTS` 에 없는 변형: "댄스" → "엔스모드" 등) 는 후처리 쪽 개선 과제로
- VAD threshold (`350`) 가 벤치 환경에서 과해 4/48 케이스 drop 발생. Pi 실환경에서 mic_gain=25% 기준 잘 동작하는지 별도 확인 필요
