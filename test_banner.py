"""Photo banner: needs no camera, no token, no config.

    python -m pytest test_banner.py
"""
from PIL import Image, ImageStat

import banner


def darker(out, img, box):
    """Mean brightness of a region, before vs after. Sampling single pixels is
    unreliable here: a point either lands on the plate or on the glyphs drawn
    over it, and both are 'the overlay worked'."""
    return ImageStat.Stat(out.crop(box)).mean[0] < ImageStat.Stat(img.crop(box)).mean[0] - 12


def photo(w=1280, h=720):
    return Image.new("RGB", (w, h), (120, 120, 120))


def reading(left_ml=4.0, right_ml=111.0, left_t=28.0, right_t=None):
    pots = []
    for side, ml, t in (("left", left_ml, left_t), ("right", right_ml, right_t)):
        p = {"side": side, "volume_ml": ml, "ok": ml is not None}
        if t is not None:
            p["temp_c"] = t
        pots.append(p)
    return {"pots": pots}


def test_returns_a_same_sized_image():
    img = photo()
    out = banner.draw(img, reading())
    assert out.size == img.size
    assert out.mode == "RGB"


def test_overlay_actually_marks_both_bottom_corners():
    img = photo()
    out = banner.draw(img, reading())
    W, H = img.size
    # the plates darken their corners; the top of the frame is untouched
    assert darker(out, img, (10, H - 150, 260, H - 10))
    assert darker(out, img, (W - 260, H - 150, W - 10, H - 10))
    assert out.getpixel((W // 2, 20)) == img.getpixel((W // 2, 20))


def test_missing_reading_returns_the_original_object():
    img = photo()
    assert banner.draw(img, None) is img
    assert banner.draw(img, {}) is img
    assert banner.draw(img, {"pots": []}) is img


def test_unreadable_pot_still_gets_a_plate():
    """A blank corner reads as a broken overlay; "? ml" says the pot was not
    measurable in this frame, which is the truth."""
    r = reading(left_ml=None)
    r["pots"][0]["volume_ml"] = None
    img = photo()
    out = banner.draw(img, r)
    assert darker(out, img, (10, 720 - 150, 260, 710))


def test_temperature_is_optional():
    with_temp = banner.draw(photo(), reading(left_t=80.0, right_t=45.0))
    without = banner.draw(photo(), reading(left_t=None, right_t=None))
    assert with_temp.size == without.size


def test_one_pot_only():
    r = {"pots": [{"side": "right", "volume_ml": 900.0}]}
    img = photo()
    out = banner.draw(img, r)
    W, H = 1280, 720
    assert darker(out, img, (W - 300, H - 150, W - 10, H - 10))
    assert out.getpixel((40, H - 40)) == (120, 120, 120)      # left corner clean


def test_scales_with_frame_size():
    img = photo(640, 360)
    small = banner.draw(img, reading())
    assert small.size == (640, 360)
    assert darker(small, img, (5, 280, 140, 355))


def test_safe_draw_swallows_bad_input():
    img = photo()
    assert banner.safe_draw(img, {"pots": [{"side": "left", "volume_ml": object()}]}) is not None


def test_full_pot_number_fits_inside_the_frame():
    out = banner.draw(photo(), reading(left_ml=1250.0, right_ml=1250.0))
    assert out.size == (1280, 720)
