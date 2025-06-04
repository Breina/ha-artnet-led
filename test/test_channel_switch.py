from custom_components.artnet_led.util.channel_switch import to_values, from_values

max_mireds: int = 500
min_mireds: int = 153
mid_temp = round((max_mireds - min_mireds) / 2 + min_mireds)


def test_to_values_ch():
    values = to_values("ch", 1, True, 255, cold_white=255, warm_white=128)

    assert values[0] == 255
    assert values[1] == 128

    values = to_values("ch", 1, True, 255, cold_white=128, warm_white=64)

    assert values[0] == 255
    assert values[1] == 128

    values = to_values("ch", 1, True, 128, cold_white=128, warm_white=64)
    assert values[0] == 128
    assert values[1] == 64


def test_to_values_dCH():
    values = to_values("dCH", 1, True, 255, cold_white=255, warm_white=128)

    assert values[0] == 255
    assert values[1] == 255
    assert values[2] == 128

    values = to_values("dCH", 1, True, 255, cold_white=128, warm_white=64)

    assert values[0] == 255
    assert values[1] == 255
    assert values[2] == 128

    values = to_values("dCH", 1, True, 128, cold_white=128, warm_white=64)
    assert values[0] == 128
    assert values[1] == 255
    assert values[2] == 128


def test_to_values_color_temp():
    values = to_values("ch", 1, True, 255, color_temp=mid_temp, min_mireds=min_mireds, max_mireds=max_mireds)

    assert values[0] >= 254
    assert values[1] >= 254


def test_from_values_ch():
    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("ch", 1, [255, 0], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 255
    assert warm_white == 0
    assert color_temp == min_mireds

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("ch", 1, [0, 255], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 0
    assert warm_white == 255
    assert color_temp == max_mireds

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("ch", 1, [255, 255], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 255
    assert warm_white == 255
    assert color_temp == mid_temp

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("ch", 1, [128, 128], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 128
    assert cold_white == 255
    assert warm_white == 255
    assert color_temp == mid_temp

def test_from_values_dCH():
    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("dCH", 1, [255, 255, 0], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 255
    assert warm_white == 0
    assert color_temp == min_mireds

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("dCH", 1, [255, 0, 255], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 0
    assert warm_white == 255
    assert color_temp == max_mireds

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("dCH", 1, [255, 255, 255], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 255
    assert warm_white == 255
    assert color_temp == mid_temp

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("dCH", 1, [255, 128, 128], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 255
    assert cold_white == 128
    assert warm_white == 128
    assert color_temp == mid_temp

    is_on, brightness, _, _, _, cold_white, warm_white, color_temp = \
        from_values("dCH", 1, [128, 255, 255], min_mireds=min_mireds, max_mireds=max_mireds)

    assert is_on
    assert brightness == 128
    assert cold_white == 255
    assert warm_white == 255
    assert color_temp == mid_temp
