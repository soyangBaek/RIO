# Utterance Scenarios

이 문서는 RIO가 `어떤 발화`를 들었을 때 `어떤 동작`으로 이어지는지를, 실제 코드(`src/app/**`)와 설정 파일(`configs/triggers.yaml`, `configs/devices.yaml`)을 기준으로 정리한 카탈로그입니다.

- 기준 문서: [prd.md](./prd.md), [architecture.md](./architecture.md), [state-machine.md](./state-machine.md), [scenarios.md](./scenarios.md)
- 분기 기준은 문장이 아니라 `intent`입니다. 문장 alias는 [configs/triggers.yaml](../configs/triggers.yaml), 동적 패턴은 [intent_parser.py](../src/app/domains/speech/intent_parser.py)를 참고합니다.

---

## 1. 발화 처리 파이프라인

아래 단계는 음성 한 번이 실제 동작으로 바뀌기까지의 공통 경로입니다. 개별 시나리오는 이 루프를 공유하며, `intent`에 따라 §4의 도메인 분기로 갈라집니다.

1. `Audio Worker`가 VAD 시작을 감지 → `voice.activity.started` 발행
   - 이 시점에 `Activity: Idle -> Listening` 전이 ([activity_fsm.py:29-31](../src/app/core/state/activity_fsm.py#L29-L31))
   - 얼굴이 없으면 `oneshot=startled` 트리거 ([reducers.py:104-109](../src/app/core/state/reducers.py#L104-L109))
2. STT 결과를 `intent_parser.parse_intent()`에 전달
   - `KoreanCommandNormalizer`로 1차 정규화 → 소문자/공백 정규화
   - `_parse_dynamic_smarthome` → `_parse_dynamic_generic` → `triggers.yaml` alias 매칭 순으로 평가 ([intent_parser.py:294-373](../src/app/domains/speech/intent_parser.py#L294-L373))
3. `stt_confidence < 0.6` 또는 매칭 실패 → `voice.intent.unknown`
   - `oneshot=confused`, `Activity: Listening -> Idle`
4. 성공 → `voice.intent.detected(intent, payload)` 발행
   - `INTENT_TO_ACTION_KIND` 매핑으로 `ActionKind` 결정 ([models.py:67-94](../src/app/core/state/models.py#L67-L94))
   - `Activity: Listening -> Executing(kind)` 전이
5. `effect_planner.plan_effects` → `ExecutionRequest` 구성 → `ExecutorRegistry.dispatch(kind)`
6. 도메인 서비스가 `task.started` → (도메인 고유 이벤트) → `task.succeeded | task.failed` 발행
   - 성공/실패에 따라 `oneshot=happy | confused`가 따라붙음

> `VOICE_INTENT_DETECTED` payload는 `intent`, `text`, `confidence` 외에 파서가 넣은 `payload`(예: `device_key`, `action`, `temperature_c`, `delay_seconds`)를 그대로 실행 쪽에 전달합니다.

---

## 2. Intent 정규화 요약

### 2.1 YAML alias 우선순위

- [configs/triggers.yaml](../configs/triggers.yaml)의 intent → alias 리스트가 있으면 `_token_overlap_score`로 점수화 ([intent_parser.py:54-76](../src/app/domains/speech/intent_parser.py#L54-L76))
- 동일 토큰이 겹칠수록 점수↑, 완전 일치 → 1.0, 부분 포함 → 0.88~0.98
- 최종 `confidence = min(stt_confidence, best_score)`가 `intent_match_confidence_min(=0.6)` 미만이면 `unknown_intent`

### 2.2 동적 패턴 (`_parse_dynamic_*`)

YAML에 적지 않아도 되는 자연어 패턴입니다. 가장 먼저 평가되므로 alias보다 우선합니다.

- `_parse_dynamic_smarthome` — 스마트홈 명령 ([intent_parser.py:79-213](../src/app/domains/speech/intent_parser.py#L79-L213))
  - `N도(로)` 또는 `N degrees|c` 패턴 + `에어컨/온도` → `smarthome.aircon.set_temperature`
  - `N도(로)` + `난방/히터/보일러` → `smarthome.heater.set_temperature`
  - 둘 다 16~30°C 범위를 벗어나면 `reason=temperature_out_of_range`로 `unknown`
  - `에어컨|aircon|ac|냉방` + `켜|꺼` → `smarthome.aircon.on/off`
  - `난방|히터|보일러|heater` + `켜|꺼` → `smarthome.heater.on/off`
  - `간접등|무드등|indirect light|mood light` + `켜|꺼` → `smarthome.indirect_light.on/off`
  - `조명|전등|불|light|lamp` + `켜|꺼` → `smarthome.light.on/off`
  - `(로봇)청소기|vacuum` + `실행/시작/돌려/켜` → `smarthome.robot_cleaner.start`, `멈춰/정지/꺼` → `stop`
  - `공기청정기|air purifier` + `켜|꺼` → `smarthome.air_purifier.on/off`
  - `컴퓨터|pc|피씨` + `켜|꺼` → `smarthome.computer.on/off`
  - `티비|tv|텔레비전` + `켜|꺼` → `smarthome.tv.on/off`
  - `음악|노래|music` + `틀어/재생/play` → `smarthome.music.play`, `꺼/멈춰/stop` → `smarthome.music.stop`
  - `다 꺼|전부 꺼|모두 꺼|외출 모드|all off` → `smarthome.all.off`
- `_parse_dynamic_generic` — 그 외 일반 명령 ([intent_parser.py:216-291](../src/app/domains/speech/intent_parser.py#L216-L291))
  - `댄스모드|dance|춤춰` → `dance.start`
  - `사진` + `찍어/찍자/take/capture` → `camera.capture`
  - `게임(모드)|game mode` → `ui.game_mode.enter`
  - `날씨|weather` → `weather.current`
  - `(숫자)시간|분|초|시` + `알려줘|타이머|알람|뒤|후` → `timer.create`
  - `취소|cancel|그만` → `system.cancel`
  - `알겠어|확인|오케이|okay|ok` → `system.ack`

---

## 3. Intent → 상태 → 실행 요약 표

| 발화 예시 | Intent | ActionKind | 실행 주체 | 주요 전이 | 결과 oneshot |
|---|---|---|---|---|---|
| "춤춰줘" | `dance.start` | `DANCE` | `_dance_execution_handler_factory` ([main.py:302-336](../src/app/main.py#L302-L336)) | `Listening → Executing(dance) → Idle` (10s 후) | — |
| "사진 찍어줘" | `camera.capture` | `PHOTO` | `_photo_execution_handler_factory` ([main.py:229-300](../src/app/main.py#L229-L300)) | `Listening → Executing(photo) → Idle` (3s 카운트다운) | — |
| "게임 모드" | `ui.game_mode.enter` | `GAME` | `GamesService` ([games/service.py](../src/app/domains/games/service.py)) | `Listening → Executing(game) → Idle` | — |
| "5분 뒤에 알려줘" | `timer.create` | `TIMER_SETUP` | `TimerService` ([timers/service.py](../src/app/domains/timers/service.py)) | `Listening → Executing(timer_setup) → Idle` (즉시 복귀) | `confused` on 파싱 실패 |
| "날씨 알려줘" | `weather.current` | `WEATHER` | `_weather_execution_handler` ([main.py:193-221](../src/app/main.py#L193-L221)) | `Listening → Executing(weather) → Idle` | `confused` on 실패 |
| "에어컨 켜줘" | `smarthome.aircon.on` | `SMARTHOME` | `SmartHomeService` ([smart_home/service.py](../src/app/domains/smart_home/service.py)) | `Listening → Executing(smarthome) → Idle` | `happy`/`confused` |
| "에어컨 28도로 맞춰줘" | `smarthome.aircon.set_temperature` | `SMARTHOME` | 동일 | 동일 | 동일 |
| "불 꺼줘" | `smarthome.light.off` | `SMARTHOME` | 동일 | 동일 | 동일 |
| "다 꺼" | `smarthome.all.off` | `SMARTHOME` | `SmartHomeService._handle_all_off` | 동일 (client의 `reset_all()` 호출) | 동일 |
| "취소" | `system.cancel` | — | Activity reducer 직접 처리 | `Listening/Executing(dance|game) → Idle` | — |
| "알겠어" | `system.ack` | — | Activity reducer 직접 처리 | `Alerting → Idle` | — |

---

## 4. 도메인별 발화 시나리오

각 시나리오는 `입력 문장 → intent → 발행 이벤트 → 출력(표정/UI/사운드/TTS)` 흐름을 코드 기준으로 기술합니다.

### 4.1 댄스 `dance.start`

- **발화 예시**: "춤춰줘", "댄스 모드", "rio dance", "emo dance"
- **매칭 경로**: `_parse_dynamic_generic` (댄스/dance/춤춰) 또는 YAML alias
- **실행 순서**:
  1. `VOICE_INTENT_DETECTED(intent="dance.start")` → `Executing(DANCE)` 전이
  2. `_dance_execution_handler_factory.handler`가 `TASK_STARTED` 발행 + `sfx.play("dance")`
  3. `DANCE_DURATION_SECONDS=10.0` 후 `threading.Timer`가 `sfx.stop("dance")` + `TASK_SUCCEEDED` 발행 ([main.py:330-333](../src/app/main.py#L330-L333))
- **Scene Selector 파생**:
  - UI: `NormalFace` (Executing이지만 PHOTO/GAME 아님 → [scene_selector.py:26-36](../src/app/core/state/scene_selector.py#L26-L36))
  - Mood: `ATTENTIVE` (Executing focus lock)
  - 씬 키: 기본 경로로 `default_scene` 흐름 (댄스 전용 씬 키는 현재 미지정)
- **인터럽트 정책**: `Executing(DANCE)` 중 `system.cancel`/`system.ack`만 허용, 일반 intent는 drop ([interrupts.py:56-63](../src/app/domains/behavior/interrupts.py#L56-L63)). `timer.expired`는 허용되어 `Alerting` 선점.

### 4.2 사진 촬영 `camera.capture`

- **발화 예시**: "사진 찍어줘", "사진 찍자", "take a photo", "photo please"
- **매칭 경로**: `_parse_dynamic_generic` (`사진` + `찍어|찍자|take|capture`)
- **실행 순서**:
  1. `Executing(PHOTO)` 전이
  2. `_photo_execution_handler_factory.handler`가 `photo_countdown_end_at = now + 3s` 설정 + `TASK_STARTED(countdown=[3,2,1])`
  3. `threading.Timer(3s)` 후 `orchestrator.webcam_capture.capture()` 호출
  4. 성공: `TASK_SUCCEEDED(photo_path)` + TTS "Photo taken." + sfx `shutter`
  5. 실패: `TASK_FAILED(message)` + `oneshot=confused` + sfx `error`
- **Scene Selector 파생**:
  - UI: `CameraUI` (kind=PHOTO 고정 override)
  - Mood: `ATTENTIVE`
  - 씬 키: `take_photo_countdown` ([effect_planner.py:55-56](../src/app/domains/behavior/effect_planner.py#L55-L56))
- **인터럽트 정책**: 최강 focus lock. `system.cancel`/`system.ack` 외 모든 intent drop, `timer.expired`는 `HOLD_ALERT`로 유보 후 촬영 종료 뒤 처리 ([interrupts.py:47-54](../src/app/domains/behavior/interrupts.py#L47-L54)).

### 4.3 게임 모드 `ui.game_mode.enter`

- **발화 예시**: "게임 모드", "게임모드", "게임 모드로 바꿔줘", "enter game mode"
- **매칭 경로**: `_parse_dynamic_generic` 또는 YAML alias
- **실행 순서**:
  1. `Executing(GAME)` 전이
  2. `GamesService.__call__`가 `TASK_STARTED` + `TASK_SUCCEEDED(ui_mode="game")` 즉시 발행
  3. 메타데이터 `ui_mode="game"` → `extended.ui_mode = "game"`로 유지됨
  4. TTS "Entering game mode." + sfx `success`
- **Scene Selector 파생**:
  - UI: `GameUI` (kind=GAME이면 override, 또는 idle 중에도 `ui_mode=="game"`이면 `GameUI`)
  - Mood: `ATTENTIVE`
- **인터럽트 정책**: DANCE와 동일. `system.cancel`로만 빠져나옴.

### 4.4 타이머 `timer.create`

- **발화 예시**: "5분 뒤에 알려줘", "3분 있다 알려줘", "오후 7시에 알려줘", "10초 후에 알려줘", "set a timer"
- **매칭 경로**: `_parse_dynamic_generic`이 숫자+단위 + 타이머 힌트 조합을 체크. 실제 시간 파싱은 [timer_parser.py](../src/app/domains/speech/timer_parser.py)가 담당(상대/절대 시간 모두 지원).
- **실행 순서**:
  1. `Executing(TIMER_SETUP)` 전이
  2. `TimerService`가 `payload["delay_seconds"]`를 확인
     - ≤ 0이면 `TASK_FAILED(message="delay_seconds must be positive")` → `oneshot=confused`
     - > 0이면 `scheduler.add_timer(delay_seconds, label, timer_id)` → `TASK_SUCCEEDED(timer_id, label, delay_seconds)`
  3. sfx `timer_registered` 재생
  4. 등록 즉시 `Executing → Idle` 복귀 (타이머 만료는 별도 이벤트)
- **타이머 만료**: 등록된 `delay_seconds` 경과 후 `TIMER_EXPIRED` 발행
  - `Activity → Alerting`, UI=`AlertUI`, Mood=`ALERT`, sfx `alert`, TTS `"{label} time is up."`
  - `Executing(PHOTO)` 중이면 촬영 끝날 때까지 `HOLD_ALERT`

### 4.5 날씨 `weather.current`

- **발화 예시**: "날씨 알려줘", "오늘 날씨", "weather"
- **실행 순서**:
  1. `Executing(WEATHER)` 전이
  2. `_weather_execution_handler`가 `TASK_STARTED` 발행
  3. `WeatherClient.fetch_current(location="seoul")` 호출
  4. 성공: `WEATHER_RESULT(ok=true, condition, temperature_c, ...)` + `TASK_SUCCEEDED`
     - TTS `"Current weather is {condition}, temperature {temperature} degrees."`
  5. 실패: `WEATHER_RESULT(ok=false, ...)` + `TASK_FAILED`
     - `oneshot=confused`, TTS `"Failed to fetch weather."`, sfx `error`
- **Scene Selector**: UI=`NormalFace`, Mood=`ATTENTIVE`

### 4.6 스마트홈 `smarthome.*`

모든 스마트홈 intent는 `ActionKind.SMARTHOME`으로 묶여 `SmartHomeService` 하나가 처리합니다.

- **공통 실행 순서**:
  1. `build_smart_home_command(intent, payload)` ([payloads.py:57-91](../src/app/domains/smart_home/payloads.py#L57-L91))
     - `INTENT_TO_DEVICE_ACTION`으로 `(device_key, action)` 매핑
     - `configs/devices.yaml`에서 `device_id`, `display_name`, `template`, `action_label` 로드
     - `template.format(device_id, action, **payload)`로 `content` 문자열 완성
  2. `TASK_STARTED` + `SMARTHOME_REQUEST_SENT(content, request_url, ...)`
  3. `HomeClient.control(content)` — PUT `/device/control`, body `{"content": "..."}`
  4. `SMARTHOME_RESULT(ok, message, device_id, action, ...)` 발행
     - 성공: `oneshot=happy` + sfx `success` + TTS `message` (default: `"{display_name} {action_label} done"`)
     - 실패: `oneshot=confused` + sfx `error` + TTS 실패 메시지
  5. 종결: ok면 `TASK_SUCCEEDED`, 아니면 `TASK_FAILED`

- **intent별 `content` 예시** (devices.yaml 기본값 기준):

| 발화 예시 | Intent | content 문자열 |
|---|---|---|
| "에어컨 켜줘" | `smarthome.aircon.on` | `aircon.living_room:on` |
| "에어컨 꺼줘" | `smarthome.aircon.off` | `aircon.living_room:off` |
| "에어컨 28도로 맞춰줘" | `smarthome.aircon.set_temperature` | `aircon.living_room:set_temperature:28` |
| "난방 26도로 맞춰줘" | `smarthome.heater.set_temperature` | `heater.living_room:set_temperature:26` |
| "난방 켜줘" | `smarthome.heater.on` | `heater.living_room:on` |
| "불 켜줘" / "불 꺼줘" | `smarthome.light.on/off` | `light.main:on` / `light.main:off` |
| "간접등 켜줘" | `smarthome.indirect_light.on` | `light.indirect:on` |
| "티비 켜줘" | `smarthome.tv.on` | `tv.living_room:on` |
| "컴퓨터 꺼줘" | `smarthome.computer.off` | `computer.desk:off` |
| "로봇 청소기 돌려줘" | `smarthome.robot_cleaner.start` | `cleaner.bot:start` |
| "청소기 멈춰" | `smarthome.robot_cleaner.stop` | `cleaner.bot:stop` |
| "공기청정기 켜줘" | `smarthome.air_purifier.on` | `purifier.living_room:on` |
| "음악 틀어줘" | `smarthome.music.play` | `speaker.main:play` |
| "음악 꺼줘" | `smarthome.music.stop` | `speaker.main:stop` |
| "다 꺼" | `smarthome.all.off` | `all:off` (POST `/api/reset`) |

- **온도 경계**: `16 ≤ temperature_c ≤ 30`만 허용. 벗어나면 `intent=None, reason="temperature_out_of_range"` → `voice.intent.unknown`처럼 `oneshot=confused` 처리
- **인터럽트 정책**: Executing(smarthome) 중 새 intent는 `DEFER_INTENT`로 1개만 저장. 현재 작업 종료 직후 `_maybe_replay_deferred`가 재주입 ([interrupts.py:65-74](../src/app/domains/behavior/interrupts.py#L65-L74), [main.py:470+](../src/app/main.py#L470))

### 4.7 시스템 제어 `system.cancel` / `system.ack`

- **발화 예시**
  - `system.cancel`: "취소", "cancel", "그만"
  - `system.ack`: "알겠어", "확인", "okay", "ok", "오케이"
- **동작** ([activity_fsm.py:19-57](../src/app/core/state/activity_fsm.py#L19-L57))
  - `Listening` 중 → `Activity: Listening → Idle` (조용히 종료)
  - `Executing(DANCE|GAME)` 중 → `Activity: Executing → Idle`
  - `Executing(PHOTO)` 중 → 허용되지만 카메라 시퀀스는 자체적으로 계속 진행
  - `Alerting` 중 `system.ack` → `Alerting → Idle` (알림 확인)
- 별도 도메인 실행 없음. `INTENT_TO_ACTION_KIND`에 매핑도 없음.

---

## 5. 음성 없이 발생하는 상황 반응 (참고)

음성 명령과 엮여서 자주 관측되는 경로입니다.

| 상황 | 트리거 이벤트 | 결과 |
|---|---|---|
| 얼굴 없는데 말을 걺 | `voice.activity.started` + `face_present=false` | `oneshot=startled`, `ListeningUI + search indicator` ([reducers.py:104-109](../src/app/core/state/reducers.py#L104-L109), [scene_selector.py:76](../src/app/core/state/scene_selector.py#L76)) |
| 장기 부재 후 얼굴 재등장 + 음성 | `vision.face.detected` → `voice.activity.started` | `oneshot=welcome` 후 listening 진입 ([reducers.py:134-141](../src/app/core/state/reducers.py#L134-L141)) |
| STT 매칭 실패 | `voice.intent.unknown` | `oneshot=confused`, `Activity → Idle` |
| 무음 타임아웃 | `voice.activity.ended` | oneshot 없이 `Activity → Idle` |
| VAD 중 `terminal_input` 소스 발화 | `voice.activity.started(source="audio.terminal_input")` | startled oneshot 제외 (터미널 모의 입력 시 과잉 반응 방지) |

---

## 6. 출력 구성(표정 / UI / 사운드 / TTS) 정리

### 6.1 표정 (Mood) 우선순위

[scene_selector.py:44-64](../src/app/core/state/scene_selector.py#L44-L64) 기준.

1. `Activity == Alerting` → `ALERT`
2. active oneshot → 이름 매핑 (`startled`, `confused`, `welcome`, `happy`, `angry→startled`, `lovely→happy`)
3. `Activity == Listening | Executing` → `ATTENTIVE`
4. `ui_mode == "game"` → `ATTENTIVE`
5. Idle 분기: `Away→INACTIVE`, `Idle→CALM`, `Engaged→ATTENTIVE`, `Sleepy→SLEEPY`

### 6.2 UI 선택

[scene_selector.py:26-41](../src/app/core/state/scene_selector.py#L26-L41) 기준.

- `Listening` → `ListeningUI`
- `Alerting` → `AlertUI`
- `Executing(PHOTO)` → `CameraUI`
- `Executing(GAME)` → `GameUI`
- `Executing(weather/smarthome/timer_setup/dance)` → `NormalFace`
- `ui_mode=="game"` (Idle 중 잔존) → `GameUI`
- 그 외 `Sleepy` → `SleepUI`, 나머지 → `NormalFace`
- `Listening + face_present=false` → `ListeningUI` + `search_indicator=true`

### 6.3 사운드 / TTS 매핑

[effect_planner.py:90-155](../src/app/domains/behavior/effect_planner.py#L90-L155) 기준.

| 이벤트 | 추가 sfx | 추가 TTS |
|---|---|---|
| `VOICE_ACTIVITY_STARTED` | `listening_cue` | — |
| `TIMER_EXPIRED` | `alert` | `"{label} time is up."` |
| `SMARTHOME_RESULT(ok=true)` | `success` | `message` (또는 `"{display_name} {action_label} done"`) |
| `SMARTHOME_RESULT(ok=false)` | `error` | `message` |
| `WEATHER_RESULT(ok=true)` | (없음) | `"Current weather is {condition}, temperature {temperature} degrees."` |
| `WEATHER_RESULT(ok=false)` | (없음) | `"Failed to fetch weather."` |
| `TASK_SUCCEEDED(PHOTO)` | `shutter` | `"Photo taken."` |
| `TASK_SUCCEEDED(GAME)` | `success` | `"Entering game mode."` |
| `TASK_SUCCEEDED(TIMER_SETUP)` | `timer_registered` | — |
| `TASK_FAILED(*)` | `error` | `message`(기본 `"Task failed."`) |
| oneshot triggered | oneshot 이름과 동일한 sfx | — |

---

## 7. 샘플 시나리오 (End-to-End)

### 7.1 "RIO, 에어컨 28도로 맞춰줘"

1. 얼굴 없이 말 시작 → `voice.activity.started` → `Activity: Idle→Listening`, `oneshot=startled`, `ListeningUI + search indicator`, sfx `listening_cue`+`startled`
2. STT가 "RIO 에어컨 28도로 맞춰줘" 전달
3. `_parse_dynamic_smarthome`이 `N도(로)` + `에어컨` 매칭, `16 ≤ 28 ≤ 30` 통과 → `smarthome.aircon.set_temperature`, payload=`{device_key:"aircon", action:"set_temperature", temperature_c:28}`
4. `VOICE_INTENT_DETECTED` → `Activity: Listening→Executing(smarthome)`, Mood=`ATTENTIVE`, UI=`NormalFace`
5. `SmartHomeService`가 `content="aircon.living_room:set_temperature:28"` 생성 → `PUT /device/control` 전송
6. 응답 `ok=true` → `SMARTHOME_RESULT(ok=true)` + `TASK_SUCCEEDED` → `oneshot=happy` → sfx `success`+`happy` + TTS `"Air conditioner Set temperature done"` → `Activity → Idle`

### 7.2 "사진 찍어줘" 도중 타이머 만료

1. "사진 찍어줘" → `camera.capture` → `Executing(PHOTO)`, UI=`CameraUI`, 3s 카운트다운 시작
2. 2초 후 `timer.expired` 발행
3. 인터럽트 정책이 `HOLD_ALERT` 판정 → 이벤트 보류 ([interrupts.py:48-49](../src/app/domains/behavior/interrupts.py#L48-L49))
4. 3초 카운트다운 종료 → `webcam_capture.capture()` → `TASK_SUCCEEDED` + sfx `shutter` + TTS `"Photo taken."`
5. `Activity: Executing→Idle` 직후, 보류된 `timer.expired` 재발행
6. `Activity: Idle→Alerting`, Mood=`ALERT`, UI=`AlertUI`, sfx `alert`, TTS `"{label} time is up."`
7. 사용자 "알겠어" → `system.ack` → `Alerting→Idle`

### 7.3 "불 켜줘" 도중 "티비도 켜줘"

1. "불 켜줘" → `smarthome.light.on` → `Executing(smarthome)` 진입, HTTP 요청 진행 중
2. 응답 도착 전 사용자가 "티비 켜줘"
3. `VOICE_INTENT_DETECTED(smarthome.tv.on)` 수신 → 인터럽트 정책이 `DEFER_INTENT`로 페이로드 보관 ([interrupts.py:68-73](../src/app/domains/behavior/interrupts.py#L68-L73))
4. 최초 요청 응답 → `SMARTHOME_RESULT(ok=true)` → `oneshot=happy` → `Activity: Executing→Idle`
5. `_maybe_replay_deferred`가 저장된 intent를 `VOICE_INTENT_DETECTED`로 재주입
6. 곧바로 `Activity: Idle→Executing(smarthome)` → 티비 요청 송신

---

## 8. 참고

- Topic/페이로드 계약: [architecture.md §6](./architecture.md#6-이벤트-계약)
- 상태 머신/Oneshot 정책 상세: [state-machine.md](./state-machine.md)
- 시나리오 ID(`VOICE-*`, `SYS-*`, `POL-*` 등) 전체 카탈로그: [scenarios.md](./scenarios.md)
- 얼굴 표정 에셋 매핑: [face_scenario.md](./face_scenario.md)
