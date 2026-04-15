# RIO 프로젝트 Tasklist

## Context

RIO는 Raspberry Pi 기반 `desktop pet + smart-home hub` 프로젝트로, `docs/`의 5개 문서(`prd.md`, `architecture.md`, `state-machine.md`, `scenarios.md`, `project-layout.md`)가 완전히 작성되어 있고 `src/app/` 이하 디렉터리 트리는 `.gitkeep`만 있는 **빈 스켈레톤 상태**입니다. 지금은 구현을 시작하기 전 단계로, 문서 전체를 코드로 번역하기 위한 **실행 가능한 태스크 목록(tasklist)**을 만드는 것이 목표입니다.

사용자 결정 사항:
- 저장 경로: `/home/willtek/.claude/tasks/`
- JSON 구조: **태스크당 1파일** (`NNN_<module>_<file>.json`)
- 언어 전략: **Python 올-인** (architecture §8.3 근거). 비-Python은 `language_notes` 필드에 Phase 3+ 최적화 후보로만 기록
- 세분화: **파일 단위** (project-layout의 `권장 초기 파일` 각각이 1태스크)
- 이번 턴 범위: **tasklist 작성만**, 구현은 별도 지시 있을 때까지 금지

## Tasklist 스키마 (task-per-file JSON)

각 태스크 JSON 파일은 다음 필드를 가집니다:

```json
{
  "id": "T-003",
  "title": "Event bus queue implementation",
  "phase": 1,
  "language": "python",
  "targetdir": "src/app/core/bus/",
  "target_file": "src/app/core/bus/queue_bus.py",
  "dependencies": ["T-001", "T-002"],
  "source_docs": [
    "docs/architecture.md §3",
    "docs/project-layout.md §5.bus"
  ],
  "description": "multiprocessing.Queue 기반 이벤트 버스. 워커 프로세스 → 메인 오케스트레이터 단방향 이벤트 전달. publish/subscribe 인터페이스 제공.",
  "responsibilities": [
    "Event envelope 큐잉",
    "워커 생존 감시와 연동될 수 있는 노출",
    "bounded queue (overflow 정책 문서화)"
  ],
  "acceptance_criteria": [
    "단위 테스트에서 publish→poll 사이클이 1ms 이내 반환",
    "큐 overflow 시 drop_oldest 정책 적용"
  ],
  "language_notes": "Python multiprocessing.Queue로 시작. Phase 3+ 지연 민감 시 Rust+PyO3 교체 후보.",
  "estimated_effort": "S"
}
```

- `id`: `T-NNN` (zero-padded, 전역 고유)
- `phase`: architecture §9의 구현 순서 단계 (1~7) 또는 8(tests) / 9(entry) / 10(configs)
- `language`: 현재는 모두 `python`. 장래 재검토용 `language_notes`로 구분
- `targetdir`: 상대 경로 (프로젝트 루트 기준)
- `dependencies`: 선행 태스크의 `id` 배열. DAG로 해석
- `estimated_effort`: S(≤0.5일) / M(0.5~2일) / L(>2일)

## 태스크 전체 목록 (76개)

### Phase 1 — Core Infrastructure (15 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-001 | src/app/core/events/models.py | — | S |
| T-002 | src/app/core/events/topics.py | T-001 | S |
| T-003 | src/app/core/bus/queue_bus.py | T-001,T-002 | M |
| T-004 | src/app/core/bus/router.py | T-003 | M |
| T-005 | src/app/core/state/models.py | T-001 | S |
| T-006 | src/app/core/state/store.py | T-005 | S |
| T-007 | src/app/core/state/extended_state.py | T-005,T-006 | M |
| T-008 | src/app/core/state/context_fsm.py | T-005 | M |
| T-009 | src/app/core/state/activity_fsm.py | T-005 | M |
| T-010 | src/app/core/state/oneshot.py | T-005,T-006 | M |
| T-011 | src/app/core/state/scene_selector.py | T-005 | M |
| T-012 | src/app/core/state/reducers.py | T-007,T-008,T-009,T-010,T-011 | L |
| T-013 | src/app/core/scheduler/timer_scheduler.py | T-003 | M |
| T-014 | src/app/core/safety/heartbeat_monitor.py | T-003 | M |
| T-015 | src/app/core/safety/capabilities.py | — | S |

