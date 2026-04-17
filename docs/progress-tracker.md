# RIO 개발 진행 현황 (Progress Tracker)

> 기준일: 2026-04-17 | 기준 branch: `develop`

---

## 전체 요약

| 구분 | 진행률 | 비고 |
|------|--------|------|
| **MVP (M1)** | **100%** | 2026-04-15 게이트 통과 |
| **Phase 2 (M2)** | **~20%** | 제스처 감지만 구현, 게임 로직 미착수 |
| **테스트** | **90%** | MVP 시나리오 전수 커버, Phase 2 부분 커버 |
| **문서** | **100%** | PRD, Architecture, State-Machine, Scenarios, Project-Layout, Current-Behaviors |

---

## 1. 완료된 항목 (Done)

### 1.1 Core State Management
| 항목 | 파일 | 상태 |
|------|------|------|
| Context FSM (Away/Idle/Engaged/Sleepy) | `core/state/context_fsm.py` | Done |
| Activity FSM (Idle/Listening/Executing/Alerting) | `core/state/activity_fsm.py` | Done |
| Extended State (face presence, timestamps) | `core/state/extended_state.py` | Done |
| Reducers (Event → State 전이) | `core/state/reducers.py` | Done |
| Oneshot 이벤트 (startled/welcome/happy/confused) | `core/state/oneshot.py` | Done |
| Scene Selector (Mood + UI 파생) | `core/state/scene_selector.py` | Done |
| State/Action 데이터 모델 | `core/state/models.py` | Done |

### 1.2 Event System
| 항목 | 파일 | 상태 |
|------|------|------|
| QueueBus (이벤트 브로커) | `core/bus/queue_bus.py` | Done |
| Router (구독/발행) | `core/bus/router.py` | Done |
| 27개 Topic 정의 | `core/bus/topics.py` | Done |
| Event 모델 (메타데이터, 트레이싱) | `core/bus/models.py` | Done |

### 1.3 Workers
| 항목 | 파일 | 상태 |
|------|------|------|
| Audio Worker (마이크 폴링, VAD) | `workers/audio_worker.py` | Done |
| Vision Worker (카메라, 얼굴, 제스처) | `workers/vision_worker.py` | Done |
| Touch Worker (터치스크린 폴링) | `workers/touch_worker.py` | Done |

### 1.4 Input Adapters
| 항목 | 파일 | 상태 |
|------|------|------|
| 마이크 캡처 | `adapters/audio/capture.py` | Done |
| VAD (음성 활동 감지) | `adapters/audio/vad.py` | Done |
| STT (음성→텍스트) | `adapters/audio/stt.py` | Done |
| Terminal 입력 (테스트용) | `adapters/audio/terminal_input.py` | Done |
| Intent Normalizer | `adapters/audio/intent_normalizer.py` | Done |
| 카메라 스트림 | `adapters/vision/camera_stream.py` | Done |
| 얼굴 감지 (MediaPipe) | `adapters/vision/face_detector.py` | Done |
| 얼굴 추적 | `adapters/vision/face_tracker.py` | Done |
| 제스처 감지 | `adapters/vision/gesture_detector.py` | Done |
| 상호작용 추적 (재등장 감지) | `adapters/vision/interaction_tracker.py` | Done |
| 터치 입력 | `adapters/touch/input.py` | Done |
| 터치 제스처 매핑 | `adapters/touch/gesture_mapper.py` | Done |

### 1.5 Output Adapters
| 항목 | 파일 | 상태 |
|------|------|------|
| Pygame 렌더러 | `adapters/display/renderer.py` | Done |
| Face Compositor (표정 합성) | `adapters/display/face_compositor.py` | Done |
| 3-Layer UI (Core/Overlay/HUD) | `adapters/display/layers.py` | Done |
| Eye Tracking | `adapters/display/eye_tracking.py` | Done |
| HUD (상태 텍스트, 타이머) | `adapters/display/hud.py` | Done |
| SFX (효과음 8종) | `adapters/speaker/sfx.py` | Done |
| TTS placeholder | `adapters/speaker/tts.py` | Done |

