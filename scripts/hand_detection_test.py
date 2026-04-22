"""
Hand detection test using MediaPipe.
Displays live webcam feed with hand landmarks and gesture info.
"""

import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


def count_fingers(hand_landmarks, handedness):
    """Count extended fingers based on landmark positions."""
    landmarks = hand_landmarks.landmark
    fingers = []

    # Thumb: compare tip x-position to IP joint (flipped for left hand)
    is_right = handedness.classification[0].label == "Right"
    if is_right:
        fingers.append(landmarks[4].x < landmarks[3].x)
    else:
        fingers.append(landmarks[4].x > landmarks[3].x)

    # Index, Middle, Ring, Pinky: tip y < pip joint y means extended
    for tip_id in [8, 12, 16, 20]:
        fingers.append(landmarks[tip_id].y < landmarks[tip_id - 2].y)

    return sum(fingers), fingers


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open camera")
        return

    print("Hand detection started. Press 'q' to quit.")

    with mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
        max_num_hands=2,
    ) as hands:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)
            rgb.flags.writeable = True

            h, w, _ = frame.shape

            if results.multi_hand_landmarks:
                for idx, (hand_lm, handedness) in enumerate(
                    zip(results.multi_hand_landmarks, results.multi_handedness)
                ):
                    mp_drawing.draw_landmarks(
                        frame,
                        hand_lm,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style(),
                    )

                    finger_count, _ = count_fingers(hand_lm, handedness)
                    label = handedness.classification[0].label
                    score = handedness.classification[0].score

                    wrist = hand_lm.landmark[0]
                    cx, cy = int(wrist.x * w), int(wrist.y * h)

                    text = f"{label} ({score:.2f}) | Fingers: {finger_count}"
                    cv2.putText(
                        frame,
                        text,
                        (cx - 60, cy - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

            hand_count = len(results.multi_hand_landmarks) if results.multi_hand_landmarks else 0
            cv2.putText(
                frame,
                f"Hands detected: {hand_count}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2,
            )

            cv2.imshow("Hand Detection Test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