### Phase 2 — Basic Adapters (display / touch / speaker) (8 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-016 | src/app/adapters/display/layers.py | — | M |
| T-017 | src/app/adapters/display/eye_tracking.py | T-016 | M |
| T-018 | src/app/adapters/display/hud.py | T-016 | M |
| T-019 | src/app/adapters/display/renderer.py | T-016,T-017,T-018 | L |
| T-020 | src/app/adapters/touch/input.py | T-001 | M |
| T-021 | src/app/adapters/touch/gesture_mapper.py | T-020 | M |
| T-022 | src/app/adapters/speaker/sfx.py | — | S |
| T-023 | src/app/adapters/speaker/tts.py | — | M |

### Phase 3 — Domain Logic (presence / speech / behavior) (8 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-024 | src/app/domains/presence/signals.py | T-007 | S |
| T-025 | src/app/domains/presence/helpers.py | T-024 | S |
| T-026 | src/app/domains/speech/intent_parser.py | — | M |
| T-027 | src/app/domains/speech/timer_parser.py | — | M |
| T-028 | src/app/domains/speech/dedupe.py | T-001 | S |
| T-029 | src/app/domains/behavior/interrupts.py | T-012 | M |
| T-030 | src/app/domains/behavior/effect_planner.py | T-011,T-012 | L |
| T-031 | src/app/domains/behavior/executor_registry.py | T-030 | M |

### Phase 4 — Feature Services (photo / timers / smart_home) (4 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-032 | src/app/domains/photo/service.py | T-031 | M |
| T-033 | src/app/domains/timers/service.py | T-013,T-031 | M |
| T-034 | src/app/domains/smart_home/payloads.py | — | S |
| T-035 | src/app/domains/smart_home/service.py | T-034,T-031 | M |

### Phase 5 — Peripheral Adapters (audio / vision / camera / weather / home_client) (14 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-036 | src/app/adapters/audio/capture.py | — | M |
| T-037 | src/app/adapters/audio/vad.py | T-036 | M |
| T-038 | src/app/adapters/audio/stt.py | T-037 | L |
| T-039 | src/app/adapters/audio/intent_normalizer.py | T-026 | M |
| T-040 | src/app/adapters/vision/camera_stream.py | — | M |
| T-041 | src/app/adapters/vision/face_detector.py | T-040 | L |
| T-042 | src/app/adapters/vision/face_tracker.py | T-041 | M |
| T-043 | src/app/adapters/vision/gesture_detector.py | T-040 | L |
| T-044 | src/app/adapters/camera/storage.py | — | S |
| T-045 | src/app/adapters/camera/capture.py | T-044 | M |
| T-046 | src/app/adapters/weather/normalizer.py | — | S |
| T-047 | src/app/adapters/weather/client.py | T-046 | M |
| T-048 | src/app/adapters/home_client/mapper.py | — | S |
| T-049 | src/app/adapters/home_client/client.py | T-048 | M |

### Phase 6 — Workers (2 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-050 | src/app/workers/audio_worker.py | T-003,T-036,T-037,T-038,T-039 | L |
| T-051 | src/app/workers/vision_worker.py | T-003,T-040,T-041,T-042,T-043 | L |

### Phase 7 — Gesture / Games / Scenes (6 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-052 | src/app/domains/gesture/catalog.py | — | S |
| T-053 | src/app/domains/gesture/mapper.py | T-052,T-043 | M |
| T-054 | src/app/domains/games/service.py | T-031 | M |
| T-055 | src/app/scenes/assets.py | — | S |
| T-056 | src/app/scenes/builders.py | T-055 | M |
| T-057 | src/app/scenes/catalog.py | T-055,T-056 | M |

### Phase 8 — Entry Point (1 task)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-058 | src/app/main.py | T-004,T-012,T-014,T-019,T-029,T-031,T-050,T-051 | L |

### Phase 9 — Tests (13 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-059 | tests/unit/test_context_fsm.py | T-008 | S |
| T-060 | tests/unit/test_activity_fsm.py | T-009 | S |
| T-061 | tests/unit/test_oneshot.py | T-010 | M |
| T-062 | tests/unit/test_scene_selector.py | T-011 | M |
| T-063 | tests/unit/test_intent_parser.py | T-026 | S |
| T-064 | tests/unit/test_timer_parser.py | T-027 | S |
| T-065 | tests/integration/test_voice_to_execution.py | T-058 | L |
| T-066 | tests/integration/test_photo_sequence.py | T-032 | M |
| T-067 | tests/integration/test_smart_home_flow.py | T-035 | M |
| T-068 | tests/integration/test_weather_lookup.py | T-047 | M |
| T-069 | tests/simulation/face_event_replay.py | T-003 | M |
| T-070 | tests/simulation/transcript_injection.py | T-003 | M |
| T-071 | tests/simulation/long_scenario_playback.py | T-069,T-070 | L |

