# -*- coding: utf-8 -*-
"""
東証（東京証券取引所）カレンダー＆営業日計算ユーティリティ (calendar_util.py)

東証の休場日ルール:
1. 土曜日・日曜日
2. 国民の祝日および振替休日・国民の休日
3. 年末年始（12月31日、1月1日、1月2日、1月3日）
"""

import math
from datetime import date, timedelta
from typing import List, Set


def get_vernal_equinox_day(year: int) -> int:
    """春分の日（3月）の日にちを計算（1980〜2099年対応の天文学的略算式）"""
    if year < 1980 or year > 2099:
        return 20
    return int(20.8431 + 0.242194 * (year - 1980) - int((year - 1980) / 4))


def get_autumnal_equinox_day(year: int) -> int:
    """秋分の日（9月）の日にちを計算（1980〜2099年対応の天文学的略算式）"""
    if year < 1980 or year > 2099:
        return 23
    return int(23.2488 + 0.242194 * (year - 1980) - int((year - 1980) / 4))


def get_nth_monday(year: int, month: int, n: int) -> date:
    """第n月曜日を計算（ハッピーマンデー用）"""
    first_day = date(year, month, 1)
    # first_day.weekday(): 0=月曜, 1=火曜, ..., 6=日曜
    offset = (0 - first_day.weekday()) % 7
    first_monday = first_day + timedelta(days=offset)
    return first_monday + timedelta(weeks=n - 1)


def get_japanese_holidays(year: int) -> Set[date]:
    """指定された年の日本の祝日（振替休日・国民の休日を含む）セットを返す"""
    holidays: Set[date] = set()

    # 固定祝日
    fixed_holidays = [
        (1, 1),    # 元日
        (2, 11),   # 建国記念の日
        (2, 23),   # 天皇誕生日 (2020年以降)
        (4, 29),   # 昭和の日
        (5, 3),    # 憲法記念日
        (5, 4),    # みどりの日
        (5, 5),    # こどもの日
        (8, 11),   # 山の日
        (11, 3),   # 文化の日
        (11, 23),  # 勤労感謝の日
    ]
    for m, d in fixed_holidays:
        holidays.add(date(year, m, d))

    # ハッピーマンデー祝日
    holidays.add(get_nth_monday(year, 1, 2))  # 成人の日: 1月第2月曜日
    holidays.add(get_nth_monday(year, 7, 3))  # 海の日: 7月第3月曜日
    holidays.add(get_nth_monday(year, 9, 3))  # 敬老の日: 9月第3月曜日
    holidays.add(get_nth_monday(year, 10, 2)) # スポーツの日: 10月第2月曜日

    # 春分の日・秋分の日
    holidays.add(date(year, 3, get_vernal_equinox_day(year)))
    holidays.add(date(year, 9, get_autumnal_equinox_day(year)))

    # 国民の休日（祝日と祝日に挟まれた平日）の判定
    # 例: 9月の敬老の日と秋分の日の間の火曜日など
    sorted_holidays = sorted(holidays)
    national_holidays = set()
    for i in range(len(sorted_holidays) - 1):
        d1 = sorted_holidays[i]
        d2 = sorted_holidays[i + 1]
        if (d2 - d1).days == 2:
            between_day = d1 + timedelta(days=1)
            # 日曜でなければ国民の休日
            if between_day.weekday() != 6:
                national_holidays.add(between_day)
    holidays.update(national_holidays)

    # 振替休日の判定
    # 祝日が日曜日の場合、その日後において最も近い「国民の祝日でない日」を振替休日とする
    substitute_holidays = set()
    for h in sorted(holidays):
        if h.weekday() == 6:  # 日曜日
            sub = h + timedelta(days=1)
            while sub in holidays or sub in substitute_holidays:
                sub += timedelta(days=1)
            substitute_holidays.add(sub)
    holidays.update(substitute_holidays)

    return holidays


def is_tse_trading_day(target_date: date) -> bool:
    """東証の立会日（営業日）であるかを判定"""
    # 1. 土日
    if target_date.weekday() in (5, 6):
        return False

    # 2. 年末年始（12/31, 1/1, 1/2, 1/3）
    m, d = target_date.month, target_date.day
    if (m == 12 and d == 31) or (m == 1 and d in (1, 2, 3)):
        return False

    # 3. 祝日判定
    holidays = get_japanese_holidays(target_date.year)
    if target_date in holidays:
        return False

    return True


def get_tse_business_days_between(start_date: date, end_date: date) -> int:
    """
    start_date の翌日（または今日が休場なら次の日から）から end_date までの
    東証営業日数（両端は start_dateを含まず、end_dateを含む）を算出。
    ※start_date >= end_date の場合は 0。
    """
    if start_date >= end_date:
        return 0

    count = 0
    cur = start_date + timedelta(days=1)
    while cur <= end_date:
        if is_tse_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count
