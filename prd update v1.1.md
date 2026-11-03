# PRD Bot Telegram inDrive — Update v1.1

Tanggal: 2026-11-02

## Ringkasan Update v1.1

Update v1.1 memperbaiki bug "Jam Terbaik" di rekap harian dan menambah saran harga otomatis berdasarkan rentang jarak, tanpa driver perlu input apa pun.

| Area | Sebelumnya | v1.1 |
| --- | --- | --- |
| Jam Terbaik | Muncul jam tanpa order (21.00–22.00 padahal order terakhir selesai 20.26) | Dihitung dari timestamp order asli, zona waktu WIB |
| Saran harga | Belum ada / butuh input manual | Tabel saran harga per rentang jarak, sudah termasuk jarak jemput + antar |
| Input driver | Berpotensi manual | Nol input tambahan, karena di inDrive siapa cepat dia dapat |
| Rekap harian | Order, pendapatan, jarak, jam terbaik | Ditambah pendapatan per jam dan Rp per km |

## Latar Belakang dan Masalah

Rekap 02-11-2026 menunjukkan dua masalah: data jam terbaik tidak masuk akal, dan driver belum punya patokan harga yang cepat dipakai saat order masuk.

**Data rekap 02-11-2026 (WIB):**

| Metrik | Nilai |
| --- | --- |
| Order | 8 |
| Pendapatan kotor | Rp135.100 |
| Jarak tercatat | 58,1 km |
| Bensin | Rp25.000 |
| Order pertama | 14.13 |
| Order terakhir masuk / selesai | 19.45 / 20.26 |
| Rekap dikirim bot | 21.14 |
| Jam terbaik (versi bot) | 21.00–22.00 (Rp26.000) |

**Masalah 1: bug Jam Terbaik.** Tidak ada order yang selesai setelah 20.26, tetapi bot melaporkan jam terbaik 21.00–22.00. Penyebab belum dipastikan. Dugaan: bot memakai waktu kirim rekap, bukan waktu order, atau ada selisih zona waktu (UTC vs WIB).

**Masalah 2: tidak ada patokan harga.** Di inDrive penumpang menawar harga dan order diambil driver yang paling cepat. Driver tidak sempat menghitung jarak jemput + antar, sehingga mudah menerima order yang tidak menguntungkan.

**Angka riil hari itu:** 6 jam 13 menit narik, ±Rp21.700/jam kotor, ±Rp17.700/jam setelah bensin, ±Rp2.325/km kotor.

## Tujuan

Tujuan v1.1: rekap harian akurat, dan driver punya patokan harga yang bisa dibaca dalam hitungan detik tanpa mengetik apa pun.

**Tujuan:**

- Jam Terbaik di rekap selalu cocok dengan jam order sebenarnya (0 kasus jam tanpa order).
- Bot mengirim tabel saran harga per rentang jarak, sudah termasuk jarak jemput + antar.
- Driver tidak perlu input jarak atau tawaran untuk mendapat saran.
- Bot menerima atau menolak order otomatis.
- Bot membaca atau mengotomatisasi layar aplikasi inDrive.
- Bot membuat penumpang memakai Telegram (penumpang tetap order lewat inDrive).
- fake gps untuk memindahkan lokasi driver ke titik ramai.

**Keputusan implementasi (03-11-2026):** driver menggunakan iPhone dan tidak
memiliki API/integrasi resmi inDrive. Bot tidak membaca layar/notifikasi,
tidak menerima atau menolak order, tidak memalsukan GPS, serta tidak
memindahkan pemesanan penumpang ke Telegram. Cakupan yang feasible adalah
`/cekorder <km_total> <tawaran>`: driver memasukkan jarak total dan tawaran
sendiri, bot membandingkannya dengan patokan harga per km, lalu driver
memutuskan secara manual di inDrive. Sebagai alternatif fake GPS, `/ramai`
menyediakan tautan navigasi biasa ke titik hotspot melalui lokasi asli iPhone;
tautan tidak mengubah lokasi perangkat atau aplikasi lain.

## Fitur A: Perbaikan Bug Jam Terbaik

Jam Terbaik harus dihitung dari waktu order yang benar-benar tercatat, dikelompokkan per jam dalam WIB, dan hanya memilih jam yang punya order.

**Aturan baru:**

