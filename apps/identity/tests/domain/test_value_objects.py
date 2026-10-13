from __future__ import annotations

import pytest

from apps.identity.domain.enums import FitnessGoal
from apps.identity.domain.value_objects import Email, FitnessProfile, OTPCode, PermissionCode, PhoneNumber
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestPhoneNumber:
    def test_accepts_valid_e164(self):
        assert PhoneNumber("+998901234567").value == "+998901234567"

    @pytest.mark.parametrize("bad", ["998901234567", "+0901234567", "not-a-phone", "+99890123456789012", ""])
    def test_rejects_invalid_formats(self, bad):
        with pytest.raises(ValidationFailed):
            PhoneNumber(bad)


class TestOTPCode:
    def test_accepts_six_digit_code(self):
        assert OTPCode("123456").value == "123456"

    @pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef", "12 456", ""])
    def test_rejects_invalid_codes(self, bad):
        with pytest.raises(ValidationFailed):
            OTPCode(bad)

    def test_generate_produces_valid_six_digit_code(self):
        code = OTPCode.generate()
        assert len(code.value) == 6
        assert code.value.isdigit()

    def test_generate_produces_varying_codes(self):
        codes = {OTPCode.generate().value for _ in range(20)}
        assert len(codes) > 1  # astronomically unlikely to collide 20 times if secrets.randbelow is working


class TestEmail:
    def test_accepts_valid_email(self):
        assert Email("user@example.com").value == "user@example.com"

    @pytest.mark.parametrize("bad", ["not-an-email", "user@", "@example.com", "user example.com"])
    def test_rejects_invalid_email(self, bad):
        with pytest.raises(ValidationFailed):
            Email(bad)


class TestPermissionCode:
    def test_accepts_valid_code(self):
        assert PermissionCode("identity.user.view").value == "identity.user.view"

    @pytest.mark.parametrize("bad", ["identity.view", "IDENTITY.USER.VIEW", "identity-user-view", ""])
    def test_rejects_invalid_code(self, bad):
        with pytest.raises(ValidationFailed):
            PermissionCode(bad)


class TestFitnessProfile:
    def test_accepts_none_values(self):
        profile = FitnessProfile()
        assert profile.height_cm is None
        assert profile.weight_kg is None
        assert profile.goal is None

    def test_accepts_valid_values(self):
        profile = FitnessProfile(height_cm=180, weight_kg=75, goal="muscle_gain")
        assert profile.height_cm == 180

    @pytest.mark.parametrize("height", [29, 301, -10])
    def test_rejects_height_out_of_range(self, height):
        with pytest.raises(ValidationFailed):
            FitnessProfile(height_cm=height)

    @pytest.mark.parametrize("weight", [9, 501, -1])
    def test_rejects_weight_out_of_range(self, weight):
        with pytest.raises(ValidationFailed):
            FitnessProfile(weight_kg=weight)

    def test_goal_accepts_a_real_fitness_goal_enum_member(self):
        """A real defect fix: `goal` previously accepted any arbitrary string with zero validation -- the comment justifying this claimed a circular import that does not actually exist (confirmed directly: enums.py has zero dependency on this module)."""
        profile = FitnessProfile(goal=FitnessGoal.FAT_LOSS)
        assert profile.goal is FitnessGoal.FAT_LOSS

    def test_goal_auto_converts_a_valid_raw_string(self):
        """Existing callers passing a raw string (matching the certified Application/Infrastructure convention) must not break -- the value object converts and validates transparently."""
        profile = FitnessProfile(goal="healthy_lifestyle")
        assert profile.goal is FitnessGoal.HEALTHY_LIFESTYLE

    def test_goal_rejects_an_invalid_string(self):
        """The actual defect this fix closes: previously, any string at all -- including garbage -- was silently accepted and stored."""
        with pytest.raises(ValidationFailed):
            FitnessProfile(goal="not_a_real_fitness_goal")
