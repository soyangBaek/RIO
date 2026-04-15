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
- MVP와 Phase 2를 분리해 관리한다.

## 2. MVP 시나리오

### 2.1 시스템 / 존재 맥락

| ID | 트리거 / 조건 | 상태 변화 | 기대 동작 |
|---|---|---|---|
| `SYS-01` | 부팅 완료 | `Context=Away`, `Activity=Idle` | `NormalFace(dim)`으로 시작하고 대기 상태 진입 |
| `SYS-02` | 사용자 없음 지속 | 상태 유지 | 약한 blink와 저강도 존재감만 유지 |
| `SYS-03` | 얼굴 첫 감지 | `Away -> Idle` | 화면이 깨어나고 시선 애니메이션 활성화 |
| `SYS-04` | 얼굴 없이 음성 또는 터치 먼저 감지 | `Away -> Idle` | 사용자 흔적을 감지했다는 반응 후 다음 입력 처리 |
| `SYS-05` | 얼굴이 보이는 상태에서 음성/터치 상호작용 시작 | `Idle -> Engaged` | 집중 표정과 상호작용 중심 반응 |
| `SYS-06` | 상호작용이 한동안 없음 | `Engaged -> Idle` | 집중 상태에서 일반 대기 상태로 완화 |
| `SYS-07` | 장시간 유휴 | `Idle/Engaged -> Sleepy` | 졸음 표정, 수면 UI, 꿈 계열 연출 |
| `SYS-08` | 장시간 사용자 흔적 없음 | `Idle/Sleepy -> Away` | 다시 dim 대기 상태로 복귀 |
| `SYS-09` | 장기 부재 후 사용자 재등장 | `Away/Sleepy -> Idle` | `welcome` oneshot과 반김 연출 |
| `SYS-10` | 재등장 직후 바로 말 걸기 | `Idle + Listening` | 반김이 얹힌 채 듣기 모드 진입 |

### 2.2 음성 입력 / 명령 처리

| ID | 입력 | 상태 변화 | 기대 동작 |
|---|---|---|---|
| `VOICE-01` | 일반 음성 시작 | `Idle -> Listening` | `ListeningUI`, STT HUD, listening cue 출력 |
| `VOICE-02` | intent 미해석 또는 low confidence | `Listening -> Idle` | `confused` oneshot과 실패 피드백 후 복귀 |
| `VOICE-03` | `dance.start` | `Listening -> Executing(dance)` | energetic face, 댄스 연출, 음악 재생 |
| `VOICE-04` | `camera.capture` | `Listening -> Executing(photo)` | 카운트다운, 셔터, 저장 완료 피드백 |
| `VOICE-05` | `ui.game_mode.enter` | `Listening -> Executing(game)` | 얼굴 축소, 게임 UI, 조작 영역 표시 |
| `VOICE-06` | `timer.create` | `Listening -> Executing(timer_setup)` | 시간 파싱, 타이머 등록, 확인 피드백 |
| `VOICE-07` | `weather.current` | `Listening -> Executing(weather)` | 날씨 조회, HUD, 아이콘, TTS 브리핑 |
| `VOICE-08` | `smarthome.aircon.on` | `Listening -> Executing(smarthome)` | 에어컨 제어 요청과 결과 피드백 |
| `VOICE-09` | `smarthome.light.on` | `Listening -> Executing(smarthome)` | 조명 제어 요청과 결과 피드백 |
| `VOICE-10` | `smarthome.robot_cleaner.start` | `Listening -> Executing(smarthome)` | 로봇청소기 제어 요청과 결과 피드백 |
| `VOICE-11` | `smarthome.tv.on` | `Listening -> Executing(smarthome)` | TV 제어 요청과 결과 피드백 |
| `VOICE-12` | `smarthome.music.play` | `Listening -> Executing(smarthome)` | 음악 재생 요청과 결과 피드백 |

### 2.3 상호작용 / 연출

| ID | 트리거 / 조건 | 상태 변화 | 기대 동작 |
|---|---|---|---|
| `INT-01` | 얼굴 없이 먼저 말 걸기 | `Activity=Listening`, `is_searching_for_user=true` | `startled` 후 `ListeningUI + search indicator` |
| `INT-02` | 얼굴 중심 이동 | 상태 변화 없음 | 눈동자와 얼굴 방향감 애니메이션 보정 |
| `INT-03` | 터치 탭 | `Away -> Idle` 가능 | 주의 전환 또는 깨어남 반응 |
| `INT-04` | 쓰다듬기 스트로크 | 상태 유지 | `happy` oneshot, 하트, 만족 사운드 |
| `INT-05` | 사진 촬영 진행 중 | `Executing(photo)` 유지 | `CameraUI`, 집중 표정, 셔터 시퀀스 유지 |
| `INT-06` | 날씨 조회 성공 | `Executing(weather) -> Idle` | 날씨 표정, 아이콘, TTS 브리핑 |
| `INT-07` | 스마트홈 실행 성공 | `Executing(smarthome) -> Idle` | `happy` oneshot, 성공음, HUD 결과 |
| `INT-08` | 스마트홈 실행 실패 | `Executing(smarthome) -> Idle` | `confused` 또는 미안한 피드백, 실패 HUD |
| `INT-09` | 오래 비움 | `Sleepy + Idle` | `SleepUI`, 졸음 표정, 꿈/코고는 연출 |
| `INT-10` | 타이머 만료 | `Idle/Listening/Executing -> Alerting` | `AlertUI`, alert 표정, 알림 사운드 |