### 1.6 Domain Services
| 항목 | 파일 | 상태 |
|------|------|------|
| Effect Planner | `domains/behavior/effect_planner.py` | Done |
| Executor Registry | `domains/behavior/executor_registry.py` | Done |
| Interrupt Policy | `domains/behavior/interrupts.py` | Done |
| Intent Parser (14개 정규 인텐트) | `domains/speech/intent_parser.py` | Done |
| Timer Parser (자연어 시간) | `domains/speech/timer_parser.py` | Done |
| Dedupe (중복 인텐트 필터) | `domains/speech/dedupe.py` | Done |
| Presence Signals | `domains/presence/signals.py` | Done |
| Presence Helpers | `domains/presence/helpers.py` | Done |
| Photo Service (카운트다운→촬영→저장) | `domains/photo/service.py` | Done |
| Timer Service (등록/만료/알림) | `domains/timers/service.py` | Done |
| Smart Home Service | `domains/smart_home/service.py` | Done |
| Smart Home Payloads | `domains/smart_home/payloads.py` | Done |
| Weather Client | `adapters/weather/client.py` | Done |
| Weather Normalizer | `adapters/weather/normalizer.py` | Done |
| Home Client (HTTP) | `adapters/home_client/client.py` | Done |

### 1.7 Orchestration
| 항목 | 파일 | 상태 |
|------|------|------|
| Main Orchestrator (이벤트 루프) | `main.py` | Done |

### 1.8 Infrastructure
| 항목 | 파일 | 상태 |
|------|------|------|
| Config (경로 해석) | `core/config.py` | Done |
| Timer Scheduler | `core/scheduler/timer_scheduler.py` | Done |
| Capabilities (HW 감지) | `core/safety/capabilities.py` | Done |
| Heartbeat Monitor | `core/safety/heartbeat_monitor.py` | Done |

### 1.9 Configuration & Assets
| 항목 | 상태 |
|------|------|
| robot.yaml (HW 스펙) | Done |
| thresholds.yaml (행동 타이밍) | Done |
| triggers.yaml (음성 트리거) | Done |
| devices.yaml (스마트홈 매핑) | Done |
| scenes.yaml (씬 타이밍/사운드) | Done |
| 표정 PNG 23종 | Done |
| 애니메이션 TXT 4종 | Done |
| 효과음 MP3 2종 | Done |
| UI 에셋 2종 | Done |

### 1.10 테스트
| 항목 | 상태 |
|------|------|
| 유닛 테스트 11개 | Done |
| 통합 테스트 5개 | Done |
| 시뮬레이션 테스트 3개 | Done |
| 라이브 인터랙션 테스트 | Done |
| 라이브 비전 테스트 | Done |
| Demo Reactions | Done |

### 1.11 시나리오 커버리지 (scenarios.md 기준)
| 시나리오 그룹 | 범위 | 상태 |
|--------------|------|------|
| SYS (시스템/프레즌스) | SYS-01 ~ SYS-11 | 11/11 Done |
| VOICE (음성 입력) | VOICE-01 ~ VOICE-19 | 19/19 Done |
| INT (인터랙션) | INT-01 ~ INT-11 | 11/11 Done |
| POL (정책/인터럽트) | POL-01 ~ POL-08 | 8/8 Done |
| ONE (원샷 네스팅) | ONE-01 ~ ONE-05 | 5/5 Done |
| SCN (씬 오버라이드) | SCN-01 ~ SCN-05 | 5/5 Done |
| OPS (장애/저하) | OPS-01 ~ OPS-07 | 7/7 Done |

---

## 2. 진행 중 / 부분 구현 (In Progress)

