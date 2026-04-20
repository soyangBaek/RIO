# 제스처 인식 개선 (2026-04-20)

> 작성일: 2026-04-20 (v_sign 손바닥 조건 추가분 포함)
> 작업 범위: 웹캠 제스처 인식 디버깅 도구 추가 / finger_gun → point 오분류 수정 / v_sign 손바닥 전용 분류
> 테스트 진입점: `D:/python/python.exe scripts/gesture_probe.py --device <N> --show-window`

---

## 요약

1. 제스처 인식률을 **오케스트레이터 없이** 웹캠만으로 테스트할 수 있는 독립 스크립트 추가
2. `GestureDetector`에 프레임별 디버그 스냅샷(`inspect()`) 추가
3. **엄지 판정 로직 교체** — 손이 기울거나 카메라 각도가 정면이 아닐 때 엄지가 감지되지 않아 `finger_gun`이 `point`로 오분류되던 문제 해결
4. **`v_sign`에 손바닥 방향 조건 추가** — 손등이 카메라를 향할 때는 `v_sign`으로 분류하지 않음

---

## 환경 사전 준비

### Python / 의존성

- 인터프리터: `D:/python/python.exe` (WindowsApps 스텁 사용 금지)
- 필수 패키지:
  ```bash
  D:/python/python.exe -m pip install opencv-python "mediapipe==0.10.14"
  ```

> ⚠️ **mediapipe 버전 주의**: 최신 `0.10.33` Windows wheel은 legacy `mp.solutions.hands` API를 제거한 Tasks 전용 빌드입니다. 현재 `GestureDetector`는 legacy API로 작성되어 있어 **0.10.14** 같은 구버전이 필요합니다. 향후 Tasks API로 마이그레이션은 별도 작업.

### USB 웹캠 사용

USB 웹캠 디바이스 인덱스 확인:
```bash
D:/python/python.exe scripts/gesture_probe.py --list-devices
```

출력 예:
```
  [0] OPEN  read_ok=True  640x480    ← 내장 카메라
  [1] OPEN  read_ok=True  1280x720   ← USB 웹캠
```

Windows에서는 `--backend dshow`(기본값)가 USB 웹캠에 안정적. MSMF가 필요하면 `--backend msmf`.

---

## 1. 신규 추가 파일: `scripts/gesture_probe.py`

### 목적
`RioOrchestrator`/FSM/렌더러/오디오 워커를 전부 건너뛰고 **웹캠 → `GestureDetector` → 콘솔 HUD**만 돌리는 독립 루프. `_classify_hand` 규칙 변경 시 즉시 피드백 확인용.

### 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--device N` | 0 | 웹캠 디바이스 인덱스 |
| `--list-devices` | - | 인덱스 0~7 프로빙 후 종료 |
| `--width` / `--height` | 640 / 480 | 캡처 해상도 |
| `--fps` | 15.0 | 루프 목표 FPS |
| `--confidence` | 0.75 | MediaPipe hand confidence 최소값 |
| `--cooldown` | 0.5 | 동일 제스처 재방출 간격 (초). 프로덕션 8초보다 짧게 기본값 설정 |
| `--show-window` | - | OpenCV 창에 손 랜드마크 오버레이 표시 (q로 종료) |
| `--backend` | `dshow` | Windows 캡처 백엔드 (`auto`/`dshow`/`msmf`) |
| `--log-file PATH` | - | 분류된 제스처를 CSV로 append |
| `--log-unemitted` | - | 쿨다운/confidence로 차단된 프레임도 로그에 포함 |

### HUD 출력 포맷

```
RIO Gesture Probe  (Ctrl+C to exit)
fps             : 14.8

hand_present    : True
fingers         : thumb=U index=U middle=. ring=. pinky=.
handedness      : Right  palm_facing=True
classified      : finger_gun  conf=1.00
emitted         : True
cooldown_remain : 0.42s

-- recent log (newest first) --
  * 14:32:47.123  finger_gun   conf=1.00  EMIT
    14:32:46.891  finger_gun   conf=1.00  seen
  * 14:32:45.004  v_sign       conf=1.00  EMIT

Known gestures: finger_gun, v_sign, wave, point   (* = emitted event)
```

