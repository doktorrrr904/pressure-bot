#!/usr/bin/env python3
"""Оповещения о магнитных бурях в Telegram (Kp-индекс, NOAA SWPC).

Молчит, пока магнитное поле спокойное. Пишет, когда буря началась, усилилась,
ослабла или закончилась. Уровень по шкале NOAA: G1 слабая ... G5 экстремальная.
"""
import json
import os
import sys
import time
import urllib.request

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
STATE_FILE = "storm_state.json"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
FORCE_REPORT = os.environ.get("FORCE_REPORT") == "1"

NAMES = {
    1: "слабая",
    2: "умеренная",
    3: "сильная",
    4: "очень сильная",
    5: "экстремальная",
}


def parse_latest(rows):
    """Возвращает (время, Kp) последней строки. Понимает оба формата NOAA."""
    if not rows:
        raise ValueError("пустой ответ")
    if isinstance(rows[0], list):
        header = [str(h).lower() for h in rows[0]]
        ti, ki = header.index("time_tag"), header.index("kp")
        items = [(r[ti], r[ki]) for r in rows[1:]]
    else:
        items = [(r.get("time_tag"), r.get("Kp", r.get("kp"))) for r in rows]
    for t, k in reversed(items):
        try:
            return t, float(k)
        except (TypeError, ValueError):
            continue
    raise ValueError("нет значения Kp")


def fetch_kp():
    last_error = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(KP_URL, timeout=30) as resp:
                return parse_latest(json.load(resp))
        except Exception as e:  # повторяем при сетевых сбоях
            last_error = e
            time.sleep(5)
    raise last_error


def g_level(kp):
    """Уровень бури по шкале NOAA: 0 — бури нет, 1..5 — G1..G5."""
    if kp >= 8.99:
        return 5
    n = int(kp + 0.5)
    if n >= 9:  # Kp 9- (8.67) по шкале NOAA ещё G4
        n = 8
    return max(0, n - 4)


def label(level):
    return "G%d (%s)" % (level, NAMES[level])


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

    tag, kp = fetch_kp()
    level = g_level(kp)

    state = load_state()
    prev = state.get("level")

    messages = []
    if prev is None:
        if level > 0:
            messages.append(
                "Бот запущен. Сейчас идёт магнитная буря %s, Kp %.2f." % (label(level), kp)
            )
    elif level != prev:
        if prev == 0:
            messages.append(
                "Началась магнитная буря: %s, Kp %.2f." % (label(level), kp)
            )
        elif level == 0:
            messages.append(
                "Магнитная буря закончилась, поле спокойное. Kp %.2f." % kp
            )
        elif level > prev:
            messages.append(
                "Буря усилилась: %s → %s, Kp %.2f." % (label(prev), label(level), kp)
            )
        else:
            messages.append(
                "Буря ослабла: %s → %s, Kp %.2f." % (label(prev), label(level), kp)
            )

    if FORCE_REPORT and not messages:
        if level == 0:
            messages.append("Проверка: магнитной бури нет, Kp %.2f." % kp)
        else:
            messages.append(
                "Проверка: идёт магнитная буря %s, Kp %.2f." % (label(level), kp)
            )

    for m in messages:
        send_telegram(m)

    save_state({"level": level})
    print("time=%s kp=%.2f level=%d sent=%d" % (tag, kp, level, len(messages)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
