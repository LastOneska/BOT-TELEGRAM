# PRD: Bot Telegram Asisten Driver Ojol

## 1. Latar Belakang
Driver ojol sering kehilangan penumpang bukan karena lambat klik, tapi karena **standby di tempat yang salah** atau **menawar harga yang kurang pas** (khususnya di inDrive). Bot ini menjadi asisten yang membantu driver mengambil keputusan, sementara driver tetap menerima dan menawar order sendiri di aplikasi.

## 2. Tujuan
- Driver tahu **di mana dan kapan** area ramai, tanpa input manual.
- Driver mendapat **saran harga tawaran** yang kompetitif.
- Driver bisa **melacak pendapatan** dan pola orderannya.

## 3. Goals yang paling diinginkan
- Fake GPS / manipulasi lokasi.
- Auto-accept atau auto-bid order.
- Akses atau scraping data internal Gojek / Grab / inDrive.

## 4. Pengguna
Driver ojol/taksi online yang memakai Telegram. Level teknis awam, sehingga perintah harus sederhana.

## 5. Fitur

| # | Fitur | Perintah | Prioritas |
|---|-------|----------|-----------|
| 1 | Prediksi titik ramai sekarang | `/ramai` | P0 |
| 2 | Jadwal jam ramai per area | `/jam` | P0 |
| 3 | Alert sebelum jam ramai | otomatis, `/alert on/off` | P1 |
| 4 | Kalkulator saran tawaran | `/tawar <km>` | P1 |
| 5 | Catat orderan & pendapatan | `/catat <km> <harga>`, `/rekap` | P1 |
| 6 | Feedback "di sini ramai" (opsional) | kirim lokasi asli | P2 |

### Cara kerja prediksi (tanpa input driver)
- **Lokasi pemicu keramaian** dari OpenStreetMap (Overpass API): stasiun, terminal, kampus, mall, pasar, rumah sakit, kawasan kantor.
- **Aturan jam** per jenis lokasi (contoh: stasiun 06.00-08.30 dan 16.30-19.00).
- **Faktor tambahan**: cuaca (Open-Meteo) dan hari libur nasional.
- **Skor keramaian** = bobot lokasi x faktor jam x faktor cuaca/libur, lalu diurutkan.

### Rumus saran tawaran (sederhana)
`harga dasar = tarif per km x jarak + biaya jemput`, lalu dikali pengali jam ramai/hujan.
Output berupa **rentang** (misal "Rp18.000-22.000"), bukan angka tunggal.

## 6. Alur Pengguna
1. Driver kirim `/start`, bot meminta pilih kota/area.
2. Driver ketik `/ramai`, bot membalas 3-5 area teratas + jam puncaknya.
3. Driver standby ke area tersebut.
4. Order masuk di aplikasi, driver ketik `/tawar 4.5`, bot memberi rentang harga, driver menawar secara manual.
5. Selesai order, driver `/catat 4.5 20000`.
6. Akhir hari `/rekap`, bot menampilkan total dan jam paling menguntungkan.

## 7. Arsitektur
- **Bahasa**: Python
- **Library bot**: `python-telegram-bot`
- **Data lokasi**: OpenStreetMap Overpass API (di-cache lokal)
- **Cuaca**: Open-Meteo
- **Database**: SQLite (tabel `users`, `areas`, `orders`)
- **Scheduler**: JobQueue bawaan `python-telegram-bot` untuk alert
- **Config**: `config.py` berisi kota, tarif per km, jam ramai

## 8. Metrik Keberhasilan
- Jumlah driver aktif harian
- Frekuensi pemakaian `/ramai` dan `/tawar`
- Feedback driver: "prediksi akurat" (tombol 👍/👎 di setiap hasil `/ramai`)

## 9. Risiko

| Risiko | Penanganan |
|--------|-----------|
| Prediksi kurang akurat (bukan data real-time) | Tampilkan label "prediksi", tambah feedback driver di P2 |
| Data OSM tidak lengkap | Titik manual bisa ditambah lewat config |
| Tarif per km beda tiap kota | Diatur per kota di config |
| Dikira mirip tool "tuyul" | Dicatat jelas di Non-Goals: bot hanya memberi informasi, aksi tetap manual |

## 10. Tahapan
1. **Tahap 1**: bot dasar `/start` + struktur project
2. **Tahap 2**: ambil data lokasi dari OSM + `/ramai`
3. **Tahap 3**: aturan jam + `/jam` + faktor cuaca/libur
4. **Tahap 4**: `/tawar` + `/catat` + `/rekap` (SQLite)
5. **Tahap 5**: alert terjadwal
6. **Tahap 6**: feedback driver (opsional)

## 11. Yang Sudah Diputuskan
- Kota Bandung(akan masuk ke `config.py`)