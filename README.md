# Asisten Driver Ojol Telegram

Bot informasi untuk driver di Bandung. Bot memperkirakan lokasi dan jam yang berpotensi ramai, menghitung rentang saran tarif, menyimpan order secara lokal, serta mengirim pengingat terjadwal. Bot tidak mengakses aplikasi Gojek, Grab, atau inDrive, tidak menerima/menawar order otomatis, dan tidak memanipulasi lokasi.

## Menjalankan bot

1. Gunakan Python 3.10 atau lebih baru.
2. Buat bot Telegram melalui BotFather dan salin tokennya.
3. Buat virtual environment dan pasang dependensi:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. Salin `.env.example` menjadi `.env`, lalu isi token. `main.py` memuat `.env` secara otomatis. Jangan commit token.
5. Jalankan `python main.py`.

Database SQLite dibuat otomatis di `driver_bot.sqlite3`. Atur `DATABASE_PATH` untuk memakai lokasi lain. Bot memakai koneksi internet untuk mengambil lokasi OpenStreetMap melalui Overpass dan data cuaca Open-Meteo. Lokasi OSM disimpan di cache selama tujuh hari; jika layanan gagal dan cache tersedia, bot menyatakan bahwa data yang dipakai sudah lama.

## Perintah

| Perintah | Fungsi |
|---|---|
| `/start` atau `/help` | Panduan penggunaan |
| `/ramai` | Lima lokasi dengan skor prediksi tertinggi saat ini |
| `/jam` | Pola jam puncak menurut jenis lokasi |
| `/alert on` / `/alert off` | Mengaktifkan atau mematikan pengingat |
| `/tawar 4.5` | Saran rentang tarif untuk jarak 4,5 km |
| `/catat 4.5 20000` | Mencatat jarak dan pendapatan order selesai |
| `/rekap` | Rekap order, pendapatan, jarak, dan jam terbaik hari ini |

Pengguna tetap mengirim `/start` dan mengaktifkan `/alert on` untuk menerima pesan terjadwal. Alert dijadwalkan menurut zona waktu Bandung (WIB).

## Pengaturan dan batasan prediksi

Kota, titik tengah, batas area OSM, jenis lokasi, pola jam, dan tarif dasar dapat disesuaikan di `config.py`. Tarif awal adalah Rp2.500/km ditambah biaya jemput Rp5.000; faktor jam puncak dan hujan serta rentang ±5% juga ada di sana. Nilai ini adalah asumsi awal, bukan tarif resmi platform atau jaminan pendapatan.

Skor ramai menggabungkan jenis lokasi, jadwal perkiraan, cuaca Open-Meteo, dan kalender hari libur Indonesia. Penyesuaian cuaca merupakan heuristik sederhana (mal/rumah sakit dan pasar diberi faktor berbeda), bukan data permintaan aktual. Data OSM bukan data order real-time. Ketepatan bergantung pada kelengkapan data lokasi dan pola lokal. Periksa kondisi serta biaya perjalanan sendiri sebelum mengambil keputusan.

## Tes

Jalankan tes inti dengan:

```powershell
python -m unittest discover -s tests -v
```
