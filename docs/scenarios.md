# Scenario Catalog

이 문서는 RIO가 실제로 어떤 상황에서 어떻게 동작해야 하는지를 시나리오 단위로 정리한 구현 기준 문서입니다.

기준 문서:

- [prd.md](./prd.md)
- [architecture.md](./architecture.md)
- [state-machine.md](./state-machine.md)

이 문서는 기능 목록을 다시 설명하는 문서가 아니라,
구현자와 테스트 작성자가 `입력 -> 상태 변화 -> 기대 반응`을 빠르게 확인할 수 있도록 만든 시나리오 카탈로그입니다.

## 1. 문서 사용 원칙

- 이 문서는 현재 문서에 명시된 동작 범위를 시나리오 형태로 풀어쓴다.
- 조합 가능한 모든 미세 상태를 나열하지 않고, 구현과 테스트에 직접 필요한 대표 동작 케이스를 모두 포함한다.
- 시나리오의 상태 표기는 [state-machine.md](./state-machine.md)의 `Context`, `Activity`, `Oneshot`, `Derived Output` 기준을 따른다.
- 상태 표기 규약: `Context=X, Activity=Y, oneshot=Z` 형태로 통일한다. 전이는 `A -> B`로 적는다.
- MVP와 Phase 2를 분리해 관리한다.

## 2. MVP 시나리오

### 2.1 시스템 / 존재 맥락

| ID | 트리거 / 조건 | 상태 변화 | 기대 동작 |
|---|---|---|---|
| `SYS-01` | 부팅 완료 | `Context=Away, Activity=Idle` | `NormalFace(dim)`으로 시작하고 대기 상태 진입 |
| `SYS-02` | 사용자 없음 지속 | 상태 유지 | 약한 blink와 저강도 존재감만 유지 |
| `SYS-03` | 얼굴 첫 감지 | `Context: Away -> Idle` | 화면이 깨어나고 시선 애니메이션 활성화 |
| `SYS-04` | 얼굴 없이 음성 또는 터치 먼저 감지 | `Context: Away -> Idle`, `oneshot=startled` | 사용자 흔적을 감지했다는 놀람 반응 후 다음 입력 처리 (§2.3 `INT-01`과 연계) |
| `SYS-05` | 얼굴이 보이는 상태에서 음성/터치 상호작용 시작 | `Context: Idle -> Engaged` | 집중 표정과 상호작용 중심 반응 |
| `SYS-06` | 상호작용이 한동안 없음 | `Context: Engaged -> Idle` | 집중 상태에서 일반 대기 상태로 완화 |
| `SYS-07a` | `Idle`에서 장시간 유휴 | `Context: Idle -> Sleepy` | 졸음 표정, `SleepUI`, 꿈 계열 연출 |
| `SYS-07b` | `Engaged`에서 장시간 유휴 | `Context: Engaged -> Sleepy` | `Engaged`에서 직접 Sleepy로 진입 (state-machine.md §3 다이어그램 기준) |
| `SYS-08a` | `Idle`에서 장시간 얼굴 없음 | `Context: Idle -> Away` | 다시 dim 대기 상태로 복귀 |
| `SYS-08b` | `Sleepy`에서 장시간 얼굴 없음 | `Context: Sleepy -> Away` | `SleepUI`에서 `NormalFace(dim)`으로 복귀 |
| `SYS-09` | 장기 부재 후 얼굴 재감지 | `Context: Away -> Idle`, `oneshot=welcome` | `welcome` oneshot과 반김 연출 (단, `away_started_at` 이후 `welcome_min_away_ms` 경과 조건) |
| `SYS-10a` | `Sleepy` 중 얼굴 재감지 (gentle_wake) | `Context: Sleepy -> Idle`, `oneshot=welcome` | 얼굴 감지만이 gentle_wake 트리거. 반김 연출 |
| `SYS-10b` | `Sleepy` 중 음성/터치만 감지 (얼굴 없음) | `Context: Sleepy` 유지, `Activity: Idle -> Listening`, `oneshot=startled` | 갑작스런 자극은 Sleepy를 깨우지 않고 startled로 처리 |
| `SYS-11` | 재등장 직후 바로 말 걸기 | `Context=Idle, Activity: Idle -> Listening, oneshot=welcome` | 반김이 얹힌 채 듣기 모드 진입 (state-machine.md §8.4) |