1. Setiap order disimpan dengan timestamp UTC, lalu dikonversi ke Asia/Jakarta (UTC+07:00) sebelum dikelompokkan.
2. Waktu acuan order = waktu order selesai, karena pendapatan baru pasti saat itu.
3. Order dikelompokkan per jam penuh (14.00–15.00, 15.00–16.00, dst.), dan hanya jam yang punya minimal 1 order yang dihitung.
4. Jam Terbaik = jam dengan total pendapatan tertinggi. Jika seri, pilih yang jumlah ordernya lebih banyak.
5. Jika hari itu 0 order, tampilkan "Jam terbaik: -".
6. Batas hari rekap = 00.00 WIB, bukan 00.00 UTC.
7. Waktu yang dipakai untuk mengelompokkan tidak boleh berasal dari waktu kirim rekap.

**Cara menemukan akar masalah (untuk developer):** cetak daftar (timestamp mentah, timestamp WIB, jam kelompok) untuk 8 order tanggal 02-11-2026, lalu bandingkan dengan jam asli di aplikasi. Jika semua jam bergeser +7, masalahnya zona waktu. Jika jam terbaik selalu sama dengan jam kirim rekap, masalahnya salah ambil waktu.

## Fitur B: Saran Harga Otomatis

Bot menyediakan tabel saran harga per rentang total jarak (jemput + antar) yang bisa dibuka satu tap, tanpa driver mengetik jarak atau tawaran.

**Tabel saran harga (default Rp1.950–2.500 per km):**

Harga dihitung dari batas atas tiap rentang × Rp per km, dibulatkan ke atas ke kelipatan Rp500. Contoh: 5 km × Rp1.950 = Rp9.750, jadi Rp10.000.

| Total jarak (jemput + antar) | Saran minimal (Rp1.950/km) | Saran maksimal (Rp2.500/km) |
| --- | --- | --- |
| 0–5 km | Rp10.000 | Rp12.500 |
| 5–10 km | Rp19.500 | Rp25.000 |
| 10–15 km | Rp29.500 | Rp37.500 |
| 15–20 km | Rp39.000 | Rp50.000 |
| Di atas 20 km | Rp1.950 × jarak | Rp2.500 × jarak |

**Cara driver memakainya (tanpa input):**

1. Pesan tabel saran harga disematkan (pin) di chat bot, jadi bisa dilihat sekilas saat order masuk.
2. Perintah `/harga` menampilkan tabel yang sama dalam satu tap.
3. Driver membandingkan jarak yang sudah tertera di aplikasi inDrive dengan tabel, lalu memutuskan sendiri.

**Pengaturan sekali di awal (bukan saat narik):**

- `/setkm 1950 2500` mengubah batas bawah dan atas Rp per km, tabel dihitung ulang otomatis.
- `/resetharga` mengembalikan ke default Rp1.950–2.500/km.
- Angka tabel dibulatkan ke atas ke kelipatan Rp500 agar mudah ditawarkan.

**Evaluasi di rekap harian:** bot membandingkan Rp per km aktual hari itu dengan angka saran, supaya driver tahu apakah harinya di atas atau di bawah patokan.

## Format Rekap Harian Baru

Rekap tetap pendek dan terkirim otomatis, dengan tiga baris tambahan: durasi narik, pendapatan per jam, dan perbandingan Rp per km dengan patokan.

**Contoh keluaran memakai data 02-11-2026:**

```
Rekap hari ini (02-11-2026 WIB)
• Order: 8
• Pendapatan: Rp135.100
• Jarak tercatat: 58,1 km
• Durasi narik: 6 j 13 m (14.13–20.26)
• Pendapatan/jam: Rp21.700
• Pendapatan/km: Rp2.325 (patokan Rp1.950–2.500, dalam rentang)
• Jam terbaik: <jam dari data order> (Rp<total jam itu>)
```

**Rumus:**

- Durasi narik = waktu order pertama diterima sampai order terakhir selesai. Bot tidak tahu kapan driver mulai online, jadi waktu menunggu sebelum order pertama tidak terhitung.
- Pendapatan/jam = pendapatan ÷ durasi narik (dalam jam).
- Pendapatan/km = pendapatan ÷ jarak tercatat.
- Patokan Rp1.950–2.500/km mengikuti tabel saran harga dan bisa diubah lewat `/setkm`. Status di rekap: di bawah rentang, dalam rentang, atau di atas rentang.

## Kebutuhan Data dan Teknis

Perubahan teknis kecil: simpan waktu order dengan benar, konversi ke WIB saat menghitung, dan simpan rentang harga sebagai konfigurasi.

**Data per order yang harus tersimpan:**

