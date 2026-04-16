# Current Behaviors

이 문서는 `현재 코드 기준으로 실제 동작하는 입력/반응`을 정리한 운영 문서입니다.

- 목표/우선순위/장기 방향은 [prd.md](./prd.md)를 기준으로 봅니다.
- 이 문서는 `지금 바로 테스트 가능한 입력`, `현재 반응`, `실행 경계`를 빠르게 확인하기 위한 참고 문서입니다.
- 기준 진입점은 `scripts/live_interaction_test.py`입니다.

## 1. 실행 방법

기본 실행:

```bash
cd /home/willtek/work/emo-homehub-rpi/scripts
python3 live_interaction_test.py
```

- 기본값은 `mock` 서비스 모드입니다.
- 스마트홈/날씨는 mock 결과를 반환하고, 상태/HUD/sfx/tts 흐름을 확인하는 데 적합합니다.

실제 HTTP 확인:

```bash
cd /home/willtek/work/emo-homehub-rpi/scripts
python3 live_interaction_test.py --real-services
```

- 스마트홈 요청은 [configs/devices.yaml](../configs/devices.yaml)의 `home_client` 설정을 사용합니다.
- 이 모드에서는 출력의 `http_sent`, `http_status`, `http_target`, `http_payload` 필드로 실제 요청 여부를 확인할 수 있습니다.

## 2. 상태 축

현재 런타임은 두 개의 상태 축과 oneshot 반응으로 동작합니다.

- `Context`
  - `Away`: 사용자 부재 대기
  - `Idle`: 기본 대기
  - `Engaged`: 상호작용 집중 상태
  - `Sleepy`: 졸음/수면 상태
- `Activity`
  - `Idle`: 작업 없음
  - `Listening`: 입력 청취 중
  - `Executing`: 작업 실행 중
  - `Alerting`: 타이머 알림 중
- `Oneshot`
  - `startled`: 화들짝 반응
  - `welcome`: 반김 반응
  - `happy`: 만족/기쁨 반응
  - `confused`: 실패/미해석 반응

## 3. 자동 상태 시나리오

| 상황 | 현재 반응 |
|---|---|
| 부팅 직후 | `Context=Away`, `Activity=Idle`, dim된 대기 상태로 시작 |
| 얼굴 첫 감지 | `Away -> Idle`, 화면이 깨어나고 시선 추적이 붙음 |
| 얼굴이 보이는 상태에서 음성/터치 시작 | `Idle -> Engaged` |
| 상호작용이 한동안 없음 | `Engaged -> Idle` |
| 오래 유휴 | `Idle/Engaged -> Sleepy` |
| 얼굴이 오래 안 보임 | `Idle/Sleepy -> Away` |
| 장기 부재 후 얼굴 재등장 | `welcome` 반응 |
| 얼굴 없이 먼저 말 걸기/터치 | `startled` 반응 후 입력 처리 |
| 타이머 만료 | `Alerting` 진입, 알림 사운드/표정/HUD 출력 |

## 4. Voice 입력

현재 저장소에서 `voice`는 실제 마이크 대신 `터미널 문자열 입력`으로 가장 안정적으로 검증할 수 있습니다.

### 4.1 지원 명령

| 입력 예시 | Canonical intent | 현재 반응 |
|---|---|---|
| `사진 찍어줘`, `사진 찍자` | `camera.capture` | 카운트다운 후 사진 촬영, 셔터 사운드, 저장 완료 HUD/TTS |
| `날씨 알려줘`, `날씨 조회`, `오늘 날씨` | `weather.current` | 날씨 조회 후 HUD/TTS 브리핑 |
| `게임 모드로 바꿔줘`, `게임 모드` | `ui.game_mode.enter` | `GameUI` 진입 및 유지 |
| `춤춰`, `댄스 모드`, `rio dance` | `dance.start` | 댄스 실행 흐름 시작 |
| `에어컨 켜줘`, `에어컨 켜기` | `smarthome.aircon.on` | 스마트홈 제어 요청 |
| `에어컨 꺼줘`, `에어컨 끄기` | `smarthome.aircon.off` | 스마트홈 제어 요청 |
| `온도 28도로 맞춰줘` | `smarthome.aircon.set_temperature` | 에어컨 온도 설정 요청 |
| `불 켜줘`, `조명 켜기` | `smarthome.light.on` | 조명 켜기 요청 |
| `불 꺼줘`, `조명 끄기` | `smarthome.light.off` | 조명 끄기 요청 |
| `로봇 청소기 실행시켜줘`, `청소기 돌려줘` | `smarthome.robot_cleaner.start` | 로봇청소기 시작 요청 |
| `티비 켜줘` | `smarthome.tv.on` | TV 켜기 요청 |
| `음악 틀어줘`, `노래 틀어줘` | `smarthome.music.play` | 음악 재생 요청 |
| `취소` | `system.cancel` | Listening 중 입력 취소, 게임 모드 같은 UI mode도 해제 |
| `확인`, `알겠어` | `system.ack` | Alerting 중 알림 해제 |