### 2.2 음성 입력 / 명령 처리

| ID | 입력 | 상태 변화 | 기대 동작 |
|---|---|---|---|
| `VOICE-01` | 일반 음성 시작 | `Activity: Idle -> Listening` | `ListeningUI`, STT HUD, listening cue 출력 |
| `VOICE-02` | intent 미해석 또는 low confidence (`voice.intent.unknown`) | `Activity: Listening -> Idle`, `oneshot=confused` | `confused` oneshot과 실패 피드백 후 복귀 |
| `VOICE-03` | VAD 시작 후 무음 타임아웃 (`timeout_or_no_intent`) | `Activity: Listening -> Idle` | oneshot 없이 조용히 복귀 (사용자가 말을 걸었다 만 경우) |
| `VOICE-04` | `dance.start` | `Activity: Listening -> Executing(dance)` | energetic face, 댄스 연출, 음악 재생 |
| `VOICE-05` | `camera.capture` | `Activity: Listening -> Executing(photo)` | 카운트다운, 셔터, 저장 완료 피드백 |
| `VOICE-06` | `ui.game_mode.enter` | `Activity: Listening -> Executing(game)` | 얼굴 축소, 게임 UI, 조작 영역 표시 |
| `VOICE-07` | `timer.create` | `Activity: Listening -> Executing(timer_setup) -> Idle` | 시간 파싱, 타이머 등록, 확인 피드백 후 즉시 Idle 복귀 |
| `VOICE-08` | `timer.create` 시간 파싱 실패 | `Activity: Executing(timer_setup) -> Idle`, `oneshot=confused` | 파싱 실패 피드백 후 복귀 |
| `VOICE-09` | `weather.current` | `Activity: Listening -> Executing(weather)` | 날씨 조회, HUD, 아이콘, TTS 브리핑 |
| `VOICE-10` | `smarthome.aircon.on` | `Activity: Listening -> Executing(smarthome)` | 에어컨 제어 요청과 결과 피드백 |
| `VOICE-11` | `smarthome.aircon.off` | `Activity: Listening -> Executing(smarthome)` | 에어컨 종료 요청과 결과 피드백 |
| `VOICE-12` | `smarthome.aircon.set_temperature` | `Activity: Listening -> Executing(smarthome)` | 온도 설정 요청과 결과 피드백 |
| `VOICE-13` | `smarthome.light.on` | `Activity: Listening -> Executing(smarthome)` | 조명 제어 요청과 결과 피드백 |
| `VOICE-14` | `smarthome.light.off` | `Activity: Listening -> Executing(smarthome)` | 조명 종료 요청과 결과 피드백 |
| `VOICE-15` | `smarthome.robot_cleaner.start` | `Activity: Listening -> Executing(smarthome)` | 로봇청소기 제어 요청과 결과 피드백 |
| `VOICE-16` | `smarthome.tv.on` | `Activity: Listening -> Executing(smarthome)` | TV 제어 요청과 결과 피드백 |
| `VOICE-17` | `smarthome.music.play` | `Activity: Listening -> Executing(smarthome)` | 음악 재생 요청과 결과 피드백 |
| `VOICE-18` | `system.cancel` (Listening 중) | `Activity: Listening -> Idle` | 현재 듣기 취소, 조용한 복귀 |
| `VOICE-19` | `system.ack` (Alerting 중) | `Activity: Alerting -> Idle` | 알림 확인 피드백 후 복귀 (§2.4 `POL-06`과 연계) |

### 2.3 상호작용 / 연출

