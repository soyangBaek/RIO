# Recommended Project Layout

구현을 시작할 때는 아래 구조를 추천합니다.

```text
emo-homehub-rpi/
├── README.md
├── docs/
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
│       │   ├── vision/
│       │   ├── gpio/
│       │   ├── display/
│       │   ├── motor/
│       │   ├── camera/
│       │   ├── weather/
│       │   └── thinq/
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

## 각 디렉토리의 역할

### `configs/`

코드가 아니라 조정 가능한 정책을 넣는 곳입니다.

예:

- 얼굴 미검출 몇 초 후 `FaceLost`로 볼지
- 몇 분 동안 부재 시 졸음 상태 진입할지
- 어떤 음성 문장을 어떤 명령으로 정규화할지
- 어떤 ThinQ 디바이스를 어떤 이름으로 노출할지

이걸 처음부터 분리해두면 나중에 튜닝이 매우 쉬워집니다.

### `assets/`

emo pet 특성상 자산이 많아질 가능성이 높습니다.

예:

- 표정 PNG / SVG
- 꿈 애니메이션
- 코 고는 소리
- 반김 효과음
- 게임 UI 아이콘

### `src/app/core/`

프로젝트의 뼈대입니다.

- `events/`: 공통 이벤트 모델
- `bus/`: pub/sub, 라우팅
- `state/`: 전역 상태 저장소, FSM
- `scheduler/`: 타이머, 반복 작업
- `safety/`: watchdog, 오류 복구, graceful degradation

### `src/app/adapters/`

외부 세계와 만나는 포인트입니다.

예:

- 마이크, 카메라, GPIO
- 모터 드라이버
- 디스플레이 렌더러
- OpenWeatherMap
- ThinQ

핵심 원칙:

- 이 계층은 교체 가능해야 합니다.
- 예를 들어 STT 엔진을 바꾸더라도 상위 도메인 계층은 그대로 가야 합니다.

### `src/app/domains/`

비즈니스 로직이 들어가는 곳입니다.

예:

- `presence/`: 얼굴 존재/부재/재등장
- `speech/`: 명령 인식 후 의도 해석
- `gesture/`: 손동작/머리방향 이벤트
- `behavior/`: 감정 및 반응 결정
- `photo/`: 사진 촬영 흐름
- `games/`: 핑퐁, 참참참, 갤로그
- `smart_home/`: 기기 제어
- `timers/`: 자연어 타이머

### `src/app/scenes/`

복합 액션 시퀀스를 관리하기 좋은 위치입니다.

예:

- `surprised_then_track`
- `sleep_mode_loop`
- `take_photo_countdown`
- `welcome_back`
- `lose_chamchamcham`

즉, 단일 명령보다 `연출 단위`를 모아두는 폴더입니다.

### `tests/`

이 프로젝트는 하드웨어가 섞여 있으므로 테스트를 분리하는 게 중요합니다.

- `unit/`: 상태 전이, 규칙, 명령 파싱
- `integration/`: 이벤트 플로우, 서비스 연동
- `simulation/`: 카메라/마이크 없이 이벤트 재생 테스트

## 구현 순서에 맞춘 최소 시작 구조

아직은 코드 없이 시작하더라도, 첫 구현은 아래 3축부터 잡는 걸 추천합니다.

1. `core/events`, `core/bus`, `core/state`
2. `domains/presence`, `domains/behavior`, `domains/timers`
3. `adapters/audio`, `adapters/vision`, `adapters/display`

이 3축이 잡히면 나머지 기능은 비교적 자연스럽게 올라갑니다.

