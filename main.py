# Import modul yang diperlukan
import tkinter as tk  # Modul standar Python untuk membuat GUI
from tkinter import ttk, filedialog, messagebox  # Widget tambahan, dialog file, dan kotak pesan
from threading import Thread, Event  # Untuk menjalankan operasi di thread terpisah dan sinyal pembatalan
import os  # Untuk berinteraksi dengan sistem operasi, seperti membuat direktori
import yt_dlp  # Pustaka untuk mendownload video dari YouTube dan situs lain
import subprocess  # Untuk menjalankan perintah eksternal, di sini digunakan untuk yt-dlp
import pandas as pd  # Pustaka untuk manipulasi data dan ekspor ke Excel/CSV
import math # Untuk perhitungan batch
import time # Untuk jeda antar download

# --- Konfigurasi Default ---
BATCH_SIZE = 100 # Jumlah video Shorts per batch/folder. Bisa diubah sesuai kebutuhan.
DEFAULT_DOWNLOAD_DELAY_SECONDS = 5 # Nilai default jeda dalam detik antara setiap upaya download video.
DEFAULT_RETRIES = 3 # Nilai default jumlah percobaan ulang download per video.
ERROR_FOLDER_NAME = "batching_error" # Nama folder untuk menyimpan log error

# Mapping nama format user-friendly ke string format yt-dlp
# yt-dlp akan mencoba memilih format terbaik yang sesuai dengan kriteria ini.
# Sintaks format selector: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md#format-selection
FORMAT_OPTIONS = {
    "Best Quality (Default)": "bestvideo+bestaudio/best", # Kualitas terbaik, container otomatis (biasanya mp4/mkv)
    "Best Quality (MP4)": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", # Prioritaskan MP4 container
    "Best Quality (MKV)": "bestvideo[ext=mkv]+bestaudio[ext=opus]/best[ext=mkv]", # Prioritaskan MKV container
    "1080p (MP4)": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[ext=mp4]", # 1080p di container MP4
    "720p (MP4)": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[ext=mp4]", # 720p di container MP4
    "480p (MP4)": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[ext=mp4]", # 480p di container MP4
    # Catatan: Format seperti .mov tidak umum di YouTube dan mungkin memerlukan konversi
    # yang membutuhkan ffmpeg dan menambah kompleksitas. Kita fokus pada format native.
}

# --- Variabel Global untuk Kontrol Proses ---
cancel_event = Event() # Event untuk memberi sinyal pembatalan ke thread download
current_subprocess = None # Menyimpan referensi ke proses yt-dlp yang sedang berjalan

# --- Fungsi Utama ---

