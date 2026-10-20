FoxyVPN Desktop 🦊
A clean, personal Windows client for the Firefox Built-in VPN service.

FoxyVPN Desktop wraps the foxyvpn engine with a simple dark-themed GUI: connect withyour own Firefox Account, pick a country, and route all your apps through a local proxy —no technical setup required.

⚠️ Unofficial project — not affiliated with or endorsed by Mozilla.Use it only with an account and entitlement you are authorized to use, and inaccordance with Mozilla's terms of service.

✨ Features
🔑 Your own account — every user signs in with their own Firefox Account email.The password is asked only once (in a console popup) and never stored.
🔁 Auto re-connect — after the first sign-in, a session token is cached locally(~/.foxyvpn-tokens.json) and later connections are fully silent.
🌍 Country picker — all Firefox Built-in VPN server locations, plus theauto-selected "Recommended" server.
🖥️ All apps, not just Firefox — an HTTP→SOCKS bridge is published as theWindows system proxy, so Chrome, Edge, Opera, Firefox and most desktop apps aretunneled automatically. SOCKS5 is also available directly for apps like Telegram.
🩺 Self-healing tunnel — background health checks detect a wedged tunnel andrestart the engine automatically (inspired by the Android FoxyVPN client).
🚫 Smart refusal cache — destinations rejected by the upstream edge (ad/trackingdomains) are refused locally with exponential backoff instead of wasting round trips.
🧹 Clean disconnect — the engine (and all of its child processes) is reliablykilled, and the system proxy is always restored on exit.
📦 Download
Grab the two executables from the Releases page:

File	Purpose
FoxyVPNDesktop.exe	The graphical interface
foxyvpn-engine.exe	The VPN engine (required — must sit next to the GUI)
Both files must stay in the same folder.

The app ships with a built-in auto-updater: when a new version is published, it offersto download and replace itself on the next launch.

🚀 Usage
Run FoxyVPNDesktop.exe
Enter your own Firefox Account email (an account that has the FirefoxBuilt-in VPN service, with its ~50 GB monthly data limit)
Press Connect
First time: a console window opens — enter your email and password there.Keep it open until you disconnect.
After that: connections are automatic, no prompts.
Tick Force a fresh sign-in to log in again from scratch.
Wait for CONNECTED — with the Route all Windows apps checkbox enabled,browsers and most apps are tunneled automatically.
Manual app configuration
App type	Address
SOCKS5-aware apps (Telegram, etc.)	SOCKS5 → 127.0.0.1:1080
HTTP-proxy-aware apps	HTTP → 127.0.0.1:8080
🛠 How it works
Your apps   │   ├─ System proxy (HTTP) ─►  HTTP bridge :8080 ─┐   ├─ Direct SOCKS5 ─────────────────────────────┤   │                                             ▼   │                              foxyvpn-engine (SOCKS5 :1080)   │                                             │   │                              HTTP/2 tunnel (proxy-pass)   │                                             ▼   └──────────────────────────────►  Firefox VPN edge (Fastly MASQUE)
The engine handles Firefox Accounts login, Fastly anti-bot challenge solving
