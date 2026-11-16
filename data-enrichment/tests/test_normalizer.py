"""Stage 2 unit normalization (Cymbal grocery + GM)."""
import pytest

from app.normalizer import normalize, parse_allergens, parse_dimensions, parse_months


@pytest.mark.parametrize("key,raw,value,unit", [
    ("net_weight_g", "3切（約240g）", 240, "g"),
    ("net_weight_g", "1kg", 1000, "g"),
    ("net_weight_g", "１．５ｋｇ", 1500, "g"),
    ("net_weight_g", "200g×3袋", 600, "g"),
    ("net_weight_g", "450g（150g×3個）", 450, "g"),
    ("net_volume_ml", "1.8L", 1800, "ml"),
    ("net_volume_ml", "700ml×3個", 700, "ml"),
    ("net_volume_ml", "詰替用 大容量 1200ml", 1200, "ml"),
    ("pack_count", "10個入", 10, "個"),
    ("pack_count", "3切（約240g）", 3, "個"),
    ("pack_count", "40g×12袋", 12, "個"),
    ("pack_count", "北海道産 生さんま 2尾", 2, "個"),
    ("servings", "4人前", 4, "人前"),
    ("servings", "10皿分", 10, "人前"),
    ("best_before_days", "製造日より12ヶ月", 360, "日"),
    ("best_before_days", "1年", 365, "日"),
    ("best_before_days", "180日", 180, "日"),
    ("cook_time_min", "600Wで約2分30秒", 2.5, "分"),
    ("cook_time_min", "5分", 5, "分"),
    ("width_cm", "幅45×奥行45×高さ40cm", 45, "cm"),
    ("depth_cm", "W42×D54×H42cm", 54, "cm"),
    ("height_cm", "幅45×奥行45×高さ40cm", 40, "cm"),
    ("width_cm", "37×22cm", 37, "cm"),
    ("depth_cm", "370×220mm", 22, "cm"),
    ("diameter_cm", "直径26×深さ7.5cm", 26, "cm"),
    ("diameter_cm", "28cm", 28, "cm"),
])
def test_numeric(key, raw, value, unit):
    r = normalize(key, raw)
    assert r.ok, r.note
    assert r.value == pytest.approx(value) and r.unit == unit


@pytest.mark.parametrize("raw,value", [
    ("冷蔵食品", "冷蔵"), ("要冷蔵（10℃以下）", "冷蔵"), ("-18℃以下で保存", "冷凍"), ("冷凍食品", "冷凍"),
    ("直射日光・高温多湿を避けて保存", "常温"), ("常温食品", "常温"),
])
def test_storage(raw, value):
    r = normalize("storage_method", raw)
    assert r.ok and r.value == value


def test_storage_unknown_fails():
    assert not normalize("storage_method", "お早めにお召し上がりください").ok


@pytest.mark.parametrize("raw,value", [
    ("特定原材料：えび・小麦・卵・乳", "えび・小麦・卵・乳"),
    ("特定原材料：乳成分・大豆", "乳・大豆"),
    ("アレルゲン：海老、カニ", "えび・かに"),
    ("小麦・大豆・鶏肉", "小麦・大豆・鶏肉"),
    ("特定原材料：なし", "なし"),
    ("allergens: なし", "なし"),
    ("■アレルギー 特定原材料：小麦・卵・乳", "小麦・卵・乳"),
])
def test_allergens(raw, value):
    r = normalize("allergens", raw)
    assert r.ok, r.note
    assert r.value == value


def test_allergens_unknown_token_fails():
    items, note = parse_allergens("特定原材料：小麦・ナツメグ")
    assert items is None and "ナツメグ" in note
    assert not normalize("allergens", "特定原材料：小麦・ナツメグ").ok


def test_allergen_order_is_canonical():
    items, _ = parse_allergens("乳・えび・小麦")
    assert items == ["えび", "小麦", "乳"]


def test_months():
    assert parse_months("10月〜2月") == [10, 11, 12, 1, 2]
    assert parse_months("10 / 11 / 12") == [10, 11, 12]
    assert normalize("season", "旬：9月〜11月").value == "9月〜11月"
    assert normalize("season", "秋").value == "9月〜11月"


def test_bool_and_pet():
    assert normalize("ih_compatible", "IH・ガス火対応").value is True
    assert normalize("ih_compatible", "ガス火専用").value is False
    assert normalize("dishwasher_safe", "食洗機不可").value is False
    assert normalize("target_pet", "シニア犬用ドッグフード").value == "犬"
    assert normalize("target_pet", "猫用パウチ").value == "猫"


def test_dimensions_assumed_order():
    d = parse_dimensions("45×45×40cm")
    assert d["w"] == 45 and d["d"] == 45 and d["h"] == 40 and d["_assumed"]


def test_unknown_key():
    assert not normalize("tatami", "6畳").ok