| Field | Isi | Catatan |
| --- | --- | --- |
| order_id | ID unik order | Untuk mencegah order terhitung dua kali |
| selesai_at | Waktu order selesai (UTC) | Dasar Jam Terbaik dan batas hari |
| diterima_at | Waktu order diterima (UTC) | Dasar durasi narik |
| pendapatan | Rupiah (angka bulat) | Simpan sebagai integer, bukan teks |
| jarak_km | Desimal 1 angka | Untuk Rp per km |

**Konfigurasi baru:**

- `TIMEZONE = "Asia/Jakarta"` (di Python: `zoneinfo.ZoneInfo`).
- `RP_PER_KM_MIN = 1950` dan `RP_PER_KM_MAX = 2500`; tabel harga dihitung dari dua angka ini dan bisa diubah lewat `/setkm`.
- `PEMBULATAN = 500`.

**Perintah bot baru:** `/harga`, `/setkm`, `/resetharga`, dan `/cekorder`.

**Batasan:** bot hanya memakai data yang sudah masuk ke sistemnya. Cara data order masuk (input driver, notifikasi, atau cara lain) tidak diubah di v1.1. Bot tidak memalsukan GPS; tautan navigasi hotspot memakai lokasi aktual perangkat.
`/cekorder` menggunakan input manual; tidak membaca order dari aplikasi dan
tidak membuat keputusan otomatis.

## Acceptance Criteria dan Test Plan

v1.1 dianggap selesai jika semua skenario di bawah lolos dan rekap memakai data order asli, bukan waktu kirim rekap.

| Skenario | Hasil yang diharapkan |
| --- | --- |
| Data 02-11-2026 (8 order, terakhir selesai 20.26) | Jam Terbaik berada antara 14.00 dan 21.00, tidak pernah 21.00–22.00 |
| Order selesai 17.30 UTC (00.30 WIB) | Masuk rekap tanggal WIB berikutnya |
| Hari tanpa order | Rekap menampilkan "Jam terbaik: -" |
| Dua jam dengan total pendapatan sama | Dipilih jam dengan order lebih banyak |
| Rekap dikirim jam 21.14 | Hasil Jam Terbaik sama persis dengan jika dikirim jam 23.00 |
| Rekap 02-11-2026 (Rp2.325/km) | Status "dalam rentang" terhadap patokan Rp1.950–2.500 |
| `/harga` | Tabel saran harga muncul dalam satu pesan |
| `/cekorder 5 10000` | Membandingkan tawaran dengan patokan Rp1.950–2.500/km tanpa tindakan otomatis |
| `/setkm 2000 2600` | Baris 0–5 km jadi Rp10.000–13.000, rekap berikutnya memakai rentang baru |
| `/setkm` dengan format salah, atau min lebih besar dari maks | Bot membalas contoh format yang benar, tabel tidak berubah |
| `/resetharga` | Rentang kembali ke Rp1.950–2.500/km |

**Checklist rilis:**

- [ ] Akar masalah bug Jam Terbaik ditemukan dan dicatat
- [ ] Semua skenario di tabel lolos
- [ ] Tabel harga disematkan di chat bot
- [ ] Dicoba satu hari penuh dengan order nyata sebelum dianggap final

## Pertanyaan Terbuka dan Rencana Rilis

Ada empat hal yang perlu diputuskan atau dipantau sebelum dan sesudah rilis.

**Pertanyaan terbuka:**

- Rentang Rp1.950–2.500/km perlu diuji seminggu. Jika terlalu tinggi dan tawaran sering tidak diterima penumpang, turunkan batas bawah lewat `/setkm`.
- Apakah jarak yang tertera di inDrive sudah mencakup jarak jemput, atau hanya jarak antar? Jika hanya jarak antar, tabel perlu dibaca dengan tambahan jarak jemput.
- Bensin dan biaya kendaraan tidak tercatat di bot. Perlu ditambah supaya rekap bisa menampilkan pendapatan bersih?
- Bagian PRD v1 selain yang dibahas di sini (misalnya titik ramai dan jam ramai) tidak diubah dan perlu digabung dengan dokumen ini.

**Rencana rilis:**

1. Temukan dan perbaiki akar bug Jam Terbaik, uji dengan data 02-11-2026.
2. Tambah tabel harga, `/harga`, `/setkm`, `/resetharga`.
3. Tambah baris baru di rekap harian.
4. Uji satu hari penuh dengan order nyata, lalu evaluasi angka saran harga setelah seminggu.