# Smart Maggot Farming Monitor

Website native HTML, JavaScript, dan Tailwind CSS untuk memonitor kondisi budidaya maggot dari ESP32. Backend FastAPI menerima payload melalui Mosquitto MQTT, menyimpan riwayat ke MySQL, dan menyediakan REST API untuk dashboard, monitoring, notifikasi, serta laporan PDF/Excel.

## Sensor dan aturan kondisi

Sistem hanya memakai perangkat yang tersedia di `Magot.ino`:

| Perangkat | Data | Aturan |
| --- | --- | --- |
| DHT22 | Suhu | Normal jika `temperature > 29` dan `temperature < 39` |
| DHT22 | Kelembapan | Dicatat dan divisualisasikan tanpa ambang abnormal |
| MQ | Nilai gas mentah | Abnormal jika `gas > 2000` |
| Buzzer | `ON` / `OFF` | Status peringatan yang dilaporkan ESP32 |

Jika DHT22 gagal dibaca, `Magot.ino` mengirim suhu dan kelembapan bernilai `0`. Backend menyimpan data tersebut sebagai masalah DHT, tetapi tidak memasukkannya ke statistik suhu/kelembapan.

Contoh payload MQTT:

```json
{
  "temperature": 32.4,
  "humidity": 74,
  "gas": 1840,
  "buzzer": "OFF"
}
```

Topik default: `esp32/sensor_data`.

## Fitur

- Login admin tanpa registrasi publik.
- Semua halaman dan REST API data dilindungi session cookie `HttpOnly`.
- Monitoring suhu, kelembapan, gas, dan buzzer dengan polling REST setiap 2 detik.
- Grafik native SVG tanpa dependensi CDN.
- Notifikasi ketika kondisi berubah dari normal menjadi abnormal.
- Status data online, terlambat, atau belum tersedia.
- Laporan sensor dengan filter tanggal maksimal 7 hari.
- Export laporan ke PDF dan Excel.
- Retensi data otomatis selama 90 hari.
- Tampilan responsif yang mengikuti tema dashboard Smart Maggot Farming.

## Arsitektur

```text
DHT22 + MQ + Buzzer
        |
       ESP32
        |
        | MQTT esp32/sensor_data
        v
     Mosquitto
        |
        v
Paho MQTT di FastAPI
        |
        v
MySQL db_mocom_maggot
        |
        v
REST API FastAPI
        |
        | polling 2 detik
        v
Browser
```

Backend wajib dijalankan dengan **satu Uvicorn worker** agar hanya ada satu subscriber MQTT dan data tidak tersimpan ganda.

## Struktur penting

```text
backend/
  api.py          # FastAPI, REST route, halaman, login, lifecycle
  auth.py         # Hash password, session token, rate limiter
  config.py       # Konfigurasi environment
  hardware.py     # Subscriber Mosquitto MQTT
  konektor.py     # Koneksi MySQL
  model.py        # Schema dan query MySQL
  sistem.py       # Validasi, aturan abnormal, statistik, export
css/
  input.css       # Sumber Tailwind
  output.css      # Hasil build Tailwind
js/
  app.js          # Helper API, shell, format, grafik
  dashboard.js
  monitor.js
  laporan.js
  login.js
view/
  dashboard.html
  monitor.html
  laporan.html
  login.html
tests/
```

## Persyaratan

- Python 3.11 atau lebih baru
- Node.js dan npm
- MySQL Server
- Mosquitto MQTT broker
- Database MySQL bernama `db_mocom_maggot`

Database harus sudah dibuat. Tabel `users`, `sessions`, `sensor_readings`, dan `notifications` dibuat otomatis ketika aplikasi pertama dijalankan.

## Instalasi

### 1. Aktifkan virtual environment

PowerShell:

```powershell
.\Scripts\Activate.ps1
```

Jika membuat environment baru:

```powershell
python -m venv .
.\Scripts\Activate.ps1
```

### 2. Instal dependensi Python dan Tailwind

```powershell
python -m pip install -r requirements.txt
npm install
```

### 3. Siapkan MySQL

```sql
CREATE DATABASE IF NOT EXISTS db_mocom_maggot
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

Pastikan akun MySQL memiliki izin membuat tabel, membaca, menulis, memperbarui, dan menghapus data pada database tersebut.

### 4. Buat konfigurasi lokal

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=db_mocom_maggot
MYSQL_USER=root
MYSQL_PASSWORD=admin

MQTT_HOST=192.168.18.43
MQTT_PORT=1883
MQTT_TOPIC=esp32/sensor_data
MQTT_ENABLED=true

ADMIN_USERNAME=admin
ADMIN_PASSWORD=ganti-dengan-password-minimal-12-karakter
SESSION_TOKEN_PEPPER=ganti-dengan-rangkaian-rahasia-yang-panjang
```

