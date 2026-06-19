from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request
from flask_login import login_required, current_user
from database import get_db
import subprocess
import os
import json
import urllib.request
import sys
from datetime import datetime

server_bp = Blueprint('server', __name__, url_prefix='/server')

APP_DIR = r"C:\ALIDEEA"
WATCHDOG_LOG = os.path.join(APP_DIR, "watchdog.log")


def _check_flask():
    try:
        urllib.request.urlopen("http://127.0.0.1:5000", timeout=3)
        return True
    except Exception:
        return True  # daca rulam, inseamna ca Flask e ok


def _check_ngrok():
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3) as r:
            data = json.loads(r.read())
            tunnels = data.get("tunnels", [])
            if tunnels:
                return True, tunnels[0].get("public_url", "—")
            return False, "—"
    except Exception:
        return False, "—"


def _check_bot():
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


def _check_watchdog():
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            parts = [p.strip('"') for p in line.strip().split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                pid = int(parts[1])
                cmd_r = subprocess.run(
                    ["wmic", "process", "where", f"ProcessId={pid}", "get",
                     "CommandLine", "/FORMAT:VALUE"],
                    capture_output=True, text=True, timeout=5
                )
                if "watchdog.py" in cmd_r.stdout.lower():
                    return True
        return False
    except Exception:
        return False


def _get_log_tail(n=40):
    if not os.path.exists(WATCHDOG_LOG):
        return []
    try:
        with open(WATCHDOG_LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception:
        return []


@server_bp.route('/')
@login_required
def index():
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))

    ngrok_ok, ngrok_url = _check_ngrok()
    status = {
        'flask':    True,
        'ngrok':    ngrok_ok,
        'ngrok_url': ngrok_url,
        'bot':      _check_bot(),
        'watchdog': _check_watchdog(),
    }
    log_lines = _get_log_tail(40)

    return render_template('server/index.html', status=status, log_lines=log_lines)


@server_bp.route('/api/status')
@login_required
def api_status():
    if not current_user.is_admin():
        return jsonify({'error': 'unauthorized'}), 403
    ngrok_ok, ngrok_url = _check_ngrok()
    return jsonify({
        'flask':     True,
        'ngrok':     ngrok_ok,
        'ngrok_url': ngrok_url,
        'bot':       _check_bot(),
        'watchdog':  _check_watchdog(),
        'time':      datetime.now().strftime('%H:%M:%S'),
    })


@server_bp.route('/restart-flask', methods=['POST'])
@login_required
def restart_flask():
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('server.index'))

    # Scriem un fisier flag; watchdog-ul va detecta ca Flask nu mai raspunde
    # si il va reporni. Noi inchidem procesul curent.
    import threading
    def do_exit():
        import time
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=do_exit, daemon=True).start()

    flash('Flask se reporneste... pagina va reveni in 15-20 secunde.', 'info')
    return render_template('server/restarting.html')


@server_bp.route('/restart-ngrok', methods=['POST'])
@login_required
def restart_ngrok():
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('server.index'))

    NGROK = r"C:\ngrok\ngrok.exe"
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True, timeout=5)
        import time; time.sleep(2)
        subprocess.Popen(
            [NGROK, "start", "alideea"],
            cwd=APP_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
        )
        flash('ngrok repornit.', 'success')
    except Exception as e:
        flash(f'Eroare restart ngrok: {e}', 'danger')
    return redirect(url_for('server.index'))
