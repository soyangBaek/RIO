# Project Layout

이 문서는 `prd.md`와 `architecture.md`를 코드 구조로 번역한 문서입니다.
폴더 구조 역시 하나의 구현 방향만 보도록 정리합니다.

## 1. 기본 구조

```text
RIO/
├── README.md
├── docs/
│   ├── prd.md
│   ├── current-behaviors.md
│   ├── architecture.md
│   ├── state-machine.md
│   ├── scenarios.md
│   └── project-layout.md
├── configs/
│   ├── README.md
│   ├── robot.yaml
│   ├── thresholds.yaml
│   ├── triggers.yaml
│   ├── devices.yaml
│   └── scenes.yaml
├── assets/
│   ├── expressions/
│   ├── sounds/
│   ├── animations/
│   └── ui/
├── src/
│   └── app/
│       ├── core/
│       │   ├── events/
│       │   ├── bus/
│       │   ├── state/
│       │   ├── scheduler/
│       │   ├── safety/
│       │   └── config.py
│       ├── workers/
│       ├── adapters/
│       │   ├── audio/
│       │   ├── speaker/
│       │   ├── vision/
│       │   ├── touch/
│       │   ├── display/
│       │   ├── camera/
│       │   ├── weather/
│       │   └── home_client/
│       ├── domains/
│       │   ├── presence/
│       │   ├── speech/
│       │   ├── gesture/
│       │   ├── behavior/
│       │   ├── photo/
│       │   ├── games/
│       │   ├── smart_home/
│       │   └── timers/
│       ├── scenes/
│       └── main.py
├── scripts/
│   ├── demo_reactions.py
│   ├── live_interaction_test.py
│   └── live_vision_state_test.py
└── tests/
    ├── unit/
    ├── integration/
    └── simulation/
```

## 2. 문서와 코드의 관계

- `docs/prd.md`
  - 기능과 구현 기준의 원문
- `docs/architecture.md`
  - 런타임, 이벤트 흐름, 계층 구조
- `docs/state-machine.md`
  - 상태 전이 규칙
- `docs/scenarios.md`
  - 구현해야 하는 동작 시나리오와 테스트 기준
- `src/`
  - 위 문서를 코드로 옮기는 자리

즉, 구현자는 먼저 `prd -> state-machine -> scenarios -> architecture -> src` 순서로 보는 것이 맞습니다.

`architecture.md`의 런타임 블록은 아래처럼 실제 경로에 대응됩니다.

| 런타임 블록 | 실제 코드 위치 |
| :--- | :--- |
| `Event Router` | `src/app/core/bus/` |
| `Extended State Update` | `src/app/core/state/extended_state.py` |
| `Context / Activity Reducers` | `src/app/core/state/context_fsm.py`, `src/app/core/state/activity_fsm.py`, `src/app/core/state/reducers.py` |
| `Oneshot Dispatcher` | `src/app/core/state/oneshot.py` |
| `Scene Selector` | `src/app/core/state/scene_selector.py` |
| `Effect Planner` | `src/app/domains/behavior/effect_planner.py` |
| `Executor Registry` | `src/app/domains/behavior/executor_registry.py` |
| `Photo / Timer / SmartHome / Game Services` | `src/app/domains/` |
| `Camera / Weather / Home Client Adapters` | `src/app/adapters/` |

## 3. `configs/`

이 프로젝트는 구현 파라미터를 코드에 박아넣지 않고 설정으로 분리합니다.

### `robot.yaml`

- 터치스크린 해상도
- 웹캠 장치 정보
- 오디오 입출력 장치 정보
- 화면 배치

### `thresholds.yaml`

Context / Activity FSM 전이와 파생 상황 계산에 쓰이는 수치 기준입니다. 단위는 모두 명시합니다. 아래 값은 문서 기준 기본값(default)이며, 튜닝은 이 파일에서만 수행합니다.