def get_shorts_metadata(channel_url, num_videos_limit, proxy, progress_label_var):
    """
    Mengambil metadata (URL, Title, Description) dari video Shorts channel YouTube tertentu.
    Mencoba mengambil semua Shorts yang tersedia atau hingga batas num_videos_limit.
    Mendukung penggunaan proxy.

    Args:
        channel_url (str): URL channel YouTube.
        num_videos_limit (int or None): Jumlah maksimum video yang akan diambil metadatanya. None untuk semua.
        proxy (str or None): Alamat proxy (misal: "http://host:port"). None atau string kosong jika tidak pakai proxy.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk mengupdate teks label status.

    Returns:
        list: Daftar dictionary, di mana setiap dictionary berisi metadata satu Shorts
              (keys: 'url', 'title', 'description'), atau list kosong jika tidak ditemukan atau terjadi kesalahan.
    """
    # Opsi untuk yt_dlp saat mengambil informasi channel
    ydl_opts = {
        'quiet': True,
        'extract_flat': False, # Kita perlu metadata lengkap
        'ignoreerrors': True, # Lanjutkan meskipun ada error pada satu atau beberapa video
        'no_warnings': True, # Sembunyikan peringatan
    }

    # Tambahkan opsi proxy jika disediakan
    if proxy:
        ydl_opts['proxy'] = proxy
        print(f"Using proxy for metadata fetch: {proxy}")


    # Batasi jumlah item playlist jika num_videos_limit diberikan
    if num_videos_limit is not None and num_videos_limit > 0:
         # yt-dlp playlist_items format: START:END (1-based index)
         # Kita ingin 1 hingga num_videos_limit
         ydl_opts['playlist_items'] = f'1:{num_videos_limit}'
         print(f"Limiting metadata fetch to first {num_videos_limit} items.")
    else:
         # Jika tidak ada limit, coba ambil semua
         ydl_opts['playlist_items'] = '1:' # Coba ambil semua item dari awal
         print("Attempting to fetch metadata for all available Shorts.")


    # Memodifikasi URL channel untuk mengarah ke halaman Shorts channel
    channel_url_shorts = channel_url.strip() # Hapus spasi awal/akhir
    # Logika parsing URL yang lebih robust (bisa disempurnakan lagi jika perlu)
    try:
        if '/@' in channel_url_shorts:
            parts = channel_url_shorts.split('/@')
            username_part = parts[1].split('/')[0]
            channel_url_shorts = f'https://www.youtube.com/@{username_part}/shorts'
        elif '/channel/' in channel_url_shorts:
             channel_id = channel_url_shorts.split('/channel/')[1].split('/')[0]
             channel_url_shorts = f'https://www.youtube.com/channel/{channel_id}/shorts'
        elif '/user/' in channel_url_shorts:
             user_id = channel_url_shorts.split('/user/')[1].split('/')[0]
             channel_url_shorts = f'https://www.youtube.com/user/{user_id}/shorts'
        elif '/c/' in channel_url_shorts: # Custom URL
             custom_id = channel_url_shorts.split('/c/')[1].split('/')[0]
             channel_url_shorts = f'https://www.youtube.com/c/{custom_id}/shorts'
        else: # Fallback atau jika URL sudah base channel, coba tambahkan /shorts
             channel_url_shorts = channel_url_shorts.rstrip('/') + '/shorts' # Pastikan tidak ada double slash
             # Hapus path lain jika ada sebelum menambahkan /shorts
             if any(p in channel_url_shorts for p in ['/about', '/community', '/playlist', '/playlists', '/streams', '/featured', '/videos']):
                  print(f"Warning: URL '{channel_url}' might contain extra path, attempting to clean.")
                  channel_url_shorts = channel_url_shorts.split('/about')[0].split('/community')[0].split('/playlist')[0].split('/playlists')[0].split('/streams')[0].split('/featured')[0].split('/videos')[0].rstrip('/') + '/shorts'

    except Exception as e:
         print(f"Warning: Could not parse channel URL {channel_url}. Attempting to add /shorts directly. Error: {e}")
         # Fallback jika parsing gagal total
         channel_url_shorts = channel_url.strip().rstrip('/') + '/shorts'


    print(f"Attempting to extract metadata from: {channel_url_shorts}") # Debugging/Informasi
    # --- Peningkatan Feedback GUI ---
    progress_label_var.set(f"Step 1/3: Fetching metadata from {channel_url_shorts} (this may take a while for many videos)...")
    # --- End Peningkatan Feedback GUI ---

    all_shorts_metadata = []
    try:
        # Menggunakan yt_dlp untuk mengekstrak informasi lengkap
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # yt-dlp untuk playlist/channel akan mengembalikan dict dengan key 'entries'
            # atau None jika tidak ditemukan
            result = ydl.extract_info(channel_url_shorts, download=False)

        # Memproses hasil ekstraksi
        if result and 'entries' in result and result['entries']:
            # Iterasi melalui setiap entri (video/Short)
            for entry in result['entries']:
                # Pastikan entri valid dan memiliki ID
                if entry and entry.get('id'):
                    video_id = entry['id']
                    # Gunakan .get() dengan nilai default untuk menghindari KeyError
                    video_title = entry.get('title', 'Untitled')
                    video_description = entry.get('description', '')
                    # Pastikan ini memang Shorts (cek durasi atau format URL, yt-dlp biasanya sudah filter)
                    # Atau hanya ambil jika URL format Shorts
                    short_url = f'https://www.youtube.com/shorts/{video_id}'
                    all_shorts_metadata.append({
                        'url': short_url,
                        'title': video_title,
                        'description': video_description
                    })
                else:
                    # Ini akan muncul di konsol jika ada entri yang dilewati
                    print(f"Skipping invalid or missing entry during metadata fetch: {entry}")


            print(f"Found and extracted metadata for {len(all_shorts_metadata)} Shorts.") # Debugging/Informasi
            return all_shorts_metadata
        else:
            # Jika tidak ada entri ditemukan
            print("No Shorts videos found on the channel or failed to extract metadata.")
            return []
    except Exception as e:
        # Menangkap kesalahan selama proses ekstraksi
        print(f"An error occurred during metadata extraction: {e}")
        # --- Peningkatan Feedback GUI ---
        progress_label_var.set(f"Step 1/3: Error fetching metadata: {e}")
        # --- End Peningkatan Feedback GUI ---
        return []

def save_metadata_to_excel(metadata_list, output_filepath):
    """
    Menyimpan daftar metadata Shorts ke dalam file Excel di lokasi spesifik.

    Args:
        metadata_list (list): Daftar dictionary berisi metadata Shorts untuk batch ini.
        output_filepath (str): Path lengkap file Excel yang akan disimpan (termasuk nama file).

    Returns:
        bool: True jika berhasil menyimpan, False jika gagal.
    """
    if not metadata_list:
        print(f"No metadata to save to Excel file: {output_filepath}")
        return False

    try:
        # Buat DataFrame pandas dari list metadata
        df = pd.DataFrame(metadata_list)

        # Urutkan kolom sesuai keinginan
        df = df[['url', 'title', 'description']]

        # Ganti nama kolom agar lebih user-friendly di Excel
        df.rename(columns={'url': 'Link URL', 'title': 'Title', 'description': 'Description'}, inplace=True)

        # Simpan DataFrame ke file Excel
        df.to_excel(output_filepath, index=False) # index=False agar tidak menyimpan index DataFrame

        print(f"Successfully saved metadata to {output_filepath}")
        return True
    except Exception as e:
        print(f"Error saving metadata to Excel file {output_filepath}: {e}")
        return False


