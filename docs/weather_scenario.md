# Weather Scenario

RIO의 날씨 조회 기능을 사용자가 언제/어떻게 쓰는지, 내부적으로 어떤 이벤트가 오가는지, 그리고 어떻게 실행/테스트하는지를 한 곳에 정리한 문서.

관련 시나리오 ID (참고):
- [`VOICE-09`](./scenarios.md) — `weather.current` intent 처리
- [`INT-06a` / `INT-06b`](./scenarios.md) — 성공/실패 피드백

---

## 1. 개요

사용자가 "날씨 알려줘" 라고 말하면 RIO 는:

1. 음성을 `weather.current` intent 로 해석
2. Open-Meteo API 로 현재 날씨 조회
3. 얼굴 패널을 `robot_right.png` 로 전환
4. 우상단에 조건별 벡터 아이콘 오버레이 (맑음=해, 흐림=구름, 비=우산 등)
5. 효과음 재생 (Animal Crossing flourish)
6. 6초 후 얼굴과 아이콘이 동시에 원래 상태로 복귀

TTS 멘트는 없다 (음성으로 수치를 읽지 않음) — 시각 + 효과음 중심.

---

## 2. 음성 트리거

| 입력 예시 | 매칭 intent |
|---|---|
| "날씨 알려줘" | `weather.current` |
| "오늘 날씨" | `weather.current` |
| "날씨 조회" | `weather.current` |
| "weather" | `weather.current` |
| "what's the weather" | `weather.current` |

Intent alias 는 `configs/triggers.yaml:32-37` 에서 관리.

위치 지정은 현재 하드코딩된 기본값(`seoul`) 만 지원. 사용자가 "부산 날씨" 같이 말해도 ASR → intent 파이프라인이 location 필드를 뽑아내지 않기 때문에 서울로 조회된다. `live_weather_test.py` 의 `weather busan` 명령으로는 직접 location 을 지정할 수 있다.

---

## 3. 이벤트 흐름

```
VOICE_INTENT_DETECTED {intent: weather.current}
  └─> activity: Listening → Executing(weather)
      └─> registry.dispatch(ActionKind.WEATHER)
           │
           ├─> TASK_STARTED          (kind=weather)
           ├─> WeatherClient.fetch_current()  ← Open-Meteo HTTP GET
           ├─> orchestrator.weather_display_end_at = now + 6s
           ├─> orchestrator.weather_icon_key = "sunny" | "cloudy" | ...
           ├─> WEATHER_RESULT        (ok, condition, temperature_c, icon_key)
           └─> TASK_SUCCEEDED | TASK_FAILED
```

`WEATHER_RESULT` 이벤트는 effect_planner 에서:
- 성공 시 `"weather"` SFX alias 재생
- 실패 시 `"weather_failed"` SFX alias + `oneshot=confused`

핵심 소스:
- Handler factory: `src/app/main.py:_weather_execution_handler_factory`
- HTTP 호출: `src/app/adapters/weather/client.py`
- WMO → icon 매핑: `src/app/adapters/weather/normalizer.py`
- SFX alias: `src/app/adapters/speaker/sfx.py`
- 표정 선택: `src/app/adapters/display/preview_window.py:choose_face_asset_key`
- 아이콘 드로잉: `src/app/adapters/display/preview_window.py:_draw_weather_icon`

---

## 4. 외부 API

