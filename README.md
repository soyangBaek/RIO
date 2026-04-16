# RIO

RIO는 Raspberry Pi 위에서 동작하는 `desktop pet + smart-home hub` 프로젝트입니다.
이 저장소의 문서는 `감정형 반응`, `음성/비전 인터랙션`, `ThinQ 연동`을 하나의 구현 방향으로 맞추는 것을 목표로 합니다.

## 문서 기준

`[docs/prd.md](./docs/prd.md)`가 이 프로젝트의 기준 문서입니다.

- 기능 범위
- 구현 기준
- 명령 의도 체계
- 우선 구현 순서

위 항목에서 다른 문서와 충돌이 생기면 `prd.md`를 우선합니다.
`architecture.md`, `state-machine.md`, `project-layout.md`는 모두 `prd.md`를 구현 가능한 형태로 풀어쓴 파생 문서입니다.

## 고정된 구현 방향

이 저장소는 아래 기준으로 통일합니다.

- 플랫폼: `Raspberry Pi` 기반 Linux
- 하드웨어: `터치스크린`, `스피커`, `마이크`, `웹캠`
- 주 언어: `Python`
- 실행 구조: `main orchestrator + audio worker + vision worker`
- 핵심 방식: `event-driven + state-centered`
- 비전: `OpenCV + MediaPipe`
- 스마트홈 연동: `로컬 home-client`로 HTTP 요청 전달
- 화면: `로컬 3-layer face UI`

의도적으로 제외한 것:

- Jetson과 Raspberry Pi를 동시에 기준 플랫폼으로 두는 문서화
- React, Tkinter, PyQt 등 여러 UI 프레임워크를 동시에 기준으로 두는 문서화
- 명령어 문자열을 문서마다 다르게 하드코딩하는 방식
- 눈 방향 변화를 모터 제어로 전제하는 문서화
- 전용 터치 센서를 현재 기본 하드웨어처럼 전제하는 문서화

## 문서 목록

- [PRD / 기준 문서](./docs/prd.md)
- [Current Behaviors](./docs/current-behaviors.md)
- [Architecture](./docs/architecture.md)
- [State Machine](./docs/state-machine.md)
- [Scenario Catalog](./docs/scenarios.md)
- [Project Layout](./docs/project-layout.md)

## 현재 상태

기본 구조와 입력/반응 플로우는 구현되어 있으며, `scripts/live_interaction_test.py`로 현재 동작을 직접 검증할 수 있습니다.
실행 가능한 입력과 현재 반응은 [docs/current-behaviors.md](./docs/current-behaviors.md)에 정리되어 있습니다.