| ID | 트리거 / 조건 | 상태 변화 | 기대 동작 |
|---|---|---|---|
| `INT-01` | 얼굴 없이 먼저 말 걸기 | `Activity=Listening, is_searching_for_user=true, oneshot=startled` | `startled` 후 `ListeningUI + search indicator` (state-machine.md §8.1) |
| `INT-02` | 얼굴 중심 이동 | 상태 변화 없음 | 눈동자와 얼굴 방향감 애니메이션 보정 |
| `INT-03a` | `Context=Away`에서 터치 탭 | `Context: Away -> Idle` | 깨어남 반응 |
| `INT-03b` | `Context=Idle/Engaged`에서 터치 탭 | 상태 변화 없음 | 주의 전환 애니메이션 |
| `INT-03c` | `Context=Sleepy`에서 터치 탭 | `Context: Sleepy` 유지, `oneshot=startled` | 갑작스런 자극 반응 (gentle_wake 아님) |
| `INT-04` | 쓰다듬기 스트로크 | 상태 유지, `oneshot=happy` | `happy` oneshot, 하트, 만족 사운드 |
| `INT-05` | 사진 촬영 진행 중 | `Executing(photo)` 유지 | `CameraUI`, 집중 표정, 셔터 시퀀스 유지 |
| `INT-06a` | 날씨 조회 성공 | `Executing(weather) -> Idle` | 날씨 표정, 아이콘, TTS 브리핑 |
| `INT-06b` | 날씨 조회 실패 | `Executing(weather) -> Idle`, `oneshot=confused` | 실패 피드백, HUD 메시지 (§2.5 `OPS-01`과 연계) |
| `INT-07` | 스마트홈 실행 성공 | `Executing(smarthome) -> Idle`, `oneshot=happy` | `happy` oneshot, 성공음, HUD 결과 |
| `INT-08` | 스마트홈 실행 실패 | `Executing(smarthome) -> Idle`, `oneshot=confused` | `confused` oneshot, 실패 HUD |
| `INT-09` | 오래 비움 | `Context=Sleepy, Activity=Idle` | `SleepUI`, 졸음 표정, 꿈/코고는 연출 |
| `INT-10` | 타이머 만료 | `Activity: Idle/Listening/Executing(except photo) -> Alerting` | `AlertUI`, alert 표정, 알림 사운드 |
| `INT-11` | 촬영 중 일시적 얼굴 손실 (`recent_face_loss`) | 상태 변화 없음, focus lock | `CameraUI`와 표정(`attentive`) 유지, 흔들림 없음 |

### 2.4 실행 정책 / 인터럽트

| ID | 상황 | 정책 | 기대 동작 |
|---|---|---|---|
| `POL-01` | `Alerting` 발생 | 최우선 선점 (단, `Executing(photo)` 제외) | 현재 작업을 끊고 알림 먼저 실행 |
| `POL-02` | `Executing(photo)` 중 새 명령 | 무시 | `system.cancel`, `system.ack` 외 신규 intent 무시 |
| `POL-03` | `Executing(photo)` 중 `timer.expired` 발생 | defer | 촬영 시퀀스가 짧으므로 종료 직후 `Alerting` 처리 |
| `POL-04` | `Executing(smarthome/weather/timer_setup)` 중 새 명령 | `deferred_intent` 1개 저장 | 현재 작업 완료 후 최신 보류 명령 처리 |
| `POL-05` | `Executing -> Idle` 직후 `deferred_intent` 존재 | 즉시 재진입 | intent 확정 여부에 따라 `Idle -> Executing(kind)` 또는 `Idle -> Listening` |
| `POL-06` | `Executing(game/dance)` 중 새 명령 | 기본 무시 | `system.cancel`, `high_priority_alert`(MVP=`timer.expired`)만 허용 |
| `POL-07` | 실행 중 일시적 얼굴 손실 (`recent_face_loss`) | focus lock | UI와 표정 흔들림 없이 현재 작업 유지 |
| `POL-08` | `Alerting` 종료 (`system.ack` 또는 timeout) | `Activity: Alerting -> Idle` | 자동 작업 복원 없이 Context 기준 화면으로 복귀 |

### 2.5 Oneshot 중첩 정책

state-machine.md §5.1을 직접 검증하는 시나리오입니다.