| 항목 | 값 |
|---|---|
| Provider | [Open-Meteo](https://api.open-meteo.com/) |
| Endpoint | `https://api.open-meteo.com/v1/forecast` |
| API key | 불필요 (비상업 무료) |
| 요청 파라미터 | `latitude`, `longitude`, `current_weather=true`, `timezone=auto` |
| 응답 필드 사용 | `current_weather.temperature`, `current_weather.weathercode` |
| 타임아웃 | `configs/thresholds.yaml:task.http_timeout_ms` (기본 3s) |
| 재시도 | `configs/thresholds.yaml:task.http_retry_count` (기본 1) |

### WMO weathercode → icon_key 매핑

| WMO 코드 | condition | icon_key | 시각적 표현 |
|---|---|---|---|
| 0, 1 | clear / mostly clear | `sunny` | 회전하는 해 + 8방향 rays |
| 2, 3 | partly cloudy / overcast | `cloudy` | 겹친 회색 구름 |
| 45, 48 | fog | `fog` | 수평 파형 4줄 |
| 51–57, 61–67, 80–82 | drizzle / rain / showers | `rainy` | 구름 + 떨어지는 파란 빗줄 3개 |
| 71–77, 85–86 | snow / snow showers | `snowy` | 구름 + 회전하는 눈송이 3개 |
| 95, 96, 99 | thunderstorm | `thunder` | 구름 + 깜빡이는 번개 |
| 그 외 | unknown | `unknown` | 물음표 |

정확한 매핑은 `normalizer.py:_WMO_TO_ICON`.

---

## 5. 얼굴 표정

| 상황 | 표정 asset_key | fallback |
|---|---|---|
| 날씨 조회 중 (Activity=Executing weather) | `robot_right` | `attentive` |
| 조회 완료 후 6초간 | `robot_right` | `attentive` |
| 6초 경과 후 | 평상시 mood 로 복귀 | - |

핵심 동작: weather 는 네트워크 호출이 1초 내로 끝나 `Executing → Idle` 로 금방 돌아가므로, `rio.weather_display_end_at` 타이머를 이용해 Idle 복귀 후에도 6초간 `robot_right.png` 를 유지한다. 이 분기는 `preview_window.py:choose_face_asset_key` 안에 있다. (참고: `assets/expressions/weather_face.png` 는 현재 사용되지 않음.)

---

## 6. 아이콘 오버레이

얼굴 패널 중앙 (face_rect 의 중심) 에 반경 110px 의 원형 영역으로 그려진다. 반투명 배경 원(alpha≈0.55) 이 아이콘 뒤에 깔려서 얼굴 표정 위에 올라가도 아이콘 모양이 선명하게 보인다. 6초의 마지막 1초는 선형 페이드아웃.

| icon_key | 그려지는 요소 | 애니메이션 |
|---|---|---|
| `sunny` | 노란 원 + 8개 ray 라인 | ray 각도 `now_s * 0.6` rad 회전 |
| `cloudy` | 겹친 회색 원 3개 + 베이스 타원 | 정지 |
| `rainy` | 구름 + 3개 빗줄 | 빗줄 y = `now_s * 120 % 30` 하강 루프 |
| `snowy` | 구름 + 3개 눈송이 (6방향 교차선) | 회전 `now_s * 0.8` + 상하 `sin` |
| `thunder` | 짙은 구름 + 지그재그 번개 | `sin(now_s*6) > -0.3` 일 때만 그려짐 (깜빡임) |
| `fog` | 수평 파형 4줄 | `sin(x/10 + now_s*2)` 오프셋 |
| `unknown` | 물음표 텍스트 | 정지 |

PNG 에셋은 추가하지 않고 cv2 primitive 로 그린다. 디스플레이 duration 은 `configs/devices.yaml:weather.display_seconds` 에서 조정 가능 (기본 6.0).

---

## 7. 효과음 & TTS

| 상황 | SFX alias | 파일 | TTS |
|---|---|---|---|
| 조회 성공 (WEATHER_RESULT ok=True) | `weather` | `assets/sounds/flourish-emote-animal-crossing.mp3` | 없음 |
| 조회 실패 (WEATHER_RESULT ok=False) | `weather_failed` → `error` | `assets/sounds/surprise-emote.mp3` (둘 다) | 없음 |

실패 시에는 `WEATHER_RESULT ok=False` 와 `TASK_FAILED` 가 각각 SFX 를 유발하므로 두 개가 순차로 울린다 (smarthome 실패와 동일 패턴). TTS 멘트는 의도적으로 제거됨 — 과거에는 영어로 "Current weather is ..." 를 읽었으나 SFX 중심으로 교체.

---

## 8. Config

### `configs/devices.yaml`

```yaml
weather:
  base_url: "https://api.open-meteo.com/v1/forecast"
  default_location: "seoul"
  display_seconds: 6.0
  locations:
    seoul:   { latitude: 37.5665, longitude: 126.9780 }
    busan:   { latitude: 35.1796, longitude: 129.0756 }
    incheon: { latitude: 37.4563, longitude: 126.7052 }
```

- 새 도시를 추가하려면 `locations` 아래에 `name: {latitude, longitude}` 한 줄만 넣으면 된다.
- `default_location` 은 반드시 `locations` 에 등록된 이름이어야 하며, 없을 경우 `fetch_current` 는 `{ok: False, message: "unknown_location:..."}` 를 돌려준다.

---

## 9. 실행 방법

### 9.1 프로덕션 경로 — `scripts/run_rio_app.py`

실제 앱 진입점. 마이크 / 카메라 / 스피커 / 디스플레이 전부 활성화된 상태에서 음성으로 테스트한다.

```bash
python scripts/run_rio_app.py --profile app --preview
```

기대 동작:
1. `[RIO] startup report` 에서 weather 항목은 별도 표시 없음 (endpoint 확인은 하고 싶으면 `configs/devices.yaml` 열기)
2. 마이크에 "날씨 알려줘" → 인식 블록에 `intent: weather.current`, `confidence` 표시
3. `── activity: Listening → Executing (weather) ──` 전이 로그
4. 프리뷰 창 얼굴이 `robot_right` 로 전환
5. 우상단 아이콘 등장 (맑음/흐림/비 등)
6. Animal Crossing flourish 효과음 재생
7. 6초 뒤 얼굴 + 아이콘 동시 소멸, Idle 복귀

주요 플래그:
| 플래그 | 용도 |
|---|---|
| `--no-preview` | 프리뷰 창 없이 헤드리스 실행 |
| `--no-voice` | 음성 백엔드 비활성화 (이 경로로는 weather 트리거 불가) |
| `--trace-events` | task / intent / oneshot 이벤트를 한 줄씩 로깅 |

실패 경로 재현: 인터넷을 끊거나 `configs/devices.yaml` 의 `base_url` 을 `https://api.example.invalid/x` 로 바꿔두고 실행 → TASK_FAILED, `oneshot=confused`, HUD "Weather failed", `surprise-emote.mp3` 재생.

### 9.2 터미널 단독 테스트 — `scripts/live_weather_test.py`

마이크 없이 stdin 으로 명령어를 쳐서 날씨 파이프라인만 단독으로 검증하는 도구. 음성 인식이 준비되지 않은 환경(BT mic 미연결, 샌드박스 등) 이나 아이콘 / 효과음 UX 만 빠르게 확인할 때 쓴다.

```bash
python scripts/live_weather_test.py              # 터미널만
python scripts/live_weather_test.py --preview    # 프리뷰 창 + 터미널
python scripts/live_weather_test.py --preview --fullscreen
```

#### 명령어

| 명령 | 동작 |
|---|---|
| `w` / `weather` | 기본 위치(seoul) 로 `weather.current` intent 발행 → 실제 Open-Meteo 호출 |
| `w busan` / `weather busan` | 지정 위치로 호출 (devices.yaml 의 locations 키) |
| `mock sunny` | 네트워크 건너뛰고 성공 결과를 직접 주입 (icon_key=sunny) |
| `mock cloudy` / `mock rainy` / `mock snowy` / `mock thunder` / `mock fog` / `mock unknown` | 각 아이콘의 UI 검증 |
| `fail` | 실패 결과 시뮬레이션 (SFX + confused oneshot) |
| `s` / `status` | orchestrator 의 현재 weather 상태 덤프 (icon_key, display 잔여 시간, last SFX) |
| `h` / `help` | 명령어 도움말 |
| `q` / `quit` / `exit` | 종료 (Ctrl+C 도 가능) |

#### 사용 시나리오

**1) 새 아이콘 디자인 확인** — 네트워크 호출 없이 아이콘 7종을 빠르게 돌려본다.
```
> mock sunny
> mock rainy
> mock thunder
> mock unknown
```

