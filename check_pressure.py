#!/usr/bin/env python3
"""Проверка атмосферного давления в Казани и уведомления в Telegram.

Запускается по расписанию в GitHub Actions. Помнит прошлый статус в state.json,
поэтому пишет только при изменении: выше нормы, ниже нормы, вернулось в норму
или резкий перепад.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

LAT, LON = 55.79, 49.12          # Казань
HPA_TO_MMHG = 0.750062
LOW, HIGH = 744.0, 764.0         # норма, мм рт. ст. (как на Яндекс.Погоде)
JUMP = 3.0                       # резкий перепад: мм рт. ст. за 3 часа
STATE_FILE = "state.json"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
FORCE_REPORT = os.environ.get("FORCE_REPORT") == "1"


def fetch_data():
    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": "surface_pressure",
        "hourly": "surface_pressure",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "Europe/Moscow",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    last_error = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.load(resp)
        except Exception as e:  # повторяем при сетевых сбоях
            last_error = e
            time.sleep(5)
    raise last_error


def status_of(p):
    if p > HIGH:
        return "high"
    if p < LOW:
        return "low"
    return "ok"


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, sort_keys=True, indent=1)
        f.write("\n")


def send_telegram(text):
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    body = json.dumps({"chat_id": CHAT_ID, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def main():
    if not TOKEN or not CHAT_ID:
        print("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1

    data = fetch_data()
    cur = data["current"]
    p = cur["surface_pressure"] * HPA_TO_MMHG

    times = data["hourly"]["time"]
    vals = [v * HPA_TO_MMHG for v in data["hourly"]["surface_pressure"]]
    idx = max(i for i, t in enumerate(times) if t <= cur["time"])
    d3 = vals[idx] - vals[idx - 3] if idx >= 3 else None

    status = status_of(p)
    is_jump = d3 is not None and abs(d3) >= JUMP

    state = load_state()
    prev_status = state.get("status")
    prev_jump = bool(state.get("jump", False))

    norm = "норма %d–%d" % (LOW, HIGH)
    messages = []

    if prev_status is None:
        names = {"ok": "в норме", "high": "выше нормы", "low": "ниже нормы"}
        messages.append(
            "Бот запущен. Давление в Казани сейчас %.1f мм рт. ст., %s (%s)."
            % (p, names[status], norm)
        )
    elif status != prev_status:
        if status == "ok":
            messages.append(
                "Давление вернулось в норму: %.1f мм рт. ст. (%s)." % (p, norm)
            )
        elif status == "high":
            messages.append(
                "Давление поднялось выше нормы: %.1f мм рт. ст. (%s)." % (p, norm)
            )
        else:
            messages.append(
                "Давление опустилось ниже нормы: %.1f мм рт. ст. (%s)." % (p, norm)
            )

    if is_jump and not prev_jump:
        word = "выросло" if d3 > 0 else "упало"
        messages.append(
            "Резкий перепад: давление %s на %.1f мм рт. ст. за 3 часа. "
            "Сейчас %.1f мм рт. ст." % (word, abs(d3), p)
        )

    if FORCE_REPORT and not messages:
        names = {"ok": "в норме", "high": "выше нормы", "low": "ниже нормы"}
        change = "нет данных" if d3 is None else "%+.1f мм за 3 часа" % d3
        messages.append(
            "Проверка: давление %.1f мм рт. ст., %s, изменение %s."
            % (p, names[status], change)
        )

    for m in messages:
        send_telegram(m)

    save_state({"status": status, "jump": is_jump})
    print(
        "time=%s p=%.1f status=%s d3=%s jump=%s sent=%d"
        % (cur["time"], p, status, "n/a" if d3 is None else "%.2f" % d3, is_jump, len(messages))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
