"""Tests for jrboard.flap: visual-width preservation and final resolution."""

from __future__ import annotations

from jrboard.flap import flap_frames, lock_threshold, scramble_line
from jrboard.width import get_visual_width


def test_scramble_preserves_visual_width_ascii() -> None:
    target = "Shinjuku 17"
    for progress in (0.0, 0.25, 0.5, 0.75):
        scrambled = scramble_line(target, progress, seed=1)
        assert get_visual_width(scrambled) == get_visual_width(target)


def test_scramble_preserves_visual_width_cjk() -> None:
    target = "新宿 各駅停車 品川・渋谷方面"
    for progress in (0.0, 0.3, 0.6, 0.9):
        scrambled = scramble_line(target, progress, seed=7)
        assert get_visual_width(scrambled) == get_visual_width(target)


def test_scramble_passes_ansi_through() -> None:
    target = "\033[38;5;148m新宿\033[0m"
    scrambled = scramble_line(target, 0.2, seed=3)
    # ANSI sequences preserved verbatim; width unchanged.
    assert "\033[38;5;148m" in scrambled
    assert "\033[0m" in scrambled
    assert get_visual_width(scrambled) == get_visual_width(target)


def test_scramble_full_progress_equals_target() -> None:
    target = "新宿 各駅停車"
    assert scramble_line(target, 1.0, seed=42) == target


def test_scramble_spaces_pass_through() -> None:
    target = "A B C"
    scrambled = scramble_line(target, 0.0, seed=5)
    # Space positions (indices 1 and 3) must remain spaces.
    assert scrambled[1] == " "
    assert scrambled[3] == " "


def test_scramble_is_deterministic() -> None:
    target = "Shinjuku"
    a = scramble_line(target, 0.4, seed=11)
    b = scramble_line(target, 0.4, seed=11)
    assert a == b


def test_lock_threshold_in_unit_interval() -> None:
    total = 20
    for index in range(total):
        value = lock_threshold(index, total, jitter_seed=0)
        assert 0.0 <= value <= 0.999


def test_lock_threshold_is_deterministic() -> None:
    assert lock_threshold(5, 20, 0) == lock_threshold(5, 20, 0)


def test_flap_frames_last_frame_equals_targets() -> None:
    targets = ["新宿 各駅停車", "Shinjuku 17", "品川・渋谷方面"]
    frames = list(flap_frames(targets, steps=10, seed=0))
    assert len(frames) == 10
    assert frames[-1] == targets


def test_flap_frames_preserve_width_every_frame() -> None:
    targets = ["新宿 17", "Yoyogi"]
    for frame in flap_frames(targets, steps=8, seed=2):
        assert len(frame) == len(targets)
        for rendered, target in zip(frame, targets):
            assert get_visual_width(rendered) == get_visual_width(target)


def test_flap_frames_single_step_is_resolved() -> None:
    targets = ["新宿"]
    frames = list(flap_frames(targets, steps=1, seed=0))
    assert frames == [["新宿"]]
