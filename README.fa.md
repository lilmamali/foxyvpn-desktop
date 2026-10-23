[README.fa.md](https://github.com/user-attachments/files/33892182/README.fa.md)
[فارسی](README.fa.md) | [English](README.md)

# FoxyVPN Desktop

کلاینت گرافیکی ویندوز برای VPN داخلی فایرفاکس (از طریق پکیج `foxyvpn`).
هر کاربر با **اکانت فایرفاکس خودش** وارد می‌شه — رمز فقط بار اول پرسیده می‌شه و **هرگز ذخیره نمی‌شه**.

> 🦊 استفاده شخصی، توزیع بین دوستان به‌صورت فایل `.exe` اجرایی.

---

## ✨ امکانات

- 🔐 **ورود با اکانت فایرفاکس هر کاربر** — رمز ذخیره نمی‌شه، فقط توکن OAuth نگه‌داری می‌شه
- 🌍 **۳۳ کشور** (بارگذاری خودکار از موتور با `--list-servers`)
- 🔄 **اتصال مجدد خودکار** هنگام بیماری تونل (پورت‌شده از اپ اندروید)
- 🚦 **پل HTTP→SOCKS5 روی `127.0.0.1:8080`** تا همه برنامه‌های ویندوز از تونل رد بشن
- 📊 **پنل مصرف ماهانه** با نوار پیشرفت (شمارش محلی + سینک سقف از موزیلا)
- 🛡️ **کش ردشده‌ها با backoff نمایی** (پورت‌شده از اپ اندروید)
- 🔄 **آپدیت‌ر خودکار** — هنگام اجرا چک می‌کنه، در صورت وجود نسخه جدید پیشنهاد دانلود و نصب می‌ده
- 🧹 **خاموش‌کردن تمیز** — پردازه‌های موتور رو می‌کشه، پروکسی ویندوز رو موقع خروج/کرش برمی‌گردونه

---

## 📦 ساختار پروژه (توزیع بین کاربر)

```
FoxyVPN-Pack/
├── FoxyVPNDesktop.exe   ← رابط گرافیکی (PySide6، پنجره‌ای)
├── foxyvpn-engine.exe   ← موتور (کنسولی، --collect-all foxyvpn)
└── README.txt           ← راهنمای فارسی کاربر
```

هر دو فایل exe باید توی **همون پوشه** باشن.

---

## 🛠️ بیلد (فقط توسعه‌دهنده)

### ۱) ساخت venv و نصب پیش‌نیازها

```cmd
cd C:\Users\<you>\fox
python -m venv venv
venv\Scripts\activate
pip install PySide6 psutil pyinstaller foxyvpn
```

### ۲) بیلد موتور

```cmd
venv\Scripts\pyinstaller --onefile --name foxyvpn-engine ^
    --collect-all foxyvpn ^
    --hidden-import foxyvpn.__main__ ^
    venv\Lib\site-packages\foxyvpn\__main__.py
```

### ۳) بیلد رابط گرافیکی

```cmd
venv\Scripts\pyinstaller --onefile --windowed --name FoxyVPNDesktop app.py
```

خروجی: `dist\FoxyVPNDesktop.exe`. این فایل رو کنار `foxyvpn-engine.exe` بذار.

---

## 🚀 استفاده (کاربر نهایی)

1. `FoxyVPNDesktop.exe` و `foxyvpn-engine.exe` رو توی یه پوشه بذار.
2. `FoxyVPNDesktop.exe` رو اجرا کن.
3. ایمیل اکانت فایرفاکست رو وارد کن → **Connect** رو بزن.
4. یه پنجره کنسول باز می‌شه — رمزت رو اونجا وارد کن. خودش بسته می‌شه.
5. وضعیت سبز می‌شه → **CONNECTED**.
6. تیک **"Route all Windows apps through the VPN"** رو بزن تا مرورگرها هم از تونل رد بشن.

کاربرهای قبلی خودکار وصل می‌شن (توکن OAuth کش‌شده).

---

## 📊 پنل مصرف دیتا

- نوار پیشرفت، مصرف ماهانه رو نشون می‌ده (از ۵۰ گیگ برای اکانت رایگان).
- دکمه **↻ Sync with Mozilla** رو بزن تا سقف ماهانه از API موزیلا به‌روز بشه.
- مصرف به‌صورت محلی از طریق I/O پردازه موتور (`psutil`) شمرده می‌شه؛ ماه اول هر ماه ریست می‌شه.
- ذخیره در `%LOCALAPPDATA%\FoxyVPNDesktop\usage.json`.

---

## ⚠️ محدودیت‌ها

- **سقف ۵۰ گیگ ماهانه** برای اکانت رایگان فایرفاکس.
- **مغایرت کشور خروجی**: موزیلا از anycast استفاده می‌کنه — ممکنه کشور IP خروجی با انتخابت فرق داشته باشه.
- **اختلالات سرویس موزیلا**: اگه `--list-servers` کار نکنه، فقط "Recommended" نمایش داده می‌شه.
- **شمارش مصرف به‌ازای دستگاه**: مصرف دستگاه‌های دیگه با همون اکانت، اینجا حساب نمی‌شه.

---

## 🔧 فایل‌های تنظیمات

| تنظیمات | مسیر |
|---------|------|
| توکن‌های OAuth | `%USERPROFILE%\.foxyvpn-tokens.json` |
| فایل وضعیت | `%LOCALAPPDATA%\FoxyVPNDesktop\status.json` |
| فایل مصرف | `%LOCALAPPDATA%\FoxyVPNDesktop\usage.json` |
| وضعیت موتور | `%LOCALAPPDATA%\FoxyVPNDesktop\proxy-state.json` |

---

## 🔄 روند انتشار (نگهدارنده)

1. کد `app.py` رو ویرایش کن.
2. `APP_VERSION` رو بالا ببر (مثلاً `"1.0"` → `"1.1"`).
3. بیلد کن: `pyinstaller --onefile --windowed --name FoxyVPNDesktop app.py`.
4. یه Release جدید توی گیت‌هاب با tag `v1.1` بساز و `FoxyVPNDesktop.exe` رو آپلود کن.
5. فایل `version.json` روی برنچ `main` رو آپدیت کن:
   ```json
   { "version": "1.1", "asset": "FoxyVPNDesktop.exe" }
   ```
6. کلاینت‌های موجود، خودکار به کاربرها پیشنهاد آپدیت می‌دن.

---

## 📝 لایسنس

MIT — ببین [LICENSE](LICENSE).