```yaml
presence:
  face_lost_timeout_ms: 800        # recent_face_loss 파생 상황 유지 시간
  away_timeout_ms: 60000           # Idle/Sleepy -> Away 전이 (no_face_long_timeout)
  welcome_min_away_ms: 3000        # just_reappeared 파생 상황 최소 경과 시간
  face_moved_sample_hz: 10         # vision.face.moved 샘플링 주기

behavior:
  idle_to_sleepy_timeout_ms: 120000  # Idle/Engaged -> Sleepy 전이 (long_idle)
  intent_cooldown_ms: 1500           # 동일 intent 재수신 무시 구간
  startled_oneshot_min_ms: 600       # startled oneshot 최소 지속 시간

vision:
  face_confidence_min: 0.6
  gesture_confidence_min: 0.75
  head_direction_confidence_min: 0.7

voice:
  stt_confidence_min: 0.5       # 이 미만은 voice.intent.unknown으로 발행
  intent_match_confidence_min: 0.6

task:
  http_timeout_ms: 3000         # home_client, weather 공용
  http_retry_count: 1
```

필드 추가 시 단위 suffix(`_ms`, `_hz`, `_min`)를 유지합니다. 상태 머신 문서와 수치가 어긋나면 이 파일이 기준입니다.

### `triggers.yaml`

- intent별 음성 alias
- command normalization 룰

예:

- `dance.start`
- `camera.capture`
- `smarthome.aircon.on`

### `devices.yaml`

- home-client 대상 장치 이름
- 장치 ID 또는 매핑 정보

### `scenes.yaml`

- 장면별 사운드
- 표정
- 오버레이 자산
- 지속 시간
- oneshot별 priority / duration 기본값
- `Executing(kind)`별 UI/사운드 연출 매핑

## 4. `assets/`

PRD의 3-layer UI를 구현하기 위한 자산 폴더입니다.

### `assets/expressions/`

- 기본 표정
- 놀람
- 졸음
- 반김
- 웃음

### `assets/sounds/`

- 셔터
- 성공/실패 비프
- 화들짝
- 코 고는 소리
- 만족 사운드

### `assets/animations/`

- 꿈 애니메이션
- 댄스 연출
- 반김 연출
- 오버레이 연출

### `assets/ui/`

- HUD 아이콘
- 날씨 아이콘
- 게임 버튼
- 상태 배지

## 5. `src/app/core/`

RIO의 공통 기반 계층입니다.

### `events/`

- 공통 이벤트 포맷
- topic 정의
- trace / metadata 정의
- 권장 초기 파일:
  - `models.py`
  - `topics.py`

### `bus/`

- 이벤트 라우터
- 구독/발행 인터페이스
- 워커 입력 큐와 메인 루프 연결
- 권장 초기 파일:
  - `queue_bus.py`
  - `router.py`

### `state/`

- authoritative state, extended state, derived output을 함께 다루는 핵심 계층입니다.
- 구현 책임:
  - Context FSM (`Away` / `Idle` / `Engaged` / `Sleepy`)
  - Activity FSM (`Idle` / `Listening` / `Executing` / `Alerting`)
  - extended state (`face_present`, `last_face_seen_at`, `deferred_intent` 등)
  - oneshot dispatcher (순간 반응 이벤트, 중첩 정책)
  - Scene Selector (파생 출력: Mood + UI)
  - 전역 상태 저장소
- 권장 초기 파일:
  - `models.py`
  - `store.py`
  - `context_fsm.py`
  - `activity_fsm.py`
  - `extended_state.py`
  - `oneshot.py`
  - `scene_selector.py`
  - `reducers.py`

구현 관점에서 역할을 나누면 아래처럼 보는 것이 좋습니다.

- `extended_state.py`
  - 이벤트를 받아 `face_present`, `last_face_seen_at`, `deferred_intent` 같은 값을 갱신
- `context_fsm.py`, `activity_fsm.py`
  - 전이 규칙만 가진다
- `reducers.py`
  - `extended state update -> fsm transition -> oneshot trigger` 순서를 조합한다
- `scene_selector.py`
  - 최종 `(Mood, UI)`를 파생한다

### `scheduler/`

- 타이머 등록
- timeout 이벤트 발행
- 반복 작업
- 권장 초기 파일:
  - `timer_scheduler.py`

### `safety/`

- 워커 생존 감시
- degraded mode 전환
- 예외 복구
- 권장 초기 파일:
  - `heartbeat_monitor.py`
  - `capabilities.py`