**2) 실제 API 동작 검증**
```
> weather
> weather busan
> status
```

**3) 실패 경로 연출 확인**
```
> fail
> status
```

`live_weather_test.py` 는 음성 / 카메라 / 스마트홈 bridge 를 전혀 요구하지 않기 때문에, 개발 중 가장 빠른 피드백 루프이다.

---

## 10. 테스트

| 파일 | 커버 |
|---|---|
| `tests/unit/test_weather_normalizer.py` | WMO 매핑 (sunny/rainy/snowy/thunder/unknown), WeatherClient 의 location 해석 fallback |
| `tests/integration/test_weather_lookup.py` | 성공 / 실패 두 경로, SFX history 검증, TTS 미발생 확인, HUD 메시지 |
| `tests/integration/test_voice_to_execution.py` | 음성 intent → WEATHER_RESULT → IDLE 복귀 |
| `tests/integration/test_orchestrator_interrupts.py` | 다른 action 실행 중 weather intent 가 DROP/DEFER 되는 interrupt 정책 |
| `tests/unit/test_activity_fsm.py::test_listening_to_executing_weather` | `weather.current` 가 Executing(weather) 로 전이하는지 |
| `tests/unit/test_intent_parser.py::test_matches_weather_lookup_alias` | alias 매칭 |

