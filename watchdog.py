"""
Watchdog ALIDEEA - porneste si supravegheaza Flask, ngrok, Telegram bot.
Daca vreun serviciu cade, il reporneste automat in max 30 secunde.
"""
import subprocess
import time
import os
import urllib.request
import json
import logging
import sys

PYTHON  = r"C:\Users\zambe\AppData\Local\Programs\Python\Python313\python.exe"
NGROK   = r"C:\ngrok\ngrok.exe"
APP_DIR = r"C:\ALIDEEA"
LOG     = os.path.join(APP_DIR, "watchdog.log")

# --- Logging separat de Flask (foloseste nume explicit, nu root logger) ---
logger = logging.getLogger("alideea_watchdog")
logger.setLevel(logging.INFO)
logger.propagate = False
fh = logging.FileHandler(LOG, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [WD] %(message)s", "%Y-%m-%d %H:%M:%S"))
logger.addHandler(fh)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(logging.Formatter("%(asctime)s [WD] %(message)s", "%Y-%m-%d %H:%M:%S"))
logger.addHandler(sh)

def log(msg):
    logger.info(msg)

# --- Instanta unica: omoara orice alt watchdog.py inainte de a porni ---
def get_pids_by_name(exe_name):
    """Returneaza lista de PID-uri pentru un executabil, fara PID-ul curent."""
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10
        )
        pids = []
        for line in r.stdout.splitlines():
            parts = [p.strip('"') for p in line.strip().split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                pid = int(parts[1])
                if pid != os.getpid():
                    pids.append(pid)
        return pids
    except Exception:
        return []

def kill_other_watchdogs():
    """Opreste orice alt watchdog.py care ruleaza."""
    for pid in get_pids_by_name("python.exe"):
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            # Cauta in linia de comanda daca e watchdog - folosim wmic doar pt asta
            cmd_r = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:VALUE"],
                capture_output=True, text=True, timeout=5
            )
            if "watchdog.py" in cmd_r.stdout.lower():
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5)
                log(f"Oprit watchdog vechi (PID {pid})")
        except Exception:
            pass

# --- Verificari servicii ---
def flask_ok():
    try:
        urllib.request.urlopen("http://127.0.0.1:5000", timeout=5)
        return True
    except Exception:
        return False

def ngrok_ok():
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3) as r:
            data = json.loads(r.read())
            return len(data.get("tunnels", [])) > 0
    except Exception:
        return False

def process_alive(keyword):
    """Verifica daca ruleaza un proces Python care contine keyword in command line."""
    try:
        for pid in get_pids_by_name("python.exe"):
            r = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:VALUE"],
                capture_output=True, text=True, timeout=5
            )
            if keyword.lower() in r.stdout.lower():
                return True
        return False
    except Exception:
        return False


def bot_alive_via_pid():
    """Verifica daca botul Telegram ruleaza folosind fisierul PID (metoda fiabila)."""
    pid_file = os.path.join(APP_DIR, "bot.pid")
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return str(pid) in r.stdout
    except Exception:
        return False

def kill_by_name(exe_name):
    subprocess.run(["taskkill", "/F", "/IM", exe_name],
                   capture_output=True, timeout=5)

def kill_by_keyword(keyword):
    """Opreste procesele Python care contin keyword in command line."""
    for pid in get_pids_by_name("python.exe"):
        try:
            r = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:VALUE"],
                capture_output=True, text=True, timeout=5
            )
            if keyword.lower() in r.stdout.lower():
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5)
        except Exception:
            pass

def launch(cmd, name, wait_sec=0):
    try:
        subprocess.Popen(
            cmd,
            cwd=APP_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        if wait_sec:
            time.sleep(wait_sec)
        log(f"Pornit: {name}")
    except Exception as e:
        log(f"EROARE pornire {name}: {e}")

def kill_telegram_bots():
    """La pornire, omoara orice proces cu conexiune activa la Telegram via netstat."""
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=8)
        telegram_ips = ("149.154.", "91.108.", "160.79.")
        pids_to_kill = set()
        for line in r.stdout.splitlines():
            if "ESTABLISHED" in line and any(ip in line for ip in telegram_ips):
                parts = line.strip().split()
                if parts and parts[-1].isdigit():
                    proc_id = int(parts[-1])
                    if proc_id != os.getpid():
                        pids_to_kill.add(proc_id)
        for proc_id in pids_to_kill:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(proc_id)], capture_output=True, timeout=30)
                log(f"Oprit bot Telegram vechi (PID {proc_id})")
            except subprocess.TimeoutExpired:
                # Fallback: Windows API direct
                try:
                    import ctypes
                    PROCESS_TERMINATE = 0x0001
                    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, proc_id)
                    if handle:
                        ctypes.windll.kernel32.TerminateProcess(handle, 1)
                        ctypes.windll.kernel32.CloseHandle(handle)
                        log(f"Oprit bot Telegram vechi via API (PID {proc_id})")
                except Exception as ex:
                    log(f"Nu pot opri PID {proc_id}: {ex}")
    except Exception as e:
        log(f"Eroare kill_telegram_bots: {e}")


# --- Logica supraveghere ---
def ensure_flask():
    if flask_ok():
        return
    log("Flask nu raspunde - repornesc...")
    kill_by_keyword("app.py")
    time.sleep(3)
    launch([PYTHON, os.path.join(APP_DIR, "app.py")], "Flask", wait_sec=12)
    if flask_ok():
        log("Flask OK.")
    else:
        log("Flask inca nu raspunde - reincerce la urmatorul ciclu.")

def ensure_ngrok():
    if ngrok_ok():
        return
    log("ngrok offline - repornesc...")
    kill_by_name("ngrok.exe")
    time.sleep(3)
    launch([NGROK, "start", "alideea"], "ngrok", wait_sec=8)
    if ngrok_ok():
        log("ngrok OK.")
    else:
        log("ngrok inca offline - reincerce la urmatorul ciclu.")

def ensure_bot():
    if bot_alive_via_pid() or process_alive("telegram_bot.py"):
        return
    log("Bot Telegram oprit - repornesc...")
    bot_pid_file = os.path.join(APP_DIR, "bot.pid")
    proc = subprocess.Popen(
        [PYTHON, os.path.join(APP_DIR, "telegram_bot.py")],
        cwd=APP_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
    )
    try:
        with open(bot_pid_file, "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    log(f"Pornit: Bot Telegram (PID {proc.pid})")

# --- Main ---
def main():
    kill_telegram_bots()
    kill_other_watchdogs()
    log(f"=== Watchdog pornit (PID {os.getpid()}) ===")

    time.sleep(10)

    while True:
        try:
            ensure_flask()
            if flask_ok():
                ensure_ngrok()
            ensure_bot()
        except Exception as e:
            log(f"Eroare neasteptata: {e}")
        time.sleep(30)

if __name__ == "__main__":
    main()