## 6. `src/app/workers/`

런타임에서 입력을 polling하는 워커 구성요소입니다.
현재 저장소의 기본 런너(`RioOrchestrator`, `scripts/live_interaction_test.py`)는 이 워커들을 메인 오케스트레이터 안에서 직접 호출하며,
필요 시 프로세스 경계로 확장할 수 있도록 책임 단위만 먼저 분리해두었습니다.

- `audio_worker.py`
  - 마이크 캡처
  - VAD
  - STT
  - intent normalization 호출
  - `voice.*` 이벤트 발행
- `vision_worker.py`
  - 카메라 프레임 수신
  - 얼굴 검출 / 이동 추적
  - gesture 추론
  - `vision.*` 이벤트 발행
- `touch_worker.py`
  - 터치 입력 샘플 수집
  - 탭/스트로크 변환
  - `touch.*` 이벤트와 heartbeat 발행

## 6.1 `src/app/main.py`

메인 오케스트레이터 진입점입니다.

- `core/bus` 초기화
- worker 객체 초기화와 polling
- 이벤트 루프 실행
- `extended state -> reducers -> oneshot -> scene selector -> effect planner -> executor registry` 순서 연결
- degraded mode와 종료 시 cleanup 수행

추가로 현재 저장소에는 `core/config.py`가 있어,
문서/스크립트/테스트 어디에서 실행하더라도 repo-relative 경로로 설정 파일과 데이터 경로를 찾을 수 있게 해줍니다.

## 7. `src/app/adapters/`

외부 입출력을 담당하는 계층입니다.

### `audio/`

- 마이크 입력
- VAD
- STT adapter
- intent normalization helper
- live 테스트용 터미널 transcript 입력
- 권장 초기 파일:
  - `capture.py`
  - `vad.py`
  - `stt.py`
  - `intent_normalizer.py`
  - `terminal_input.py`

### `speaker/`

- TTS 출력
- 효과음 재생
- 알림 사운드 큐 관리
- 권장 초기 파일:
  - `tts.py`
  - `sfx.py`

### `vision/`

- 카메라 프레임 수신
- OpenCV / MediaPipe 처리
- 얼굴/손동작 이벤트 생성
- 얼굴 재등장 / 고개 방향 같은 상호작용 이벤트 추적
- 권장 초기 파일:
  - `camera_stream.py`
  - `face_detector.py`
  - `face_tracker.py`
  - `gesture_detector.py`
  - `interaction_tracker.py`

### `touch/`

- 터치스크린 이벤트 수신
- 탭/드래그/쓰다듬기 제스처 변환
- 권장 초기 파일:
  - `input.py`
  - `gesture_mapper.py`

### `display/`

RIO 화면 렌더러의 핵심입니다.

구현 책임:

- Layer 1 `Core Face`
- Layer 2 `Action Overlay`
- Layer 3 `System HUD`
- 얼굴 중심 좌표를 기반으로 한 눈동자/시선 애니메이션
- 게임 모드 UI
- 카운트다운/알림 렌더링
- 권장 초기 파일:
  - `renderer.py`
  - `layers.py`
  - `eye_tracking.py`
  - `hud.py`

### `camera/`

- 웹캠 기반 사진 촬영
- 저장 경로 관리
- 권장 초기 파일:
  - `capture.py`
  - `storage.py`

### `weather/`

- 날씨 API 요청
- 응답 정규화
- 권장 초기 파일:
  - `client.py`
  - `normalizer.py`

### `home_client/`

- 로컬 smart-home home-client HTTP 호출
- 제어 성공/실패 이벤트 변환
- 권장 초기 파일:
  - `client.py`
  - `mapper.py`

## 8. `src/app/domains/`

비즈니스 로직 계층입니다.

### `presence/`

- `Context FSM` 자체를 소유하지는 않습니다.
- 대신 아래 판단 로직을 제공하는 보조 도메인입니다.
  - 사용자 증거 집계 (`face`, `voice`, `touch`)
  - `confirmed_user_and_interacting` 판단
  - `just_reappeared`, `recent_face_loss` 같은 파생 상황 helper
  - away / sleepy 관련 threshold 적용