def download_videos_from_links(links, output_path, format_string, retries, download_delay_seconds, proxy, progress_var, progress_label_var, batch_info="", cancel_event=None):
    """
    Mendownload daftar video dari URL yang diberikan menggunakan subprocess yt-dlp
    ke dalam direktori output yang ditentukan, dengan pilihan format, retries, delay, proxy, dan pembatalan.

    Args:
        links (list): Daftar string URL video yang akan didownload.
        output_path (str): Path direktori tempat video akan disimpan (subfolder batch).
        format_string (str): String format yt-dlp yang akan digunakan (misal: "bestvideo+bestaudio/best").
        retries (int): Jumlah percobaan ulang download per video.
        download_delay_seconds (int): Jeda dalam detik antara setiap upaya download video.
        proxy (str or None): Alamat proxy (misal: "http://host:port"). None atau string kosong jika tidak pakai proxy.
        progress_var (tk.IntVar): Variabel Tkinter untuk mengupdate nilai progress bar.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk mengupdate teks label status.
        batch_info (str): String tambahan untuk label status (misal: "Batch 1/5").
        cancel_event (threading.Event or None): Event untuk memeriksa apakah proses dibatalkan.

    Returns:
        list: Daftar URL video yang gagal didownload dalam batch ini.
    """
    global current_subprocess # Deklarasikan untuk memodifikasi variabel global

    total_links = len(links)
    failed_links_in_batch = [] # List untuk menyimpan URL yang gagal dalam batch ini

    if total_links == 0:
        progress_label_var.set(f"{batch_info} Step 3/3: No videos to download in this batch.")
        progress_var.set(0)
        return failed_links_in_batch # Kembalikan list kosong

    print(f"{batch_info} Starting download of {total_links} videos into {output_path} with format '{format_string}', retries={retries}, delay={download_delay_seconds}s, proxy={proxy if proxy else 'None'}...") # Debugging/Informasi

    for index, link in enumerate(links, start=1):
        # --- Cek Pembatalan Sebelum Memulai Download Video Berikutnya ---
        if cancel_event and cancel_event.is_set():
            print(f"{batch_info} Download cancelled by user.")
            progress_label_var.set(f"{batch_info} Download cancelled.")
            break # Keluar dari loop download jika dibatalkan
        # --- End Cek Pembatalan ---

        link = link.strip() # Hapus spasi di awal/akhir link
        # Update label status sebelum memulai download
        progress_label_var.set(f"{batch_info} Step 3/3: Downloading video {index}/{total_links}...")

        try:
            # Menjalankan yt-dlp sebagai subprocess menggunakan Popen untuk control
            command = [
                'yt-dlp',
                '--quiet',
                '--no-part', # Opsional: jangan gunakan file .part
                '--retries', str(retries), # Menggunakan nilai retries dari input GUI
                '--output', os.path.join(output_path, '%(title)s.%(ext)s'),
                '--format', format_string, # Menggunakan nilai format dari input GUI
            ]

            # Tambahkan opsi proxy jika disediakan
            if proxy:
                command.extend(['--proxy', proxy])

            # Tambahkan link video terakhir
            command.append(link)

            print(f"Executing command: {' '.join(command)}") # Debugging: tampilkan perintah lengkap

            current_subprocess = subprocess.Popen(
                command,
                stdout=subprocess.PIPE, # Tangkap output standar
                stderr=subprocess.PIPE, # Tangkap error standar
                text=True # Menggunakan teks untuk output yang ditangkap
            )

            # Tunggu subprocess selesai. Menggunakan communicate() dengan timeout=None
            # adalah cara sederhana untuk menunggu tanpa polling manual yang kompleks.
            # Pembatalan ditangani oleh on_cancel_button_click yang me-kill subprocess.
            try:
                stdout, stderr = current_subprocess.communicate(timeout=None) # Tunggu tanpa timeout
                return_code = current_subprocess.returncode
            except subprocess.TimeoutExpired:
                 # Ini seharusnya tidak terjadi dengan timeout=None, tapi tetap jaga
                print(f"{batch_info} yt-dlp process for {link} timed out.")
                current_subprocess.kill() # Paksa hentikan jika timeout
                stdout, stderr = current_subprocess.communicate()
                return_code = current_subprocess.returncode # Akan jadi non-zero

            current_subprocess = None # Reset variabel global

            if cancel_event and cancel_event.is_set():
                 # Jika dibatalkan, proses sudah dihentikan di on_cancel_button_click
                 print(f"{batch_info} Download of {link} was terminated.")
                 progress_label_var.set(f"{batch_info} Step 3/3: Video {index}/{total_links} cancelled.")
                 break # Keluar dari loop download

            if return_code != 0:
                # Jika yt-dlp mengembalikan kode error non-zero (dan tidak dibatalkan)
                error_msg = f"yt-dlp failed for {link} (code {return_code}): {stderr.strip() if stderr else 'No error message'}"
                print(error_msg)
                # --- Peningkatan Feedback GUI ---
                progress_label_var.set(f"{batch_info} Step 3/3: Video {index}/{total_links} failed.") # Pesan lebih ringkas
                # --- End Peningkatan Feedback GUI ---
                # messagebox.showwarning("Download Failed", f"Failed to download {link}:\n{error_msg}") # Opsional: tampilkan peringatan per video
                # --- Tambahkan URL ke daftar gagal ---
                failed_links_in_batch.append(link)
                # --- End Tambahkan URL ---
                # --- Lanjutkan ke video berikutnya meskipun gagal ---
                # Tidak menggunakan 'break' di sini agar error pada satu video tidak menghentikan seluruh batch
                pass
                # --- End Lanjutkan ---
            else:
                # Update label status setelah berhasil
                # --- Peningkatan Feedback GUI ---
                progress_label_var.set(f"{batch_info} Step 3/3: Video {index}/{total_links} downloaded.") # Pesan lebih ringkas
                # --- End Peningkatan Feedback GUI ---
                print(f"{batch_info} Successfully downloaded: {link}") # Debugging/Informasi

        except FileNotFoundError:
             error_msg = "Error: yt-dlp command not found. Make sure yt-dlp is installed and in your system's PATH."
             print(error_msg)
             progress_label_var.set(error_msg)
             messagebox.showerror("Error", error_msg) # Tampilkan pesan error di GUI
             # Hentikan proses download jika yt-dlp tidak ditemukan
             # --- Tambahkan sisa link di batch ke daftar gagal karena proses terhenti ---
             failed_links_in_batch.extend(links[index-1:]) # Tambahkan link saat ini dan sisa link
             # --- End Tambahkan sisa link ---
             break # Keluar dari loop download untuk batch ini
        except Exception as e:
            error_msg = f"An unexpected error occurred while downloading {link}: {e}"
            print(error_msg)
            # --- Peningkatan Feedback GUI ---
            progress_label_var.set(f"{batch_info} Step 3/3: Video {index}/{total_links} failed.") # Pesan lebih ringkas
            # --- End Peningkatan Feedback GUI ---
            # messagebox.showwarning("Download Failed", f"Failed to download {link}:\n{error_msg}") # Opsional: tampilkan peringatan per video
            # --- Tambahkan URL ke daftar gagal ---
            failed_links_in_batch.append(link)
            # --- End Tambahkan URL ---
            # --- Lanjutkan ke video berikutnya meskipun gagal ---
            pass
            # --- End Lanjutkan ---
        finally:
            # Update progress bar setelah setiap video (berhasil atau gagal/dibatalkan)
            # Progress bar ini menunjukkan progress DALAM batch saat ini
            # Jika dibatalkan, progress bar mungkin tidak mencapai 100% untuk batch ini
            progress_var.set(int((index / total_links) * 100))

            # --- Tambahkan Jeda Antar Download ---
            # Jeda hanya jika bukan video terakhir dalam batch dan proses belum dibatalkan
            if index < total_links and not (cancel_event and cancel_event.is_set()):
                print(f"Waiting for {download_delay_seconds} seconds before next download...")
                time.sleep(download_delay_seconds)
            # --- End Tambahkan Jeda ---


    # Setelah loop selesai untuk batch ini (baik selesai semua, ada yang gagal, atau dibatalkan)
    if not (cancel_event and cancel_event.is_set()):
        batch_finish_status = f"{batch_info} Step 3/3: Finished downloading videos for this batch."
        progress_label_var.set(batch_finish_status)
        print(batch_finish_status) # Debugging/Informasi
        # progress_var.set(100) # Opsional: Pastikan progress bar penuh di akhir batch jika tidak dibatalkan

    return failed_links_in_batch # Kembalikan daftar URL yang gagal