### 4.2 타이머 명령

현재 타이머는 일부 문구만 안정적으로 동작합니다.

| 입력 예시 | 결과 |
|---|---|
| `5분 뒤에 알려줘` | 타이머 등록 성공 |
| `알람 맞춰줘` | intent는 잡히지만 현재는 시간 파싱 실패 |
| `timer` | intent는 잡히지만 현재는 시간 파싱 실패 |
| `30초 후에 알려줘` | 현재 alias가 약해서 `unknown_intent` 가능 |
| `오후 3시 반에 알려줘` | 현재 alias가 약해서 `unknown_intent` 가능 |

### 4.3 얼굴 부재 상태에서의 음성

- 얼굴이 없어도 스마트홈/날씨/사진 같은 명령은 처리됩니다.
- 다만 시작 순간에는 `startled` 반응이 먼저 보일 수 있습니다.
- 이 경우 실제 실행 여부는 `doing`, `last_result`, `http_*` 필드로 확인하는 것이 정확합니다.

## 5. Vision 입력

현재 웹캠 기준으로 아래 입력이 반응합니다.

| 입력 | 현재 반응 |
|---|---|
| 얼굴 검출 | 깨어남, 시선 추적, 상태 전이 |
| 얼굴 중심 이동 | 눈동자/방향 보정 |
| 손 흔들기 `wave` | 인사 반응, `안녕!`, welcome 계열 반응 |
| 손가락 총 `finger_gun` | `빵야!`, startled 계열 반응 |
| V자 손동작 `v_sign` | 사진 촬영 트리거 |
| 얼굴이 잠깐 사라졌다가 다시 등장 `peekaboo` | `찾았다!`, welcome/happy 계열 반응 |
| 얼굴이 왼쪽/오른쪽으로 치우침 | `head_left` / `head_right` 제스처 발생, 게임 방향 피드백 |

참고:

- `point`는 감지는 되지만 현재 별도 실행 행동은 연결되어 있지 않습니다.
- `wave`, `finger_gun`, `peekaboo`, `head_left/right`는 `반응형 이벤트`이고, `v_sign`은 `실행형 이벤트`입니다.

## 6. Touch / Logic 입력

현재 `touch` 반응 로직과 worker 경로는 들어가 있습니다.
다만 실제 물리 터치스크린 장치에서 샘플을 읽어오는 하드웨어 바인딩은 아직 추상화 단계라,
실전 검증은 `live_interaction_test.py`의 시뮬레이션 명령이 가장 정확합니다.

### 6.1 현재 반응

| 입력 | 현재 반응 |
|---|---|
| 탭 | 주의 전환, `톡!`, 가벼운 반응 |
| 쓰다듬기 스트로크 | `happy`, 하트/만족 계열 반응 |
| 타이머 종료 | `Alerting`, 알림 사운드/HUD |

### 6.2 live 테스트용 보조 명령

| 명령 | 현재 반응 |
|---|---|
| `/tap` | 터치 탭 시뮬레이션 |
| `/stroke` | 쓰다듬기 시뮬레이션 |
| `/timer [label]` | 타이머 만료 시뮬레이션 |
| `/gesture wave` | 손 흔들기 시뮬레이션 |
| `/gesture finger_gun` | 빵야 시뮬레이션 |
| `/gesture v_sign` | 사진 촬영 제스처 시뮬레이션 |
| `/gesture head_left` | 왼쪽 방향 게임 제스처 시뮬레이션 |
| `/gesture head_right` | 오른쪽 방향 게임 제스처 시뮬레이션 |
| `/gesture peekaboo` | 숨바꼭질 재등장 시뮬레이션 |
| `/face left` | 왼쪽 얼굴 위치 시뮬레이션 |
| `/face center` | 중앙 얼굴 위치 시뮬레이션 |
| `/face right` | 오른쪽 얼굴 위치 시뮬레이션 |
| `/face lost` | 얼굴 손실 시뮬레이션 |
| `/status` | 현재 상태 출력 |
| `/help` | 도움말 출력 |
| `/quit` | 종료 |

