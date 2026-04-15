# Project Layout

이 문서는 `prd.md`와 `architecture.md`를 코드 구조로 번역한 문서입니다.
폴더 구조 역시 하나의 구현 방향만 보도록 정리합니다.

## 1. 기본 구조

```text
RIO/
├── README.md
├── docs/
│   ├── prd.md
│   ├── architecture.md
│   ├── state-machine.md
│   └── project-layout.md
├── configs/
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
│       │   └── safety/
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
- `src/`
  - 위 문서를 코드로 옮기는 자리

즉, 구현자는 먼저 `prd -> architecture -> state-machine -> src` 순서로 보는 것이 맞습니다.

## 3. `configs/`

이 프로젝트는 구현 파라미터를 코드에 박아넣지 않고 설정으로 분리합니다.

### `robot.yaml`

- 터치스크린 해상도
- 웹캠 장치 정보
- 오디오 입출력 장치 정보
- 화면 배치

### `thresholds.yaml`

Presence / Behavior / Vision 상태 전이에 쓰이는 수치 기준입니다. 단위는 모두 명시합니다. 아래 값은 문서 기준 기본값(default)이며, 튜닝은 이 파일에서만 수행합니다.

```yaml
presence:
  face_lost_timeout_ms: 800        # FaceVisible -> FaceLost 전이
  sleepy_absence_timeout_ms: 60000 # FaceLost -> SleepyAbsence 전이
  reappeared_window_ms: 3000       # ReappearedWindow 유지 시간
  face_moved_sample_hz: 10         # vision.face.moved 샘플링 주기

behavior:
  idle_to_sleepy_timeout_ms: 120000  # Idle -> Sleepy 전이
  intent_cooldown_ms: 1500           # 동일 intent 재수신 무시 구간
  startled_scene_min_ms: 1200        # Startled 최소 유지 시간

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

### `bus/`

- 이벤트 라우터
- 구독/발행 인터페이스
- 워커 입력 큐와 메인 루프 연결

### `state/`

- Context FSM (Away/Idle/Engaged/Sleepy)
- Activity FSM (Idle/Listening/Executing/Alerting)
- Oneshot dispatcher (순간 반응 이벤트, 중첩 정책)
- Scene Selector (파생 출력: Mood + UI)
- 전역 상태 저장소

### `scheduler/`

- 타이머 등록
- timeout 이벤트 발행
- 반복 작업

### `safety/`

- 워커 생존 감시
- degraded mode 전환
- 예외 복구

## 6. `src/app/adapters/`

외부 입출력을 담당하는 계층입니다.

### `audio/`

- 마이크 입력
- VAD
- STT adapter
- raw transcript 전달

### `speaker/`

- TTS 출력
- 효과음 재생
- 알림 사운드 큐 관리

### `vision/`

- 카메라 프레임 수신
- OpenCV / MediaPipe 처리
- 얼굴/손동작 이벤트 생성

### `touch/`

- 터치스크린 이벤트 수신
- 탭/드래그/쓰다듬기 제스처 변환

### `display/`

RIO 화면 렌더러의 핵심입니다.

구현 책임:

- Layer 1 `Core Face`
- Layer 2 `Action Overlay`
- Layer 3 `System HUD`
- 얼굴 중심 좌표를 기반으로 한 눈동자/시선 애니메이션
- 게임 모드 UI
- 카운트다운/알림 렌더링

### `camera/`

- 웹캠 기반 사진 촬영
- 저장 경로 관리

### `weather/`

- 날씨 API 요청
- 응답 정규화

### `home_client/`

- 로컬 smart-home home-client HTTP 호출
- 제어 성공/실패 이벤트 변환

## 7. `src/app/domains/`

비즈니스 로직 계층입니다.

### `presence/`

- 얼굴 존재/부재 추적
- 재등장 window
- sleepy absence 판단

### `speech/`

- transcript -> intent normalization
- alias 처리
- command parsing
- low-confidence / unknown / duplicate intent 분류 (`voice.intent.unknown` 발행 포함)

### `gesture/`

- 손총
- V자
- 손 흔들기
- 고개 방향

### `behavior/`

- 감정/반응 상태 전이
- reaction rule
- scene selection

### `photo/`

- 사진 촬영 시퀀스
- 카운트다운
- 저장 완료 피드백

### `games/`

- 핑퐁
- 갤로그
- 참참참

### `smart_home/`

- intent -> home-client 요청 변환
- 결과 피드백

### `timers/`

- 자연어 시간 파싱
- 타이머 상태 관리
- 종료 알람

## 8. `src/app/scenes/`

RIO는 단순 함수 호출보다 `연출 단위`가 중요하므로 씬 단위 구성을 둡니다.

예:

- `startled_then_track`
- `welcome_back`
- `sleep_mode_loop`
- `take_photo_countdown`
- `smarthome_feedback`
- `petting_reaction`

## 9. `tests/`

하드웨어 프로젝트이므로 테스트를 분리해서 봐야 합니다.

### `unit/`

- 상태 전이
- intent 정규화
- 타이머 파싱

### `integration/`

- 이벤트 플로우
- smart-home adapter
- weather adapter

### `simulation/`

- 카메라 없이 face event 재생
- 마이크 없이 transcript event 주입
- 긴 시나리오 재생

## 10. 구현 시작 순서

1. `core/events`, `core/state`, `core/bus`
2. `domains/presence`, `domains/speech`, `domains/behavior`
3. `adapters/display`, `adapters/audio`, `adapters/speaker`, `adapters/vision`, `adapters/touch`
4. `domains/photo`, `domains/timers`, `domains/smart_home`, `adapters/home_client`
5. `gesture`, `games`

이 순서를 유지하면 PRD의 MVP 범위를 가장 적은 충돌로 구현할 수 있습니다.
