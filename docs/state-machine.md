# State Machine

이 문서는 `prd.md`를 기준으로 RIO의 상태 전이를 실제 구현 가능한 형태로 정리한 문서입니다.
핵심 원칙은 `하나의 거대한 FSM 대신 여러 개의 작은 FSM`입니다.

## 1. 상태 머신 구성

RIO는 아래 4개의 FSM으로 나눕니다.

1. `Presence FSM`
2. `Behavior FSM`
3. `UI FSM`
4. `Task FSM`

이 네 가지를 동시에 보고 Main Orchestrator가 최종 액션을 결정합니다.

## 2. Presence FSM

Presence FSM은 `보임/사라짐/재등장`과 관련된 시간 맥락을 관리합니다.

```mermaid
stateDiagram-v2
    [*] --> NoFace
    NoFace --> Searching : voice_detected_without_face
    NoFace --> FaceVisible : face_detected
    Searching --> FaceVisible : face_detected
    FaceVisible --> FaceLost : face_missing_over_threshold
    FaceLost --> SleepyAbsence : absence_timeout
    FaceLost --> ReappearedWindow : face_detected
    SleepyAbsence --> ReappearedWindow : face_detected
    ReappearedWindow --> FaceVisible : window_elapsed
```

상태 의미:

- `NoFace`: 화면 안에 얼굴이 없음
- `Searching`: 음성은 감지됐지만 아직 얼굴을 찾는 중
- `FaceVisible`: 얼굴이 안정적으로 검출됨
- `FaceLost`: 최근까지 보였으나 잠시 놓친 상태
- `SleepyAbsence`: 장시간 부재로 수면/졸음 연출 가능 상태
- `ReappearedWindow`: 재등장 직후 특별 반응을 줄 수 있는 짧은 시간창

## 3. Behavior FSM

Behavior FSM은 로봇이 지금 어떤 연출 단위로 움직이는지 관리합니다.

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Attentive : face_or_voice_or_touch
    Idle --> Sleepy : idle_timeout
    Attentive --> Startled : voice_without_face
    Attentive --> Dancing : intent_dance_start
    Attentive --> PhotoMode : intent_camera_capture
    Attentive --> GameMode : intent_enter_game_mode
    Attentive --> SmartHomeHandling : smarthome_intent
    Sleepy --> Attentive : face_or_voice_or_touch
    Startled --> Attentive : startled_scene_done
    Dancing --> Attentive : dance_scene_done
    PhotoMode --> Attentive : photo_scene_done
    GameMode --> Attentive : exit_game_mode
    SmartHomeHandling --> Attentive : feedback_done
```

상태 의미:

- `Idle`: 기본 대기
- `Attentive`: 사용자에게 주의를 두고 있는 상태
- `Sleepy`: 장시간 유휴 후 수면/꿈 연출 상태
- `Startled`: 화들짝 놀람 반응
- `Dancing`: 댄스 씬
- `PhotoMode`: 사진 촬영 씬
- `GameMode`: 게임 UI 및 조작 활성 상태
- `SmartHomeHandling`: 스마트홈 명령 처리 및 피드백 상태

## 4. UI FSM

UI FSM은 얼굴/오버레이/HUD가 어떤 레이아웃으로 보이는지 관리합니다.

```mermaid
stateDiagram-v2
    [*] --> NormalFaceUI
    NormalFaceUI --> ListeningUI : voice_detected
    ListeningUI --> NormalFaceUI : intent_done_or_timeout
    NormalFaceUI --> CameraUI : enter_photo_mode
    NormalFaceUI --> GameUI : enter_game_mode
    NormalFaceUI --> SleepUI : enter_sleepy
    GameUI --> NormalFaceUI : exit_game_mode
    CameraUI --> NormalFaceUI : photo_done
    SleepUI --> NormalFaceUI : wake_up
```

상태 의미:

- `NormalFaceUI`: 기본 얼굴 화면
- `ListeningUI`: STT/HUD를 강조하는 청취 상태
- `CameraUI`: 카운트다운과 플래시를 보여주는 촬영 상태
- `GameUI`: 얼굴 축소 및 게임 입력 UI 상태
- `SleepUI`: 졸음/꿈 애니메이션 상태

## 5. Task FSM

Task FSM은 시간이 걸리거나 외부 서비스가 필요한 작업을 관리합니다.

대상:

- 타이머
- 날씨 조회
- 스마트홈 명령
- 사진 저장

```mermaid
stateDiagram-v2
    [*] --> Ready
    Ready --> Running : task_started
    Running --> Succeeded : task_succeeded
    Running --> Failed : task_failed
    Succeeded --> Ready : ack_or_scene_done
    Failed --> Ready : ack_or_retry
```

이 FSM을 따로 두는 이유:

- 외부 API 실패를 행동 상태와 분리 가능
- 스마트홈 실패 시에도 감정 연출은 정상 유지 가능
- 여러 작업이 동시에 돌더라도 추적 단위를 분리 가능

## 6. 대표 시나리오

### 6.1 얼굴 없이 음성 감지

- Presence: `NoFace -> Searching`
- Behavior: `Idle/Attentive -> Startled`
- UI: `NormalFaceUI -> ListeningUI`
- 이후 얼굴 검출 시:
  - Presence: `Searching -> FaceVisible`
  - Behavior: `Startled -> Attentive`

### 6.2 "사진 찍어줘"

- Behavior: `Attentive -> PhotoMode`
- UI: `NormalFaceUI -> CameraUI`
- Task: `Ready -> Running`
- 완료 후:
  - Task: `Running -> Succeeded`
  - Behavior: `PhotoMode -> Attentive`
  - UI: `CameraUI -> NormalFaceUI`

### 6.3 오래 방치됨

- Presence: `FaceLost -> SleepyAbsence`
- Behavior: `Idle -> Sleepy`
- UI: `NormalFaceUI -> SleepUI`

### 6.4 재등장 직후 말 걸기

- Presence: `SleepyAbsence -> ReappearedWindow`
- Behavior: `Sleepy -> Attentive`
- `voice_detected`가 window 안에 들어오면 추가 반김/깜짝 연출 실행

### 6.5 스마트홈 명령

- Intent: `smarthome.*`
- Behavior: `Attentive -> SmartHomeHandling`
- Task: `Ready -> Running`
- 성공 또는 실패 후:
  - Task: `Running -> Succeeded/Failed`
  - Behavior: `SmartHomeHandling -> Attentive`

## 7. 상태 저장소에 반드시 있어야 하는 값

- `face_present`
- `face_last_seen_at`
- `voice_last_detected_at`
- `reappeared_at`
- `current_behavior_state`
- `current_ui_state`
- `presence_state`
- `active_timers`
- `pending_tasks`
- `current_game`

## 8. 설계 규칙

1. 상태 머신은 전이만 담당하고 실제 사운드/UI 호출은 액션 플래너가 담당합니다.
2. 하나의 이벤트가 여러 FSM에 동시에 영향을 줄 수 있어야 합니다.
3. 모든 전이는 timestamp와 함께 기록합니다.
4. `n초`, `n분`, confidence 임계치, alias 문구는 설정 파일로 뺍니다.
5. Phase 2 기능이 아직 없더라도 상태 이름과 이벤트 계약은 지금 문서 기준을 따릅니다.
