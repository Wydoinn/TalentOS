from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest


def test_binary_probabilities_from_logits():
    from app.models.face_spoof import _binary_probabilities

    real_prob, spoof_prob, confidence = _binary_probabilities(
        np.array([3.0, 1.0], dtype=np.float32),
        real_index=0,
    )

    assert real_prob > spoof_prob
    assert confidence > 0.5


def test_binary_probabilities_from_single_logit():
    from app.models.face_spoof import _binary_probabilities

    real_prob, spoof_prob, confidence = _binary_probabilities(
        np.array([2.0], dtype=np.float32),
        real_index=0,
    )

    assert real_prob > 0.5
    assert np.isclose(real_prob + spoof_prob, 1.0, atol=1e-5)
    assert confidence >= real_prob


def test_square_crop_is_resized_to_target_shape():
    from app.models.face_spoof import _crop_face_square

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    crop = _crop_face_square(frame, (100, 80, 250, 200), scale=1.6, output_size=128)

    assert crop is not None
    assert crop.shape == (128, 128, 3)


def test_square_crop_handles_large_out_of_bounds_expansion():
    from app.models.face_spoof import _crop_face_square

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    crop = _crop_face_square(frame, (300, 240, 350, 280), scale=20.0, output_size=128)

    assert crop is not None
    assert crop.shape == (128, 128, 3)


def test_face_spoof_model_raises_when_weights_are_missing(tmp_path, monkeypatch):
    import sys
    import types

    from app.models.face_spoof import FaceSpoofModel

    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        types.SimpleNamespace(InferenceSession=object),
    )
    with patch("app.models.face_spoof.settings") as settings_mock:
        settings_mock.FACE_SPOOF_MODEL_PATH = tmp_path / "missing.onnx"
        settings_mock.DEVICE = "cpu"
        settings_mock.FACE_SPOOF_INPUT_SIZE = 128
        settings_mock.FACE_SPOOF_MEAN = [151.2405, 119.595, 107.8395]
        settings_mock.FACE_SPOOF_STD = [63.0105, 56.457, 55.0035]

        with pytest.raises(RuntimeError, match="Face anti-spoof model was not found"):
            FaceSpoofModel().load()


def test_normalise_waveform_preserves_length():
    from app.models.audio_spoof import _normalise_waveform

    waveform = np.linspace(-1.0, 1.0, 32000, dtype=np.float32)
    normalized = _normalise_waveform(waveform)

    assert normalized.shape == waveform.shape
    assert np.isfinite(normalized).all()


def test_audio_preprocess_keeps_nonempty_audio():
    from app.models.audio_spoof import AudioSpoofModel

    processed = AudioSpoofModel()._preprocess(np.zeros(8000, np.float32), 16000)

    assert len(processed) == 8000
    assert np.isfinite(processed).all()


def test_audio_preprocess_replaces_empty_audio():
    from app.config import get_settings
    from app.models.audio_spoof import AudioSpoofModel

    processed = AudioSpoofModel()._preprocess(np.array([], dtype=np.float32), 16000)

    assert len(processed) == get_settings().AUDIO_SAMPLE_RATE
    assert np.isfinite(processed).all()


def test_audio_infer_maps_real_probability():
    import torch

    from app.models.audio_spoof import AudioSpoofModel

    class DummyModel:
        def __call__(self, tensor):
            return torch.tensor([[0.1, 0.9]], dtype=torch.float32, device=tensor.device)

    model = AudioSpoofModel()
    model._model = DummyModel()
    model.loaded = True

    result = model.infer(np.zeros(16000, np.float32), 16000)

    assert result.real_prob > result.spoof_prob
    assert result.is_real is True


def test_extract_frames_respects_max_frames(monkeypatch):
    from app.pipeline import preprocessor as preprocessor_module

    total_frames = 35
    source_frames = [
        np.full((8, 8, 3), fill_value=index, dtype=np.uint8)
        for index in range(total_frames)
    ]

    class FakeCapture:
        def __init__(self, frames):
            self._frames = frames
            self._index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == preprocessor_module.cv2.CAP_PROP_FPS:
                return 7.0
            if prop == preprocessor_module.cv2.CAP_PROP_FRAME_COUNT:
                return len(self._frames)
            if prop == preprocessor_module.cv2.CAP_PROP_FRAME_WIDTH:
                return self._frames[0].shape[1]
            if prop == preprocessor_module.cv2.CAP_PROP_FRAME_HEIGHT:
                return self._frames[0].shape[0]
            return 0

        def read(self):
            if self._index >= len(self._frames):
                return False, None
            frame = self._frames[self._index]
            self._index += 1
            return True, frame

        def release(self):
            return None

    monkeypatch.setattr(
        preprocessor_module.cv2,
        "VideoCapture",
        lambda _: FakeCapture(source_frames),
    )
    monkeypatch.setattr(preprocessor_module.settings, "MAX_FRAMES", 30)
    monkeypatch.setattr(preprocessor_module.settings, "MIN_VIDEO_DURATION_SEC", 1.0)
    monkeypatch.setattr(preprocessor_module.settings, "MAX_VIDEO_DURATION_SEC", 15.0)

    media = preprocessor_module.MediaPreprocessor()
    frames, info, _ = media._extract_frames("sample.mp4")

    assert info.total_frames == total_frames
    assert len(frames) == 30
    assert np.array_equal(frames[0], source_frames[0])
    assert np.array_equal(frames[-1], source_frames[-1])


def test_extract_frames_tolerates_invalid_metadata(monkeypatch):
    from app.pipeline import preprocessor as preprocessor_module

    total_frames = 150
    source_frames = [
        np.full((8, 8, 3), fill_value=index % 255, dtype=np.uint8)
        for index in range(total_frames)
    ]

    class FakeCapture:
        def __init__(self, frames):
            self._frames = frames
            self._index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == preprocessor_module.cv2.CAP_PROP_FPS:
                return 25.0
            if prop == preprocessor_module.cv2.CAP_PROP_FRAME_COUNT:
                return -9.223372036854776e18
            if prop == preprocessor_module.cv2.CAP_PROP_FRAME_WIDTH:
                return self._frames[0].shape[1]
            if prop == preprocessor_module.cv2.CAP_PROP_FRAME_HEIGHT:
                return self._frames[0].shape[0]
            if prop == preprocessor_module.cv2.CAP_PROP_POS_MSEC:
                return self._index * 40.0
            return 0

        def read(self):
            if self._index >= len(self._frames):
                return False, None
            frame = self._frames[self._index]
            self._index += 1
            return True, frame

        def release(self):
            return None

    monkeypatch.setattr(
        preprocessor_module.cv2,
        "VideoCapture",
        lambda _: FakeCapture(source_frames),
    )
    monkeypatch.setattr(preprocessor_module.settings, "MAX_FRAMES", 30)
    monkeypatch.setattr(preprocessor_module.settings, "MIN_VIDEO_DURATION_SEC", 4.0)
    monkeypatch.setattr(preprocessor_module.settings, "MAX_VIDEO_DURATION_SEC", 15.0)

    media = preprocessor_module.MediaPreprocessor()
    frames, info, _ = media._extract_frames("sample.webm")

    assert len(frames) > 1
    assert info.total_frames == total_frames
    assert info.duration_sec >= 4.0