## 7. 서비스 모드

### 7.1 Mock 모드

기본 실행은 `mock` 모드입니다.

- 날씨와 스마트홈은 실제 외부 요청 대신 mock 결과를 반환합니다.
- 출력 예시:
  - `service_mode: mock`
  - `http_mode: mock`
  - `http_sent: mock`
  - `http_target: mock://home-client/device/control`

### 7.2 Real HTTP 모드

`--real-services`를 주면 스마트홈은 실제 HTTP 요청을 보냅니다.

- 설정 파일: [configs/devices.yaml](../configs/devices.yaml)
- 확인 필드:
  - `http_sent`
  - `http_status`
  - `http_target`
  - `http_payload`

예시:

- `에어컨 켜줘` -> `http_payload: aircon.living_room:on`
- `에어컨 꺼줘` -> `http_payload: aircon.living_room:off`
- `온도 28도로 맞춰줘` -> `http_payload: aircon.living_room:set_temperature:28`
- `조명 켜기` -> `http_payload: light.main:on`

## 8. 화면/사운드 반응

입력에 따라 현재 프로그램은 보통 아래 조합으로 반응합니다.

- 상태 변화:
  - `Away`, `Idle`, `Engaged`, `Sleepy`
  - `Listening`, `Executing`, `Alerting`
- UI:
  - `NormalFace`
  - `ListeningUI`
  - `CameraUI`
  - `GameUI`
  - `AlertUI`
- oneshot:
  - `startled`
  - `welcome`
  - `happy`
  - `confused`
- HUD:
  - `듣고 있어`
  - `제어 성공`
  - `날씨 조회 실패`
  - `빵야!`
  - `안녕!`
  - `사진 저장 완료`
  - `게임 모드 준비 완료`
- sfx:
  - `startled`
  - `welcome`
  - `happy`
  - `success`
  - `error`
  - `alert`
  - `shutter`
  - `tap`
  - `game_move`

## 9. 현재 부분 구현 / 제한 사항

아래는 현재 경계가 남아 있는 항목입니다.

- 실제 마이크 기반 음성 입력은 아직 완전한 실장비 경로가 아닙니다.
  - 현재는 `터미널 문자열 입력`이 가장 정확한 검증 경로입니다.
- 실제 터치스크린 장치 read 바인딩은 아직 추상화 단계입니다.
  - 반응 로직과 worker는 존재하지만, 하드웨어 드라이버 연결은 후속 작업입니다.
- 일부 음성 alias는 아직 부족합니다.
  - 예: `TV 끄기`, `음악 중지` 계열은 내부 모델은 있으나 현재 trigger 문구가 충분히 열려 있지 않습니다.
- 타이머 자연어는 일부 문구만 안정적으로 파싱됩니다.
- `point` 제스처는 감지만 되고 별도 행동은 아직 없습니다.
- `참참참`, `빵야`, `숨바꼭질`은 반응/HUD 수준까지는 연결되었지만 완전한 게임 로직은 아닙니다.

## 10. 테스트 기준

현재 문서에 적힌 동작은 아래 테스트들로 일부 고정되어 있습니다.

- 입력 반응 통합 테스트: [tests/integration/test_input_reactions.py](../tests/integration/test_input_reactions.py)
- 스마트홈 흐름: [tests/integration/test_smart_home_flow.py](../tests/integration/test_smart_home_flow.py)
- 날씨 흐름: [tests/integration/test_weather_lookup.py](../tests/integration/test_weather_lookup.py)
- 사진 인터럽트 정책: [tests/integration/test_photo_sequence.py](../tests/integration/test_photo_sequence.py)
- intent 파싱: [tests/unit/test_intent_parser.py](../tests/unit/test_intent_parser.py)
- 터치 worker: [tests/unit/test_touch_worker.py](../tests/unit/test_touch_worker.py)
- 비전 interaction tracker: [tests/unit/test_vision_interaction_tracker.py](../tests/unit/test_vision_interaction_tracker.py)
