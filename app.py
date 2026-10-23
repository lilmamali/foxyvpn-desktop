import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import winreg
import ctypes
import json
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)
import psutil

USAGE_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FoxyVPNDesktop" / "usage.json"


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n:.0f} B"
        n /= 1024


class DataCounter:
    MONTHLY_LIMIT_GB = 50  # پیش‌فرض؛ با Sync از موزیلا به‌روز می‌شه

    def __init__(self):
        self.pid = None
        self.last_bytes = 0
        self.session_bytes = 0
        self.max_bytes = self._load_max()
        self.remaining_bytes = self._load_remaining()
        self.subscribed = False

    def _load_max(self):
        try:
            d = json.loads(USAGE_FILE.read_text())
            if d.get("month") == self._current_month():
                return d.get("max", self.MONTHLY_LIMIT_GB * (1024**3))
        except Exception:
            pass
        return self.MONTHLY_LIMIT_GB * (1024**3)

    def _load_remaining(self):
        try:
            d = json.loads(USAGE_FILE.read_text())
            if d.get("month") == self._current_month():
                return d.get("remaining", d.get("max", self.MONTHLY_LIMIT_GB * (1024**3)))
        except Exception:
            pass
        return self.MONTHLY_LIMIT_GB * (1024**3)

    def _save(self):
        try:
            USAGE_FILE.parent.mkdir(exist_ok=True)
            USAGE_FILE.write_text(json.dumps({
                "max": self.max_bytes,
                "remaining": self.remaining_bytes,
                "month": self._current_month(),
                "subscribed": self.subscribed,
            }))
        except Exception:
            pass

    def update_from_mozilla(self, max_bytes, subscribed):
        self.max_bytes = max_bytes
        self.subscribed = subscribed
        if self.remaining_bytes > max_bytes or not self._same_month_saved():
            self.remaining_bytes = max_bytes
        self._save()

    def _same_month_saved(self):
        try:
            d = json.loads(USAGE_FILE.read_text())
            return d.get("month") == self._current_month()
        except Exception:
            return False

    @staticmethod
    def _current_month():
        return time.strftime("%Y-%m")

    def _tree_bytes(self):
        try:
            p = psutil.Process(self.pid)
            total = 0
            for proc in [p] + p.children(recursive=True):
                try:
                    io = proc.io_counters()
                    total += io.read_bytes + io.write_bytes
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return total
        except psutil.NoSuchProcess:
            return None

    def start(self, pid):
        self.pid = pid
        self.last_bytes = self._tree_bytes() or 0
        self.session_bytes = 0

    def tick(self):
        if self.pid is None:
            return self.session_bytes
        cur = self._tree_bytes()
        if cur is None:
            return self.session_bytes
        delta = cur - self.last_bytes
        if delta > 0:
            self.session_bytes += delta
            self.remaining_bytes = max(0, self.remaining_bytes - delta)
            self._save()
        self.last_bytes = cur
        return self.session_bytes


data_counter = DataCounter()

APP_NAME = "FoxyVPN Desktop"
APP_DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FoxyVPNDesktop"
APP_DATA.mkdir(parents=True, exist_ok=True)
STATUS_FILE = APP_DATA / "status.json"
STATE_FILE = APP_DATA / "proxy-state.json"
HOST = "127.0.0.1"
PORT = 1080
HTTP_PORT = 8080
ENGINE_NAME = "foxyvpn-engine.exe"

# تنظیمات آپدیت‌ر — ریپو پابلیک، نیازی به توکن نیست
GITHUB_USER = "lilmamali"
GITHUB_REPO = "foxyvpn-desktop"
APP_VERSION = "1.0"
UPDATE_CHECK_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/version.json"
)
TOKENS_FILE = Path.home() / ".foxyvpn-tokens.json"

PROMPT_KEYWORDS = ("password", "email", "code", "2fa", "two-factor", "two factor",
                   "verification", "confirm", "press enter", "link", "sign in")


def engine_executable():
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent / ENGINE_NAME
        return candidate if candidate.is_file() else None
    project = Path(__file__).resolve().parent
    for p in (project / "dist" / ENGINE_NAME,
              project / "venv" / "Scripts" / "foxyvpn.exe",
              project / ENGINE_NAME):
        if p.is_file():
            return p
    return None