| 항목 | 현재 상태 | 남은 작업 |
|------|----------|----------|
| **제스처 감지 (Phase 2)** | 감지 로직 구현됨 (wave, finger_gun, v_sign, peekaboo, head_left/right) | 각 제스처별 반응 행동/씬 연결 미완 |
| **V-Sign → 사진 촬영** | 동작 확인됨 | Phase 2 시나리오 P2-05 정식 검증 필요 |
| **Scene Catalog** | 기본 씬 정의됨 (149줄) | 게임/제스처 전용 씬 추가 필요 |

---

## 3. 미착수 항목 (Not Started)

### 3.1 게임 로직 (Games) — Phase 2 핵심
| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **참참참 게임 로직** | 좌/우 방향 맞추기 승패 판정, 라운드 관리 | High |
| **빵야 (Finger Gun) 반응** | finger_gun 제스처 감지 → KO/리액션 시퀀스 | High |
| **숨바꼭질 (Peekaboo) 게임** | 얼굴 사라짐/재등장 기반 게임 규칙 | Medium |
| 게임 점수/상태 관리 | 연속 승리, 패배 카운트, 감정 변화 | Medium |

### 3.2 제스처 반응 확장
| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **Wave 제스처 반응** | 손 흔들기 → 인사 씬/애니메이션 | Medium |
| **Point 제스처 액션** | 감지됨, 행동 미정의 (화면 하이라이트? 방향 지시?) | Low |

### 3.3 음성 인식 개선
| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **음성 트리거 확장** | TV 끄기, 음악 정지 등 부족한 alias 추가 (triggers.yaml) | Medium |
| **Timer 자연어 확장** | "3시 30분", "2시간 후", 한국어 시간 표현 지원 | Medium |
| **실제 마이크 경로 안정화** | 현재 Terminal 입력이 더 안정적; 하드웨어 mic 경로 개선 | Low |

### 3.4 하드웨어 바인딩 (Raspberry Pi)
| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **실제 마이크 통합** | Pi 하드웨어에 맞는 오디오 드라이버 연결 | Medium |
| **물리 터치스크린 드라이버** | 디바이스 모델에 맞는 입력 드라이버 바인딩 | Medium |

### 3.5 추가 에셋
| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **게임 전용 표정** | 참참참/빵야/숨바꼭질 진행 중 표정 | High |
| **게임 효과음** | 승리/패배/라운드 시작 사운드 | High |
| **제스처 반응 애니메이션** | wave 인사, point 반응 등 | Medium |

---

## 4. 코드 규모

| 구분 | 파일 수 | 라인 수 |
|------|---------|---------|
| 소스 코드 (src/) | 63 | ~4,547 |
| 테스트 (tests/) | 22 | — |
| 스크립트 (scripts/) | 3 | ~2,400 |
| 문서 (docs/) | 6 | ~2,000 |
| 설정 (configs/) | 5 | — |
| 에셋 (assets/) | 60+ | — |

---

## 5. 다음 단계 권장 순서

```
1. [High] 게임 서비스 로직 구현 (참참참 → 빵야 → 숨바꼭질)
   └─ games/service.py 확장 + 승패 판정 + 씬 연결

2. [High] 게임 전용 에셋 추가 (표정 PNG + 효과음 MP3)
   └─ assets/expressions/, assets/sounds/

3. [Medium] 제스처 반응 행동 연결
   └─ gesture/mapper.py 확장 + effect_planner.py 반영

4. [Medium] 음성 트리거/타이머 파서 개선
   └─ triggers.yaml 업데이트 + timer_parser.py 확장

5. [Low/HW] 라즈베리파이 하드웨어 바인딩
   └─ 마이크 + 터치스크린 실제 디바이스 연결
```

---

*이 문서는 docs/ 디렉토리의 PRD, architecture, state-machine, scenarios, project-layout, current-behaviors와 실제 소스 코드를 대조하여 작성되었습니다.*