| ID | 상황 | 정책 | 기대 동작 |
|---|---|---|---|
| `ONE-01` | `welcome`(priority=20) 진행 중 `startled`(30) 트리거 | priority preempt | 즉시 `startled`로 교체, 남은 시간 버림 |
| `ONE-02` | `happy`(20) 진행 중 새 `happy` 트리거 (20% 경과 시점) | same priority coalesce | 새 이벤트 무시 (깜빡임 방지) |
| `ONE-03` | `happy`(20) 진행 중 새 `welcome` 트리거 (85% 경과 시점) | same priority, 80% 이상 경과 | 새 이벤트로 교체 |
| `ONE-04` | `startled`(30) 진행 중 `happy`(20) 트리거 | lower priority drop | 새 이벤트 무시 |
| `ONE-05` | 다수 oneshot 동시 트리거 | queue 금지 | 가장 높은 priority만 표출, 나머지는 큐잉 없이 버림 |

### 2.6 Scene Selector Override

state-machine.md §6.4 override 규칙을 검증합니다.

| ID | 상황 | 파생 결과 | 기대 동작 |
|---|---|---|---|
| `SCN-01` | `Context=Sleepy, Activity=Alerting` | 표정=`alert`, UI=`AlertUI` | Alerting override로 Context와 무관하게 `alert`/`AlertUI` (state-machine.md §8.6) |
| `SCN-02` | `Context=Away, Activity=Alerting` | 표정=`alert`, UI=`AlertUI` | 부재 중 타이머도 반드시 인지 가능하게 표출 |
| `SCN-03` | `Executing(photo)` 중 `Engaged -> Idle` (얼굴 잠깐 이탈) | 표정=`attentive` 유지 | Executing focus lock으로 `calm` 흔들림 방지 |
| `SCN-04` | `Executing(smarthome)` 중 성공 → `oneshot=happy` | 표정: `attentive -> happy -> attentive` | oneshot 우선(§6.1의 2번이 3번보다 앞섬)이 focus lock을 일시적으로 덮음 |
| `SCN-05` | `Activity=Listening, face_present=false` | UI=`ListeningUI` + search indicator | 별도 UI 상태 만들지 않고 `ListeningUI` 내부 추가 요소로 표시 |

### 2.7 실패 / 운영

| ID | 장애 / 조건 | 영향 | 기대 동작 |
|---|---|---|---|
| `OPS-01` | 날씨 API 실패 | 날씨 기능 실패 | 실패 사운드, HUD 메시지, `oneshot=confused`, 로컬 반응 유지 |
| `OPS-02` | home-client 실패 | 스마트홈 기능 실패 | 실패 표정/HUD 유지, 시스템 전체는 계속 동작 |
| `OPS-03` | 카메라 없음 | 얼굴/시선 추적 비활성 | `face_present=false` 고정, 음성/터치 기반 동작 유지 |
| `OPS-04` | 터치스크린 없음 | 터치 반응 비활성 | 음성/비전 기반 동작 유지 |
| `OPS-05a` | 마이크 없음 | 음성 명령 비활성 | 비전/터치 기반 동작 유지 |
| `OPS-05b` | STT 엔진 실패 (마이크는 작동) | voice.intent 미발행 | VAD 이벤트는 남지만 intent 경로 비활성, `system.degraded.entered` 발행 |
| `OPS-06` | vision_worker heartbeat 이상 | face tracking 상실 | `face_present=false` 고정 처리, `system.degraded.entered` 발행, 음성/터치로 동작 유지 |
| `OPS-07` | audio_worker heartbeat 이상 | 음성 경로 상실 | `system.degraded.entered` 발행, 비전/터치로 동작 유지 |

## 3. Phase 2 시나리오

### 3.1 제스처 기반 놀이 / 고급 상호작용

아래 항목은 feature-complete 기준의 Phase 2 목표입니다.
현재 저장소에는 `wave`, `finger_gun`, `peekaboo`, `head_left/right`, `v_sign`에 대한 프로토타입 반응 경로가 일부 선반영되어 있습니다.

