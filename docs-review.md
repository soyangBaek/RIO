# RIO 문서 리뷰 - 개선 필요 사항

대상 문서: [docs/prd.md](docs/prd.md), [docs/architecture.md](docs/architecture.md), [docs/project-layout.md](docs/project-layout.md), [docs/state-machine.md](docs/state-machine.md)

## 1. 문서 간 불일치

### 1.1 프로세스 책임 경계 불명확
- [prd.md:44-47](docs/prd.md#L44-L47), [architecture.md:41-45](docs/architecture.md#L41-L45)에서 `Main Orchestrator + Audio Worker + Vision Worker` 3프로세스로 고정.
- 그러나 [architecture.md:54-59](docs/architecture.md#L54-L59) 플로우차트의 `Touchscreen / Timer` 블록이 어느 프로세스에 속하는지 명시 없음.
- **보완**: 터치/타이머/네트워크 응답 이벤트의 실행 위치(메인 프로세스 내부 모듈인지 별도 워커인지)를 architecture.md에 명시.

### 1.2 MVP 게임 모드 범위 공백
- [prd.md:76-86](docs/prd.md#L76-L86) MVP에 "게임 모드 UI 전환" 포함.
- 실제 게임 콘텐츠(핑퐁, 갤로그, 참참참)는 [project-layout.md:276-280](docs/project-layout.md#L276-L280)에만 존재.
- [prd.md:88-95](docs/prd.md#L88-L95) Phase 2에는 "게임 콘텐츠 확장"만.
- **보완**: MVP 단계에서 게임 모드 진입 시 표시할 최소 콘텐츠(예: 게임 선택 placeholder UI) 정의.

### 1.3 Presence FSM 전이 경로 누락
- [state-machine.md:21-32](docs/state-machine.md#L21-L32) 다이어그램에 `FaceVisible → ReappearedWindow` 직행 경로 없음.
- `FaceLost` vs `SleepyAbsence`에서 재등장 시 Behavior 반응 강도(단순 반김 vs 깜짝+반김) 차이 규칙 없음.
- **보완**: 재등장 반응 강도를 Presence 이전 상태에 따라 분기하는 규칙을 state-machine.md에 추가.

## 2. 누락된 규격

### 2.1 설정 파일 스키마 부재
- [project-layout.md:76-113](docs/project-layout.md#L76-L113)에 `configs/*.yaml` 항목 나열만 존재.
- 실제 키 이름, 단위(초/ms), 기본값 예시 없음.
- 특히 `thresholds.yaml`의 `face lost timeout`, `sleepy timeout`, `reappeared window duration`은 상태머신 동작의 핵심인데 수치 없음.
- **보완**: 각 yaml의 스키마와 기본값을 문서 또는 샘플 파일로 제공.

### 2.2 이벤트 토픽 전체 목록 부재
- [architecture.md:93-99](docs/architecture.md#L93-L99)에 예시 일부만.
- `timer.expired`, `smarthome.result`, `task.*`, `ui.state.changed` 등 전체 topic 네이밍 규칙과 목록이 한 곳에 없음.
- **보완**: architecture.md에 모든 topic을 나열한 표 추가(도메인.객체.동사 네이밍 규칙 포함).

### 2.3 Intent 실패/미인식 경로 미정의
- confidence 낮은 STT 결과, 알 수 없는 intent, 중복 intent(댄스 중 다시 "춤춰") 처리 규칙 없음.
- **보완**: speech 도메인의 fallback intent(`intent.unknown`, `intent.low_confidence`)와 Behavior 반응 규칙 정의.

### 2.4 좌표계/해상도 규격
- [architecture.md:162](docs/architecture.md#L162) display adapter가 face center를 애니메이션 입력으로 받음.
- 정규화 좌표계([-1, 1])인지 픽셀인지 미정의.
- **보완**: vision 이벤트 payload의 좌표 규격을 architecture.md 이벤트 계약에 명시.

### 2.5 로그/디버그 채널
- [architecture.md:217](docs/architecture.md#L217) `trace_id`만 언급.
- 로깅 레벨, 파일 위치, 시뮬레이션 이벤트 재생 포맷([project-layout.md:322-325](docs/project-layout.md#L322-L325)) 구체 스펙 없음.
- **보완**: 로그 포맷/레벨/출력 위치와 시뮬레이션용 이벤트 JSON 스키마 정의.

### 2.6 부팅/종료 시퀀스
- 워커 기동 순서, 헬스체크 방식, `safety/` 모듈의 degraded mode 트리거 조건([project-layout.md:179-183](docs/project-layout.md#L179-L183)) 서술만 존재.
- **보완**: architecture.md에 기동 시퀀스와 degraded mode 전이 표 추가.

### 2.7 보안/개인정보 정책
- 카메라/마이크 원본 저장 정책, 사진 보존 기간, `HOME_CLIENT_IP` 설정 방식 미정의.
- **보완**: PRD 또는 별도 섹션에 데이터 보존/네트워크 설정 정책 추가.

## 3. 사소한 개선

### 3.1 intent 표의 `ui.game_mode.exit` 부재
- [prd.md:107-118](docs/prd.md#L107-L118) intent 표에 진입(`ui.game_mode.enter`)만 있고 퇴장 intent 없음.

### 3.2 비결정적 규칙 문장
- [prd.md:152](docs/prd.md#L152) "손 흔들기 → slow blink 또는 인사"의 "또는"이 구현 기준 문서에 부적절.
- **보완**: 결정 규칙(예: 이전 반응 쿨다운 기준)으로 명시.

### 3.3 상태 저장소 자료구조 미정의
- [state-machine.md:180](docs/state-machine.md#L180) `pending_tasks`가 list인지 map인지, 동시 실행 한도 미정의.
- **보완**: 각 상태 필드의 타입과 제약을 표로 정리.

### 3.4 문서 간 상호 링크 부재
- PRD에서 "자세한 전이는 state-machine.md §3 참고" 같은 참조가 없어 탐색성 낮음.
- **보완**: 각 문서에서 관련 섹션 앵커 링크 추가.

## 4. 우선 보완 순서

1. `thresholds.yaml` 기본값 정의 (2.1)
2. 이벤트 토픽 전체 목록 (2.2)
3. 프로세스-책임 경계 명시 (1.1)
4. Intent 실패 경로 (2.3)
5. 좌표계 규격 (2.4)

이 다섯 개가 먼저 정리되지 않으면 구현 시작 시 즉각적인 해석 충돌이 발생합니다.
