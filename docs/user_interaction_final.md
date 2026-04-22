# RIO 사용자 인터랙션 종합 정리

> 사용자(User) 관점에서의 모든 Input → Output 정리

---

## 1. 음성 명령 (Voice Commands)

### 1.1 스마트홈 제어

| 사용자 발화 (Input) | 로봇 반응 (Output) |
|---|---|
| "에어컨 켜줘" | 에어컨 ON → 기쁜 표정 + 성공 효과음 (`pride-emote.mp3`) + HUD "Control OK" |
| "에어컨 꺼줘" | 에어컨 OFF → 기쁜 표정 + 성공 효과음 + HUD "Control OK" |
| "난방 켜줘" | 난방 ON → 기쁜 표정 + 성공 효과음 |
| "난방 꺼줘" | 난방 OFF → 기쁜 표정 + 성공 효과음 |
| "거실 등 켜줘" | 거실 등 ON → 기쁜 표정 + 성공 효과음 |
| "거실 등 꺼줘" | 거실 등 OFF → 기쁜 표정 + 성공 효과음 |
| "간접등 켜줘" | 간접등 ON → 기쁜 표정 + 성공 효과음 |
| "간접등 꺼줘" | 간접등 OFF → 기쁜 표정 + 성공 효과음 |
| "티비 켜줘" | TV ON → 기쁜 표정 + 성공 효과음 |
| "티비 꺼줘" | TV OFF → 기쁜 표정 + 성공 효과음 |
| "컴퓨터 켜줘" | 컴퓨터 ON → 기쁜 표정 + 성공 효과음 |
| "컴퓨터 꺼줘" | 컴퓨터 OFF → 기쁜 표정 + 성공 효과음 |
| "청소기 돌려줘" | 로봇청소기 시작 → 기쁜 표정 + 성공 효과음 |
| "청소기 정지" | 로봇청소기 정지 → 기쁜 표정 + 성공 효과음 |
| "공기청정기 켜줘" | 공기청정기 ON → 기쁜 표정 + 성공 효과음 |
| "공기청정기 꺼줘" | 공기청정기 OFF → 기쁜 표정 + 성공 효과음 |
| "음악 틀어줘" | 스피커 재생 → 기쁜 표정 + 성공 효과음 |
| "음악 꺼줘" | 스피커 정지 → 기쁜 표정 + 성공 효과음 |
| "다 꺼줘" | 전체 기기 OFF → 성공 효과음 |

**실패 시**: 혼란 표정 (`smarthome_fail.png`) + 에러 효과음 (`surprise-emote.mp3`) + HUD "Control failed" + TTS 실패 메시지

---

### 1.2 사진 촬영

| 사용자 발화 (Input) | 로봇 반응 (Output) |
|---|---|
| "사진 찍어줘" | 얼굴 → `photo_ready.png` → 3-2-1 카운트다운 → 셔터 효과음 (`camera_shutter.mp3`) → `photo_cute.png` (0.9초) → HUD "Photo saved" → TTS "Photo taken." |

- 촬영 중 UI가 `CameraUI`로 전환됨
- **촬영 중에는 "멈춰줘"/"확인" 외 모든 명령 무시**
- 촬영 중 타이머 만료 시 → 촬영 완료 후 알림 재생

---

### 1.3 타이머

| 사용자 발화 (Input) | 로봇 반응 (Output) |
|---|---|
| "5분 뒤에 알려줘" | 타이머 등록 → 효과음 (`timer_ring.mp3`) + HUD "Timer set: 5 min" |
| "30초 뒤에 알려줘" | 타이머 등록 → 효과음 + HUD "Timer set: 30s" |
| (타이머 만료 시) | 알림 상태 진입 → 알림 표정 + `AlertUI` + 효과음 (`timer_ring.mp3`) + HUD "Timer done" + TTS "{라벨} time is up." |
| "확인" (알림 중) | 알림 해제 → Idle로 복귀 |

**주의**: "N분/초 뒤에 알려줘" 형식이어야 함. 시간 값 누락 시 혼란 표정 표시.

---

### 1.4 날씨

| 사용자 발화 (Input) | 로봇 반응 (Output) |
|---|---|
| "날씨 알려줘" | Open-Meteo API 호출 → 얼굴 `robot_right.png` + 날씨 아이콘 오버레이 (6초) + 효과음 (`flourish-emote-animal-crossing.mp3`). TTS 없음 |

**날씨 아이콘 매핑**:
| 날씨 | 아이콘 |
|---|---|
| 맑음 (WMO 0-1) | ☀ 회전하는 태양 |
| 흐림 (WMO 2-3) | ☁ 회색 구름 |
| 안개 (WMO 45, 48) | 🌫 물결 모양 |
| 비 (WMO 51-67, 80-82) | 🌧 구름 + 빗방울 |
| 눈 (WMO 71-77, 85-86) | ❄ 구름 + 회전하는 눈송이 |
| 천둥 (WMO 95, 96, 99) | ⚡ 구름 + 번개 |