def save_metadata_to_excel(metadata_list, output_filepath):
    """
    Menyimpan daftar metadata Shorts ke dalam file Excel di lokasi spesifik.

    Args:
        metadata_list (list): Daftar dictionary berisi metadata Shorts untuk batch ini.
        output_filepath (str): Path lengkap file Excel yang akan disimpan (termasuk nama file).

    Returns:
        bool: True jika berhasil menyimpan, False jika gagal.
    """
    if not metadata_list:
        print(f"No metadata to save to Excel file: {output_filepath}")
        return False

    try:
        # Buat DataFrame pandas dari list metadata
        df = pd.DataFrame(metadata_list)

        # Urutkan kolom sesuai keinginan
        df = df[['url', 'title', 'description']]

        # Ganti nama kolom agar lebih user-friendly di Excel
        df.rename(columns={'url': 'Link URL', 'title': 'Title', 'description': 'Description'}, inplace=True)

        # Simpan DataFrame ke file Excel
        df.to_excel(output_filepath, index=False) # index=False agar tidak menyimpan index DataFrame

        print(f"Successfully saved metadata to {output_filepath}")
        return True
    except Exception as e:
        print(f"Error saving metadata to Excel file {output_filepath}: {e}")
        return False

def save_failed_urls_to_file(failed_urls, output_directory, batch_number):
    """
    Menyimpan daftar URL yang gagal ke file error.txt di subfolder error batch.

    Args:
        failed_urls (list): Daftar string URL yang gagal.
        output_directory (str): Path direktori utama tempat folder error akan dibuat.
        batch_number (int): Nomor batch.
    """
    if not failed_urls:
        print(f"No failed URLs to save for Batch {batch_number}.")
        return

    # Buat path untuk folder error utama dan subfolder error batch
    error_main_folder = os.path.join(output_directory, ERROR_FOLDER_NAME)
    error_batch_folder = os.path.join(error_main_folder, f"Batch_{batch_number}_Errors")
    error_filepath = os.path.join(error_batch_folder, "error.txt")

    try:
        # Buat folder error jika belum ada
        os.makedirs(error_batch_folder, exist_ok=True)
        print(f"Created error directory for Batch {batch_number}: {error_batch_folder}")

        # Tulis URL yang gagal ke file error.txt
        with open(error_filepath, 'w') as f:
            for url in failed_urls:
                f.write(url + '\n')

        print(f"Successfully saved {len(failed_urls)} failed URLs to {error_filepath}")
    except Exception as e:
        print(f"Error saving failed URLs to file {error_filepath}: {e}")


# --- Fungsi GUI ---

def browse_folder(folder_var):
    """
    Membuka dialog untuk memilih folder utama dan mengupdate variabel Tkinter.

    Args:
        folder_var (tk.StringVar): Variabel Tkinter untuk menyimpan path folder utama yang dipilih.
    """
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        folder_var.set(folder_selected)
        print(f"Main output folder selected: {folder_selected}") # Debugging/Informasi


