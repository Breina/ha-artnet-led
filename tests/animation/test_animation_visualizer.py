import time

import pytest

from custom_components.dmx.animation.engine import DmxAnimationEngine
from custom_components.dmx.entity.light import ChannelMapping, ChannelType
from tests.dmx_test_framework import MockHomeAssistant


@pytest.fixture
def mock_hass():
    """Fixture providing a mock HomeAssistant instance"""
    return MockHomeAssistant()


CHANNEL_COLORS = {
    ChannelType.RED: "#FF4444",
    ChannelType.GREEN: "#44FF44",
    ChannelType.BLUE: "#4444FF",
    ChannelType.COLD_WHITE: "#ADD8E6",
    ChannelType.WARM_WHITE: "#FFE4B5",
    ChannelType.COLOR_TEMPERATURE: "#FFA500",
    ChannelType.DIMMER: "#FFFFFF",
}


def plot_animation_data(
    captured_frames, hass, title: str = "DMX Animation Data", y_range: tuple[int, int] = (0, 255), save_path: str = None
):
    """
    Create an interactive plot of the captured animation data

    Args:
        title: Plot title
        y_range: Y-axis range tuple (min, max)
        save_path: Optional path to save the plot
    """
    if not captured_frames:
        print("No animation data captured to plot")
        return

    from matplotlib import pyplot as plt

    # Set up the plot with dark background
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")

    # Extract timestamps and convert to relative time
    start_time = captured_frames[0][0]
    times = [(frame[0] - start_time) for frame in captured_frames]

    # Group data by channel type
    channel_data = {}
    for timestamp, frame_values in captured_frames:
        relative_time = timestamp - start_time
        for channel_type, value in frame_values.items():
            if channel_type not in channel_data:
                channel_data[channel_type] = {"times": [], "values": []}
            channel_data[channel_type]["times"].append(relative_time)
            channel_data[channel_type]["values"].append(value)

    # Plot each channel type
    for channel_type, data in channel_data.items():
        color = CHANNEL_COLORS.get(channel_type, "#FFFFFF")
        label = channel_type.name.replace("_", " ").title()

        # Plot with dots and lines
        ax.plot(
            data["times"], data["values"], color=color, marker="o", markersize=3, linewidth=1.5, label=label, alpha=0.8
        )

    # Formatting
    ax.set_xlabel("Time (seconds)", color="white")
    ax.set_ylabel("Value", color="white")
    ax.set_title(title, color="white", fontsize=14, fontweight="bold")
    ax.set_ylim(y_range)
    ax.grid(True, alpha=0.3, color="gray")
    ax.legend(loc="upper right", framealpha=0.8)

    # Make tick labels white
    ax.tick_params(colors="white")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, facecolor="black", edgecolor="black", dpi=150)
        print(f"Plot saved to: {save_path}")


@pytest.mark.asyncio
@pytest.mark.skip(reason="Run manually to plot animations")
async def test_rgb_fade_animation(mock_hass):
    """Test RGB color fade with visualization"""
    captured_frames = []

    def capture_output_frame(frame_values: dict[ChannelType, int]):
        timestamp = time.time()
        captured_frames.append((timestamp, frame_values.copy()))

    engine = DmxAnimationEngine(mock_hass, max_fps=60)
    engine._output_frame = capture_output_frame

    channel_mappings = [
        ChannelMapping([1], None, ChannelType.RED),
        ChannelMapping([2], None, ChannelType.GREEN),
        ChannelMapping([3], None, ChannelType.BLUE),
    ]

    await animate(
        engine,
        channel_mappings,
        {ChannelType.RED: 0, ChannelType.GREEN: 0, ChannelType.BLUE: 0},
        {ChannelType.RED: 255, ChannelType.GREEN: 0, ChannelType.BLUE: 0},
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.RED: 255, ChannelType.GREEN: 0, ChannelType.BLUE: 0},
        {ChannelType.RED: 0, ChannelType.GREEN: 255, ChannelType.BLUE: 0},
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.RED: 0, ChannelType.GREEN: 255, ChannelType.BLUE: 0},
        {ChannelType.RED: 0, ChannelType.GREEN: 0, ChannelType.BLUE: 255},
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.RED: 0, ChannelType.GREEN: 0, ChannelType.BLUE: 255},
        {ChannelType.RED: 255, ChannelType.GREEN: 0, ChannelType.BLUE: 0},
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.RED: 255, ChannelType.GREEN: 0, ChannelType.BLUE: 0},
        {ChannelType.RED: 255, ChannelType.GREEN: 255, ChannelType.BLUE: 255},
    )

    plot_animation_data(
        captured_frames,
        mock_hass,
        title="RGB Fade Animation (Off → Red → Green → Blue → Red → White)",
        y_range=(0, 255),
        save_path="animation/plots/rgb_fade_animation.png",
    )

    print(f"Captured {len(captured_frames)} frames")


