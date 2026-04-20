# RIO 구현 로드맵 (2026-04-20)

> 기준 branch: `develop`
> 관련 문서: [architecture.md](./architecture.md), [scenarios.md](./scenarios.md), [progress-tracker.md](./progress-tracker.md), [manual-test/voice-test-plan.md](./manual-test/voice-test-plan.md)

이 문서는 현재 저장소 상태를 기준으로 앞으로 해야 할 일을 4가지 범주로 정리한 실행 문서입니다.
단순 TODO 목록이 아니라, 각 범주별로 아래를 함께 정의합니다.

- 현재 상태
- 왜 필요한지
- 구체 작업 항목
- 완료 기준 (Definition of Done)
- 권장 우선순위

---

## 0. 현재 판단 요약

### 0.1 핵심 상태

| 범주 | 현재 상태 | 판단 |
|------|-----------|------|
| `main.py` / 실제 런타임 | `RioOrchestrator` 는 존재하지만 실제 사용자용 실행 경로는 `scripts/live_interaction_test.py`, `scripts/live_voice_interaction_test.py` 중심 | **실사용 진입점 정리 필요** |
| 시나리오 구현 | 기본 FSM, 사진/날씨/스마트홈/댄스는 연결됨. 게임/제스처 Phase 2는 일부 씬과 진입만 존재 | **추가 구현 필요** |
| ThinQ HTTP 연결 | `SmartHomeService -> HomeClient -> /device/control -> tools/thinq_server.py` 경로는 있음 | **브리지 운영 완결 필요** |
| 성능 최적화 | `faster-whisper`, OpenCV, MediaPipe 자체는 이미 네이티브. 병목은 Python 메인 루프와 동시 실행 구조에 가까움 | **측정 후 선택적 네이티브화 필요** |

### 0.2 최근 음성 경로에서 확인된 사실

- `voice_sandbox` 와 `live_*` 는 핵심 음성 설정을 거의 공유한다.
- 그런데 `live_*` 는 음성만 돌리지 않고 카메라, 얼굴 검출, 제스처, 렌더링까지 함께 수행한다.
- 따라서 샌드박스보다 `BUSY drop`, `EMPTY decode`, STT 오인식이 더 잘 발생한다.
- 즉 문제는 두 가지다.
  - 런타임 구조 문제: 음성과 비전이 한 루프에서 경쟁함
  - 설정 튜닝 문제: `mic_gain_percent`, `condition_on_previous_text`, `drop_while_busy`, `vad.threshold` 등이 아직 보수적으로 잡혀 있음

이 판단은 아래 네 범주의 우선순위에도 직접 영향을 준다.

---

## 1. `main.py` (실제 어플리케이션 구동 진입점 및 런타임 테스트)

### 1.1 현재 상태

- [src/app/main.py](../src/app/main.py)는 `RioOrchestrator` 조립과 서비스 바인딩을 담당한다.
- 하지만 실제 실행은 여전히 테스트 성격이 강한 [scripts/live_interaction_test.py](../scripts/live_interaction_test.py), [scripts/live_voice_interaction_test.py](../scripts/live_voice_interaction_test.py)에 의존한다.
- 현재 `live_*` 스크립트는 아래를 한 프로세스/한 루프에서 동시에 돌린다.
  - 음성 캡처 + RMS VAD + Whisper
  - 카메라 캡처 + 얼굴/제스처 검출
  - 상태 출력 + 미리보기 렌더링
- 이 구조는 개발용으로는 좋지만, 실제 구동 진입점으로 쓰기에는 역할이 너무 많고 성능 편차가 크다.

### 1.2 목표

목표는 `테스트 스크립트`와 `실제 앱 실행 진입점`을 분리하는 것이다.

- `main.py` 기반 앱 실행 경로를 명확히 만든다.
- 런타임 모드별 설정을 분리한다.
- 실제 구동 시 어떤 기능이 degraded 상태인지 시작 시점에 즉시 보이게 한다.
- 음성/비전 병목을 측정 가능한 구조로 만든다.

### 1.3 구체 작업

#### A. 실제 실행 진입점 정리

- 사용자용 실행 스크립트 추가
  - 예: `scripts/run_rio_app.py`