실행:
```bash
python -m unittest discover -s tests -t .
```

---

## 11. 실패 모드 / 예외 동작

| 상황 | 반응 |
|---|---|
| 네트워크 타임아웃 | `URLError` 잡혀 `{ok: False, message: <urllib error>}` → TASK_FAILED, confused, weather_failed SFX |
| 잘못된 JSON 응답 | `JSONDecodeError` 잡혀 동일하게 실패 처리 |
| 알려지지 않은 weathercode | normalizer 가 `icon_key="unknown"`, `condition="unknown"` 으로 폴백 → 아이콘은 물음표 |
| `devices.yaml` 의 `locations` 가 비어있음 | `{ok: False, message: "unknown_location:..."}` → 실패 경로 |
| `base_url` 이 잘못된 URL | 재시도 후 `URLError` 실패 |
| 다른 action 실행 중 weather intent 수신 | interrupt 정책에 따라 DROP 또는 DEFER (state-machine.md §interrupt 참조) |

---

## 12. 관련 파일 인덱스

| 역할 | 경로 |
|---|---|
| 진입점 (프로덕션) | `scripts/run_rio_app.py` |
| 진입점 (터미널 테스트) | `scripts/live_weather_test.py` |
| HTTP 클라이언트 | `src/app/adapters/weather/client.py` |
| 응답 정규화 | `src/app/adapters/weather/normalizer.py` |
| Handler factory / orchestrator 필드 | `src/app/main.py` (`_weather_execution_handler_factory`, `weather_display_end_at`, `weather_icon_key`) |
| SFX alias | `src/app/adapters/speaker/sfx.py` |
| SFX 트리거 / TTS 제거 | `src/app/domains/behavior/effect_planner.py` |
| 얼굴 표정 선택 | `src/app/adapters/display/preview_window.py:choose_face_asset_key` |
| 아이콘 드로잉 | `src/app/adapters/display/preview_window.py:_draw_weather_icon` |
| 얼굴 에셋 | `assets/expressions/robot_right.png` |
| 효과음 에셋 | `assets/sounds/flourish-emote-animal-crossing.mp3`, `assets/sounds/surprise-emote.mp3` |
| Intent alias | `configs/triggers.yaml` |
| 위치 / 엔드포인트 | `configs/devices.yaml` |
| 타임아웃 / 재시도 | `configs/thresholds.yaml` |