- 권장 초기 파일:
  - `signals.py`
  - `helpers.py`

### `speech/`

- 음성 의미 해석 규칙을 담당합니다.
- 구현 책임:
  - alias 처리
  - canonical intent 매핑
  - 자연어 시간 파싱
  - low-confidence / unknown / duplicate intent 분류
- 권장 초기 파일:
  - `intent_parser.py`
  - `timer_parser.py`
  - `dedupe.py`

### `gesture/`

- Phase 2에서 확장된 제스처 중심 도메인이지만,
  현재 저장소에도 `wave`, `finger_gun`, `peekaboo`, `head_left/right`, `v_sign` 같은 반응형/실행형 프로토타입이 일부 선반영되어 있습니다.
- 손총, V자, 손 흔들기, 고개 방향 규칙을 정의합니다.
- 권장 초기 파일:
  - `catalog.py`
  - `mapper.py`

### `behavior/`

- 상태 전이는 `core/state`가 가진다는 점이 중요합니다.
- `behavior/`는 그 위에서 아래 책임을 가집니다.
  - interrupt policy
  - effect planner
  - executor registry
  - scene-to-output command planning
- 권장 초기 파일:
  - `effect_planner.py`
  - `executor_registry.py`
  - `interrupts.py`

즉,

- `core/state`는 "상태가 어떻게 바뀌는가"
- `domains/behavior`는 "그 상태를 보고 무엇을 실행할 것인가"

를 담당합니다.

### `photo/`

- 사진 촬영 시퀀스
- 카운트다운
- 저장 완료 피드백
- 권장 초기 파일:
  - `service.py`

### `games/`

- 게임 모드 진입과 게임 콘텐츠 실행
- 현재는 게임 모드 UI 전환과 방향 피드백 중심이며,
  실제 게임 콘텐츠/판정 로직은 이후 확장합니다.
- 권장 초기 파일:
  - `service.py`

### `smart_home/`

- intent -> home-client 요청 변환
- 결과 피드백
- 권장 초기 파일:
  - `service.py`
  - `payloads.py`

### `timers/`

- 타이머 상태 관리
- 종료 알람
- 권장 초기 파일:
  - `service.py`

## 9. `src/app/scenes/`

RIO는 단순 함수 호출보다 `연출 단위`가 중요하므로 씬 단위 구성을 둡니다.

예:

- `startled_then_track`
- `welcome_back`
- `sleep_mode_loop`
- `take_photo_countdown`
- `smarthome_feedback`
- `petting_reaction`

권장 초기 파일:

- `catalog.py`
- `builders.py`
- `assets.py`

## 10. `tests/`

하드웨어 프로젝트이므로 테스트를 분리해서 봐야 합니다.

### `unit/`

- Context / Activity reducer
- oneshot 중첩 정책
- scene selector
- intent 정규화
- 타이머 파싱

### `integration/`

- 이벤트 플로우
- smart-home adapter
- weather adapter
- photo sequence

### `simulation/`

- 카메라 없이 face event 재생
- 마이크 없이 transcript event 주입
- 긴 시나리오 재생

## 11. 초기 구현 순서 (기록)

아래 순서는 저장소를 처음 세울 때의 권장 부트스트랩 순서입니다.
현재 저장소는 이 단계를 지난 상태이므로, 새 기능을 붙일 때는 이 순서를 그대로 따르기보다
현재 파일 책임과 테스트 경계를 기준으로 수정 범위를 잡는 편이 맞습니다.

1. `core/events`, `core/bus`, `core/state`
2. `workers/audio_worker.py`, `workers/vision_worker.py`
3. `adapters/display`, `adapters/touch`, `adapters/speaker`
4. `domains/presence`, `domains/speech`, `domains/behavior`
5. `domains/photo`, `domains/timers`, `domains/smart_home`
6. `adapters/camera`, `adapters/weather`, `adapters/home_client`
7. `gesture`, `games`

이 순서를 유지하면 [scenarios.md](./scenarios.md)의 `SYS-*`, `VOICE-*`, `INT-*`, `POL-*` 순서로 자연스럽게 검증을 붙일 수 있습니다.