- 이 스크립트는 `RioOrchestrator` 를 기준으로 앱을 시작하고 종료하도록 정리한다.
- `live_interaction_test.py` 와 `live_voice_interaction_test.py` 는 테스트 하네스로 남긴다.

#### B. 런타임 프로파일 분리

- `configs/voice.yaml` 은 공용 기본값으로 유지한다.
- 아래처럼 프로파일별 설정 파일을 나눈다.
  - `configs/runtime_app.yaml`
  - `configs/runtime_live_test.yaml`
  - `configs/voice_sandbox.yaml`
- 분리 대상
  - 카메라 FPS
  - preview on/off
  - voice trace on/off
  - Whisper 모델 크기
  - `drop_while_busy`
  - `condition_on_previous_text`
  - mic gain

#### C. 부팅/헬스 체크 정리

- 앱 시작 시 아래를 한 번에 출력한다.
  - mic available
  - camera available
  - touch available
  - voice backend started / disabled reason
  - home client target URL
  - ThinQ bridge health
- `voice_backend.start()` 실패 시 단순히 꺼버리는 수준에서 끝내지 말고, 상태 저장소에 degraded flag 를 남긴다.

#### D. 런타임 계측 추가

- 음성 경로
  - `speech START`
  - `speech END`
  - `ASR decode ms`
  - `intent detected`
  - `BUSY drop count`
- 비전 경로
  - frame loop ms
  - face detect ms
  - gesture detect ms
- 메인 루프
  - `pump_workers()` 소요 시간
  - `process_frame()` 소요 시간
  - preview draw ms

#### E. 실제 앱용 수동 테스트/스모크 테스트 작성

- 현재는 라이브 테스트 계획 문서가 mostly 테스트 스크립트 기준이다.
- 실제 앱 실행 진입점 기준으로 별도 스모크 테스트를 만든다.
  - 부팅
  - 얼굴 감지
  - 음성 명령 1건
  - 타이머 알림
  - 스마트홈 HTTP 요청
  - 종료 및 자원 정리

### 1.4 완료 기준

- `scripts/run_rio_app.py` 같은 실제 앱 진입점이 존재한다.
- 테스트 하네스와 실제 실행 경로가 문서상/코드상 분리되어 있다.
- 앱 시작 시 사용 가능한 센서와 비활성화 이유가 모두 출력된다.
- 최소 1개 문서와 1개 자동 smoke test 가 새 진입점을 기준으로 작성되어 있다.

### 1.5 권장 우선순위

**최우선**

이 범주는 나머지 범주의 기반이므로 4개 범주 중 **가장 먼저** 정리하는 것이 좋다.

---

## 2. 시나리오 추가 (RIO의 추가 액션 구현, 미비된 구현)

### 2.1 현재 상태

- 기본 시나리오는 이미 꽤 많이 연결되어 있다.
- 음성 intent 도 `dance`, `photo`, `weather`, `timer`, `smart-home`, `cancel/ack`까지 확장된 상태다.
- 하지만 추가 액션/Phase 2 관점에서는 아직 비어 있는 부분이 있다.

현재 대표적인 미비 항목:

- [src/app/domains/games/service.py](../src/app/domains/games/service.py)
  - 현재는 사실상 `"Game mode ready"` 를 반환하는 placeholder 에 가깝다.
- [src/app/domains/gesture/mapper.py](../src/app/domains/gesture/mapper.py)
  - 현재는 `v_sign -> camera.capture` 만 실제 intent 합류 경로가 있다.
- `wave`, `finger_gun`, `peekaboo`, `head_left/right`
  - 씬/리액션은 일부 있으나 실제 게임 규칙이나 액션 결과까지는 연결이 약하다.

### 2.2 목표

목표는 `화면 반응이 있는 프로토타입`을 넘어서 `액션이 완료되는 시나리오`를 늘리는 것이다.

- 게임 모드는 실제 게임 규칙을 가진 액션이 되어야 한다.
- 제스처는 단순 시각 효과가 아니라 실행 흐름에 연결되어야 한다.
- 음성으로 들어온 intent 와 제스처로 들어온 intent 가 같은 실행기로 수렴해야 한다.

### 2.3 구체 작업

#### A. 게임 모드 실제 구현