Catatan keamanan:

- `ADMIN_PASSWORD` minimal 12 karakter dan hanya digunakan saat akun admin belum ada.
- Password admin disimpan menggunakan hash `scrypt`.
- Jika akun admin sudah ada, perubahan `ADMIN_PASSWORD` pada `.env` tidak mengubah password akun tersebut.
- `SESSION_TOKEN_PEPPER` wajib diisi dengan nilai rahasia yang panjang.
- Jangan commit `.env`.

### 5. Build Tailwind CSS

```powershell
npm run build:css
```

Untuk development dengan build otomatis:

```powershell
npm run watch:css
```

## Menjalankan aplikasi

```powershell
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Buka:

```text
http://127.0.0.1:8000
```

Jangan menaikkan jumlah worker. Subscriber MQTT berjalan pada lifecycle aplikasi dan satu worker adalah deployment yang didukung.

## Konfigurasi Mosquitto dan ESP32

Nilai berikut harus konsisten antara `.env` dan `Magot.ino`:

```cpp
const char* mqtt_server = "192.168.18.43";
const int mqtt_port = 1883;
const char* mqtt_topic = "esp32/sensor_data";
```

Konfigurasi default mengikuti broker pada jaringan lokal terpercaya. Untuk penggunaan di luar jaringan lokal, aktifkan username/password, ACL topik, dan TLS pada Mosquitto; lalu isi `MQTT_USERNAME`, `MQTT_PASSWORD`, dan `MQTT_TLS=true`.

Untuk menjalankan dashboard tanpa mencoba terhubung ke broker:

```dotenv
MQTT_ENABLED=false
```

## Halaman

| URL | Fungsi |
| --- | --- |
| `/login` | Login admin |
| `/dashboard` | Ringkasan sensor dan notifikasi |
| `/monitor` | Grafik serta tabel real-time |
| `/laporan` | Filter laporan dan export |

## REST API utama

Semua endpoint berikut, kecuali login, membutuhkan session:

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/sensors/latest
GET  /api/sensors/history
GET  /api/dashboard/summary
GET  /api/notifications
GET  /api/reports/summary
GET  /api/reports/readings
GET  /api/reports/export.pdf
GET  /api/reports/export.xlsx
```

## Testing dan verifikasi

```powershell
python -m pytest
python -m compileall backend tests
npm run build:css
git diff --check
```

`pytest.ini` membatasi pencarian test ke folder `tests`, sehingga pytest tidak mengumpulkan test milik package virtual environment.

### Mengisi data dummy

Setelah aplikasi pernah dijalankan agar tabel database terbentuk, data testing
dapat diisi menggunakan `dummy.sql`:

```powershell
mysql -u root -p db_mocom_maggot -e "source dummy.sql"
```

Konfigurasi default menambahkan 336 pembacaan untuk tujuh hari terakhir dengan
interval 30 menit. Data mencakup kondisi normal, suhu dan gas abnormal, masalah
DHT22, buzzer tidak konsisten, serta notifikasi transisi. Ubah argumen pada
`CALL seed_dummy_sensor_data(7, 30);` di bagian bawah file untuk menyesuaikan
jumlah hari dan interval. Script menambahkan data tanpa menghapus data yang
sudah ada, sehingga sebaiknya digunakan hanya pada database development/testing.

## Penyimpanan data

- Timestamp disimpan dalam UTC.
- Tampilan dan batas tanggal laporan memakai `DISPLAY_TIMEZONE`, default `Asia/Jakarta`.
- Riwayat sensor disimpan 90 hari secara default.
- Notifikasi dibuat sekali ketika kondisi mulai abnormal, bukan setiap payload dua detik.
- Laporan PDF memuat maksimal 1.000 baris detail.
- Excel dapat memuat semua data dalam rentang laporan maksimal tujuh hari.

## Troubleshooting

### Aplikasi gagal startup karena admin

Pastikan `ADMIN_USERNAME`, `ADMIN_PASSWORD` minimal 12 karakter, dan `SESSION_TOKEN_PEPPER` sudah terisi.

### MySQL tidak dapat diakses

Periksa `MYSQL_HOST`, port, nama database, username, password, serta izin akun MySQL.

### Data sensor tidak masuk

Periksa:

1. ESP32 terhubung ke WiFi.
2. Alamat broker pada `Magot.ino` sama dengan `MQTT_HOST`.
3. Mosquitto berjalan di port yang sama.
4. Topik adalah `esp32/sensor_data`.
5. Log backend tidak menampilkan payload yang ditolak.

### Dashboard menampilkan “Data terlambat”

Data terbaru lebih lama dari `STALE_AFTER_SECONDS`, default 10 detik. Periksa koneksi ESP32, WiFi, dan Mosquitto.
