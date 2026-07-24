from __future__ import annotations

import io
from typing import Any

import cv2
import numpy as np

from app.core.exceptions import ApiError


class VisionAnalysisService:
    _face_detector: Any = None
    _face_mesh: Any = None

    async def analyze_frame(self, image_bytes: bytes) -> dict[str, Any]:
        return self._analyze_sync(image_bytes)

    def _analyze_sync(self, image_bytes: bytes) -> dict[str, Any]:
        frame = self._decode_image(image_bytes)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        detector, face_mesh = self._get_detectors()
        detection_results = detector.process(rgb_frame)
        mesh_results = face_mesh.process(rgb_frame)

        detections = list(detection_results.detections or [])
        mesh_faces = list(mesh_results.multi_face_landmarks or [])
        detected_face_count = max(len(detections), len(mesh_faces))
        if detected_face_count == 0:
            return {
                "face_count": 0,
                "gaze_status": "NO_FACE",
                "normalized_offset": None,
                "message": "No face detected in the current camera frame.",
            }

        image_height, image_width = rgb_frame.shape[:2]
        if detected_face_count > 1:
            return {
                "face_count": detected_face_count,
                "gaze_status": "MULTIPLE_FACES",
                "normalized_offset": None,
                "message": "Multiple faces detected in the camera frame.",
                "frame_width": image_width,
                "frame_height": image_height,
            }

        if mesh_faces:
            landmarks = mesh_faces[0].landmark
            left_eye = landmarks[33]
            right_eye = landmarks[263]
            nose_tip = landmarks[1]
            face_left = min(point.x for point in landmarks)
            face_right = max(point.x for point in landmarks)
            face_center_x = (face_left + face_right) / 2.0
            eye_mid_x = (left_eye.x + right_eye.x) / 2.0
            inter_eye_distance = max(abs(right_eye.x - left_eye.x), 0.06)
            head_turn_offset = abs(nose_tip.x - eye_mid_x) / inter_eye_distance
            face_center_offset = abs(face_center_x - 0.5) / 0.5
            nose_center_offset = abs(nose_tip.x - 0.5) / 0.5
            normalized_offset = max(
                head_turn_offset,
                face_center_offset * 0.7,
                nose_center_offset * 0.55,
            )
        else:
            relative_box = detections[0].location_data.relative_bounding_box
            center_x = relative_box.xmin + (relative_box.width / 2.0)
            normalized_offset = abs(float(center_x) - 0.5) / 0.5

        gaze_threshold = 0.32
        gaze_status = "AWAY" if normalized_offset > gaze_threshold else "CENTERED"
        message = (
            "Candidate head orientation appears away from the center of the screen."
            if gaze_status == "AWAY"
            else "Candidate gaze is centered."
        )

        return {
            "face_count": detected_face_count,
            "gaze_status": gaze_status,
            "normalized_offset": round(normalized_offset, 4),
            "message": message,
            "frame_width": image_width,
            "frame_height": image_height,
        }

    def _decode_image(self, image_bytes: bytes) -> np.ndarray:
        buffer = np.frombuffer(io.BytesIO(image_bytes).read(), dtype=np.uint8)
        frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if frame is None:
            raise ApiError(
                status_code=422,
                code="invalid_frame",
                message="The uploaded camera frame could not be decoded.",
            )
        return frame

    def _get_detectors(self):
        if self.__class__._face_detector is not None and self.__class__._face_mesh is not None:
            return self.__class__._face_detector, self.__class__._face_mesh

        try:
            import mediapipe as mp
        except Exception as exc:  # pragma: no cover - import depends on runtime environment.
            raise ApiError(
                status_code=503,
                code="vision_dependency_missing",
                message=f"MediaPipe is not available for vision checks: {exc}",
            ) from exc

        self.__class__._face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=0.5,
        )
        self.__class__._face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=3,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
        return self.__class__._face_detector, self.__class__._face_mesh