- `Cham Cham Cham`
  - 좌/우 선택
  - 라운드 진행
  - 승패 판정
  - 재시도 / 종료
- `Peekaboo`
  - 얼굴 손실/재등장 패턴과 연계
  - 성공/실패 반응
- `Finger gun`
  - 단발 리액션이 아니라 상태 있는 미니 게임 또는 KO 액션으로 확장

#### B. 제스처와 액션 연결 강화

- `wave`
  - 단순 인사 씬 외에 welcome / attention 전환으로 연결할지 정의
- `finger_gun`
  - 리액션, 사운드, oneshot, cooldown 정책 확정
- `peekaboo`
  - `InteractionTracker` 와 게임 흐름 연결
- `head_left/right`
  - 게임 방향 판정과 연결

#### C. 액션별 종료 규약 통일

- 각 액션은 최소한 아래를 일관되게 가져야 한다.
  - `TASK_STARTED`
  - 중간 상태 또는 보조 이벤트
  - `TASK_SUCCEEDED` / `TASK_FAILED`
  - 취소 가능 여부
  - 인터럽트 정책

#### D. 씬/에셋/사운드 보강

- 액션이 늘어나면 아래도 같이 필요하다.
  - face asset
  - overlay animation
  - sfx
  - HUD text
- 구현은 코드보다 에셋 부족 때문에 막히는 경우가 많으므로 문서와 작업을 같이 묶는다.

#### E. 시나리오 문서/테스트 동시 업데이트

- [docs/scenarios.md](./scenarios.md) 에 새 시나리오를 추가한다.
- 새 액션이 들어가면 unit/integration/manual test 3종을 함께 만든다.

### 2.4 완료 기준

- `ui.game_mode.enter` 가 placeholder 가 아니라 실제 진행 가능한 액션이 된다.
- 제스처 3종 이상이 실제 액션 흐름과 연결된다.
- 각 신규 액션별로 `started/succeeded/failed/cancel` 규약이 문서화된다.
- 최소 1개의 통합 테스트와 1개의 수동 테스트 시나리오가 추가된다.

### 2.5 권장 우선순위

**2순위**

단, `main.py` 기반 실제 실행 진입점 정리가 먼저 끝난 뒤 들어가는 것이 효율적이다.

---

## 3. ThinQ와 구동 사이의 HTTP 연결 완료

### 3.1 현재 상태

현재 연결 구조는 아래처럼 이미 존재한다.

```text
VOICE / GESTURE / TERMINAL
  -> intent
  -> SmartHomeService
  -> HomeClient
  -> PUT /device/control
  -> tools/thinq_server.py
  -> ThinQ dashboard / state store
```

관련 파일:

- [src/app/domains/smart_home/service.py](../src/app/domains/smart_home/service.py)
- [src/app/adapters/home_client/client.py](../src/app/adapters/home_client/client.py)
- [configs/devices.yaml](../configs/devices.yaml)
- [tools/thinq_server.py](../tools/thinq_server.py)
- [assets/ui/thinq_dashboard.html](../assets/ui/thinq_dashboard.html)

즉, **코드상 연결은 이미 있다**.
다만 아직 아래 의미에서 "완료" 단계는 아니다.

- 운영 시 어떤 순서로 프로세스를 띄워야 하는지가 불명확하다.
- bridge down / timeout / invalid payload 대응이 충분히 문서화되어 있지 않다.
- 실제 ThinQ bridge 를 앱 부팅과 같이 관리하는 구조가 없다.
- 실기기 기준 검증보다 로컬 브리지 중심 테스트가 더 많다.

### 3.2 목표

목표는 "HTTP가 보내진다" 수준이 아니라, **RIO 앱에서 ThinQ 브리지까지의 운영 경로가 닫힌 상태**를 만드는 것이다.

### 3.3 구체 작업

#### A. 장치 매핑 확정

- [configs/devices.yaml](../configs/devices.yaml) 의 장치 키와 브리지 상태 키를 완전히 맞춘다.
- 확인 대상
  - `tv.living_room`
  - `light.main`
  - `aircon.living_room`
  - `cleaner.bot`
  - `speaker.main`

#### B. 에러 처리 표준화