def on_start_button_click(folder_var, channel_entry, num_videos_entry, format_combobox, delay_entry, retries_entry, proxy_entry, progress_var, progress_label_var, start_button, cancel_button):
    """
    Fungsi yang dipanggil saat tombol 'Start Process' diklik.
    Memulai proses pengambilan metadata, batching, penyimpanan Excel, dan download video
    di thread terpisah.

    Args:
        folder_var (tk.StringVar): Variabel Tkinter yang menyimpan path folder output utama.
        channel_entry (ttk.Entry): Widget entry yang berisi URL channel.
        num_videos_entry (ttk.Entry): Widget entry yang berisi jumlah video yang diinginkan.
        format_combobox (ttk.Combobox): Widget combobox untuk pilihan format.
        delay_entry (ttk.Entry): Widget entry untuk download delay.
        retries_entry (ttk.Entry): Widget entry untuk jumlah retries.
        proxy_entry (ttk.Entry): Widget entry untuk alamat proxy.
        progress_var (tk.IntVar): Variabel Tkinter untuk progress bar.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk label status.
        start_button (ttk.Button): Tombol Start Process.
        cancel_button (ttk.Button): Tombol Cancel Process.
    """
    main_output_directory = folder_var.get()
    channel_url = channel_entry.get().strip() # Ambil URL dan hapus spasi
    num_videos_str = num_videos_entry.get().strip()
    selected_format_name = format_combobox.get()
    selected_format_string = FORMAT_OPTIONS.get(selected_format_name, FORMAT_OPTIONS["Best Quality (Default)"]) # Ambil string format yt-dlp
    proxy_address = proxy_entry.get().strip() # Ambil alamat proxy

    # Validasi input dasar
    if not main_output_directory:
        progress_label_var.set("Please select a main output folder.")
        messagebox.showwarning("Input Missing", "Please select a main output folder.")
        print("Error: Main output folder not selected.")
        return
    if not channel_url:
        progress_label_var.set("Please enter a YouTube channel URL.")
        messagebox.showwarning("Input Missing", "Please enter a YouTube channel URL.")
        print("Error: Channel URL not entered.")
        return

    # Validasi input jumlah video
    num_videos_limit = None
    if num_videos_str:
        try:
            num_videos_limit = int(num_videos_str)
            if num_videos_limit <= 0:
                messagebox.showwarning("Invalid Input", "Number of videos must be a positive integer.")
                progress_label_var.set("Invalid number of videos.")
                print("Error: Invalid number of videos entered.")
                return
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid number for videos.")
            progress_label_var.set("Invalid number format.")
            print("Error: Non-integer number of videos entered.")
            return

    # Validasi input delay
    download_delay_seconds = DEFAULT_DOWNLOAD_DELAY_SECONDS # Default value
    delay_str = delay_entry.get().strip()
    if delay_str:
        try:
            download_delay_seconds = int(delay_str)
            if download_delay_seconds < 0: # Allow 0 delay
                 messagebox.showwarning("Invalid Input", "Download delay must be a non-negative integer.")
                 progress_label_var.set("Invalid download delay.")
                 print("Error: Invalid download delay entered.")
                 return
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid number for download delay.")
            progress_label_var.set("Invalid delay format.")
            print("Error: Non-integer delay entered.")
            return

    # Validasi input retries
    retries = DEFAULT_RETRIES # Default value
    retries_str = retries_entry.get().strip()
    if retries_str:
        try:
            retries = int(retries_str)
            if retries < 0: # Allow 0 retries
                 messagebox.showwarning("Invalid Input", "Number of retries must be a non-negative integer.")
                 progress_label_var.set("Invalid number of retries.")
                 print("Error: Invalid number of retries entered.")
                 return
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid number for retries.")
            progress_label_var.set("Invalid retries format.")
            print("Error: Non-integer retries entered.")
            return

    # Nonaktifkan tombol Start dan aktifkan tombol Cancel
    start_button.config(state=tk.DISABLED)
    cancel_button.config(state=tk.NORMAL)

    # Reset progress bar dan label status
    progress_var.set(0)
    # --- Peningkatan Feedback GUI ---
    progress_label_var.set("Starting process...")
    # --- End Peningkatan Feedback GUI ---
    print(f"Starting process for channel: {channel_url}, limit: {num_videos_limit if num_videos_limit is not None else 'All'}, format: {selected_format_name} ({selected_format_string}), delay: {download_delay_seconds}s, retries: {retries}, proxy: {proxy_address if proxy_address else 'None'}") # Debugging/Informasi

    # Reset cancel event
    cancel_event.clear()

    # Buat direktori output utama jika belum ada
    try:
        os.makedirs(main_output_directory, exist_ok=True)
        print(f"Ensured main output directory exists: {main_output_directory}") # Debugging/Informasi
    except Exception as e:
        error_msg = f"Error creating main output directory: {e}"
        print(error_msg)
        progress_label_var.set(error_msg)
        messagebox.showerror("Directory Error", error_msg)
        # Re-enable Start button if directory creation fails before thread starts
        root.after(100, lambda: start_button.config(state=tk.NORMAL))
        root.after(100, lambda: cancel_button.config(state=tk.DISABLED))
        return


    # Karena seluruh proses bisa memakan waktu, jalankan di thread terpisah.
    def process_thread():
        """Fungsi wrapper untuk menjalankan seluruh proses batching dalam thread."""
        try:
            # 1. Ambil Metadata Shorts
            # --- Peningkatan Feedback GUI ---
            progress_label_var.set("Step 1/3: Fetching all Shorts metadata...")
            # --- End Peningkatan Feedback GUI ---
            print("Fetching all Shorts metadata...")
            # Ambil metadata, limit diterapkan di yt-dlp options, pass proxy
            all_shorts_metadata = get_shorts_metadata(channel_url, num_videos_limit, proxy_address if proxy_address else None, progress_label_var)

            if cancel_event.is_set():
                 print("Process cancelled during metadata fetching.")
                 progress_label_var.set("Process cancelled.")
                 return # Keluar jika dibatalkan

            if not all_shorts_metadata:
                # --- Peningkatan Feedback GUI ---
                progress_label_var.set("Process finished: No Shorts found or failed to fetch metadata.")
                # --- End Peningkatan Feedback GUI ---
                print("No Shorts found or failed to fetch metadata.")
                progress_var.set(0) # Reset progress if no links
                return

            # Jika num_videos_limit diberikan dan jumlah yang ditemukan lebih banyak, potong list
            # Ini penting jika yt-dlp playlist_items tidak membatasi fetch awal dengan sempurna
            # atau jika ada error pada item awal sehingga jumlah yang diambil kurang dari limit.
            # Kita pastikan hanya memproses sejumlah num_videos_limit jika diminta.
            if num_videos_limit is not None and len(all_shorts_metadata) > num_videos_limit:
                 all_shorts_metadata = all_shorts_metadata[:num_videos_limit]
                 print(f"Trimmed metadata list to {len(all_shorts_metadata)} based on user limit.")
            # Jika jumlah yang ditemukan kurang dari limit, kita proses semua yang ditemukan.

            total_videos_to_process = len(all_shorts_metadata)
            if total_videos_to_process == 0:
                 progress_label_var.set("Process finished: No Shorts found after filtering.")
                 print("No Shorts found after filtering.")
                 progress_var.set(0)
                 return

            num_batches = math.ceil(total_videos_to_process / BATCH_SIZE) # Hitung jumlah batch

            # --- Peningkatan Feedback GUI ---
            progress_label_var.set(f"Step 1/3 finished. Found {total_videos_to_process} Shorts to process. Will process in {num_batches} batches.")
            # --- End Peningkatan Feedback GUI ---
            print(f"Found {total_videos_to_process} Shorts to process. Will process in {num_batches} batches.")

            # 2. Proses per Batch
            for i in range(num_batches):
                if cancel_event.is_set():
                     print("Process cancelled between batches.")
                     progress_label_var.set("Process cancelled.")
                     break # Keluar dari loop batch jika dibatalkan

                start_index = i * BATCH_SIZE
                end_index = min(start_index + BATCH_SIZE, total_videos_to_process) # Pastikan tidak melebihi jumlah total
                current_batch_metadata = all_shorts_metadata[start_index:end_index]

                batch_number = i + 1
                batch_folder_name = f"Batch_{batch_number}"
                batch_output_directory = os.path.join(main_output_directory, batch_folder_name)
                batch_info_str = f"[Batch {batch_number}/{num_batches}]"

                # --- Peningkatan Feedback GUI ---
                progress_label_var.set(f"{batch_info_str} Step 2/3: Processing batch with {len(current_batch_metadata)} videos...")
                # --- End Peningkatan Feedback GUI ---
                print(f"{batch_info_str} Processing batch with {len(current_batch_metadata)} videos...")

                # Buat subfolder untuk batch ini
                try:
                    os.makedirs(batch_output_directory, exist_ok=True)
                    print(f"{batch_info_str} Created batch directory: {batch_output_directory}")
                except Exception as e:
                    error_msg = f"{batch_info_str} Error creating batch directory {batch_output_directory}: {e}"
                    print(error_msg)
                    progress_label_var.set(error_msg)
                    messagebox.showerror("Directory Error", error_msg)
                    continue # Lanjutkan ke batch berikutnya jika pembuatan folder gagal

                # 3. Simpan Metadata Batch ke Excel di dalam subfolder batch
                excel_filename = f"shorts_metadata_batch_{batch_number}.xlsx"
                excel_filepath = os.path.join(batch_output_directory, excel_filename)

                # --- Peningkatan Feedback GUI ---
                progress_label_var.set(f"{batch_info_str} Step 2/3: Saving metadata to Excel...")
                # --- End Peningkatan Feedback GUI ---
                print(f"{batch_info_str} Saving metadata to Excel...")
                save_metadata_to_excel(current_batch_metadata, excel_filepath)
                # Status berhasil/gagal disimpan di dalam fungsi save_metadata_to_excel

                # 4. Siapkan daftar URL untuk Download Video di batch ini
                shorts_links_to_download = [item['url'] for item in current_batch_metadata]

                # 5. Mulai Proses Download Video untuk batch ini
                if shorts_links_to_download:
                     # --- Peningkatan Feedback GUI ---
                     # Status download per video diupdate di dalam download_videos_from_links
                     # --- End Peningkatan Feedback GUI ---
                     # Pass format string, retries, delay, proxy, dan cancel event
                     failed_urls_this_batch = download_videos_from_links(
                         shorts_links_to_download,
                         batch_output_directory,
                         selected_format_string,
                         retries,
                         download_delay_seconds,
                         proxy_address if proxy_address else None,
                         progress_var,
                         progress_label_var,
                         batch_info=batch_info_str,
                         cancel_event=cancel_event
                     )

                     # --- Simpan URL yang Gagal ke File Error ---
                     if failed_urls_this_batch:
                         progress_label_var.set(f"{batch_info_str} Saving failed URLs to error file...")
                         print(f"{batch_info_str} Saving {len(failed_urls_this_batch)} failed URLs...")
                         save_failed_urls_to_file(failed_urls_this_batch, main_output_directory, batch_number)
                     # --- End Simpan URL yang Gagal ---

                else:
                     # --- Peningkatan Feedback GUI ---
                     progress_label_var.set(f"{batch_info_str} Step 3/3: No valid links found for download in this batch.")
                     # --- End Peningkatan Feedback GUI ---
                     print(f"{batch_info_str} No valid links found for download in this batch.")
                     progress_var.set(0) # Reset progress for this batch

                # Jika dibatalkan saat download batch, keluar dari loop batch
                if cancel_event.is_set():
                    print("Process cancelled during batch download.")
                    progress_label_var.set("Process cancelled.")
                    break


            # Setelah semua batch selesai atau dibatalkan
            if not cancel_event.is_set():
                final_status = f"Process finished. Successfully processed {total_videos_to_process} videos in {num_batches} batches."
                progress_label_var.set(final_status)
                print(final_status)
                progress_var.set(100) # Pastikan progress bar penuh di akhir
            else:
                 # Jika dibatalkan, status sudah diupdate di dalam loop
                 pass # Do nothing, status is already set to cancelled

        except Exception as e:
            # Tangani error tak terduga di dalam thread proses
            error_msg = f"An unexpected error occurred during the process: {e}"
            print(error_msg)
            progress_label_var.set(f"Process error: {e}")
            messagebox.showerror("Process Error", error_msg)
        finally:
            # Pastikan tombol kembali ke keadaan semula setelah proses selesai atau dibatalkan
            root.after(100, lambda: start_button.config(state=tk.NORMAL)) # Gunakan root.after karena ini di thread lain
            root.after(100, lambda: cancel_button.config(state=tk.DISABLED))
            print("Process thread finished.")


    # Buat dan mulai thread untuk menjalankan seluruh proses batching
    thread = Thread(target=process_thread)
    thread.start()