### 2.4 실행 정책 / 인터럽트

| ID | 상황 | 정책 | 기대 동작 |
|---|---|---|---|
| `POL-01` | `Alerting` 발생 | 최우선 선점 | 현재 작업을 끊고 알림 먼저 실행 |
| `POL-02` | `Executing(photo)` 중 새 명령 | 무시 | `cancel`, `ack` 외 신규 intent 무시 |
| `POL-03` | `Executing(smarthome/weather/timer_setup)` 중 새 명령 | `deferred_intent` 1개 저장 | 현재 작업 완료 후 최신 보류 명령 처리 |
| `POL-04` | `Executing(game/dance)` 중 새 명령 | 기본 무시 | `exit`, `cancel`, `high_priority_alert`만 허용 |
| `POL-05` | 실행 중 일시적 얼굴 손실 | focus lock | UI와 표정 흔들림 없이 현재 작업 유지 |
| `POL-06` | `Alerting` 종료 | `Alerting -> Idle` | 자동 작업 복원 없이 Context 기준 화면으로 복귀 |

### 2.5 실패 / 운영

| ID | 장애 / 조건 | 영향 | 기대 동작 |
|---|---|---|---|
| `OPS-01` | 날씨 API 실패 | 날씨 기능 실패 | 실패 사운드, HUD 메시지, 로컬 반응 유지 |
| `OPS-02` | home-client 실패 | 스마트홈 기능 실패 | 실패 표정/HUD 유지, 시스템 전체는 계속 동작 |
| `OPS-03` | 카메라 없음 | 얼굴/시선 추적 비활성 | 음성/터치 기반 동작 유지 |
| `OPS-04` | 터치스크린 없음 | 터치 반응 비활성 | 음성/비전 기반 동작 유지 |
| `OPS-05` | 마이크 없음 | 음성 명령 비활성 | 비전/터치 기반 동작 유지 |
| `OPS-06` | 워커 heartbeat 이상 | degraded mode 진입 | 일부 기능 상실 상태로 계속 운영 |

## 3. Phase 2 시나리오

### 3.1 제스처 기반 놀이 / 고급 상호작용

| ID | 입력 | 상태 / 처리 | 기대 동작 |
|---|---|---|---|
| `P2-01` | 손 흔들기 | gesture 인식 | slow blink 또는 인사 반응 |
| `P2-02` | 손가락 총 모양 | gesture 인식 | 쓰러짐 모션 |
| `P2-03` | 고개 좌/우 방향 | head direction 인식 | 참참참 승패 판정 |
| `P2-04` | 얼굴 가림 후 재등장 | 패턴 인식 | 숨바꼭질 반응 |
| `P2-05` | V자 손동작 | gesture 트리거 | 음성 없이 사진 촬영 루프 진입 |

## 4. 시나리오별 핵심 출력 규칙

### 4.1 화면

- `Listening` 중에는 항상 `ListeningUI`를 사용한다.
- `Executing(photo)`는 항상 `CameraUI`를 사용한다.
- `Executing(game)`는 항상 `GameUI`를 사용한다.
- `Alerting`은 Context와 무관하게 항상 `AlertUI`를 사용한다.
- `Sleepy + Idle`은 `SleepUI`를 사용한다.

### 4.2 표정

- `Alerting`은 항상 `alert` 표정을 우선한다.
- active oneshot이 있으면 기본 표정보다 oneshot 표정을 우선한다.
- `Executing(kind)` 중에는 기본 표정을 `attentive`로 고정한다.
- `Idle` 상태에서는 `Context`에 따라 `calm`, `attentive`, `sleepy`, 비활성 표정이 파생된다.

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
- oneshot이 필요한가
- 최종 표정과 UI가 무엇으로 파생되는가
- 사운드가 필요한가
- 외부 서비스 호출이 필요한가
- 실패 시 로컬 피드백이 남는가

## 6. 범위 요약

현재 문서 기준 RIO는 아래 범위의 시나리오를 지원 대상으로 본다.

- 사용자 존재 감지와 부재, 재등장
- 음성 명령 인식과 intent 기반 실행
- 사진, 타이머, 날씨, 스마트홈, 게임, 댄스
- 터치 기반 감정형 반응
- 수면/깨어남/알림
- 제스처 기반 확장 상호작용
- 네트워크 실패와 센서 degraded 대응