- `fingers` 줄의 `U`는 extended, `.`은 접힘
- `*` 마크: 실제 이벤트 방출됨
- `seen`: 분류는 됐지만 쿨다운/confidence로 차단됨

### CSV 로그 포맷 (`--log-file`)

```
timestamp,gesture,confidence,emitted,fingers
2026-04-20T14:32:47.123+09:00,finger_gun,1.000,1,thumb=1|index=1|middle=0|ring=0|pinky=0
```

중복 방출은 동일 `(gesture, emitted)` 키가 연속되면 합쳐짐 (손을 유지하고 있을 때 로그 폭주 방지).

---

## 2. 수정 파일: `src/app/adapters/vision/gesture_detector.py`

### 2-1. 디버그 스냅샷 추가

- `GestureDetector._last_debug: dict` 필드 추가
- `detect()` 호출 시 매 프레임마다 다음 키를 채움:
  - `hand_present: bool` — MediaPipe가 손을 감지했는지
  - `fingers: {thumb, index, middle, ring, pinky} | None` — 5개 손가락 extended 여부
  - `classified: str | None` — 규칙 매칭 결과
  - `confidence: float`
  - `emitted: bool` — 실제 이벤트 방출되었는지
  - `cooldown_remaining: float` — 동일 제스처 재방출까지 남은 시간(초)
- 공개 메서드 `inspect() -> dict` 추가로 외부에서 읽기 전용 접근 가능
- **기존 `detect()`의 이벤트 방출 동작은 변경 없음** (사이드이펙트 없는 계측만 추가)

### 2-2. 엄지 판정 로직 교체 ★ 핵심 수정

#### 증상
`finger_gun` 자세(엄지 + 검지만 펴기)를 취해도 `point`로 분류되는 사례 다발.

#### 원인
기존 엄지 판정:
```python
thumb_extended = abs(lm[4].x - lm[2].x) >= 0.08
```
- **엄지 끝(`lm[4]`)과 엄지 뿌리(`lm[2]`)의 x축 거리**만 봄
- 손이 기울거나 엄지가 카메라 정면을 향하면 x 차이가 임계값 미달 → `thumb_extended = False`
- `finger_gun` 조건이 깨져서 `point` 조건(검지만 체크)에 걸림

#### 수정 후 로직 (`_thumb_extended(lm)`)
세 랜드마크(`wrist=lm[0]`, `mcp=lm[2]`, `ip=lm[3]`, `tip=lm[4]`)의 기하를 기반으로 **두 조건의 AND**로 판정:

**조건 1 — 각도 일치**
- `v1 = mcp - wrist` (손 전체 방향 벡터)
- `v2 = tip - ip` (엄지 말단 방향 벡터)
- `cos(angle(v1, v2)) > 0.5` → 두 벡터가 60° 이내로 같은 방향
- 엄지가 접히면 `v2`가 손쪽으로 꺾여 음수/작은 양수가 되어 fail

**조건 2 — 거리 순서**
- `dist(tip, mcp) > dist(ip, mcp)` → 끝이 중간보다 뿌리에서 멀리 있음
- 엄지가 말려들어가면 `tip`이 `mcp` 쪽으로 당겨져 fail

```python
@staticmethod
def _thumb_extended(lm: Any) -> bool:
    wrist, mcp, ip, tip = lm[0], lm[2], lm[3], lm[4]
    v1x, v1y = mcp.x - wrist.x, mcp.y - wrist.y
    v2x, v2y = tip.x - ip.x, tip.y - ip.y
    dot = v1x * v2x + v1y * v2y
    n1 = (v1x * v1x + v1y * v1y) ** 0.5
    n2 = (v2x * v2x + v2y * v2y) ** 0.5
    if n1 < 1e-6 or n2 < 1e-6:
        return False
    cos_angle = dot / (n1 * n2)
    tip_far = (
        ((tip.x - mcp.x) ** 2 + (tip.y - mcp.y) ** 2) ** 0.5
        > ((ip.x - mcp.x) ** 2 + (ip.y - mcp.y) ** 2) ** 0.5
    )
    return cos_angle > 0.5 and tip_far
```

#### 장점
- 손 기울기/카메라 각도에 덜 민감
- 왼손/오른손 무관 (절댓값/부호 의존 제거)
- x축 거리 의존 제거