**실패 시**: 혼란 표정 + 에러 효과음 + HUD "Weather failed"

---

### 1.5 춤

| 사용자 발화 (Input) | 로봇 반응 (Output) |
|---|---|
| "춤춰줘" | 댄스 음악 10초 재생 (`dance.mp3`) + 얼굴 `dance_face.png` + RGB 색상 플래시 오버레이 (빨강→초록→파랑, 0.5초 주기) |
| "멈춰줘" (춤 중) | 음악 중지 → Idle 복귀 |

---

### 1.6 게임 모드

| 사용자 발화 (Input) | 로봇 반응 (Output) |
|---|---|
| "게임 모드" | UI → `GameUI` + 얼굴 `wet_tear.png` + 효과음 (`pride-emote.mp3`) + HUD "Game mode ready" + TTS "Entering game mode." |
| "멈춰줘" (게임 중) | 일반 모드로 복귀 |

---

### 1.7 시스템 명령

| 사용자 발화 (Input) | 상황 | 로봇 반응 (Output) |
|---|---|---|
| "멈춰줘" | 대기/듣기 중 | 조용히 Idle로 복귀 |
| "멈춰줘" | 춤/게임 중 | 현재 모드 종료 → Idle 복귀 |
| "확인" / "알겠어" | 알림 중 | 알림 해제 → Idle 복귀 |

---

### 1.8 음성 인식 실패

| 상황 (Input) | 로봇 반응 (Output) |
|---|---|
| 발음 불명확 / STT 신뢰도 < 0.6 | 혼란 표정 (`confused.png`) + HUD "Didn't catch that" → Idle 복귀 |
| 인식할 수 없는 문장 (의도 매칭 실패) | 동일한 혼란 반응 |
| 목소리가 너무 작음 (VAD 미작동) | 반응 없음 |
| VAD 작동 후 무음 타임아웃 | 조용히 Idle 복귀 |

---

## 2. 제스처 (Gesture Interactions)

### 2.1 손 제스처 (MediaPipe 기반)

| 제스처 (Input) | 인식 조건 | 로봇 반응 (Output) |
|---|---|---|
| **손 흔들기 (Wave)** | 4개 손가락 펼침 | 인사 반응: `welcome.png` + 효과음 (`pleased-emote.mp3`) + HUD "Hello!" + TTS "Hello!" |
| **손가락 총 (Finger Gun)** | 엄지+검지 펼침 | 놀람 반응: `startled.png` + 효과음 (`shocked-emote.mp3`) + HUD "Bang!" + TTS "Bang!" |
| **V 사인 (V-Sign)** | 검지+중지 펼침, 손바닥 정면 | 사진 촬영 시작 (="사진 찍어줘"와 동일) → 카운트다운 → 셔터 |
| **주먹 (Fist)** | 모든 손가락 접음 | 화남 반응: `angry_idle` ↔ `angry_talking` 0.5초 교대 (2초간) + 효과음 (`distress-emote.mp3`) |
| **양손 펼침 (Both Palms)** | 양손, 손바닥 정면 | 사랑스러운 반응: `lovely.png` 2.5초 + 효과음 (`love-emote.mp3`) |
| **가리키기 (Point)** | 검지만 펼침 | 인식되지만 **연결된 동작 없음** |

**쿨다운**: 같은 제스처 간 8초 간격

---

### 2.2 머리 방향 (얼굴 위치 기반)

| 입력 (Input) | 로봇 반응 (Output) |
|---|---|
| 얼굴 중심 ≤ 화면 35% (왼쪽) | 게임 방향 피드백 + 효과음 (`game_move`) + HUD "Head game: Left" |
| 얼굴 중심 ≥ 화면 65% (오른쪽) | 게임 방향 피드백 + 효과음 + HUD "Head game: Right" |

**쿨다운**: 같은 방향 1200ms 간격

---

### 2.3 까꿍 (Peekaboo)

| 입력 (Input) | 로봇 반응 (Output) |
|---|---|
| 얼굴 사라짐 → 2500ms 이내 재등장 | 환영 반응: `welcome.png` + 효과음 (`pleased-emote.mp3`) + HUD "Peekaboo!" + TTS "Peekaboo!" |

---

## 3. 얼굴/존재감 (Face & Presence)

### 3.1 얼굴 감지 & 추적