@pytest.mark.asyncio
@pytest.mark.skip(reason="Run manually to plot animations")
async def test_ww_cw_fade_animation(mock_hass):
    """Test RGB color fade with visualization"""
    captured_frames = []

    def capture_output_frame(frame_values: dict[ChannelType, int]):
        timestamp = time.time()
        captured_frames.append((timestamp, frame_values.copy()))

    engine = DmxAnimationEngine(mock_hass, max_fps=60)
    engine._output_frame = capture_output_frame

    channel_mappings = [
        ChannelMapping([1], None, ChannelType.WARM_WHITE),
        ChannelMapping([2], None, ChannelType.COLD_WHITE),
    ]

    await animate(
        engine,
        channel_mappings,
        {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 0},
        {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 255},
        min_kelvin=2000,
        max_kelvin=6500,
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 255},
        {ChannelType.WARM_WHITE: 255, ChannelType.COLD_WHITE: 0},
        min_kelvin=2000,
        max_kelvin=6500,
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.WARM_WHITE: 255, ChannelType.COLD_WHITE: 0},
        {ChannelType.WARM_WHITE: 255, ChannelType.COLD_WHITE: 255},
        min_kelvin=2000,
        max_kelvin=6500,
    )

    await animate(
        engine,
        channel_mappings,
        {ChannelType.WARM_WHITE: 255, ChannelType.COLD_WHITE: 255},
        {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 0},
        min_kelvin=2000,
        max_kelvin=6500,
    )

    plot_animation_data(
        captured_frames,
        mock_hass,
        title="WW/CW Fade Animation (Off → Cold → Warm → White → Off)",
        y_range=(0, 255),
        save_path="animation/plots/ww_cw_fade_animation.png",
    )

    print(f"Captured {len(captured_frames)} frames")


@pytest.mark.asyncio
@pytest.mark.skip(reason="Run manually to plot animations")
async def test_rgbww_fade_animation(mock_hass):
    """Test RGB color fade with visualization"""
    captured_frames = []

    def capture_output_frame(frame_values: dict[ChannelType, int]):
        timestamp = time.time()
        captured_frames.append((timestamp, frame_values.copy()))

    engine = DmxAnimationEngine(mock_hass, max_fps=60)
    engine._output_frame = capture_output_frame

    channel_mappings = [
        ChannelMapping([1], None, ChannelType.RED),
        ChannelMapping([2], None, ChannelType.GREEN),
        ChannelMapping([3], None, ChannelType.BLUE),
        ChannelMapping([4], None, ChannelType.COLD_WHITE),
        ChannelMapping([5], None, ChannelType.WARM_WHITE),
    ]

    await animate(
        engine,
        channel_mappings,
        {
            ChannelType.RED: 255,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 0,
            ChannelType.COLD_WHITE: 0,
            ChannelType.WARM_WHITE: 255,
        },
        {
            ChannelType.RED: 0,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 255,
            ChannelType.COLD_WHITE: 255,
            ChannelType.WARM_WHITE: 0,
        },
    )

    await animate(
        engine,
        channel_mappings,
        {
            ChannelType.RED: 0,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 255,
            ChannelType.COLD_WHITE: 255,
            ChannelType.WARM_WHITE: 0,
        },
        {
            ChannelType.RED: 255,
            ChannelType.GREEN: 255,
            ChannelType.BLUE: 255,
            ChannelType.COLD_WHITE: 0,
            ChannelType.WARM_WHITE: 0,
        },
    )

    await animate(
        engine,
        channel_mappings,
        {
            ChannelType.RED: 255,
            ChannelType.GREEN: 255,
            ChannelType.BLUE: 255,
            ChannelType.COLD_WHITE: 0,
            ChannelType.WARM_WHITE: 0,
        },
        {
            ChannelType.RED: 0,
            ChannelType.GREEN: 0,
            ChannelType.BLUE: 0,
            ChannelType.COLD_WHITE: 255,
            ChannelType.WARM_WHITE: 255,
        },
    )

    plot_animation_data(
        captured_frames,
        mock_hass,
        title="RGBWW Fade Animation (Red/WW → Blue/CW → RGB white → CW/WW white)",
        y_range=(0, 255),
        save_path="animation/plots/rgbww_fade_animation.png",
    )

    print(f"Captured {len(captured_frames)} frames")


async def animate(
    engine, channel_mappings, current_values, desired_values, min_kelvin: int = 2700, max_kelvin: int = 6500
):
    animation_id = engine.create_animation(
        channel_mappings=channel_mappings,
        current_values=current_values,
        desired_values=desired_values,
        animation_duration_seconds=1.0,
        min_kelvin=min_kelvin,
        max_kelvin=max_kelvin,
    )
    animation = engine.active_animations[animation_id]
    await animation.task
