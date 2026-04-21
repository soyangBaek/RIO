# Face Expression Scenario Map

RIO가 사용하는 모든 표정(PNG) 에셋과, 각 표정이 언제 표시되는지 정리한 문서.

## 에셋 목록

| # | 파일명 | asset_key | 사용 여부 |
|---|--------|-----------|-----------|
| 1 | `alert.png` | `alert` | ✅ |
| 2 | `angry_idle.png` | `angry_idle` | ✅ |
| 3 | `angry_talking.png` | `angry_talking` | ✅ |
| 4 | `attentive.png` | `attentive` | ✅ |
| 5 | `boot.png` | `boot` | ❌ 미사용 |
| 6 | `bored_old.png` | `bored_old` | ❌ 미사용 |
| 7 | `calm.png` | `calm` | ✅ |
| 8 | `confused.png` | `confused` | ✅ |
| 9 | `cry.png` | `cry` | ✅ |
| 10 | `cute.png` | `cute` | ✅ |
| 11 | `cute_lips.png` | `cute_lips` | ❌ 미사용 |
| 12 | `dance_face.png` | `dance_face` | ✅ |
| 13 | `happy.png` | `happy` | ✅ |
| 14 | `lovely.png` | `lovely` | ✅ |
| 15 | `photo_cute.png` | `photo_cute` | ✅ |
| 16 | `photo_ready.png` | `photo_ready` | ✅ |
| 17 | `photo_snap.png` | `photo_snap` | ❌ 미사용 |
| 18 | `robot_idle.png` | `robot_idle` | ✅ |
| 19 | `robot_left.png` | `robot_left` | ❌ 미사용 |
| 20 | `robot_right.png` | `robot_right` | ❌ 미사용 |
| 21 | `sleepy.png` | `sleepy` | ✅ |
| 22 | `smarthome_fail.png` | `smarthome_fail` | ✅ |
| 23 | `startled.png` | `startled` | ✅ |
| 24 | `triangle_tear.png` | `triangle_tear` | ❌ 미사용 |
| 25 | `weather_face.png` | `weather_face` | ✅ |
| 26 | `welcome.png` | `welcome` | ✅ |
| 27 | `wet_tear.png` | `wet_tear` | ✅ |

---

## 시나리오별 표정 매핑

### 1. 사진 촬영

| 상황 | 표정 | fallback |
|------|------|----------|
| 사진 촬영 대기 (EXECUTING PHOTO / CameraUI) | `photo_ready` | `attentive` |
| 사진 촬영 완료 직후 (900ms 이내) | `photo_cute` | `happy` |

### 2. 스마트홈 제어

| 상황 | 표정 | fallback |
|------|------|----------|
| 스마트홈 명령 성공 | `cute` | `happy` |
| 스마트홈 명령 실패 | `smarthome_fail` | `confused` |

### 3. 댄스 모드

| 상황 | 표정 | fallback | 비고 |
|------|------|----------|------|
| 댄스 실행 중 (EXECUTING DANCE) | `dance_face` | `happy` | RGB 플래시 오버레이 추가 |

### 4. 게임 모드

| 상황 | 표정 | fallback |
|------|------|----------|
| 게임 실행 중 (EXECUTING GAME / GameUI) | `wet_tear` | `attentive` |

### 5. 날씨 조회

| 상황 | 표정 | fallback |
|------|------|----------|
| 날씨 조회 중 (EXECUTING WEATHER) | `weather_face` | `attentive` |

### 6. 제스처 반응 (Oneshot)

| 제스처 | Oneshot | 표정 | fallback | 지속시간 |
|--------|---------|------|----------|----------|
| 주먹 (fist) | `angry` | `angry_idle` ↔ `angry_talking` | `startled` | 2초 (0.5초 간격 교대) |
| 양손 손바닥 (both_palms) | `lovely` | `lovely` | `happy` | 2.5초 |

### 7. 애니메이션 오버레이 연동

| 오버레이 키 | 표정 | fallback | 트리거 |
|-------------|------|----------|--------|
| `cry` | `cry` | 현재 mood | 쓰다듬기 (touch stroke) |
| `welcome` | `welcome` | 현재 mood | 손 흔들기 (wave) / 까꿍 (peekaboo) |
| `startled` | `startled` | 현재 mood | 핑거건 (finger_gun) |

### 8. 수면 / 대기

| 상황 | 표정 | fallback |
|------|------|----------|
| 수면 오버레이 + `sleepy_with_face=True` | `robot_idle` | `calm` |
| 수면 오버레이 (일반) | `sleepy` | - |
| mood == `inactive` | `sleepy` | - |

### 9. 기본 Mood 매핑 (위 조건에 해당 없을 때)

| Mood | 표정 | fallback |
|------|------|----------|
| `calm` | `calm` | - |
| `attentive` | `attentive` | `calm` |
| `happy` | `happy` | `calm` |
| `alert` | `alert` | `calm` |
| `confused` | `confused` | `calm` |
| `startled` | `startled` | `calm` |
| `welcome` | `welcome` | `calm` |
| `sleepy` | `sleepy` | `calm` |
| 기타 | 현재 mood → `calm` | `calm` |

---

## 특수 효과

| 표정 | 효과 |
|------|------|
| `dance_face` | RGB 컬러 플래시 오버레이 (빨강→초록→파랑, 0.5초 주기) |
| `calm`, `attentive` | 눈 깜빡임 오버레이 적용 |
| `angry` oneshot | `angry_idle`↔`angry_talking` 0.5초 간격 자동 교대 |

---

## 미사용 에셋

아직 코드에서 참조하지 않는 에셋들:

| 파일 | 설명 |
|------|------|
| `boot.png` | 부팅 화면용 (예정) |
| `bored_old.png` | 이전 버전 지루함 표정 |
| `cute_lips.png` | 대체 귀여움 표정 |
| `photo_snap.png` | 촬영 순간 표정 (현재 photo_cute로 대체) |
| `robot_left.png` | 로봇 좌측 시선 (예정) |
| `robot_right.png` | 로봇 우측 시선 (예정) |
| `triangle_tear.png` | 삼각 눈물 표정 |