| 상황 (Input) | 로봇 반응 (Output) |
|---|---|
| **얼굴 처음 감지** (부재 상태에서) | 화면 깨어남 + 시선 추적 활성화 |
| **얼굴 + 인터랙션** (음성/터치/제스처) | 집중 표정으로 전환, 적극적 인터랙션 모드 |
| **인터랙션 없이 대기** (5초) | 차분한 표정으로 전환 |
| **얼굴 이동** | 로봇 눈/시선이 얼굴 위치를 따라감 |
| **작업 중 얼굴 잠깐 사라짐** (< 800ms) | 포커스 유지 — UI와 표정 안정적 유지 |

### 3.2 부재 & 수면

| 상황 (Input) | 로봇 반응 (Output) |
|---|---|
| **오래 대기** (인터랙션 없이 3초) | 졸림 상태: `sleepy.png` + `SleepUI` + 수면 효과음 (`sleepy-emote.mp3`, 반복 재생) |
| **오래 얼굴 없음** (3초) | 부재 상태: 화면 어두워짐 (`NormalFace(dim)`) |

### 3.3 재등장

| 상황 (Input) | 로봇 반응 (Output) |
|---|---|
| **오래 부재 후 얼굴 감지** (≥3초 부재 후) | 환영 반응: `welcome.png` + 효과음 (`pleased-emote.mp3`) + 환영 애니메이션 |
| **수면 중 얼굴 감지** | 부드럽게 깨어남 → 환영 반응 |
| **수면 중 음성/터치만** (얼굴 없이) | 놀람 반응 (`startled.png` + `shocked-emote.mp3`). 수면에서 깨어나지 **않음** |

### 3.4 얼굴 없이 음성 인식

| 상황 (Input) | 로봇 반응 (Output) |
|---|---|
| 얼굴 없는 상태에서 음성 감지 | 놀람 반응 (`startled.png` + `shocked-emote.mp3`) → `ListeningUI` + 탐색 애니메이션 (점 움직임) → 이후 명령 정상 처리 |

---

## 4. 터치 (Touch Interactions)

| 입력 (Input) | 로봇 반응 (Output) |
|---|---|
| **탭** (짧은 터치) | 주의 전환 애니메이션 + HUD "Tap!" |
| **부재 중 탭** | 화면 깨어남: 부재 → Idle 전환 |
| **수면 중 탭** | 놀람 반응 (`startled`). 부드럽게 깨어나지 **않음** |
| **쓰다듬기** (24px 이상 드래그) | 행복 반응: `cry.png` + 하트 + 효과음 (`pleased-emote.mp3`) + HUD "Yay!" |

---

## 5. 상태 요약 (States)

### 5.1 사용자 맥락 상태 (Context States)

| 상태 | 의미 | 표정 | UI |
|---|---|---|---|
| `Away` | 사용자 없음 | 비활성 (어두움) | `NormalFace(dim)` |
| `Idle` | 사용자 존재, 대기 중 | 차분한 표정 (`calm.png`) | `NormalFace` |
| `Engaged` | 활발한 상호작용 중 | 집중 표정 (`attentive.png`) | `NormalFace` |
| `Sleepy` | 오래 대기, 졸림 | 졸린 표정 (`sleepy.png`) | `SleepUI` |

### 5.2 활동 상태 (Activity States)

| 상태 | 의미 | 표정 | UI |
|---|---|---|---|
| `Idle` | 작업 없음 | (맥락 상태 따름) | (맥락 상태 따름) |
| `Listening` | 음성 수신 중 | 집중 표정 | `ListeningUI` |
| `Executing(photo)` | 사진 촬영 중 | `photo_ready` → `photo_cute` | `CameraUI` |
| `Executing(game)` | 게임 모드 | `wet_tear` | `GameUI` |
| `Executing(weather)` | 날씨 조회 중 | `robot_right` | `NormalFace` |
| `Executing(smarthome)` | 스마트홈 제어 중 | 성공: `cute` / 실패: `smarthome_fail` | `NormalFace` |
| `Executing(dance)` | 춤 추는 중 | `dance_face` + RGB 플래시 | `NormalFace` |
| `Executing(timer_setup)` | 타이머 등록 중 | 집중 표정 | `NormalFace` |
| `Alerting` | 타이머 알림 울림 | 알림 표정 | `AlertUI` |

---

## 6. 순간 반응 (Oneshot Events)

| 반응 | 우선순위 | 지속 시간 | 트리거 |
|---|---|---|---|
| `startled` (놀람) | 30 | 600ms | 얼굴 없이 음성, 손가락 총, 수면 중 탭 |
| `confused` (혼란) | 25 | 800ms | 의도 파싱 실패, 작업 실패, 날씨 실패 |
| `angry` (화남) | 25 | 2000ms | 주먹 제스처 |
| `welcome` (환영) | 20 | 1500ms | 재등장, 손 흔들기, 까꿍 |
| `happy` (기쁨) | 20 | 1000ms | 쓰다듬기, 스마트홈 성공 |
| `lovely` (사랑) | 20 | 2500ms | 양손 펼침 제스처 |