### Phase 10 — Configs (YAML 실제 값 채우기) (5 tasks)

| id | target_file | deps | effort |
|----|-------------|------|--------|
| T-072 | configs/robot.yaml | — | S |
| T-073 | configs/thresholds.yaml | — | S |
| T-074 | configs/triggers.yaml | T-026 | S |
| T-075 | configs/devices.yaml | — | S |
| T-076 | configs/scenes.yaml | T-010 | S |

## 의존성 분석 요약

### 크리티컬 패스 (가장 긴 체인)
`T-001 → T-005 → T-007/T-008/T-009/T-010/T-011 → T-012 → T-030 → T-031 → {T-032/T-033/T-035/T-054} → T-058 → T-065`

### 핵심 병목 태스크
- **T-012** (reducers.py): 5개 FSM/oneshot/selector 파일 통합. 여기서 잘못되면 전체 행동이 어긋남
- **T-030** (effect_planner.py): 모든 도메인 실행 정책의 진입점
- **T-031** (executor_registry.py): photo/timers/smart_home/games 모두 여기를 통해 연결
- **T-058** (main.py): 워커/버스/상태/렌더러를 하나의 프로세스로 묶는 최종 조립

### 병렬화 가능 구간
- Phase 1 내부: T-008, T-009, T-011, T-015는 T-005 완료 후 서로 독립적
- Phase 2/3/5는 phase 간 독립적인 서브트리가 많아 동시 진행 가능
- Phase 5의 5개 adapter 서브그룹(audio/vision/camera/weather/home_client)은 서로 독립

### 외부 의존성 (코드 외부)
- Python 3.8+, PyYAML, OpenCV, MediaPipe, PyAudio류, 선택 STT(Whisper/Google), PyGame 또는 Pillow (디스플레이 프레임워크 미결정 — 태스크 T-016 수행 시 결정 항목으로 명시)
- Weather API 키 / Home-client 엔드포인트 / RPi 하드웨어 (웹캠/마이크/터치스크린)
- 선택 사항은 각 태스크 JSON의 `description`과 `acceptance_criteria`에 기록

### 언어 재검토 후보 (Python 올-인 유지, 참고용)
- T-041/T-042/T-043 (vision): RPi CPU 부족 시 C++/OpenCV 네이티브 교체 후보
- T-037/T-038 (audio VAD/STT): 지연 민감 시 Rust+PyO3 교체 후보
- T-019 (renderer): 60fps 미달 시 SDL2 기반 C 래퍼 고려
모두 각 태스크의 `language_notes` 필드에 기재 (현재 `language: python` 유지).

## 산출물

1. **디렉터리 생성**: `/home/willtek/.claude/tasks/rio/` (프로젝트별 서브디렉터리로 격리)
2. **INDEX.json**: 전체 태스크 요약 + 의존성 DAG. 툴/사람이 훑어볼 때 사용
   - 필드: `project`, `generated_at`, `total_tasks`, `phases[]`, `critical_path[]`, `tasks[] (id/title/phase/target_file/deps 요약)`
3. **태스크 JSON 76개**: `T-001_core_events_models.json` ~ `T-076_configs_scenes.json`
   - 파일명 규칙: `<id>_<path-slug>.json` (path-slug는 target_file에서 `/`→`_`, 확장자 제거)

## 중요 파일 (Critical Files to Reference)

- `/home/willtek/Project/RIO/docs/prd.md` — 기능 요구
- `/home/willtek/Project/RIO/docs/architecture.md` — 런타임 구조, §8.3 언어 선택 근거, §9 구현 순서
- `/home/willtek/Project/RIO/docs/state-machine.md` — FSM 전이, oneshot 정책
- `/home/willtek/Project/RIO/docs/scenarios.md` — 수용 테스트 기준 (SYS/VOICE/INT/POL/ONE/OPS)
- `/home/willtek/Project/RIO/docs/project-layout.md` — 파일 매핑
- `/home/willtek/Project/RIO/configs/thresholds.yaml` — 이미 기본값 존재, T-073에서 검증만
