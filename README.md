# YouTube Shorts Bulk Downloader & Metadata Batcher GUI

Sebuah aplikasi berbasis GUI (Graphical User Interface) menggunakan Python untuk mengunduh video YouTube Shorts secara massal dari URL channel tertentu, menyimpan metadata ke file Excel per batch, dan mengelola proses download dalam batch.

**Penting:** Mengunduh konten dari YouTube mungkin melanggar Ketentuan Layanan (Terms of Service) YouTube. Penggunaan alat ini sepenuhnya menjadi tanggung jawab pengguna. Harap gunakan alat ini secara bertanggung jawab dan patuhi hukum serta hak cipta.

## Fitur

*   Antarmuka GUI yang mudah digunakan.
*   Mengunduh video Shorts secara massal dari URL channel YouTube.
*   Opsi untuk membatasi jumlah video yang akan diproses.
*   Proses download dalam batch (ukuran batch dapat dikonfigurasi dalam kode).
*   Menyimpan metadata (URL, Judul, Deskripsi) setiap Shorts ke file Excel (`.xlsx`) di dalam folder batch.
*   Pilihan format/kualitas video yang dapat dipilih.
*   Indikator progress dan status proses.
*   Fungsi pembatalan proses yang sedang berjalan.

## Persyaratan

*   Python 3.6 atau lebih tinggi.
*   Pustaka Python: `tkinter` (biasanya sudah termasuk dalam instalasi Python standar), `yt-dlp`, `pandas`.
*   Program `yt-dlp` harus terinstal dan dapat diakses dari command line (biasanya diinstal bersama pustaka Python-nya, tapi pastikan PATH sistem Anda mengenalnya jika ada masalah).

## Instalasi

1.  Pastikan Anda sudah menginstal Python.
2.  Instal pustaka Python yang diperlukan menggunakan pip:

    ```bash
    pip install yt-dlp pandas openpyxl
    ```
    *(Catatan: `openpyxl` diperlukan oleh pandas untuk menulis file `.xlsx`)*

3.  Simpan kode Python yang Anda miliki (misalnya, beri nama `shorts_downloader_gui.py`).

## Cara Penggunaan

1.  Jalankan script Python:

    ```bash
    python shorts_downloader_gui.py
    ```

2.  Aplikasi GUI akan terbuka.
3.  **Select the MAIN folder to save batches:** Klik tombol "Browse" untuk memilih direktori utama tempat folder-folder batch (Batch_1, Batch_2, dst.) dan file Excel akan disimpan.
4.  **Enter the YouTube channel URL:** Masukkan URL channel YouTube yang ingin Anda unduh Shorts-nya (contoh: `https://www.youtube.com/@NamaChannel` atau `https://www.youtube.com/channel/ID_Channel`).
5.  **Number of videos to process (empty for all):** Masukkan jumlah maksimum Shorts yang ingin Anda proses. Biarkan kosong jika ingin memproses semua Shorts yang ditemukan di channel tersebut.
6.  **Select Video Format/Quality:** Pilih format atau kualitas video yang diinginkan dari dropdown menu.
7.  Klik tombol **"Start Batch Process"** untuk memulai.
8.  Progress bar dan label status akan menampilkan kemajuan proses (pengambilan metadata, penyimpanan Excel, download per video dalam batch).
9.  Klik tombol **"Cancel Process"** jika Anda ingin menghentikan proses yang sedang berjalan.

## Struktur Output

Di dalam folder utama yang Anda pilih, script akan membuat subfolder untuk setiap batch (misal: `Batch_1`, `Batch_2`, dst.). Setiap subfolder batch akan berisi:

*   File Excel (`.xlsx`) yang berisi metadata Shorts untuk batch tersebut.
*   File video Shorts yang berhasil diunduh untuk batch tersebut.

## Konfigurasi Lanjutan (dalam Kode)

Anda dapat mengubah ukuran batch (`BATCH_SIZE`) dengan mengedit nilai variabel di awal script Python (`test.py` atau nama file Anda).

```python
# --- Konfigurasi ---
BATCH_SIZE = 100 # Jumlah video Shorts per batch/folder. Bisa diubah sesuai kebutuhan.
