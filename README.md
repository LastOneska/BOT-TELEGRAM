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
| `/harga` | Menampilkan dan menyematkan tabel saran harga total jarak jemput + antar |
| `/setkm 1950 2500` | Mengatur patokan harga minimum dan maksimum per km |
| `/resetharga` | Mengembalikan patokan harga ke Rp1.950–2.500/km |
| `/catat 4.5 20000 14:13 [ID]` | Mencatat jarak total, pendapatan, waktu order diterima, dan ID opsional |
| `/rekap` | Rekap order, pendapatan, durasi, pendapatan/jam dan /km, serta jam terbaik |

Waktu `/catat` menggunakan WIB. Isi `HH:MM` untuk waktu diterima hari ini atau
`YYYY-MM-DDTHH:MM` untuk tanggal dan waktu lengkap. ID order bersifat opsional;
ID yang sama tidak dapat dicatat dua kali. Untuk data lama yang belum memiliki
waktu diterima, rekap menandai durasi dan pendapatan/jam sebagai tidak tersedia.
Pengaturan `/setkm` disimpan per pengguna. `/harga` memakai batas atas tiap
rentang jarak (0–5, 5–10, 10–15, dan 15–20 km), membulatkan ke atas ke Rp500,
serta menampilkan formula untuk jarak di atas 20 km. Nilai awal tabel dan
pembulatan dapat disesuaikan melalui `RP_PER_KM_MIN`, `RP_PER_KM_MAX`, dan
`PEMBULATAN` di `config.py`.

Pengguna tetap mengirim `/start` dan mengaktifkan `/alert on` untuk menerima pesan terjadwal. Alert dijadwalkan menurut zona waktu Bandung (WIB).

## Pengaturan dan batasan prediksi

Kota, titik tengah, batas area OSM, jenis lokasi, pola jam, dan tarif dasar dapat disesuaikan di `config.py`. Tarif awal adalah Rp2.500/km ditambah biaya jemput Rp5.000; faktor jam puncak dan hujan serta rentang ±5% juga ada di sana. Nilai ini adalah asumsi awal, bukan tarif resmi platform atau jaminan pendapatan.

Skor ramai menggabungkan jenis lokasi, jadwal perkiraan, cuaca Open-Meteo, dan kalender hari libur Indonesia. Penyesuaian cuaca merupakan heuristik sederhana (mal/rumah sakit dan pasar diberi faktor berbeda), bukan data permintaan aktual. Data OSM bukan data order real-time. Ketepatan bergantung pada kelengkapan data lokasi dan pola lokal. Periksa kondisi serta biaya perjalanan sendiri sebelum mengambil keputusan.

## Tes

Jalankan tes inti dengan:

```powershell
python -m unittest discover -s tests -v
```
