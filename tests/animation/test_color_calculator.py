import unittest

from custom_components.dmx.animation.color_calculator import LightTransitionAnimator
from custom_components.dmx.entity.light import ChannelType


class TestLightTransitionAnimator(unittest.TestCase):
    """Test suite for LightTransitionAnimator class."""

    def setUp(self):
        """Set up common test values."""
        self.min_kelvin = 2700
        self.max_kelvin = 6500

    def test_rgb_basic_interpolation(self):
        """Test basic RGB interpolation."""
        current = {
            ChannelType.RED: 255,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 0
        }
        desired = {
            ChannelType.RED: 0,
            ChannelType.GREEN: 255,
            ChannelType.BLUE: 0
        }

        animator = LightTransitionAnimator(current, desired)

        # Test start state
        result_start = animator.interpolate(0.0)
        self.assertEqual(result_start[ChannelType.RED], 255)
        self.assertEqual(result_start[ChannelType.GREEN], 0)
        self.assertEqual(result_start[ChannelType.BLUE], 0)

        # Test end state
        result_end = animator.interpolate(1.0)
        self.assertEqual(result_end[ChannelType.RED], 0)
        self.assertEqual(result_end[ChannelType.GREEN], 255)
        self.assertEqual(result_end[ChannelType.BLUE], 0)

        # Test middle state (should be different from simple linear interpolation)
        result_mid = animator.interpolate(0.5)
        self.assertNotEqual(result_mid[ChannelType.RED], 127)  # Not simple linear
        self.assertNotEqual(result_mid[ChannelType.GREEN], 127)

    def test_rgbw_interpolation(self):
        """Test RGBW interpolation with white channel."""
        current = {
            ChannelType.RED: 255,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 0,
            ChannelType.WARM_WHITE: 0
        }
        desired = {
            ChannelType.RED: 0,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 0,
            ChannelType.WARM_WHITE: 255
        }

        animator = LightTransitionAnimator(current, desired, self.min_kelvin, self.max_kelvin)

        result_start = animator.interpolate(0.0)
        result_end = animator.interpolate(1.0)
        result_mid = animator.interpolate(0.5)

        # Check that all channels are present
        for channel in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE, ChannelType.WARM_WHITE]:
            self.assertIn(channel, result_start)
            self.assertIn(channel, result_end)
            self.assertIn(channel, result_mid)

        # Check start and end states
        self.assertEqual(result_start[ChannelType.RED], 255)
        self.assertEqual(result_start[ChannelType.WARM_WHITE], 0)
        self.assertEqual(result_end[ChannelType.RED], 0)
        self.assertEqual(result_end[ChannelType.WARM_WHITE], 255)

    def test_warm_cold_white_interpolation(self):
        """Test warm white to cold white interpolation."""
        current = {
            ChannelType.WARM_WHITE: 255,
            ChannelType.COLD_WHITE: 0
        }
        desired = {
            ChannelType.WARM_WHITE: 0,
            ChannelType.COLD_WHITE: 255
        }

        animator = LightTransitionAnimator(current, desired, self.min_kelvin, self.max_kelvin)

        result_start = animator.interpolate(0.0)
        result_end = animator.interpolate(1.0)
        result_mid = animator.interpolate(0.5)

        # Check start state (warm)
        self.assertGreater(result_start[ChannelType.WARM_WHITE], result_start[ChannelType.COLD_WHITE])

        # Check end state (cold)
        self.assertGreater(result_end[ChannelType.COLD_WHITE], result_end[ChannelType.WARM_WHITE])

        # Check middle state (mixed)
        self.assertGreater(result_mid[ChannelType.WARM_WHITE], 0)
        self.assertGreater(result_mid[ChannelType.COLD_WHITE], 0)

    def test_color_temperature_dimmer_interpolation(self):
        """Test color temperature + dimmer interpolation."""
        current = {
            ChannelType.COLOR_TEMPERATURE: 0,  # Warm
            ChannelType.DIMMER: 255
        }
        desired = {
            ChannelType.COLOR_TEMPERATURE: 255,  # Cold
            ChannelType.DIMMER: 128
        }

        animator = LightTransitionAnimator(current, desired, self.min_kelvin, self.max_kelvin)

        result_start = animator.interpolate(0.0)
        result_end = animator.interpolate(1.0)

        # Check that color temperature and dimmer are interpolated
        self.assertEqual(result_start[ChannelType.COLOR_TEMPERATURE], 0)
        self.assertEqual(result_start[ChannelType.DIMMER], 255)
        self.assertEqual(result_end[ChannelType.COLOR_TEMPERATURE], 255)
        self.assertEqual(result_end[ChannelType.DIMMER], 128)

    def test_progress_clamping(self):
        """Test that progress values are properly clamped."""
        current = {ChannelType.RED: 0}
        desired = {ChannelType.RED: 255}

        animator = LightTransitionAnimator(current, desired)

        # Test negative progress
        result_negative = animator.interpolate(-0.5)
        self.assertEqual(result_negative[ChannelType.RED], 0)

        # Test progress > 1
        result_over = animator.interpolate(1.5)
        self.assertEqual(result_over[ChannelType.RED], 255)

    def test_same_values_interpolation(self):
        """Test interpolation when current and desired values are the same."""
        current = {
            ChannelType.RED: 128,
            ChannelType.GREEN: 64,
            ChannelType.BLUE: 192
        }
        desired = current.copy()

        animator = LightTransitionAnimator(current, desired)

        for progress in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = animator.interpolate(progress)
            self.assertEqual(result[ChannelType.RED], 128)
            self.assertEqual(result[ChannelType.GREEN], 64)
            self.assertEqual(result[ChannelType.BLUE], 192)

    def test_kelvin_bounds(self):
        """Test custom Kelvin temperature bounds."""
        custom_min = 2000
        custom_max = 8000

        current = {ChannelType.WARM_WHITE: 255, ChannelType.COLD_WHITE: 0}
        desired = {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 255}

        animator = LightTransitionAnimator(current, desired, custom_min, custom_max)

        self.assertEqual(animator.min_kelvin, custom_min)
        self.assertEqual(animator.max_kelvin, custom_max)

        # Test that interpolation still works with custom bounds
        result = animator.interpolate(0.5)
        self.assertIn(ChannelType.WARM_WHITE, result)
        self.assertIn(ChannelType.COLD_WHITE, result)

    def test_color_space_conversion_consistency(self):
        """Test that L*u*v* color space conversions are consistent."""
        # Test RGB to L*u*v* and back
        test_channels = {
            ChannelType.RED: 255,
            ChannelType.GREEN: 128,
            ChannelType.BLUE: 64
        }

        animator = LightTransitionAnimator(test_channels, test_channels)

        # Convert to RGB
        rgb = animator._channels_to_rgb(test_channels)

        # Convert to L*u*v* and back
        luv = animator._rgb_to_luv(rgb)
        rgb_back = animator._luv_to_rgb(luv)

        # Check that we get approximately the same RGB values back
        for i in range(3):
            self.assertAlmostEqual(rgb[i], rgb_back[i], places=2)

    def test_luv_color_space_properties(self):
        """Test L*u*v* color space specific properties."""
        # Test that L* (lightness) behaves correctly
        black = {ChannelType.RED: 0, ChannelType.GREEN: 0, ChannelType.BLUE: 0}
        white = {ChannelType.RED: 255, ChannelType.GREEN: 255, ChannelType.BLUE: 255}

        animator = LightTransitionAnimator(black, white)

        black_luv = animator._channels_to_luv(black)
        white_luv = animator._channels_to_luv(white)

        # Black should have L* close to 0
        self.assertLess(black_luv[0], 5)  # L* close to 0

        # White should have L* close to 100
        self.assertGreater(white_luv[0], 95)  # L* close to 100

        # u* and v* for pure black should be close to 0
        self.assertLess(abs(black_luv[1]), 5)  # u* close to 0
        self.assertLess(abs(black_luv[2]), 5)  # v* close to 0

    def test_perceptual_uniformity(self):
        """Test that L*u*v* provides better perceptual uniformity than RGB."""
        # Red to blue transition
        current = {ChannelType.RED: 255, ChannelType.GREEN: 0, ChannelType.BLUE: 0}  # Red
        desired = {ChannelType.RED: 0, ChannelType.GREEN: 0, ChannelType.BLUE: 255}  # Blue

        animator = LightTransitionAnimator(current, desired)

        # At 50% progress, we should get a visually intermediate color
        result_mid = animator.interpolate(0.5)

        # The result should not be a simple average (which would be dark)
        # L*u*v* interpolation should maintain reasonable brightness
        total_brightness = result_mid[ChannelType.RED] + result_mid[ChannelType.GREEN] + result_mid[ChannelType.BLUE]
        self.assertGreater(total_brightness, 100)  # Should not be too dark