def on_cancel_button_click(start_button, cancel_button, progress_label_var):
    """
    Fungsi yang dipanggil saat tombol 'Cancel Process' diklik.
    Memberi sinyal pembatalan ke thread download.

    Args:
        start_button (ttk.Button): Tombol Start Process.
        cancel_button (ttk.Button): Tombol Cancel Process.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk mengupdate teks label status.
    """
    print("Cancel button clicked. Signaling cancellation...")
    progress_label_var.set("Cancellation requested...")
    cancel_event.set() # Set event untuk memberi sinyal pembatalan

    # Coba terminasi subprocess yt-dlp jika sedang berjalan
    global current_subprocess
    if current_subprocess and current_subprocess.poll() is None:
        try:
            print("Attempting to terminate running yt-dlp subprocess...")
            # current_subprocess.terminate() # Kirim sinyal terminasi (lebih lembut)
            current_subprocess.kill() # Kirim sinyal kill (lebih paksa)
            print("yt-dlp subprocess terminated.")
        except Exception as e:
            print(f"Error terminating subprocess: {e}")

    # Status GUI akan diupdate oleh thread setelah benar-benar berhenti (di blok finally)


# --- Konfigurasi GUI ---

# Membuat jendela utama
root = tk.Tk()
root.title("Shorts Bulk DL & Metadata Batcher By Sewer") # Judul aplikasi diperbarui
root.geometry("700x630") # Ukuran jendela awal (opsional, diperbesar sedikit)
root.resizable(False, False) # Mencegah jendela diubah ukurannya (opsional)