- `HomeClient.control()` 의 실패 유형을 정리한다.
  - bridge unreachable
  - timeout
  - invalid JSON
  - business error
- `SmartHomeService` 결과 이벤트 payload 에 공통 필드를 넣는다.
  - `request_url`
  - `request_method`
  - `request_content`
  - `bridge_status`
  - `error_code`

#### C. 브리지 헬스체크 추가

- 앱 시작 시 `/api/state` 또는 전용 `/health` 엔드포인트를 호출해 bridge 가 살아 있는지 확인한다.
- bridge down 이면 앱은 계속 뜨되, smart-home capability 는 degraded 로 표시한다.

#### D. 실제 운영 방식 정리

- `tools/thinq_server.py` 를 단순 개발용 서버로 둘지, 실제 배포용 브리지로 둘지 결정한다.
- 실제 배포라면 아래가 필요하다.
  - systemd service 파일
  - 로그 위치
  - 재시작 정책
  - 포트 정책
  - 로컬 네트워크 접근 정책

#### E. End-to-End 검증 완료

- 음성 `"불 켜줘"` -> RIO -> `/device/control` -> ThinQ bridge -> dashboard state 변경
- gesture `v_sign` -> camera flow
- `--real-services` 모드에서 스마트홈 5개 이상 시나리오 검증

### 3.4 완료 기준

- `configs/devices.yaml` 와 `tools/thinq_server.py` 상태 키가 일치한다.
- bridge 상태를 앱 시작 시 확인할 수 있다.
- bridge down 시 실패가 조용히 묻히지 않고 HUD/로그/이벤트로 드러난다.
- 수동 검증 1회가 아니라, 최소 1개의 통합 테스트 또는 mock E2E 테스트가 존재한다.
- 실제 운영 시 `RIO app + ThinQ bridge` 기동 순서가 문서화되어 있다.

### 3.5 권장 우선순위

**3순위**

단, 실제 데모나 실기기 제어가 먼저 필요하다면 이 범주를 시나리오 추가보다 먼저 당겨도 된다.

---

## 4. 현재 병목이 되는 부분을 C++ 혹은 파이썬이 아닌 다른 언어로 구현해서 속도 증가

### 4.1 현재 상태

이 범주는 신중하게 접근해야 한다.

이미 네이티브인 부분:

- `faster-whisper`
  - 내부적으로 CTranslate2 기반
- OpenCV
- MediaPipe

즉, 지금 느린 부분을 무조건 "Whisper를 C++로 다시 짜면 해결" 같은 방식으로 접근하는 건 효율이 낮다.

현재 더 유력한 병목:

- Python 메인 루프에서 음성/비전/렌더링을 함께 돌리는 구조
- `drop_while_busy=true` 정책에 따른 음성 유실
- 낮은 mic gain 과 보수적 threshold
- preview / camera / gesture 처리와 ASR 이 CPU를 공유하는 점

### 4.2 우선 원칙

**언어 교체는 1차 해법이 아니라 3차 해법**으로 본다.

권장 순서:

1. 설정 튜닝
2. 프로세스/스레드 구조 분리
3. 그래도 부족하면 네이티브 워커 도입

### 4.3 구체 작업

#### A. 먼저 측정부터 한다

- 아래를 숫자로 남긴다.
  - 음성 decode 시간
  - frame loop 시간
  - face detect 시간
  - gesture detect 시간
  - preview draw 시간
  - CPU 사용률
  - 메모리 사용량
- 샌드박스와 live app 을 같은 문장 세트로 비교한다.

#### B. Python 구조 최적화 먼저 수행

- `live_*` 와 실제 앱에서 비전 FPS 를 낮춘다.
- preview off 모드를 더 적극적으로 쓴다.
- 음성 워커와 비전 워커의 tick 경합을 줄인다.
- 필요한 경우 프로세스 분리로 먼저 해결한다.

#### C. 네이티브화 후보를 좁힌다

네이티브화 우선 후보:

1. **오디오 캡처 + VAD 워커**
   - 이유: Python queue/callback 오버헤드가 있고, 실시간성이 중요함
   - 추천 언어: **Rust**
   - 결과물: sidecar 프로세스 또는 Python extension