| ID | 입력 | 상태 / 처리 | 기대 동작 |
|---|---|---|---|
| `P2-01` | 손 흔들기 | gesture 인식 | slow blink 또는 인사 반응 |
| `P2-02` | 손가락 총 모양 | gesture 인식 | 현재는 `빵야!`/놀람 반응, 최종 목표는 쓰러짐 연출 |
| `P2-03` | 고개 좌/우 방향 | head direction 인식 | 현재는 방향 피드백, 최종 목표는 참참참 승패 판정 |
| `P2-04` | 얼굴 가림 후 재등장 | 패턴 인식 | 현재는 `peekaboo`/반김 반응, 최종 목표는 숨바꼭질 반응 |
| `P2-05` | V자 손동작 | gesture → `camera.capture` intent 합류 | 음성 없이 `Executing(photo)` 진입, MVP 촬영 시퀀스 재사용 |

## 4. 시나리오별 핵심 출력 규칙

### 4.1 화면

state-machine.md §6.2의 UI 매핑 테이블을 요약합니다.

- `Activity=Listening` 중에는 항상 `ListeningUI`를 사용한다.
- `Activity=Executing(photo)`는 항상 `CameraUI`를 사용한다.
- `Activity=Executing(game)`는 항상 `GameUI`를 사용한다.
- `Activity=Executing(weather/smarthome/timer_setup/dance)`는 `NormalFace`를 유지한다 (Context 무관).
- `Activity=Alerting`은 Context와 무관하게 항상 `AlertUI`를 사용한다.
- `Activity=Idle` 상태에서만 Context가 UI를 결정한다:
  - `Away` → `NormalFace(dim)`
  - `Idle`/`Engaged` → `NormalFace`
  - `Sleepy` → `SleepUI`
- `is_searching_for_user=true`일 때는 `ListeningUI` 내부에 search indicator를 추가한다 (별도 UI 아님).

### 4.2 표정

state-machine.md §6.1의 우선순위를 요약합니다.

- `Activity=Alerting`은 항상 `alert` 표정을 우선한다 (Alerting override).
- active oneshot이 있으면 기본 표정보다 oneshot 표정을 우선한다.
- `Activity=Executing(kind)` 중에는 기본 표정을 `attentive`로 고정한다 (Executing focus lock).
- `Activity=Listening` 중에는 `attentive`를 사용한다.
- `Activity=Idle` 상태에서는 `Context`에 따라 파생된다:
  - `Away` → 비활성 (눈 감김/어두움)
  - `Idle` → `calm`
  - `Engaged` → `attentive`
  - `Sleepy` → `sleepy`

### 4.3 사운드

- 음성 인식 시작 시 listening cue가 가능해야 한다.
- 사진 촬영 시 셔터음이 필요하다.
- 성공/실패 피드백은 효과음으로 분리한다.
- `Sleepy` 진입 시 수면 계열 효과음을 사용할 수 있다.
- `Alerting`은 사용자가 인지 가능한 알림음을 반드시 포함한다.

## 5. 구현 체크포인트

이 문서를 실제 구현에 사용할 때는 각 시나리오마다 아래 항목을 함께 검증한다.

- 입력 이벤트가 어떤 topic으로 발행되는가
- `Context`와 `Activity`가 어떻게 전이되는가
- oneshot이 필요한가 (필요하면 priority/duration)
- 최종 표정과 UI가 무엇으로 파생되는가
- 사운드가 필요한가
- 외부 서비스 호출이 필요한가
- 실패 시 로컬 피드백이 남는가
- 인터럽트 정책(§2.4)과 충돌하지 않는가

## 6. 범위 요약

현재 문서 기준 RIO는 아래 범위의 시나리오를 지원 대상으로 본다.

- 사용자 존재 감지와 부재, 재등장
- 음성 명령 인식과 intent 기반 실행 (`system.cancel`/`system.ack` 포함)
- 사진, 타이머, 날씨, 스마트홈, 게임, 댄스
- 터치 기반 감정형 반응
- 수면/깨어남/알림
- Oneshot 중첩 정책과 Scene Selector override
- 제스처 기반 확장 상호작용 (Phase 2)
- 네트워크 실패와 센서 degraded 대응