# Konfigurasi style untuk widget ttk (tema gelap)
style = ttk.Style()
style.theme_use("clam") # Menggunakan tema 'clam' sebagai dasar
style.configure("TLabel", background="#2E2E2E", foreground="#FFFFFF") # Label
style.configure("TButton", background="#555555", foreground="#FFFFFF", borderwidth=1) # Tombol
style.map("TButton", background=[('active', '#777777')]) # Warna tombol saat di-hover/aktif
style.configure("TEntry", fieldbackground="#555555", foreground="#FFFFFF", insertbackground="#FFFFFF") # Entry (input teks)
style.configure("TCombobox", fieldbackground="#555555", foreground="#FFFFFF", selectbackground="#777777", selectforeground="#FFFFFF", background="#555555", bordercolor="#555555", arrowcolor="#FFFFFF") # Combobox
style.map("TCombobox", fieldbackground=[('readonly', '#555555')])
style.configure("Horizontal.TProgressbar", troughcolor="#555555", bordercolor="#555555", background="#009688") # Progress bar
style.configure("TFrame", background="#2E2E2E") # Frame

# Mengatur warna background jendela utama
root.configure(bg="#2E2E2E")

# Membuat frame utama untuk menampung semua widget
main_frame = ttk.Frame(root, padding="15") # Tambahkan padding
main_frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))

# Konfigurasi grid agar frame utama bisa mengembang bersama jendela
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
main_frame.columnconfigure(2, weight=1) # Kolom entry folder/channel akan mengembang

# --- Widget GUI ---

# Label dan Tombol untuk memilih folder output utama
folder_label = ttk.Label(main_frame, text="Select the MAIN folder to save batches:") # Teks diperbarui
folder_label.grid(column=0, row=0, sticky=tk.W, pady=5, padx=5) # Tambahkan padx/pady kecil

browse_button = ttk.Button(main_frame, text="Browse", command=lambda: browse_folder(folder_var)) # Gunakan lambda untuk meneruskan folder_var
browse_button.grid(column=1, row=0, sticky=tk.W, pady=5, padx=5)