2. **카메라 프레임 캡처 + 전처리**
   - 이유: 프레임 입출력과 색공간 변환이 잦음
   - 추천 언어: **C++ 또는 Rust**
   - 단, MediaPipe 자체가 이미 무거우므로 재작성 이득은 측정 후 판단

3. **이벤트 큐/링버퍼**
   - 이유: lock contention 과 불필요한 복사를 줄일 수 있음
   - 추천 언어: **Rust**

비추천 우선순위:

- Whisper 자체 재작성
- Smart-home HTTP 경로 재작성
- FSM / reducer 재작성

이 영역들은 현재 병목 대비 투자 대비 효과가 낮다.

#### D. 언어 선택 기준을 명확히 한다

추천 기준:

- **Rust**
  - 오디오/VAD/ring buffer 같은 실시간 워커에 적합
  - 배포 안정성이 높고 메모리 안전성이 좋음
- **C++**
  - OpenCV / MediaPipe / GStreamer 와 매우 강하게 붙일 때 적합
  - 단, 빌드/디버깅/크로스컴파일 부담이 큼
- **Go / Node.js / 기타**
  - 현재 문제 유형에는 우선 추천하지 않음
  - FFI/실시간 오디오/비전과의 결합 효율이 낮다

#### E. 목표 아키텍처 예시

중기 목표 예시는 아래처럼 잡을 수 있다.

```text
RIO Main (Python)
  - state, router, reducers, planners, executors

Voice Worker (Rust)
  - mic capture
  - VAD
  - optional wake-word front gate
  - transcript / intent candidate IPC

Vision Worker (Python or C++)
  - camera / mediapipe
  - face / gesture events
```

즉, 상태기계와 도메인 실행은 Python 에 남기고, 실시간 스트림 경로만 선택적으로 밖으로 뺀다.

### 4.4 완료 기준

- 병목 측정 결과가 문서로 남아 있다.
- "왜 이 부분을 네이티브화하는지" 가 수치로 설명된다.
- 1개 후보 워커를 PoC 로 분리해 전/후 지표를 비교했다.
- 개선 목표가 최소 하나는 숫자로 달성된다.
  - 예: `BUSY drop 50% 감소`
  - 예: `평균 ASR ready time 30% 감소`
  - 예: `live mode 에서 1초 미만 짧은 명령 인식률 상승`

### 4.5 권장 우선순위

**4순위**

이 범주는 반드시 1~3번을 어느 정도 정리한 뒤 시작하는 것이 좋다.

---

## 5. 권장 실행 순서

### 5.1 기본 권장 순서

1. `main.py` / 실제 앱 진입점 정리
2. 음성/비전 런타임 계측 및 설정 튜닝
3. ThinQ HTTP 운영 경로 완결
4. 시나리오 추가 구현
5. 병목 측정 후 네이티브화 PoC

### 5.2 데모 우선일 때의 순서

실기기 데모가 먼저라면 아래 순서도 가능하다.

1. `main.py` / 실제 앱 진입점 정리
2. ThinQ HTTP 연결 완료
3. 핵심 시나리오 3~5개만 우선 구현
4. 성능 최적화

---

## 6. 바로 다음 스프린트 권장 범위

다음 스프린트에서는 아래만 해도 효과가 크다.

### Sprint A

- 실제 앱 진입점 추가
- `voice.yaml` / runtime profile 분리
- voice/vision 성능 로그 계측
- `live_*` 에서 preview/off/FPS 기준 성능 비교

### Sprint B

- ThinQ bridge healthcheck
- smart-home 실패 코드 표준화
- `게임 모드` placeholder 제거
- `wave`, `finger_gun`, `peekaboo` 중 1개 액션 흐름 완성

### Sprint C

- 측정 결과를 바탕으로 Rust 기반 voice worker PoC 검토
- PoC 전/후 지표 비교

---

## 7. 한 줄 판단

지금은 **새 언어로 바로 옮기는 단계보다, 실제 앱 진입점 정리와 런타임 구조/계측 정리가 먼저**다.
그 다음에 ThinQ 운영 경로와 시나리오 구현을 닫고, 마지막으로 병목이 여전히 남는 부분만 선택적으로 네이티브화하는 것이 가장 효율적이다.