def kill_stale_engines():
    subprocess.run(
        ["taskkill", "/IM", ENGINE_NAME, "/F"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def port_in_use():
    try:
        with socket.create_connection((HOST, PORT), timeout=0.3):
            return True
    except OSError:
        return False


# ----------------- الگوهای پورت‌شده از اپ اندروید FoxyVPN -----------------

BRIDGE_BACKOFF_BASE_MS = 30_000
BRIDGE_BACKOFF_CAP_MS = 10 * 60_000
BRIDGE_REFUSAL_CACHE_CAP = 256


class RefusalCache:
    """دامنه‌هایی که edge (سرور موزیلا) رد کرده را با backoff نمایی
    به‌صورت محلی رد می‌کنیم تا رفت‌وبرگشت بیهوده به سرور ندهیم."""

    def __init__(self):
        self._records = {}

    def check(self, key):
        rec = self._records.get(key)
        if rec and time.time() * 1000 < rec[1]:
            return True
        return False

    def remember(self, key):
        rec = self._records.setdefault(key, [0, 0])
        rec[0] += 1
        backoff = min(BRIDGE_BACKOFF_BASE_MS << min(rec[0] - 1, 16), BRIDGE_BACKOFF_CAP_MS)
        rec[1] = time.time() * 1000 + backoff
        if len(self._records) > BRIDGE_REFUSAL_CACHE_CAP:
            for k in list(self._records)[:BRIDGE_REFUSAL_CACHE_CAP // 2]:
                self._records.pop(k, None)

    def forget(self, key):
        self._records.pop(key, None)


REFUSAL_CACHE = RefusalCache()


def is_local_network(host):
    h = host.lower()
    if h == "localhost":
        return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_unspecified)


# ------------------------------------------------- پل HTTP → SOCKS5

def _recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise OSError("engine closed connection during handshake")
        data += chunk
    return data


def socks_connect(host, port):
    if is_local_network(host):
        raise OSError(f"local-network destination {host} is not carried by the tunnel")

    sock = socket.create_connection((HOST, PORT), timeout=15)
    try:
        sock.sendall(b"\x05\x01\x00")
        if _recv_exact(sock, 2)[:2] != b"\x05\x00":
            raise OSError("SOCKS5 handshake failed")
        try:
            domain = host.encode("idna")
        except UnicodeError:
            domain = host.encode("utf-8")
        req = b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain + port.to_bytes(2, "big")
        sock.sendall(req)
        resp = _recv_exact(sock, 4)
        if resp[1] != 0:
            codes = {1: "general failure", 2: "not allowed", 3: "network unreachable",
                     4: "host unreachable", 5: "connection refused", 6: "TTL expired",
                     7: "command not supported", 8: "address type not supported"}
            raise OSError(f"engine rejected CONNECT to {host}:{port} "
                          f"({codes.get(resp[1], f'code {resp[1]}')})")
        atyp = resp[3]
        skip = {1: 4, 4: 16}.get(atyp)
        if skip is None:
            skip = _recv_exact(sock, 1)[0]
        _recv_exact(sock, skip + 2)
        sock.settimeout(None)
        return sock
    except Exception:
        sock.close()
        raise


def _relay(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()


class BridgeHandler(socketserver.BaseRequestHandler):
    _lock = threading.Lock()
    _failures = 0
    _failed_targets = set()

    def log(self, msg):
        logger = getattr(self.server, "logger", None)
        if logger:
            logger(msg)

    def handle(self):
        data = b""
        key = None
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(65536)
            if not chunk:
                return
            data += chunk
            if len(data) > 1_000_000:
                return
        head, _, rest = data.partition(b"\r\n\r\n")
        try:
            parts = head.split(b"\r\n")[0].split()
            method, target = parts[0].upper(), parts[1]
        except IndexError:
            return
        try:
            if method == b"CONNECT":
                host, _, port_s = target.rpartition(b":")
                host_d, port_n = host.decode(), int(port_s)
                key = f"{host_d}:{port_n}"
                if REFUSAL_CACHE.check(key):
                    raise OSError("destination recently refused by upstream edge (cached)")
                upstream = socks_connect(host_d, port_n)
                self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                if rest:
                    upstream.sendall(rest)
            else:
                url = target.partition(b"://")[2]
                hostport, _, path_q = url.partition(b"/")
                host_b, _, port_s = hostport.rpartition(b":")
                host = host_b.decode()
                port = int(port_s) if port_s else 80
                key = f"{host}:{port}"
                if REFUSAL_CACHE.check(key):
                    raise OSError("destination recently refused by upstream edge (cached)")
                upstream = socks_connect(host, port)
                new_head = head.replace(target, b"/" + path_q, 1)
                upstream.sendall(new_head + b"\r\n\r\n" + rest)
        except Exception as exc:
            self.on_failure(target, key, exc)
            try:
                self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except OSError:
                pass
            return
        with BridgeHandler._lock:
            BridgeHandler._failures = 0
            BridgeHandler._failed_targets.clear()
        if key:
            REFUSAL_CACHE.forget(key)
        t = threading.Thread(target=_relay, args=(self.request, upstream), daemon=True)
        t.start()
        _relay(upstream, self.request)

    @staticmethod
    def _classify(exc):
        msg = str(exc).lower()
        if ("rejected connect" in msg or "recently refused" in msg
                or "local-network" in msg):
            return "reject"
        return "silence"

    def on_failure(self, target, key, exc):
        msg = str(exc)
        kind = self._classify(exc)
        if kind == "reject":
            if key:
                REFUSAL_CACHE.remember(key)
        self.log(f"Bridge: {target.decode('utf-8', 'replace')} failed — {msg}")
        if kind != "silence":
            return
        with BridgeHandler._lock:
            BridgeHandler._failures += 1
            if key:
                BridgeHandler._failed_targets.add(key.rsplit(":", 1)[0])
            if (BridgeHandler._failures >= 3
                    and len(BridgeHandler._failed_targets) >= 3
                    and getattr(self.server, "on_unhealthy", None)):
                BridgeHandler._failures = 0
                BridgeHandler._failed_targets.clear()
                self.server.on_unhealthy()


class SocksBridge(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    logger = None
    on_unhealthy = None


_INTERNET_OPTION_SETTINGS_CHANGED = 39
_INTERNET_OPTION_REFRESH = 37


def set_system_proxy(enable):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
            if enable:
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ,
                                  f"127.0.0.1:{HTTP_PORT}")
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ,
                                  "localhost;127.*;10.*;172.16.*;192.168.*;<local>")
        finally:
            winreg.CloseKey(key)
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(None, _INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
        wininet.InternetSetOptionW(None, _INTERNET_OPTION_REFRESH, None, 0)
    except OSError as exc:
        print(f"system proxy error: {exc}", file=sys.stderr)


# ------------------------------------------------- آپدیت‌ر — ریپو پابلیک، بدون توکن

def check_for_update():
    """اگر نسخه جدیدی موجود باشد، (نسخه، نام asset) برمی‌گرداند."""
    try:
        req = urllib.request.Request(UPDATE_CHECK_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        latest = str(info.get("version", "")).strip()
        asset = str(info.get("asset", "")).strip()
        if latest and latest != APP_VERSION and asset:
            return latest, asset
    except Exception:
        pass
    return None


def fetch_download_url(asset_name):
    """لینک دانلود مستقیم asset از آخرین Release (ریپو پابلیک، بدون توکن)."""
    try:
        api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(api)
        req.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            rel = json.loads(resp.read().decode("utf-8"))
        for a in rel.get("assets", []):
            if a.get("name") == asset_name:
                return a.get("browser_download_url")
    except Exception:
        pass
    return None


class FoxyVPNWindow(QMainWindow):
    log_signal = Signal(str)
    line_signal = Signal(str)
    state_signal = Signal(str, str)
    ip_signal = Signal(str)
    proxy_signal = Signal(bool)
    prompt_signal = Signal(str)
    update_signal = Signal(str, str)
    mozilla_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(760, 820)   # کمی بزرگ‌تر تا متن‌ها جا بشن
        self.resize(880, 900)
        self.proc = None
        self.reader_thread = None
        self.bridge = None
        self.pending_prompt = None
        self.prompt_timer = None
        self.interactive = False
        self.restarting = False
        self.gen = 0
        self.log_signal.connect(self.add_log)
        self.line_signal.connect(self.handle_engine_line)
        self.state_signal.connect(self.set_connection_state)
        self.ip_signal.connect(self.set_ip_text)
        self.proxy_signal.connect(self.set_proxy_status)
        self.prompt_signal.connect(self.handle_prompt)
        self.update_signal.connect(self.offer_update)
        self.mozilla_signal.connect(self._apply_mozilla_usage)
        self._build_ui()
        self._style()
        kill_stale_engines()
        self.load_servers()

    # ---------------------------------------------------------------- UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(22, 18, 22, 16)
        outer.setSpacing(14)

        # ----- هدر: آیکن + عنوان + پنل مصرف + استیت -----
        header = QHBoxLayout()
        header.setSpacing(14)

        app_icon = QLabel("◇")
        app_icon.setObjectName("appIcon")
        app_icon.setFixedSize(48, 48)
        app_icon.setAlignment(Qt.AlignCenter)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel("Personal SOCKS5 proxy manager")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addWidget(app_icon, 0, Qt.AlignVCenter)
        header.addLayout(title_box, 1)

        # پنل مصرف ماهانه
        usage_panel = QFrame()
        usage_panel.setObjectName("usagePanel")
        usage_panel.setMinimumWidth(220)
        usage_panel.setMaximumWidth(240)
        ul = QVBoxLayout(usage_panel)
        ul.setContentsMargins(14, 10, 14, 12)
        ul.setSpacing(6)

        usage_title = QLabel("Monthly data limit")
        usage_title.setObjectName("usageTitle")
        ul.addWidget(usage_title)

        usage_note = QLabel(f"Resets to {DataCounter.MONTHLY_LIMIT_GB} GB on the 1st")
        usage_note.setObjectName("muted")
        usage_note.setWordWrap(True)
        ul.addWidget(usage_note)

        self.usage_bar = QProgressBar()
        self.usage_bar.setRange(0, DataCounter.MONTHLY_LIMIT_GB * 1024)
        self.usage_bar.setTextVisible(False)
        self.usage_bar.setFixedHeight(8)
        ul.addWidget(self.usage_bar)

        self.usage_text = QLabel("— GB of 50 GB left")
        self.usage_text.setObjectName("usageValue")
        ul.addWidget(self.usage_text)

        self.refresh_usage_btn = QPushButton("↻ Sync with Mozilla")
        self.refresh_usage_btn.setObjectName("secondary")
        self.refresh_usage_btn.setFixedHeight(30)
        self.refresh_usage_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_usage_btn.clicked.connect(self.refresh_from_mozilla)
        ul.addWidget(self.refresh_usage_btn)

        header.addWidget(usage_panel, 0, Qt.AlignVCenter)

        self.state_label = QLabel("NOT CONNECTED")
        self.state_label.setObjectName("state")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setMinimumHeight(34)
        self.state_label.setMinimumWidth(150)
        header.addWidget(self.state_label, 0, Qt.AlignVCenter)

        outer.addLayout(header)

        # تایمر به‌روزرسانی مصرف (هر ۵ ثانیه)
        self.usage_timer = QTimer(self)
        self.usage_timer.timeout.connect(self._tick_usage)
        self.usage_timer.start(5000)

        # ----- پنل اکانت فایرفاکس -----
        account = self.make_panel()
        al = QVBoxLayout(account)
        al.setContentsMargins(16, 14, 16, 14)
        al.setSpacing(10)
        al.addWidget(self.section_label("FIREFOX ACCOUNT"))

        # ردیف ایمیل + دکمه Refresh — کمیت ورودی ایمیل با حداقل عرض بزرگ‌تر
        email_row = QHBoxLayout()
        email_row.setSpacing(10)
        self.email = QLineEdit()
        self.email.setFixedHeight(38)
        self.email.setMinimumWidth(280)   # ← کمیت مهم برای جلوگیری از فشرده شدن
        self.email.setPlaceholderText("Your own Firefox Account email")
        self.email.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        email_row.addWidget(self.email, 1)
        self.servers_btn = QPushButton("Refresh servers")
        self.servers_btn.setObjectName("secondary")
        self.servers_btn.setFixedHeight(38)
        self.servers_btn.setMinimumWidth(130)
        self.servers_btn.setMaximumWidth(160)
        self.servers_btn.clicked.connect(self.load_servers)
        email_row.addWidget(self.servers_btn, 0)
        al.addLayout(email_row)

        note = QLabel("New users: enter your Firefox Account email, then press Connect — "
                      "the password is asked in a popup and never stored. "
                      "Returning users connect automatically.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        note.setMinimumHeight(54)
        al.addWidget(note)
        self.login_check = QCheckBox("Force a fresh sign-in (ignore cached tokens)")
        self.login_check.setMinimumHeight(24)
        al.addWidget(self.login_check)
        self.sysproxy_check = QCheckBox("Route all Windows apps through the VPN (system proxy)")
        self.sysproxy_check.setChecked(True)
        al.addWidget(self.sysproxy_check)
        outer.addWidget(account)

        # ----- پنل اتصال -----
        conn = self.make_panel()
        cl = QVBoxLayout(conn)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)
        cl.addWidget(self.section_label("CONNECTION"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.addWidget(self.section_label("SERVER LOCATION"), 0, 0)
        grid.addWidget(self.section_label("LOCAL SOCKS5 PROXY"), 0, 1)
        self.country = QComboBox()
        self.country.setFixedHeight(38)
        self.country.setMinimumWidth(260)
        self.country.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.country.addItem("Loading servers…", "REC")
        grid.addWidget(self.country, 1, 0)
        self.proxy_label = QLabel(f"{HOST}:{PORT}")
        self.proxy_label.setObjectName("value")
        grid.addWidget(self.proxy_label, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        cl.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primary")
        self.connect_btn.setFixedSize(140, 42)
        self.connect_btn.clicked.connect(self.connect_vpn)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setObjectName("secondary")
        self.disconnect_btn.setFixedSize(140, 42)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self.disconnect_vpn)
        buttons.addWidget(self.connect_btn)
        buttons.addWidget(self.disconnect_btn)
        buttons.addStretch(1)
        cl.addLayout(buttons)
        outer.addWidget(conn)

        # ----- پنل وضعیت اتصال -----
        status_panel = self.make_panel()
        sl = QVBoxLayout(status_panel)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(8)
        sl.addWidget(self.section_label("CONNECTION STATUS"))
        self.status_text = QLabel("Disconnected")
        self.status_text.setObjectName("value")
        self.status_text.setWordWrap(True)
        self.status_text.setMinimumHeight(28)
        sl.addWidget(self.status_text)
        self.ip_text = QLabel("Exit IP: —")
        self.ip_text.setObjectName("muted")
        self.ip_text.setWordWrap(True)
        self.ip_text.setMinimumHeight(36)
        sl.addWidget(self.ip_text)
        self.proxy_check = QLabel(f"Local proxy: {HOST}:{PORT} is not listening")
        self.proxy_check.setObjectName("muted")
        self.proxy_check.setWordWrap(True)
        self.proxy_check.setMinimumHeight(44)
        sl.addWidget(self.proxy_check)
        outer.addWidget(status_panel)

        outer.addWidget(self.section_label("ACTIVITY LOG"))
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(140)
        self.logs.setPlaceholderText("FoxyVPN output will appear here.")
        outer.addWidget(self.logs, 1)

        footer = QLabel("Only apps configured to use this proxy go through FoxyVPN. "
                        f"Browsers follow the system proxy ({HOST}:{HTTP_PORT}); "
                        f"apps that support SOCKS5 can use {HOST}:{PORT} directly.")
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        footer.setMinimumHeight(40)
        outer.addWidget(footer)

    def _tick_usage(self):
        used_bytes = data_counter.tick()
        remaining_mb = data_counter.remaining_bytes / (1024 * 1024)
        max_mb = data_counter.max_bytes / (1024 * 1024)
        remaining_gb = remaining_mb / 1024
        max_gb = max_mb / 1024

        self.usage_bar.setRange(0, int(max_mb))
        self.usage_bar.setValue(int(max_mb - remaining_mb))
        self.usage_text.setText(f"{remaining_gb:.1f} GB of {max_gb:.0f} GB left")

        pct = (max_mb - remaining_mb) / max_mb if max_mb > 0 else 0
        if pct >= 0.9:
            self.usage_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #ef4444; border-radius: 4px; }")
        elif pct >= 0.75:
            self.usage_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }")
        else:
            self.usage_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }")

    def refresh_from_mozilla(self):
        exe = engine_executable()
        if not exe:
            QMessageBox.warning(self, "Engine missing",
                                f"Could not find {ENGINE_NAME}.")
            return
        self.refresh_usage_btn.setEnabled(False)
        self.usage_text.setText("Fetching from Mozilla…")
        self.add_log("Fetching usage from Mozilla (--print-info)…")

        def worker():
            try:
                result = subprocess.run(
                    [str(exe), "--print-info"],
                    capture_output=True, text=True, timeout=30,
                    encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self.mozilla_signal.emit(result.stdout + "\n" + result.stderr)
            except Exception as exc:
                self.mozilla_signal.emit(f"__error__:{exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _apply_mozilla_usage(self, output):
        self.refresh_usage_btn.setEnabled(True)
        if output.startswith("__error__:"):
            self.usage_text.setText("Mozilla fetch failed")
            self.add_log(f"Mozilla fetch failed: {output[10:]}")
            return
        self.add_log(f"Mozilla output:\n{output.strip()}")

        import re
        m_max = re.search(r'maxBytes=(\d+)', output)
        m_sub = re.search(r'subscribed=(\w+)', output)
        if m_max:
            max_bytes = int(m_max.group(1))
            subscribed = bool(m_sub and m_sub.group(1) == "True")
            data_counter.update_from_mozilla(max_bytes, subscribed)
            max_gb = max_bytes / (1024**3)
            plan = "Premium" if subscribed else "Free"
            self.add_log(f"Mozilla: maxBytes = {max_gb:.1f} GB, plan = {plan}")
            self._tick_usage()
        else:
            self.usage_text.setText("Mozilla output not parseable — see log")

    @staticmethod
    def make_panel():
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setFrameShape(QFrame.NoFrame)
        return frame

    @staticmethod
    def section_label(text):
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def _style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0b1220; }
            QWidget { background-color: #0b1220; color: #e5e7eb;
                      font-family: "Segoe UI"; font-size: 10pt; }
            QLabel { background: transparent; }
            QLabel#appIcon { background-color: #172554; color: #93c5fd;
                             border-radius: 10px; font-size: 22pt; font-weight: 700; }
            QLabel#appTitle { font-size: 17pt; font-weight: 700; background: transparent; }
            QLabel#muted { color: #aab4c4; background: transparent; }
            QLabel#section { color: #d7deea; background: transparent;
                             font-size: 9pt; font-weight: 600; letter-spacing: 1px; }
            QLabel#state { color: #fbbf24; background-color: #111b2d; font-weight: 700;
                           padding: 6px 12px; border: 1px solid #374151; border-radius: 8px; }
            QFrame#usagePanel {
                background-color: #111b2d;
                border: 1px solid #263449;
                border-radius: 10px;
            }
            QLabel#usageTitle {
                color: #f9fafb;
                font-weight: 700;
                font-size: 10pt;
                background: transparent;
            }
            QLabel#usageValue {
                color: #86efac;
                font-weight: 700;
                font-size: 11pt;
                background: transparent;
            }
            QProgressBar {
                background-color: #1f2937;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #22c55e;
                border-radius: 4px;
            }
            QFrame#panel { background-color: #111b2d; border: 1px solid #263449;
                           border-radius: 12px; }
            QLabel#value { color: #f9fafb; background: transparent;
                           font-size: 11pt; font-weight: 600; }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #0b1220; color: #e5e7eb;
                border: 1px solid #374151; border-radius: 7px; padding: 6px 8px;
                selection-background-color: #2563eb; }
            QComboBox QAbstractItemView {
                background-color: #111b2d; color: #e5e7eb;
                selection-background-color: #2563eb; border: 1px solid #374151; }
            QPushButton { border-radius: 8px; font-weight: 600; }
            QPushButton#primary { background-color: #2563eb; color: white; border: none; }
            QPushButton#primary:hover { background-color: #1d4ed8; }
            QPushButton#secondary { background-color: #263449; color: #e5e7eb;
                                    border: 1px solid #374151; }
            QPushButton:disabled { background-color: #1f2937; color: #6b7280; }
            QCheckBox { spacing: 8px; background: transparent; }
        """)

    # ------------------------------------------------------------ log / state

    def add_log(self, text):
        if text:
            self.logs.append(text.rstrip())

    def set_ip_text(self, line):
        payload = line.split("exit ip", 1)[-1].strip()
        self.ip_text.setText("Exit IP: " + payload)

    def set_connection_state(self, state, status):
        if state == "__restart__":
            self.disconnect_vpn()
            self.connect_vpn()
            self.restarting = False
            return
        self.state_label.setText(state)
        if state == "CONNECTED":
            self.cancel_pending_prompt()
            self.state_label.setStyleSheet(
                "color:#86efac; background-color:#111b2d; border:1px solid #166534;"
                "border-radius:8px; padding:6px 12px; font-weight:700;")
            self.start_bridge()
            if self.sysproxy_check.isChecked():
                set_system_proxy(True)
                self.add_log(f"System proxy set to {HOST}:{HTTP_PORT}")
        else:
            self.state_label.setStyleSheet("")
            self.stop_bridge()
            set_system_proxy(False)
        self.status_text.setText(status)
        if state != "CONNECTED":
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
        self.refresh_status()

    def set_proxy_status(self, listening):
        state = "is listening" if listening else "is not listening"
        self.proxy_check.setText(f"Local proxy: {HOST}:{PORT} {state}")

    def refresh_status(self):
        threading.Thread(target=self._probe_port, daemon=True).start()

    def _probe_port(self):
        listening = port_in_use()
        self.proxy_signal.emit(listening)

    # ------------------------------------------------------------ bridge

    def start_bridge(self):
        if self.bridge:
            return
        try:
            self.bridge = SocksBridge(("127.0.0.1", HTTP_PORT), BridgeHandler)
            self.bridge.logger = lambda s: self.log_signal.emit(s)
            self.bridge.on_unhealthy = self.request_restart
            threading.Thread(target=self.bridge.serve_forever, daemon=True).start()
        except OSError as exc:
            self.add_log(f"HTTP bridge failed: {exc}")
            self.bridge = None

    def stop_bridge(self):
        if self.bridge:
            try:
                self.bridge.shutdown()
                self.bridge.server_close()
            except OSError:
                pass
            self.bridge = None
            self.add_log("HTTP bridge stopped")

    # ------------------------------------------------------------ servers / restart

    def request_restart(self):
        if self.restarting:
            return
        self.restarting = True
        self.log_signal.emit("Tunnel looks unhealthy — reconnecting…")
        self.state_signal.emit("__restart__", "Reconnecting…")

    def offer_update(self, version, asset):
        answer = QMessageBox.question(
            self, "Update available",
            f"A new version ({version}) is available.\n"
            f"Current: {APP_VERSION}\n\nDownload and install now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            self.add_log(f"Update {version} skipped by user.")
            return
        url = fetch_download_url(asset)
        if not url:
            QMessageBox.warning(self, "Update failed",
                                "Could not fetch the download link. Try again later.")
            return
        self.add_log(f"Downloading update {version}…")
        try:
            req = urllib.request.Request(url)
            tmp = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
            dest = tmp / (asset + ".new")
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as exc:
            QMessageBox.warning(self, "Update failed", f"Download failed: {exc}")
            return
        self.add_log("Update downloaded — will apply on restart.")
        target = tmp / asset
        bat = tmp / "_update.bat"
        bat.write_text(
            "@echo off\r\n"
            ":wait\r\n"
            "tasklist | find /I \"FoxyVPNDesktop.exe\" >nul && (\r\n"
            "  timeout /t 1 /nobreak >nul\r\n"
            "  goto wait\r\n"
            ")\r\n"
            f"move /Y \"{dest}\" \"{target}\"\r\n"
            f"start \"\" \"{target}\"\r\n"
            f"del \"%~f0\"\r\n",
            encoding="ascii")
        subprocess.Popen(["cmd", "/c", str(bat)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.close()
        sys.exit(0)

    def health_loop(self, gen):
        fails = 0
        while gen == self.gen:
            time.sleep(60)
            if gen != self.gen:
                return
            proc = self.proc
            if not proc or proc.poll() is not None:
                return
            if not port_in_use():
                continue
            try:
                s = socks_connect("www.cloudflare.com", 443)
                s.close()
                fails = 0
            except OSError as exc:
                if self.__class__ and BridgeHandler._classify(exc) == "reject":
                    continue
                fails += 1
                self.log_signal.emit(f"Health check failed ({fails}/2) — {exc}")
                if fails >= 2:
                    self.request_restart()
                    return

    def load_servers(self):
        self.country.clear()
        self.country.addItem("Loading servers…", "REC")
        exe = engine_executable()
        if not exe:
            self.country.clear()
            self.country.addItem("Recommended (REC)", "REC")
            self.add_log("Engine not found — only the recommended server is available.")
            return

        def worker():
            try:
                result = subprocess.run(
                    [str(exe), "--list-servers"], capture_output=True, text=True,
                    timeout=60, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                output = result.stdout + "\n" + result.stderr
                known = [
                    ("United Kingdom", "GB"), ("France", "FR"), ("Canada", "CA"),
                    ("Sweden", "SE"), ("Finland", "FI"), ("Denmark", "DK"),
                    ("Netherlands", "NL"), ("Belgium", "BE"), ("Spain", "ES"),
                    ("Austria", "AT"), ("Australia", "AU"), ("Portugal", "PT"),
                    ("Japan", "JP"), ("Italy", "IT"), ("Ireland", "IE"),
                    ("Germany", "DE"), ("United States", "US"), ("Thailand", "TH"),
                    ("Bulgaria", "BG"), ("South Africa", "ZA"), ("Peru", "PE"),
                    ("Brazil", "BR"), ("South Korea", "KR"), ("Ghana", "GH"),
                    ("Argentina", "AR"), ("Philippines", "PH"), ("Singapore", "SG"),
                    ("New Zealand", "NZ"), ("Chile", "CL"), ("Norway", "NO"),
                    ("Malaysia", "MY"), ("Mexico", "MX"), ("Colombia", "CO"),
                ]
                if result.returncode != 0:
                    self.country.clear()
                    self.country.addItem("Recommended (REC)", "REC")
                    self.log_signal.emit(
                        "Server list service is temporarily unavailable (Mozilla side). "
                        "Only the Recommended server is offered — try Refresh servers later.")
                    return
                servers = [("Recommended", "REC")]
                servers.extend((n, c) for n, c in known if c in output)
                self.country.clear()
                for name, code in servers:
                    self.country.addItem(f"{name} ({code})", code)
                self.log_signal.emit(f"Server list loaded ({len(servers) - 1} countries).")
            except Exception as exc:
                self.country.clear()
                self.country.addItem("Recommended (REC)", "REC")
                self.log_signal.emit(f"Could not load server list: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ connect

    def connect_vpn(self):
        if self.proc and self.proc.poll() is None:
            return
        exe = engine_executable()
        if not exe:
            QMessageBox.critical(
                self, "Engine missing",
                f"Could not find {ENGINE_NAME}.\n\nIt must sit in the same folder as "
                f"FoxyVPNDesktop.exe.")
            return
        if port_in_use():
            self.add_log("Port 1080 is busy — killing leftover engine…")
            kill_stale_engines()
            time.sleep(1)
            if port_in_use():
                QMessageBox.warning(
                    self, "Port busy",
                    f"{HOST}:{PORT} is occupied by another program.\n"
                    "Close it (or restart the PC) and try again.")
                return
        country = self.country.currentData() or "REC"
        args = [str(exe), "--listen", f"{HOST}:{PORT}", "--country", country,
                "--status-file", str(STATUS_FILE), "--proxy-state-file", str(STATE_FILE),
                "--idle-timeout", "300", "--max-conns", "512"]
        email = self.email.text().strip()
        if email:
            args.extend(["--email", email])
        if self.login_check.isChecked():
            args.append("--login")
        self.log_signal.emit(f"Starting engine (country={country})…")
        self.status_text.setText("Starting connection…")
        self.connect_btn.setEnabled(False)
        fresh = self.login_check.isChecked() or not TOKENS_FILE.is_file()
        self.interactive = fresh
        self.gen += 1
        gen = self.gen
        try:
            if fresh:
                self.proc = subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self.log_signal.emit("Interactive sign-in: a console window has opened —")
                self.log_signal.emit("enter your email/password THERE. It closes automatically once connected.")
                threading.Thread(target=self.monitor_engine, args=(self.proc, self.gen), daemon=True).start()
                threading.Thread(target=self.health_loop, args=(self.gen,), daemon=True).start()
            else:
                self.proc = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                threading.Thread(target=self.read_output, args=(self.proc, self.gen), daemon=True).start()
                threading.Thread(target=self.health_loop, args=(self.gen,), daemon=True).start()
            self.disconnect_btn.setEnabled(True)
            data_counter.start(self.proc.pid)
        except Exception as exc:
            self.log_signal.emit(f"Could not start engine: {exc}")
            self.proc = None
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.status_text.setText("Failed to start")

    # ------------------------------------------------- خواندن خروجی (thread پس‌زمینه)

    def read_output(self, proc, gen):
        stream = proc.stdout
        buf = b""
        try:
            while True:
                chunk = stream.read(1)
                if not chunk:
                    break
                buf += chunk
                text = buf.decode("utf-8", "replace")
                stripped = text.strip()

                if chunk in (b"\n", b"\r"):
                    line = stripped
                    buf = b""
                    if line:
                        self.line_signal.emit(line)
                    continue

                low = stripped.lower()
                if (len(stripped) > 3 and len(stripped) < 300
                        and any(k in low for k in PROMPT_KEYWORDS)):
                    if stripped.endswith(":") or stripped.endswith(" "):
                        buf = b""
                        self.prompt_signal.emit(stripped)

        except Exception as exc:
            self.log_signal.emit(f"Output reader error: {exc}")
        finally:
            code = proc.wait()

        if gen != self.gen:
            return
        self.log_signal.emit(f"Engine ended (exit code {code}).")
        self.state_signal.emit("NOT CONNECTED", "Disconnected")

    def monitor_engine(self, proc, gen):
        was_listening = False
        while gen == self.gen:
            if proc.poll() is not None:
                if not was_listening:
                    self.log_signal.emit("Sign-in window closed without connecting.")
                self.state_signal.emit("NOT CONNECTED", "Disconnected")
                return
            listening = port_in_use()
            if listening and not was_listening:
                self.state_signal.emit("CONNECTED", "Local proxy is running")
                was_listening = True
            time.sleep(1)

    def handle_engine_line(self, line):
        self.add_log(line)
        low = line.lower()
        if not any(k in low for k in PROMPT_KEYWORDS):
            self.cancel_pending_prompt()
        if "socks5 proxy listening" in low:
            self.state_signal.emit("CONNECTED", "Local proxy is running")
        if "exit ip" in low:
            self.ip_signal.emit(line)
        if "expected country" in low and "observed" in low:
            self.state_signal.emit("CONNECTED",
            "Connected (exit location differs from selected — try reconnecting)")
        if "fatal" in low or "traceback" in low:
            self.state_signal.emit("NOT CONNECTED", "Connection failed — check the activity log")
        if "401" in low or "unauthorized" in low or "forbidden" in low:
            self.log_signal.emit("(the edge rejected this session — try Force a fresh sign-in)")

    # ------------------------------------------------- پنجره رمز/کد

    def handle_prompt(self, prompt):
        self.pending_prompt = prompt
        if self.prompt_timer is None:
            self.prompt_timer = QTimer(self)
            self.prompt_timer.setSingleShot(True)
            self.prompt_timer.timeout.connect(self.show_prompt_dialog)
        self.prompt_timer.start(4000)

    def cancel_pending_prompt(self):
        if self.prompt_timer:
            self.prompt_timer.stop()
            self.prompt_timer = None
        self.pending_prompt = None

    def show_prompt_dialog(self):
        prompt = self.pending_prompt
        self.prompt_timer = None
        self.pending_prompt = None
        proc = self.proc
        if not prompt or not proc or proc.poll() is not None:
            return
        self.add_log(f"(engine is asking: {prompt})")
        low = prompt.lower()
        if "email" in low and "password" not in low:
            text, ok = QInputDialog.getText(
                self, "Firefox Account",
                prompt + "\n\nEnter your Firefox Account email:")
        elif "password" in low:
            text, ok = QInputDialog.getText(self, "Firefox Account",
                                            prompt, QLineEdit.Password)
        elif any(k in low for k in ("code", "2fa", "two-factor", "two factor",
                                    "verification")):
            text, ok = QInputDialog.getText(
                self, "Verification code",
                prompt + "\n\nCheck your email (and Spam folder) for the code:")
        elif "http" in low:
            QMessageBox.information(
                self, "Confirm in browser",
                prompt + "\n\nOpen the link, complete the sign-in, then press OK.")
            text, ok = "", True
        else:
            QMessageBox.information(self, "Action needed",
                                    prompt + "\n\nPress OK to continue.")
            text, ok = "", True
        try:
            proc.stdin.write(((text or "") + "\n").encode("utf-8"))
            proc.stdin.flush()
            self.add_log("(response sent to engine)")
        except Exception as exc:
            self.add_log(f"Could not send answer: {exc}")

    # ------------------------------------------------------------ disconnect / close

    def disconnect_vpn(self):
        self.gen += 1
        self.log_signal.emit("Stopping engine…")
        data_counter.tick()
        data_counter.pid = None
        kill_stale_engines()
        proc = self.proc
        if proc:
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        self.proc = None
        self.interactive = False
        self.ip_text.setText("Exit IP: —")
        self.state_signal.emit("NOT CONNECTED", "Disconnected")

    def closeEvent(self, event):
        if self.proc and self.proc.poll() is None:
            answer = QMessageBox.question(
                self, "Exit FoxyVPN Desktop", "Disconnect FoxyVPN before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes,
            )
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Yes:
                self.disconnect_vpn()
        set_system_proxy(False)
        self.stop_bridge()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.aboutToQuit.connect(lambda: set_system_proxy(False))

    window = FoxyVPNWindow()
    window.show()

    def update_worker():
        found = check_for_update()
        if found:
            version, asset = found
            window.update_signal.emit(version, asset)
    threading.Thread(target=update_worker, daemon=True).start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
