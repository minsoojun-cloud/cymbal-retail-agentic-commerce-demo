"""Excel Importer for the 6 `*機能表入力シート.xlsx` templates.

Auto-detects the category (`tv`, `pc`, `wine_cellar`, `cooler_warmer`, `freezer`, `refrigerator`)
from sheet names and header cells, parses all populated rows, and returns normalized items.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
from typing import Any

import openpyxl

from edion_banner.category_schemas import default_specs_for_category


def _clean_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    if isinstance(val, dt.datetime):
        return f"{val.year}年{val.month}月{val.day}日"
    if isinstance(val, dt.date):
        return f"{val.year}年{val.month}月{val.day}日"
    s = str(val).strip()
    if s in ("-", "None", "null"):
        return default
    return s


def _clean_circle(val: Any, default: str = "×") -> str:
    s = _clean_str(val)
    if s in ("〇", "○", "◯", "O", "o", "有", "対応", "true", "True", "1"):
        return "○"
    if s in ("×", "✕", "X", "x", "無", "非対応", "false", "False", "0"):
        return "×"
    return default


def _clean_tv_circle(val: Any, default: str = "×") -> str:
    return "〇" if _clean_circle(val, default) == "○" else "×"


def _dummy_jan(model_no: str) -> str:
    h = int(hashlib.md5(model_no.encode()).hexdigest(), 16)
    return f"49{h % 100000000000:011d}"


def detect_excel_category(wb: openpyxl.Workbook, filename: str = "") -> str:
    fn = filename or ""
    if "ワインセラー" in wb.sheetnames or "ワインセラー" in fn:
        return "wine_cellar"
    if "冷温庫" in wb.sheetnames or "冷温庫" in fn:
        return "cooler_warmer"
    ws = wb[wb.sheetnames[0]]
    dump = " ".join(
        str(ws.cell(r, c).value or "")
        for r in range(1, min(22, ws.max_row + 1))
        for c in range(1, min(35, ws.max_column + 1))
    )
    if "ネット動画対応コンテンツ" in dump or "おすすめ\n畳数" in dump or "テレビ" in fn:
        return "tv"
    if "Copilot+ PC" in dump or "NPU" in dump or "パソコン" in fn:
        return "pc"
    if "350L以上" in dump or "真ん中◯◯◯室" in dump or "冷蔵庫" in fn:
        return "refrigerator"
    if "急速冷凍" in dump or "冷凍・\n冷蔵\n切替" in dump or "冷凍庫" in fn:
        return "freezer"
    return "tv"


def parse_kinohyo_excel(content: bytes, filename: str = "") -> dict[str, Any]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    category = detect_excel_category(wb, filename)
    ws = wb[wb.sheetnames[0]]
    items: list[dict[str, Any]] = []

    if category == "tv":
        # Data rows start at row 18 (row 18 is 入力例, 19+ are numbered rows)
        for r in range(18, ws.max_row + 1):
            maker = _clean_str(ws.cell(r, 2).value)
            model_no = _clean_str(ws.cell(r, 4).value)
            if not maker and not model_no:
                continue
            jan = _clean_str(ws.cell(r, 5).value) or _dummy_jan(model_no)
            specs = default_specs_for_category("tv")
            specs.update(
                {
                    "maker": maker or "SONY",
                    "brand": _clean_str(ws.cell(r, 3).value, "BRAVIA"),
                    "model_no": model_no,
                    "jan_code": jan,
                    "type": _clean_str(ws.cell(r, 6).value, "MiniLED"),
                    "screen_size": ws.cell(r, 7).value or 50,
                    "display_method": _clean_str(ws.cell(r, 8).value, "量子ドット"),
                    "double_speed": _clean_tv_circle(ws.cell(r, 9).value, "〇"),
                    "smart_tv": _clean_str(ws.cell(r, 10).value, "Google TV"),
                    "dual_screen": _clean_tv_circle(ws.cell(r, 11).value, "×"),
                    "resolution": _clean_str(ws.cell(r, 12).value, "3840×2160"),
                    "recording": _clean_str(ws.cell(r, 13).value, "外付けHDD、W録画対応"),
                    "recommended_tatami": f"{_clean_str(ws.cell(r, 14).value, '8')}畳程度"
                    if not str(ws.cell(r, 14).value or "").endswith("程度")
                    else _clean_str(ws.cell(r, 14).value),
                    "viewing_distance": f"約 {_clean_str(ws.cell(r, 15).value, '1.0')} m~"
                    if "m" not in str(ws.cell(r, 15).value or "")
                    else _clean_str(ws.cell(r, 15).value),
                    "vod_netflix": _clean_tv_circle(ws.cell(r, 16).value, "〇"),
                    "vod_youtube": _clean_tv_circle(ws.cell(r, 17).value, "〇"),
                    "vod_unext": _clean_tv_circle(ws.cell(r, 18).value, "〇"),
                    "vod_tver": _clean_tv_circle(ws.cell(r, 19).value, "〇"),
                    "vod_prime": _clean_tv_circle(ws.cell(r, 20).value, "〇"),
                    "vod_abema": _clean_tv_circle(ws.cell(r, 21).value, "〇"),
                    "vod_disney": _clean_tv_circle(ws.cell(r, 22).value, "〇"),
                    "vod_dazn": _clean_tv_circle(ws.cell(r, 23).value, "〇"),
                    "vod_hulu": _clean_tv_circle(ws.cell(r, 24).value, "〇"),
                    "vod_lemino": _clean_tv_circle(ws.cell(r, 25).value, "〇"),
                    "tuner_terrestrial": ws.cell(r, 26).value if ws.cell(r, 26).value is not None else 3,
                    "tuner_bs_cs": ws.cell(r, 27).value if ws.cell(r, 27).value is not None else 3,
                    "tuner_bs4k": ws.cell(r, 28).value if ws.cell(r, 28).value is not None else 3,
                    "tuner_bs8k": ws.cell(r, 29).value if ws.cell(r, 29).value is not None else 0,
                    "audio_output": _clean_str(ws.cell(r, 30).value, "40W"),
                    "input_hdmi": _clean_str(ws.cell(r, 31).value, "4"),
                    "input_analog_audio": _clean_str(ws.cell(r, 32).value, "0"),
                    "input_video": _clean_str(ws.cell(r, 33).value, "0"),
                    "input_usb": _clean_str(ws.cell(r, 34).value, "2"),
                    "width_cm": _clean_str(ws.cell(r, 35).value, "122.8"),
                    "width_stand_cm": _clean_str(ws.cell(r, 36).value, "40.8"),
                    "height_cm": _clean_str(ws.cell(r, 37).value, "70.9"),
                    "height_stand_cm": _clean_str(ws.cell(r, 38).value, "73.9"),
                    "depth_cm": _clean_str(ws.cell(r, 39).value, "5.7"),
                    "depth_stand_cm": _clean_str(ws.cell(r, 40).value, "21.0"),
                    "weight_kg": _clean_str(ws.cell(r, 41).value, "18.8"),
                    "energy_star": _clean_str(ws.cell(r, 42).value, "3.0"),
                    "power_consumption_w": _clean_str(ws.cell(r, 43).value, "190"),
                    "energy_achievement_pct": _clean_str(ws.cell(r, 44).value, "100"),
                    "annual_power_kwh": _clean_str(ws.cell(r, 45).value, "123"),
                    "annual_elec_bill_yen": f"{int(ws.cell(r, 46).value):,}"
                    if isinstance(ws.cell(r, 46).value, (int, float))
                    else _clean_str(ws.cell(r, 46).value, "3,320"),
                }
            )
            items.append(
                {
                    "category": "tv",
                    "jan_code": jan,
                    "search_model_no": model_no,
                    "maker_name": maker,
                    "product_name": f"{specs['type']}テレビ {specs['screen_size']}V型",
                    "class_code": "31110500",
                    "edion_price": 218000,
                    "specs": specs,
                }
            )

    elif category == "pc":
        # Data rows start at row 19
        for r in range(19, ws.max_row + 1):
            maker = _clean_str(ws.cell(r, 2).value)
            model_no = _clean_str(ws.cell(r, 4).value)
            if not maker and not model_no:
                continue
            jan = _clean_str(ws.cell(r, 6).value) or _dummy_jan(model_no)
            batt_raw = _clean_str(ws.cell(r, 24).value)
            nums = re.findall(r"\d+(?:\.\d+)?", batt_raw.replace("3.0", ""))
            vid_h = nums[0] if len(nums) >= 1 else "13.5"
            idle_h = nums[1] if len(nums) >= 2 else "20.0"
            cpu_str = _clean_str(ws.cell(r, 9).value, "Intel Core Ultra7 155H")
            badge_short = "Ultra 7"
            if "X2 Plus" in cpu_str:
                badge_short = "X2 Plus"
            elif "X Elite" in cpu_str:
                badge_short = "X Elite"
            elif "Ultra5" in cpu_str or "Ultra 5" in cpu_str:
                badge_short = "Ultra 5"
            elif "Ryzen" in cpu_str:
                badge_short = "Ryzen AI"

            specs = default_specs_for_category("pc")
            specs.update(
                {
                    "maker": maker,
                    "brand_logo": _clean_str(ws.cell(r, 3).value, maker),
                    "model_no": model_no,
                    "base_model_no": _clean_str(ws.cell(r, 5).value or ws.cell(r, 25).value),
                    "jan_code": jan,
                    "release_date": _clean_str(ws.cell(r, 7).value, "2026年10月13日"),
                    "class_name": _clean_str(ws.cell(r, 8).value, "モバイル高性能"),
                    "cpu_series": cpu_str,
                    "cpu_badge_short": badge_short,
                    "npu_tops": _clean_str(ws.cell(r, 10).value, "45"),
                    "copilot_plus": _clean_circle(ws.cell(r, 11).value, "○"),
                    "storage_type": _clean_str(ws.cell(r, 12).value, "SSD"),
                    "storage_capacity": _clean_str(ws.cell(r, 13).value, "512GB"),
                    "memory_gb": _clean_str(ws.cell(r, 14).value, "16"),
                    "office": _clean_str(ws.cell(r, 15).value),
                    "display_inch": _clean_str(ws.cell(r, 16).value, "14.0"),
                    "display_pixels": _clean_str(ws.cell(r, 17).value, "1920×1200"),
                    "touch_support": _clean_circle(ws.cell(r, 18).value, "○"),
                    "refresh_rate": _clean_str(ws.cell(r, 19).value, "60Hz"),
                    "graphics": _clean_str(ws.cell(r, 20).value),
                    "weight_kg": _clean_str(ws.cell(r, 21).value, "1.2"),
                    "optical_drive": _clean_str(ws.cell(r, 22).value, "なし"),
                    "mouse": _clean_str(ws.cell(r, 23).value, "なし"),
                    "battery_video_hours": vid_h,
                    "battery_idle_hours": idle_h,
                    "battery_raw": batt_raw,
                    "original_point_1": _clean_str(ws.cell(r, 26).value),
                    "original_point_2": _clean_str(ws.cell(r, 27).value),
                    "original_point_3": _clean_str(ws.cell(r, 28).value),
                }
            )
            items.append(
                {
                    "category": "pc",
                    "jan_code": jan,
                    "search_model_no": model_no,
                    "maker_name": maker,
                    "product_name": f"{specs['brand_logo']} {specs['display_inch']}型ノートPC",
                    "class_code": "41218200",
                    "edion_price": 189800,
                    "specs": specs,
                }
            )

    elif category == "wine_cellar":
        for r in range(14, ws.max_row + 1):
            maker = _clean_str(ws.cell(r, 2).value)
            model_no = _clean_str(ws.cell(r, 3).value)
            if not maker and not model_no:
                continue
            jan = _dummy_jan(model_no)
            specs = default_specs_for_category("wine_cellar")
            specs.update(
                {
                    "maker": maker,
                    "model_no": model_no,
                    "jan_code": jan,
                    "cooling_type": _clean_str(ws.cell(r, 4).value, "ペルチェ方式"),
                    "capacity_l": ws.cell(r, 5).value or 25,
                    "bottle_count": ws.cell(r, 6).value or 8,
                    "shelf_adjustable": _clean_circle(ws.cell(r, 7).value, "×"),
                    "temp_range_single": _clean_str(ws.cell(r, 8).value, "5〜20"),
                    "temp_range_upper": _clean_str(ws.cell(r, 9).value, ""),
                    "temp_range_lower": _clean_str(ws.cell(r, 10).value, ""),
                    "temp_maintain": _clean_circle(ws.cell(r, 11).value, "×"),
                    "annual_power_kwh": ws.cell(r, 12).value or 100,
                    "annual_elec_bill_yen": f"{int(ws.cell(r, 13).value):,}"
                    if isinstance(ws.cell(r, 13).value, (int, float))
                    else _clean_str(ws.cell(r, 13).value, "1,263"),
                    "width_mm": ws.cell(r, 14).value or 252,
                    "height_mm": ws.cell(r, 15).value or 450,
                    "depth_mm": ws.cell(r, 16).value or 500,
                    "weight_kg": _clean_str(ws.cell(r, 17).value, "9.5"),
                }
            )
            items.append(
                {
                    "category": "wine_cellar",
                    "jan_code": jan,
                    "search_model_no": model_no,
                    "maker_name": maker,
                    "product_name": f"ワインセラー {specs['bottle_count']}本 {specs['capacity_l']}L",
                    "class_code": "13401001",
                    "edion_price": 19800,
                    "specs": specs,
                }
            )

    elif category == "cooler_warmer":
        for r in range(14, ws.max_row + 1):
            maker = _clean_str(ws.cell(r, 2).value)
            model_no = _clean_str(ws.cell(r, 3).value)
            if not maker and not model_no:
                continue
            jan = _clean_str(ws.cell(r, 4).value) or _dummy_jan(model_no)
            specs = default_specs_for_category("cooler_warmer")
            specs.update(
                {
                    "maker": maker,
                    "model_no": model_no,
                    "jan_code": jan,
                    "cooling_type": _clean_str(ws.cell(r, 5).value, "ペルチェ方式"),
                    "capacity_l": 24,
                    "pet_500ml_count": ws.cell(r, 6).value or 14,
                    "can_350ml_count": ws.cell(r, 7).value or 17,
                    "cool_temp_c": _clean_str(ws.cell(r, 8).value, "-9"),
                    "warm_temp_c": _clean_str(ws.cell(r, 9).value, "60"),
                    "power_ac": _clean_circle(ws.cell(r, 10).value, "○"),
                    "cord_ac_m": _clean_str(ws.cell(r, 11).value, "1.5"),
                    "power_dc": _clean_circle(ws.cell(r, 12).value, "○"),
                    "cord_dc_m": _clean_str(ws.cell(r, 13).value, "1.5"),
                    "width_mm": ws.cell(r, 14).value or 310,
                    "height_mm": ws.cell(r, 15).value or 460,
                    "depth_mm": ws.cell(r, 16).value or 375,
                    "weight_kg": _clean_str(ws.cell(r, 17).value, "8.0"),
                }
            )
            items.append(
                {
                    "category": "cooler_warmer",
                    "jan_code": jan,
                    "search_model_no": model_no,
                    "maker_name": maker,
                    "product_name": f"冷温庫 {specs['capacity_l']}L",
                    "class_code": "13402001",
                    "edion_price": 15800,
                    "specs": specs,
                }
            )

    elif category == "freezer":
        for r in range(11, ws.max_row + 1):
            maker = _clean_str(ws.cell(r, 2).value)
            model_no = _clean_str(ws.cell(r, 3).value)
            if not maker and not model_no:
                continue
            jan = _clean_str(ws.cell(r, 6).value) or _dummy_jan(model_no)
            specs = default_specs_for_category("freezer")
            specs.update(
                {
                    "maker": maker,
                    "model_no": model_no,
                    "door_open_type": _clean_str(ws.cell(r, 4).value, "右開き").replace("のみ", ""),
                    "color_name": _clean_str(ws.cell(r, 5).value, "(W) ホワイト"),
                    "jan_code": jan,
                    "capacity_l": ws.cell(r, 7).value or 105,
                    "food_space_l": ws.cell(r, 8).value or 72,
                    "door_count": ws.cell(r, 9).value or 1,
                    "door_layout": _clean_str(ws.cell(r, 10).value, "扉1枚B"),
                    "comp1_name": _clean_str(ws.cell(r, 11).value, "冷凍室"),
                    "comp1_capacity_l": ws.cell(r, 12).value or 105,
                    "comp1_food_space_l": ws.cell(r, 13).value or 72,
                    "comp2_name": _clean_str(ws.cell(r, 14).value, ""),
                    "comp2_capacity_l": ws.cell(r, 15).value or "",
                    "comp2_food_space_l": ws.cell(r, 16).value or "",
                    "height_cm": _clean_str(ws.cell(r, 29).value, "145.5"),
                    "width_cm": _clean_str(ws.cell(r, 30).value, "36.0"),
                    "depth_cm": _clean_str(ws.cell(r, 31).value, "63.5"),
                    "depth_body_only_cm": _clean_str(ws.cell(r, 32).value, "63.5"),
                    "depth_door_open_cm": _clean_str(ws.cell(r, 33).value, "95.3"),
                    "clearance_side_cm": _clean_str(ws.cell(r, 34).value, "2"),
                    "clearance_top_cm": _clean_str(ws.cell(r, 35).value, "10"),
                    "clearance_back_cm": _clean_str(ws.cell(r, 36).value, "0"),
                    "weight_kg": _clean_str(ws.cell(r, 37).value, "37"),
                    "feat_led": _clean_circle(ws.cell(r, 38).value, "×"),
                    "feat_quick_freeze": _clean_circle(ws.cell(r, 39).value, "×"),
                    "feat_mode_switch": _clean_circle(ws.cell(r, 40).value, "×"),
                    "feat_heat_top": _clean_circle(ws.cell(r, 41).value, "×"),
                    "energy_star": _clean_str(ws.cell(r, 42).value, "2.1"),
                    "energy_target_year": f"{_clean_str(ws.cell(r, 43).value, '2021')}年度"
                    if "年度" not in _clean_str(ws.cell(r, 43).value)
                    else _clean_str(ws.cell(r, 43).value),
                    "energy_achievement_pct": _clean_str(ws.cell(r, 44).value, "114"),
                    "annual_power_kwh": _clean_str(ws.cell(r, 45).value, "320"),
                    "annual_elec_bill_yen": f"{int(ws.cell(r, 46).value):,}"
                    if isinstance(ws.cell(r, 46).value, (int, float))
                    else _clean_str(ws.cell(r, 46).value, "8,640"),
                    "point_text": _clean_str(ws.cell(r, 47).value, "横幅36cmのスリムタイプ"),
                    "base_model_no": _clean_str(ws.cell(r, 48).value),
                    "original_point_1": _clean_str(ws.cell(r, 49).value),
                    "original_point_2": _clean_str(ws.cell(r, 50).value),
                    "original_point_3": _clean_str(ws.cell(r, 51).value),
                }
            )
            items.append(
                {
                    "category": "freezer",
                    "jan_code": jan,
                    "search_model_no": model_no,
                    "maker_name": maker,
                    "product_name": f"冷凍庫 {specs['capacity_l']}L",
                    "class_code": "13201001",
                    "edion_price": 49800,
                    "specs": specs,
                }
            )

    elif category == "refrigerator":
        for r in range(11, ws.max_row + 1):
            maker = _clean_str(ws.cell(r, 3).value)
            model_no = _clean_str(ws.cell(r, 4).value)
            if not maker and not model_no:
                continue
            jan = _clean_str(ws.cell(r, 9).value) or _dummy_jan(model_no)
            cap = int(float(ws.cell(r, 5).value or 501))
            specs = default_specs_for_category("refrigerator")
            specs.update(
                {
                    "long_warranty": _clean_str(ws.cell(r, 2).value, "10年"),
                    "maker": maker,
                    "model_no": model_no,
                    "capacity_l": cap,
                    "food_space_l": int(float(ws.cell(r, 6).value or 353)),
                    "door_open_type": _clean_str(ws.cell(r, 7).value, "フレンチドア"),
                    "color_name": _clean_str(ws.cell(r, 8).value, "(TW) フロストホワイト"),
                    "jan_code": jan,
                    "color2_model_no": _clean_str(ws.cell(r, 10).value),
                    "color2_name": _clean_str(ws.cell(r, 11).value),
                    "color2_jan": _clean_str(ws.cell(r, 12).value),
                    "high_freshness": _clean_circle(ws.cell(r, 23).value, "○"),
                    "middle_compartment_label": _clean_str(ws.cell(r, 24).value, "真ん中野菜室"),
                    "cooling_method": _clean_str(ws.cell(r, 26).value, "ファン式"),
                    "inverter": _clean_circle(ws.cell(r, 27).value, "○"),
                    "freezer_position_label": _clean_str(ws.cell(r, 28).value, "下段冷凍室"),
                    "auto_defrost": _clean_circle(ws.cell(r, 29).value, "○"),
                    "fridge_light": _clean_circle(ws.cell(r, 30).value, "○"),
                    "heat_top_table": _clean_circle(ws.cell(r, 31).value, "×"),
                    "smartphone_link": _clean_circle(ws.cell(r, 33).value, "○"),
                    "edion_smart_app": _clean_circle(ws.cell(r, 34).value, "×"),
                    "auto_ice": _clean_circle(ws.cell(r, 35).value, "○"),
                    "door_count": int(float(ws.cell(r, 36).value or 5)),
                    "door_layout": _clean_str(ws.cell(r, 37).value, "扉5枚A"),
                    "comp1_name": _clean_str(ws.cell(r, 38).value, "冷蔵室"),
                    "comp1_capacity_l": ws.cell(r, 39).value or 257,
                    "comp1_food_space_l": ws.cell(r, 40).value or 202,
                    "comp2_name": _clean_str(ws.cell(r, 41).value, "野菜室"),
                    "comp2_capacity_l": ws.cell(r, 42).value or 98,
                    "comp2_food_space_l": ws.cell(r, 43).value or 62,
                    "comp3_name": _clean_str(ws.cell(r, 44).value, "製氷室"),
                    "comp3_capacity_l": ws.cell(r, 45).value or "",
                    "comp3_food_space_l": ws.cell(r, 46).value or "",
                    "comp4_name": _clean_str(ws.cell(r, 47).value, ""),
                    "comp4_capacity_l": ws.cell(r, 48).value or "",
                    "comp4_food_space_l": ws.cell(r, 49).value or "",
                    "comp5_name": _clean_str(ws.cell(r, 50).value, ""),
                    "comp5_capacity_l": ws.cell(r, 51).value or "",
                    "comp5_food_space_l": ws.cell(r, 52).value or "",
                    "comp6_name": _clean_str(ws.cell(r, 53).value, ""),
                    "comp6_capacity_l": _clean_str(ws.cell(r, 54).value, ""),
                    "comp6_food_space_l": _clean_str(ws.cell(r, 55).value, ""),
                    "height_cm": _clean_str(ws.cell(r, 56).value, "185.0"),
                    "width_cm": _clean_str(ws.cell(r, 57).value, "60.0"),
                    "depth_cm": _clean_str(ws.cell(r, 58).value, "70.7"),
                    "depth_body_only_cm": _clean_str(ws.cell(r, 59).value, "70.4"),
                    "depth_door_open_cm": _clean_str(ws.cell(r, 60).value, "126.8"),
                    "clearance_side_cm": _clean_str(ws.cell(r, 61).value, "0.5"),
                    "clearance_top_cm": _clean_str(ws.cell(r, 62).value, "5"),
                    "clearance_back_cm": _clean_str(ws.cell(r, 63).value, "0"),
                    "weight_kg": _clean_str(ws.cell(r, 64).value, "108"),
                    "energy_star": _clean_str(ws.cell(r, 65).value, "3.5"),
                    "energy_target_year": f"{_clean_str(ws.cell(r, 66).value, '2021')}年度"
                    if "年度" not in _clean_str(ws.cell(r, 66).value)
                    else _clean_str(ws.cell(r, 66).value),
                    "energy_achievement_pct": _clean_str(ws.cell(r, 67).value, "101"),
                    "annual_power_kwh": _clean_str(ws.cell(r, 68).value, "279"),
                    "annual_elec_bill_yen": f"{int(ws.cell(r, 69).value):,}"
                    if isinstance(ws.cell(r, 69).value, (int, float))
                    else _clean_str(ws.cell(r, 69).value, "7,530"),
                    "feature_fridge": _clean_str(ws.cell(r, 70).value),
                    "feature_freezer": _clean_str(ws.cell(r, 71).value),
                    "feature_veggie": _clean_str(ws.cell(r, 72).value),
                    "base_model_no": _clean_str(ws.cell(r, 74).value),
                    "original_point_1": _clean_str(ws.cell(r, 75).value),
                    "original_point_2": _clean_str(ws.cell(r, 76).value),
                    "original_point_3": _clean_str(ws.cell(r, 77).value),
                }
            )
            items.append(
                {
                    "category": "refrigerator",
                    "jan_code": jan,
                    "search_model_no": model_no,
                    "maker_name": maker,
                    "product_name": f"{specs['door_count']}ドア冷蔵庫 {cap}L",
                    "class_code": "13105500",
                    "edion_price": 248000 if cap >= 350 else 89800,
                    "specs": specs,
                }
            )

    return {"category": category, "items": items}