#### 주의
- **검지/중지/약지/소지 판정은 변경하지 않음** (기존 `_is_extended`는 그대로 y좌표 비교). 보고된 증상이 엄지 한정이었고, 다른 손가락을 바꾸면 이미 잘 잡히던 `v_sign`/`wave`/`point`가 깨질 위험이 있어 수정 범위를 엄지로 한정.
- 임계값 `cos > 0.5` (60°)와 `tip_far`는 실측 기반 조정 가능. 너무 느슨하면 `point` 자세에서 엄지가 오탐될 수 있음 → 회귀 테스트 필요.

### 2-3. v_sign 손바닥 방향 조건 추가 ★ 신규 수정

#### 요구사항
`v_sign`은 **V 모양이 손바닥 쪽에서 보일 때만** 인식되어야 함. 손등이 카메라를 향한 상태에서 검지+중지만 펴면 기존엔 `v_sign`으로 분류됐으나, 이제는 분류되지 않도록 변경.

#### 신규 헬퍼: `_palm_facing_camera(lm, handedness_label)`

MediaPipe가 제공하는 두 정보를 조합:
- **landmark 좌표** — 엄지 끝(`lm[4]`)과 소지 MCP(`lm[17]`)의 x 위치
- **handedness 라벨** — `multi_handedness[0].classification[0].label` (`"Left"` / `"Right"`)

판정 규칙:

| handedness (MediaPipe 라벨) | 엄지(lm[4]) vs 소지 뿌리(lm[17]) x 비교 | 결과 |
|---|---|---|
| `Right` | 엄지 x < 소지 뿌리 x | 손바닥 ✓ |
| `Right` | 엄지 x > 소지 뿌리 x | 손등 ✗ |
| `Left`  | 엄지 x > 소지 뿌리 x | 손바닥 ✓ |
| `Left`  | 엄지 x < 소지 뿌리 x | 손등 ✗ |
| None / 기타 | — | 손등으로 간주(False) |

#### 코드 변경

```python
@staticmethod
def _palm_facing_camera(lm: Any, handedness_label: str | None) -> bool:
    thumb_x = lm[4].x
    pinky_mcp_x = lm[17].x
    if handedness_label == "Right":
        return thumb_x < pinky_mcp_x
    if handedness_label == "Left":
        return thumb_x > pinky_mcp_x
    return False
```

`_classify_hand` 시그니처 확장 (기본값 `None`으로 하위 호환 유지):
```python
def _classify_hand(self, hand_landmarks, handedness_label=None) -> str | None:
    ...
    palm_facing = self._palm_facing_camera(lm, handedness_label)
    ...
    # v_sign 조건에 palm_facing 추가 (다른 제스처는 영향 없음)
    if index_up and middle_up and not ring_up and not pinky_up and palm_facing:
        return "v_sign"
```

`detect()`에서 handedness를 실제로 추출:
```python
handedness_label = None
if result.multi_handedness:
    try:
        handedness_label = result.multi_handedness[0].classification[0].label
    except (AttributeError, IndexError):
        handedness_label = None
gesture = self._classify_hand(landmarks, handedness_label)
```

#### 디버그 스냅샷 확장
`inspect()` 결과에 두 키가 추가됨:
- `handedness: "Left" | "Right" | None`
- `palm_facing: bool`

#### 주의 & 엣지 케이스

- **MediaPipe 좌표계 기준 판정** — 이미지 flip(거울 모드) 여부와 무관하게 일관. 단, 일반 웹캠은 셀피와 반대 방향이라 MediaPipe가 "Right"로 라벨링한 손이 **실제 사용자 입장에선 왼손**일 수 있음. 판정 로직은 MediaPipe 라벨 기준으로 짜여있어 이 점은 자동 정합됨.
- **handedness가 None인 경우** — 판정 실패로 간주하여 `v_sign` 불가. `max_num_hands=1` 세팅이라 손이 검출되면 일반적으로 handedness도 같이 나옴.
- **엄지를 접은 채 V** — 엄지 landmark는 접혀있어도 `lm[4]` 좌표 자체는 존재하므로 판정 가능. 다만 엄지가 손바닥 안쪽으로 깊이 말려들어가면 x 좌표가 소지 뿌리 근처로 붙어 오판 가능성 있음 → 실측에서 경계 사례 발견 시 임계 마진 추가 검토.
- **다른 제스처(`finger_gun`/`wave`/`point`)는 palm_facing 조건 없음** — V-sign은 손바닥/손등 의미가 다른 제스처(Peace vs F-word)지만, 나머지는 방향 무관하게 동일 의미로 쓰이므로 제한 없음.

