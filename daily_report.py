#!/usr/bin/env python3
"""Утренняя сводка в Telegram: давление в Казани и магнитное поле Земли.

Запускается раз в сутки в 04:30 по Москве. Использует функции из
check_pressure.py и storm_check.py, лежащих рядом.
"""
import sys

import check_pressure as cp
import storm_check as sc


def pressure_text():
    data = cp.fetch_data()
    cur = data["current"]
    p = cur["surface_pressure"] * cp.HPA_TO_MMHG

    times = data["hourly"]["time"]
    vals = [v * cp.HPA_TO_MMHG for v in data["hourly"]["surface_pressure"]]
    idx = max(i for i, t in enumerate(times) if t <= cur["time"])
    d3 = vals[idx] - vals[idx - 3] if idx >= 3 else None

    names = {"ok": "в норме", "high": "выше нормы", "low": "ниже нормы"}
    status = names[cp.status_of(p)]
    norm = "норма %d–%d" % (cp.LOW, cp.HIGH)

    text = "Давление в Казани: %.1f мм рт. ст., %s (%s)." % (p, status, norm)
    if d3 is not None:
        text += "\nЗа 3 часа: %+.1f мм" % d3
        if abs(d3) >= cp.JUMP:
            text += " (резкий перепад)"
        text += "."
    return text


def magnetic_text():
    _, kp = sc.fetch_kp()
    level = sc.g_level(kp)
    if level > 0:
        return "Магнитная буря: %s, Kp %.2f." % (sc.label(level), kp)
    if kp >= 4:
        return "Магнитное поле: слегка возмущённое, бури нет, Kp %.2f." % kp
    return "Магнитное поле: спокойное, бури нет, Kp %.2f." % kp


def main():
    if not cp.TOKEN or not cp.CHAT_ID:
        print("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1

    parts = []
    failed = 0
    for fn, name in ((pressure_text, "Давление"), (magnetic_text, "Магнитное поле")):
        try:
            parts.append(fn())
        except Exception as e:
            failed += 1
            print("%s: ошибка: %s" % (name, e), file=sys.stderr)
            parts.append("%s: не удалось получить данные." % name)

    cp.send_telegram("Утренняя сводка\n\n" + "\n\n".join(parts))
    print("sent, failed_sources=%d" % failed)
    return 1 if failed == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