**우선순위 규칙**: 높은 우선순위가 선점. 같은 우선순위는 병합 (80% 이상 경과 시에만 재실행). 낮은 우선순위는 무시.

---

## 7. 인터럽트 정책 (Interrupt Policies)

| 현재 작업 | 새 이벤트 | 정책 |
|---|---|---|
| 사진 촬영 중 | 모든 새 의도 | **무시** (멈춰줘/확인 제외) |
| 사진 촬영 중 | 타이머 만료 | **보류** → 촬영 완료 후 알림 |
| 춤/게임 중 | 모든 새 의도 | **무시** (멈춰줘/확인, 타이머 만료 제외) |
| 스마트홈/날씨/타이머 등록 중 | 새 음성 의도 | **지연** → 현재 작업 완료 후 자동 재생 |
| 알림 중 | 확인 외 의도 | **무시** |
| 그 외 | 모든 이벤트 | **허용** |

---

## 8. 효과음 맵 (Sound Effects)

| 효과음 | 파일 | 트리거 |
|---|---|---|
| 듣기 시작 | `listening_cue.mp3` | 음성 활동 감지 시 |
| 놀람 | `shocked-emote.mp3` | 손가락 총, 얼굴 없이 음성 |
| 환영 | `pleased-emote.mp3` | 손 흔들기, 까꿍, 재등장 |
| 행복 | `pleased-emote.mp3` | 쓰다듬기, 까꿍 |
| 화남 | `distress-emote.mp3` | 주먹 제스처 |
| 사랑 | `love-emote.mp3` | 양손 펼침 |
| 성공 | `pride-emote.mp3` | 스마트홈 성공, 게임 진입 |
| 에러 | `surprise-emote.mp3` | 스마트홈 실패, 작업 실패 |
| 셔터 | `camera_shutter.mp3` | 사진 촬영 |
| 댄스 | `dance.mp3` | 댄스 모드 (10초) |
| 알림 | `timer_ring.mp3` | 타이머 만료 |
| 타이머 등록 | `timer_ring.mp3` | 타이머 설정 |
| 날씨 | `flourish-emote-animal-crossing.mp3` | 날씨 조회 성공 |
| 수면 | `sleepy-emote.mp3` | 졸림 상태 (반복) |

---

## 9. 종합 시나리오 예시

### 예시 1: 얼굴 없이 "에어컨 켜줘"
1. VAD 작동 → **놀람** 반응 + `ListeningUI` + `listening_cue.mp3`
2. STT → "에어컨 켜줘" → `smarthome.aircon.on`
3. `Executing(smarthome)` → HTTP 전송
4. 성공 → **기쁨** 반응 + `pride-emote.mp3` + HUD "Control OK" → Idle

### 예시 2: 사진 촬영 중 타이머 만료
1. "사진 찍어줘" → `CameraUI`, 3초 카운트다운
2. 카운트다운 2초에 타이머 만료 → **보류**
3. 사진 완료 → 셔터 효과음 → "Photo saved"
4. 보류된 타이머 재생 → `Alerting` + 알림
5. "확인" → Idle

### 예시 3: 연속 스마트홈 명령
1. "불 켜줘" → `Executing(smarthome)` → HTTP 전송 중
2. "티비 켜줘" 도착 → **지연 저장**
3. 거실 등 응답 → 기쁨 → Idle
4. 지연된 명령 자동 재생 → `Executing(smarthome)` → TV 명령

### 예시 4: 수면 → 깨어남
1. 오래 대기 → `Sleepy` + `sleepy.png` + 수면 효과음 반복
2. 얼굴 감지 → **환영** 반응 → `Idle` + `welcome.png`
3. 음성 시작 → `Engaged` + `Listening`

---

## 10. 미구현/부분 구현 기능

| 기능 | 현재 상태 |
|---|---|
| 참참참 (머리 방향 게임) | 머리 방향 감지 + HUD 피드백만 있음; 승패 로직 미구현 |
| 빵야 (손가락 총) | 놀람 반응 + "Bang!" HUD; "쓰러지는" 애니메이션 미구현 |
| 숨바꼭질 (까꿍) | 까꿍 감지 + 환영/기쁨 반응; 완전한 숨바꼭질 게임 미구현 |
| V사인 사진 | 동작 중 — camera.capture 파이프라인 연결됨 |
| 가리키기 제스처 | 감지되지만 동작 미연결 |
| 절대 시간 타이머 ("오후 3시") | 파서 존재하나 별칭 커버리지 부족; 실패할 수 있음 |