---

## 3. `scripts/live_vision_state_test.py` 변경

- `--debug-gesture` 플래그: HUD에 `gesture debug` 섹션(손가락 상태/분류/쿨다운) 매 프레임 갱신
- `--gesture-cooldown <초>`: `GestureDetector.emit_cooldown_seconds`를 런타임에 덮어쓰기 (기본 8초는 반복 테스트에 불편)

---

## 테스트 시나리오

### A. 회귀 (기존 제스처가 깨지지 않았는지)

각 제스처를 **정면 / 15° 기울임 / 30° 기울임** 세 각도로 시도:

```bash
D:/python/python.exe scripts/gesture_probe.py --device 1 --show-window --log-unemitted --log-file logs/regression.csv
```

확인 포인트:
- `v_sign` (손바닥 V): `fingers=thumb=? index=U middle=U ring=. pinky=.` + `palm_facing=True` → `classified: v_sign` ★ 신규 조건
- `v_sign` (손등 V): 위와 동일한 손가락 상태 + `palm_facing=False` → `classified: None` (의도적으로 미분류)
- `wave`: `fingers=thumb=? index=U middle=U ring=U pinky=U` → `classified: wave`
- `point`: `fingers=thumb=. index=U middle=. ring=. pinky=.` → `classified: point` (엄지는 반드시 `.`)
- `finger_gun`: `fingers=thumb=U index=U middle=. ring=. pinky=.` → `classified: finger_gun` ★ 수정 포인트

### B. finger_gun 각도 스위프 (수정 타겟)

`finger_gun` 자세에서 손목 각도를 0° → 45° → 90°로 돌려가며 HUD의 `thumb`이 `U`로 유지되는지 확인. CSV에 `emitted=1`으로 연속 기록되면 성공.

### C. point 오탐 체크

`point` 자세(엄지는 주먹 안으로 완전히 접음)에서 **`fingers` 줄의 `thumb`이 `.`으로 나오는지** 확인. `U`로 오탐되면 `cos_angle > 0.5` 임계값을 0.6~0.7로 올려야 함.

### D. v_sign 손바닥/손등 구분 (신규 조건)

동일한 V 손 모양을 **손바닥 방향 / 손등 방향**으로 교대 시전:

- **손바닥 V**: `palm_facing=True` + `classified: v_sign` + `emitted: True` (쿨다운 허용 시)
- **손등 V**: `palm_facing=False` + `classified: None` (분류 자체가 안 됨)

만약 손바닥인데도 `palm_facing=False`로 잡히거나 그 반대면 `handedness` 라벨이 기대와 반대인 상황 → `_palm_facing_camera`의 비교 방향 재확인 필요. 일반 웹캠은 MediaPipe에 raw(비-flip) 이미지를 넣기 때문에 MediaPipe가 말하는 "Right"는 사용자 관점의 왼손일 수 있는데, 이는 정상 동작이며 판정 로직은 MediaPipe 라벨 기준으로 짜여 있어 자동 정합됨.

---

## 롤백 방법

```bash
git diff src/app/adapters/vision/gesture_detector.py
git checkout -- src/app/adapters/vision/gesture_detector.py
```

`gesture_probe.py`는 신규 파일이라 그대로 두거나 삭제:
```bash
git rm scripts/gesture_probe.py
```

---

## 후속 작업 (별도 수정 요청으로 분리)

- [ ] `_is_extended`(검지/중지/약지/소지)도 각도 기반으로 교체하여 손 기울기 robust화
- [x] ~~MediaPipe `handedness`(left/right) 활용~~ — v_sign 손바닥/손등 구분에 적용 완료 (2-3 참고)
- [ ] `confidence`를 1.0/0.0 이진이 아닌 MediaPipe detection score와 연동
- [ ] 녹화 영상 기반 회귀 테스트 하네스 (`tests/fixtures/gestures/*.mp4` + precision/recall 산출 스크립트)
- [ ] mediapipe 0.10.33+ Tasks API 마이그레이션