# Entry untuk menampilkan path folder utama yang dipilih (readonly)
folder_var = tk.StringVar() # Variabel untuk menyimpan path folder
folder_entry = ttk.Entry(main_frame, textvariable=folder_var, state="readonly", width=50)
folder_entry.grid(column=2, row=0, sticky=(tk.W, tk.E), pady=5, padx=5)

# Label dan Entry untuk URL channel YouTube
channel_label = ttk.Label(main_frame, text="Enter the YouTube channel URL:")
channel_label.grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)

channel_entry = ttk.Entry(main_frame, width=50)
channel_entry.grid(column=1, row=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)

# Label dan Entry untuk Jumlah Video
num_videos_label = ttk.Label(main_frame, text="Number of videos to process (empty for all):")
num_videos_label.grid(column=0, row=2, sticky=tk.W, pady=5, padx=5)

num_videos_entry = ttk.Entry(main_frame, width=10) # Entry untuk jumlah video
num_videos_entry.grid(column=1, row=2, sticky=tk.W, pady=5, padx=5)
# Opsional: Set nilai default atau placeholder
# num_videos_entry.insert(0, "100")

# Label dan Combobox untuk Pilihan Format Video
format_label = ttk.Label(main_frame, text="Select Video Format/Quality:")
format_label.grid(column=0, row=3, sticky=tk.W, pady=5, padx=5)

format_combobox = ttk.Combobox(main_frame, values=list(FORMAT_OPTIONS.keys()), state="readonly", width=30)
format_combobox.grid(column=1, row=3, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)
format_combobox.set("Best Quality (Default)") # Set nilai default

# Label dan Entry untuk Download Delay
delay_label = ttk.Label(main_frame, text="Download Delay (seconds):")
delay_label.grid(column=0, row=4, sticky=tk.W, pady=5, padx=5)

delay_entry = ttk.Entry(main_frame, width=10) # Entry untuk delay
delay_entry.grid(column=1, row=4, sticky=tk.W, pady=5, padx=5)
delay_entry.insert(0, str(DEFAULT_DOWNLOAD_DELAY_SECONDS)) # Set nilai default

# Label dan Entry untuk Number of Retries
retries_label = ttk.Label(main_frame, text="Number of Retries:")
retries_label.grid(column=0, row=5, sticky=tk.W, pady=5, padx=5)

retries_entry = ttk.Entry(main_frame, width=10) # Entry untuk retries
retries_entry.grid(column=1, row=5, sticky=tk.W, pady=5, padx=5)
retries_entry.insert(0, str(DEFAULT_RETRIES)) # Set nilai default

# Label dan Entry untuk Proxy
proxy_label = ttk.Label(main_frame, text="Proxy (optional, e.g., http://host:port):")
proxy_label.grid(column=0, row=6, sticky=tk.W, pady=5, padx=5)

proxy_entry = ttk.Entry(main_frame, width=30) # Entry untuk proxy
proxy_entry.grid(column=1, row=6, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)


# Frame untuk tombol Start dan Cancel
button_frame = ttk.Frame(main_frame)
button_frame.grid(column=0, row=7, columnspan=3, pady=15) # Row disesuaikan
button_frame.columnconfigure(0, weight=1) # Agar tombol bisa di tengah
button_frame.columnconfigure(1, weight=1)

# Tombol untuk memulai proses batching
start_button = ttk.Button(button_frame, text="Start Batch Process",
                          command=lambda: on_start_button_click(folder_var, channel_entry, num_videos_entry, format_combobox, delay_entry, retries_entry, proxy_entry, progress_var, progress_label_var, start_button, cancel_button))
start_button.grid(column=0, row=0, padx=10) # Tambahkan padx antar tombol

# Tombol untuk membatalkan proses
cancel_button = ttk.Button(button_frame, text="Cancel Process", command=lambda: on_cancel_button_click(start_button, cancel_button, progress_label_var), state=tk.DISABLED) # Nonaktifkan secara default
cancel_button.grid(column=1, row=0, padx=10)

# Progress bar untuk menunjukkan kemajuan download (per batch)
progress_var = tk.IntVar() # Variabel untuk nilai progress bar (0-100)
progress_bar = ttk.Progressbar(main_frame, orient="horizontal", mode="determinate", variable=progress_var, style="Horizontal.TProgressbar")
progress_bar.grid(column=0, row=8, columnspan=3, pady=5, sticky=(tk.W, tk.E)) # Row disesuaikan

# Label untuk menampilkan status proses (termasuk info batch)
progress_label_var = tk.StringVar() # Variabel untuk teks status
progress_label = ttk.Label(main_frame, textvariable=progress_label_var, anchor=tk.CENTER) # anchor=tk.CENTER untuk teks di tengah
progress_label.grid(column=0, row=9, columnspan=3, pady=5, sticky=(tk.W, tk.E)) # Row disesuaikan

# Label penjelasan langkah-langkah proses
explanation_text = f"""Process Steps:
1. Fetching metadata for Shorts (up to specified limit, using proxy if provided).
2. Saving metadata to Excel file(s) in batch folders.
3. Downloading videos batch by batch with selected format/quality, delay, retries, and proxy.
Failed video URLs will be saved to '{ERROR_FOLDER_NAME}/Batch_X_Errors/error.txt'.""" # Teks diperbarui
explanation_label = ttk.Label(main_frame, text=explanation_text, justify=tk.LEFT, foreground="#AAAAAA", background="#2E2E2E")
explanation_label.grid(column=0, row=10, columnspan=3, pady=10, padx=5, sticky=tk.W) # Row disesuaikan


# --- Menjalankan Aplikasi GUI ---
root.mainloop()
