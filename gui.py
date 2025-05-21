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

# --- Import Modul Selenium ---
# Pastikan Anda sudah menginstal pustaka selenium dan webdriver-manager:
# pip install selenium webdriver-manager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
# --- End Import Modul Selenium ---


# --- Konfigurasi Default ---
BATCH_SIZE = 100 # Jumlah video Shorts per batch/folder. Bisa diubah sesuai kebutuhan.
DEFAULT_DOWNLOAD_DELAY_SECONDS = 5 # Nilai default jeda dalam detik antara setiap upaya download video.
DEFAULT_RETRIES = 3 # Nilai default jumlah percobaan ulang download per video.
ERROR_FOLDER_NAME = "batching_error" # Nama folder untuk menyimpan log error
SELENIUM_SCROLL_PAUSE_TIME = 5 # Jeda waktu (detik) antar scroll untuk memberi waktu konten memuat (ditingkatkan menjadi 5 detik)
SELENIUM_SCROLL_ATTEMPTS_TIMEOUT = 900 # Timeout maksimum (detik) untuk proses scrolling
SELENIUM_ELEMENT_TIMEOUT = 20 # Timeout (detik) untuk menunggu elemen muncul di halaman
SELENIUM_NO_NEW_ELEMENTS_THRESHOLD = 7 # Jumlah scroll attempt tanpa elemen baru sebelum dianggap selesai

# Mapping nama format user-friendly ke string format yt-dlp
# yt-dlp akan mencoba memilih format terbaik yang sesuai dengan kriteria ini.
# Sintaks format selector: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md#format-selection
FORMAT_OPTIONS = {
    "Best Quality (Default)": "bestvideo+bestaudio/best", # Kualitas terbaik, container otomatis (biasanya mp4/mkv)
    "Best Quality (MP4)": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", # Prioritaskan MP4 container
    "Best Quality (MKV)": "bestvideo[ext=mkv]+bestaudio[ext=opus]/best[ext=mkv]", # Prioritaskan MKV container
    "1080p (MP4)": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[ext=mp4]", # 1080p di container MP4
    "720p (MP4)": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[ext=mp4]", # 720p di container MP4
    "480p (MP4)": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=480][ext=mp4]/best[ext=mp4]", # 480p di container MP4
    # Catatan: Format seperti .mov tidak umum di YouTube dan mungkin memerlukan konversi
    # yang membutuhkan ffmpeg dan menambah kompleksitas. Kita fokus pada format native.
}

# Opsi metode scrolling Selenium
SCROLLING_METHODS = {
    "Send END Key": "send_keys_end", # Pindahkan ke atas karena terbukti paling efektif
    "Scroll to Bottom (JS)": "js_scroll_to_bottom",
    "Scroll by Viewport (JS)": "js_scroll_by_viewport",
}

# --- Variabel Global untuk Kontrol Proses ---
cancel_event = Event() # Event untuk memberi sinyal pembatalan ke thread download
current_subprocess = None # Menyimpan referensi ke proses yt-dlp yang sedang berjalan
current_driver = None # Menyimpan referensi ke WebDriver Selenium yang sedang berjalan
# Variabel global untuk menyimpan status download semua video
all_videos_download_status = [] # List of dicts: [{'url': '...', 'title': '...', 'status': 'No'}]

# --- Fungsi Selenium untuk Mendapatkan Semua URL Shorts ---

def get_all_shorts_urls_selenium(channel_url, num_videos_limit, selenium_options, scrolling_method, proxy, progress_label_var, cancel_event):
    """
    Menggunakan Selenium untuk membuka halaman Shorts channel YouTube, melakukan auto-scrolling
    hingga semua video dimuat, dan mengekstrak semua URL Shorts yang ditemukan.
    Deteksi akhir halaman berdasarkan jumlah elemen video yang ditemukan.

    Args:
        channel_url (str): URL channel YouTube.
        num_videos_limit (int or None): Jumlah maksimum video yang akan diambil URL-nya. None untuk semua.
        selenium_options (dict): Dictionary berisi opsi konfigurasi Selenium (headless, proxy, dll).
        scrolling_method (str): Metode scrolling yang akan digunakan (lihat SCROLLING_METHODS).
        proxy (str or None): Alamat proxy untuk Selenium. None atau string kosong jika tidak pakai proxy.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk mengupdate teks label status.
        cancel_event (threading.Event): Event untuk memeriksa apakah proses dibatalkan.

    Returns:
        list: Daftar string URL Shorts ('https://www.youtube.com/shorts/VIDEO_ID'),
              atau list kosong jika tidak ditemukan atau terjadi kesalahan/pembatalan.
    """
    global current_driver # Deklarasikan untuk memodifikasi variabel global

    print(f"Starting Selenium process for channel: {channel_url}")
    progress_label_var.set("Step 1/4: Starting browser and navigating...")

    # --- Konfigurasi Chrome Options ---
    options = webdriver.ChromeOptions()
    # Menambahkan argumen dari konfigurasi GUI
    if selenium_options.get("headless", True): options.add_argument("--headless=new") # Gunakan 'new' untuk versi terbaru
    if selenium_options.get("no_sandbox", True): options.add_argument("--no-sandbox")
    if selenium_options.get("disable_dev_shm_usage", True): options.add_argument("--disable-dev-shm-usage")
    if selenium_options.get("disable_notifications", True): options.add_argument("--disable-notifications")
    if selenium_options.get("disable_extensions", True): options.add_argument("--disable-extensions")
    if selenium_options.get("disable_gpu", True): options.add_argument("--disable-gpu") # Berguna terutama di lingkungan Linux tanpa GPU
    # Opsi smooth-scrolling tidak relevan di headless, tapi tetap bisa ditambahkan jika user memilih
    if selenium_options.get("enable_smooth_scrolling", False): options.add_argument("--enable-smooth-scrolling")
    if selenium_options.get("enable_webgl", False): options.add_argument("--enable-webgl") # Mungkin tidak selalu perlu, tergantung konten
    if selenium_options.get("lang_en_US", True): options.add_argument("--lang=en-US") # Set bahasa
    if selenium_options.get("start_maximized", False): options.add_argument("--start-maximized") # Mungkin tidak relevan di headless
    # Pengaturan tambahan yang penting untuk headless dan stabilitas
    options.add_argument("--disable-blink-features=AutomationControlled") # Meminimalkan deteksi sebagai bot
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--remote-allow-origins=*") # Mungkin diperlukan untuk koneksi remote/debugger
    options.add_argument("--log-level=3") # Suppress logging messages
    # Menambahkan User-Agent (opsional, bisa membantu menghindari deteksi)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")

    # Menambahkan opsi proxy jika disediakan
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
        print(f"Using proxy for Selenium: {proxy}")

    # Memodifikasi URL channel untuk mengarah ke halaman Shorts channel
    # Menggunakan logika parsing yang sama seperti di fungsi get_shorts_metadata
    channel_url_shorts = channel_url.strip()
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
             channel_url_shorts = channel_url_shorts.rstrip('/') + '/shorts'
             if any(p in channel_url_shorts for p in ['/about', '/community', '/playlist', '/playlists', '/streams', '/featured', '/videos']):
                  print(f"Warning: URL '{channel_url}' might contain extra path, attempting to clean.")
                  channel_url_shorts = channel_url_shorts.split('/about')[0].split('/community')[0].split('/playlist')[0].split('/playlists')[0].split('/streams')[0].split('/featured')[0].split('/videos')[0].rstrip('/') + '/shorts'
    except Exception as e:
         print(f"Warning: Could not parse channel URL {channel_url}. Attempting to add /shorts directly. Error: {e}")
         channel_url_shorts = channel_url.strip().rstrip('/') + '/shorts'

    print(f"Navigating to: {channel_url_shorts}")

    driver = None
    all_shorts_urls = [] # Initialize list here
    try:
        # --- Inisialisasi WebDriver ---
        # Menggunakan ChromeDriverManager untuk mengelola versi chromedriver secara otomatis
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        current_driver = driver # Simpan referensi global

        driver.get(channel_url_shorts)

        # Tunggu hingga elemen konten utama Shorts dimuat
        # Selector ini mungkin perlu disesuaikan jika YouTube berubah
        # Mencari elemen <a> dengan href yang dimulai dengan '/shorts/'
        progress_label_var.set("Step 1/4: Waiting for initial content...")
        print("Waiting for initial content...")
        # Tunggu hingga setidaknya satu elemen Shorts link muncul
        WebDriverWait(driver, SELENIUM_ELEMENT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/shorts/']"))
        )
        print("Initial content loaded.")

        # --- Auto-Scrolling Logic ---
        progress_label_var.set("Step 1/4: Scrolling to load all videos...")
        print("Starting auto-scrolling...")

        last_video_count = 0
        no_new_elements_count = 0 # Counter untuk scroll attempt tanpa elemen baru
        start_time = time.time()

        # Temukan elemen yang bisa di-scroll. Pada halaman channel, ini seringkali adalah body atau elemen spesifik.
        # Mengirim Keys.END ke body biasanya bekerja. Untuk JS scroll, kita bisa coba body atau html.
        # Kita akan menggunakan body sebagai target default untuk JS scroll juga.
        scrollable_element = driver.find_element(By.TAG_NAME, 'body')

        while True:
            if cancel_event.is_set():
                print("Scrolling cancelled by user.")
                progress_label_var.set("Step 1/4: Scrolling cancelled.")
                break # Keluar dari loop scrolling jika dibatalkan

            # Pilih metode scrolling
            if scrolling_method == SCROLLING_METHODS["Send END Key"]:
                 try:
                     # Kirim END key ke elemen body
                     scrollable_element.send_keys(Keys.END)
                 except Exception as e:
                     print(f"Error sending END key: {e}")
            elif scrolling_method == SCROLLING_METHODS["Scroll by Viewport (JS)"]:
                 # Scroll ke bawah sebesar tinggi viewport
                 driver.execute_script("window.scrollBy(0, window.innerHeight);")
            else: # Default: js_scroll_to_bottom
                 # Scroll ke bagian paling bawah halaman menggunakan JavaScript pada elemen body
                 try:
                     driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scrollable_element)
                 except Exception as e:
                      print(f"Error scrolling body with JS: {e}. Trying html element.")
                      # Fallback ke elemen html jika body gagal
                      try:
                           html_element = driver.find_element(By.TAG_NAME, 'html')
                           driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", html_element)
                      except Exception as e_html:
                           print(f"Error scrolling html with JS: {e_html}. JS scrolling failed.")


            # Tunggu konten baru dimuat
            time.sleep(SELENIUM_SCROLL_PAUSE_TIME)

            # Hitung jumlah elemen video yang ditemukan saat ini
            current_video_elements = driver.find_elements(By.CSS_SELECTOR, "a[href^='/shorts/']")
            current_video_count = len(current_video_elements)

            # --- Logika Deteksi Akhir Halaman Berbasis Jumlah Elemen ---
            if current_video_count == last_video_count:
                no_new_elements_count += 1
                print(f"Scroll attempt: No new videos found. Consecutive attempts without new videos: {no_new_elements_count}/{SELENIUM_NO_NEW_ELEMENTS_THRESHOLD}")
                if no_new_elements_count >= SELENIUM_NO_NEW_ELEMENTS_THRESHOLD:
                    print(f"Stopped scrolling after {SELENIUM_NO_NEW_ELEMENTS_THRESHOLD} attempts without finding new videos.")
                    break # Keluar dari loop jika tidak ada elemen baru setelah beberapa kali coba
            else:
                no_new_elements_count = 0 # Reset counter jika menemukan elemen baru
                # print(f"Scroll attempt: Found {current_video_count} videos (added {current_video_count - last_video_count}).") # Kurangi log ini agar tidak terlalu verbose

            last_video_count = current_video_count

            # Periksa timeout
            if time.time() - start_time > SELENIUM_SCROLL_ATTEMPTS_TIMEOUT:
                print(f"Scrolling timed out after {SELENIUM_SCROLL_ATTEMPTS_TIMEOUT} seconds.")
                progress_label_var.set("Step 1/4: Scrolling timed out.")
                break # Keluar dari loop jika timeout

            # Opsional: Berhenti scrolling jika sudah menemukan lebih dari num_videos_limit
            if num_videos_limit is not None and num_videos_limit > 0:
                 # Berhenti jika jumlah yang ditemukan sudah mencapai atau melebihi limit yang diminta
                 if current_video_count >= num_videos_limit:
                      print(f"Found approximately {current_video_count} videos, which is >= {num_videos_limit}. Stopping scroll.")
                      break # Berhenti jika jumlah video yang ditemukan sudah cukup

            # Update status GUI selama scrolling
            progress_label_var.set(f"Step 1/4: Scrolling... Found ~{current_video_count} videos...")


        print("Finished auto-scrolling.")

        # --- Ekstraksi URL Shorts ---
        # Setelah scrolling selesai (atau dibatalkan/timeout), ekstrak URL dari semua elemen yang ditemukan
        progress_label_var.set("Step 1/4: Extracting video URLs from loaded page...")
        print("Extracting video URLs from loaded page...")
        # Temukan semua elemen <a> yang memiliki atribut href yang dimulai dengan '/shorts/'
        video_elements = driver.find_elements(By.CSS_SELECTOR, "a[href^='/shorts/']")

        for element in video_elements:
            # Dapatkan nilai atribut 'href'
            href = element.get_attribute('href')
            if href:
                # URL Shorts biasanya dalam format https://www.youtube.com/shorts/VIDEO_ID
                # Pastikan URL lengkap jika hanya '/shorts/VIDEO_ID' yang didapat
                if href.startswith('/shorts/'):
                     full_url = f'https://www.youtube.com{href}'
                elif href.startswith('https://www.youtube.com/shorts/'):
                     full_url = href
                else:
                     # Lewati URL yang tidak sesuai format Shorts yang diharapkan
                     continue
                all_shorts_urls.append(full_url)

        # Hapus duplikat jika ada (Selenium mungkin menemukan elemen yang sama)
        all_shorts_urls = list(dict.fromkeys(all_shorts_urls))

        # Terapkan limit jika ada
        if num_videos_limit is not None and num_videos_limit > 0:
             all_shorts_urls = all_shorts_urls[:num_videos_limit]
             print(f"Trimmed URL list to {len(all_shorts_urls)} based on user limit.")

        print(f"Successfully extracted {len(all_shorts_urls)} Shorts URLs.")
        return all_shorts_urls

    except WebDriverException as e:
        error_msg = f"Selenium WebDriver error: {e}"
        print(error_msg)
        progress_label_var.set(f"Step 1/4: WebDriver Error: {e}")
        messagebox.showerror("WebDriver Error", error_msg)
        return []
    except TimeoutException:
        error_msg = f"Selenium Timeout: Initial element not found within {SELENIUM_ELEMENT_TIMEOUT} seconds."
        print(error_msg)
        progress_label_var.set(f"Step 1/4: Timeout Error: Initial element not found.")
        messagebox.showerror("Timeout Error", error_msg)
        return []
    except Exception as e:
        error_msg = f"An unexpected error occurred during Selenium process: {e}"
        print(error_msg)
        progress_label_var.set(f"Step 1/4: Unexpected Error: {e}")
        messagebox.showerror("Selenium Error", error_msg)
        return []
    finally:
        # Pastikan browser ditutup setelah selesai atau terjadi error
        if driver:
            driver.quit()
            current_driver = None
            print("Selenium WebDriver closed.")
        # Jika dibatalkan, status GUI sudah diupdate di dalam loop scrolling
        if not cancel_event.is_set() and all_shorts_urls: # Update final status only if not cancelled and URLs were found
             progress_label_var.set(f"Step 1/4 finished. Found {len(all_shorts_urls)} Shorts URLs.")
        elif not cancel_event.is_set() and not all_shorts_urls: # Case where no URLs were found
             progress_label_var.set("Step 1/4 finished. No Shorts URLs found.")


# --- Fungsi yt-dlp untuk Mendapatkan Metadata dari Daftar URL ---

def get_metadata_for_urls(urls, proxy, progress_label_var, cancel_event):
    """
    Mengambil metadata (URL, Title, Description) dari daftar URL video menggunakan yt-dlp.
    Memproses setiap URL satu per satu karena API yt-dlp extract_info mengharapkan string tunggal.

    Args:
        urls (list): Daftar string URL video.
        proxy (str or None): Alamat proxy (misal: "http://host:port"). None atau string kosong jika tidak pakai proxy.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk mengupdate teks label status.
        cancel_event (threading.Event): Event untuk memeriksa apakah proses dibatalkan.

    Returns:
        list: Daftar dictionary, di mana setiap dictionary berisi metadata satu Shorts
              (keys: 'url', 'title', 'description'), atau list kosong jika gagal atau dibatalkan.
    """
    if not urls:
        print("No URLs provided to fetch metadata.")
        return []

    total_urls = len(urls)
    print(f"Step 2/4: Fetching metadata for {total_urls} URLs using yt-dlp (one by one)...")
    progress_label_var.set(f"Step 2/4: Fetching metadata for {total_urls} videos...")

    # Opsi untuk yt_dlp saat mengambil informasi video individual
    ydl_opts = {
        'quiet': True,
        'extract_flat': False, # Kita perlu metadata lengkap
        'ignoreerrors': True, # Lanjutkan meskipun ada error pada satu atau beberapa video
        'no_warnings': True, # Sembunyikan peringatan
        'force_generic_extractor': True, # Mungkin membantu untuk URL individual
        # 'skip_download': True, # Opsi ini sudah implisit dengan download=False di extract_info
    }

    # Tambahkan opsi proxy jika disediakan
    if proxy:
        ydl_opts['proxy'] = proxy
        print(f"Using proxy for yt-dlp metadata fetch: {proxy}")

    all_shorts_metadata = []
    failed_metadata_urls = [] # Untuk melacak URL yang gagal diambil metadatanya

    try:
        # Inisialisasi YoutubeDL object sekali di luar loop
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Iterasi melalui setiap URL dalam list
            for index, url in enumerate(urls):
                if cancel_event.is_set():
                    print("Metadata fetching cancelled by user.")
                    progress_label_var.set("Step 2/4: Metadata fetching cancelled.")
                    return [] # Kembalikan list kosong jika dibatalkan

                # Update status GUI untuk video saat ini
                progress_label_var.set(f"Step 2/4: Fetching metadata for video {index + 1}/{total_urls}...")
                # print(f"Attempting to fetch metadata for: {url}") # Debugging per URL

                try:
                    # Panggil extract_info untuk SATU URL
                    # Jika extract_info gagal untuk URL tertentu, dengan ignoreerrors=True,
                    # ia akan mencetak error ke stderr dan mengembalikan None atau dictionary error.
                    entry = ydl.extract_info(url, download=False)

                    # Memproses hasil ekstraksi untuk URL tunggal
                    if entry and entry.get('id'):
                        video_id = entry['id']
                        video_title = entry.get('title', 'Untitled')
                        video_description = entry.get('description', '')
                        short_url = f'https://www.youtube.com/shorts/{video_id}' # Pastikan format URL Shorts
                        all_shorts_metadata.append({
                            'url': short_url,
                            'title': video_title,
                            'description': video_description
                        })
                        # print(f"Successfully fetched metadata for {url}") # Debugging per URL
                    else:
                        # Ini akan muncul di konsol jika yt-dlp mengembalikan None atau entri invalid
                        print(f"Failed to fetch metadata for {url}. Result was: {entry}")
                        failed_metadata_urls.append(url)

                except Exception as e:
                    # Tangkap error spesifik jika extract_info melempar exception untuk URL ini
                    print(f"An error occurred fetching metadata for {url}: {e}")
                    failed_metadata_urls.append(url)
                    # Lanjutkan ke URL berikutnya meskipun ada error pada satu URL

        # Setelah loop selesai
        if cancel_event.is_set():
             # Status sudah diupdate di dalam loop
             pass
        else:
            print(f"Finished metadata extraction. Successfully fetched metadata for {len(all_shorts_metadata)} out of {total_urls} URLs.")
            if failed_metadata_urls:
                print(f"Failed to fetch metadata for {len(failed_metadata_urls)} URLs.")
                # Opsional: simpan daftar URL yang gagal diambil metadatanya
                # save_failed_urls_to_file(failed_metadata_urls, output_directory_main, "metadata_fetch") # Perlu path utama
            progress_label_var.set(f"Step 2/4 finished. Fetched metadata for {len(all_shorts_metadata)} videos.")

        return all_shorts_metadata

    except Exception as e:
        # Menangkap kesalahan selama proses inisialisasi YDL atau error tak terduga
        print(f"An error occurred during yt-dlp metadata extraction process: {e}")
        progress_label_var.set(f"Step 2/4: Error fetching metadata: {e}")
        return []


# --- Fungsi Download Video (Diperbarui untuk Melacak Status) ---

def download_videos_from_links(metadata_list, output_path, format_string, retries, download_delay_seconds, proxy, global_status_list, progress_var, progress_label_var, batch_info="", cancel_event=None):
    """
    Mendownload daftar video dari metadata yang diberikan menggunakan subprocess yt-dlp
    ke dalam direktori output yang ditentukan, dengan pilihan format, retries, delay, proxy, dan pembatalan.
    Melacak status download setiap video dalam global_status_list.

    Args:
        metadata_list (list): Daftar dictionary berisi metadata Shorts untuk batch ini.
        output_path (str): Path direktori tempat video akan disimpan (subfolder batch).
        format_string (str): String format yt-dlp yang akan digunakan (misal: "bestvideo+bestaudio/best").
        retries (int): Jumlah percobaan ulang download per video.
        download_delay_seconds (int): Jeda dalam detik antara setiap upaya download video.
        proxy (str or None): Alamat proxy (misal: "http://host:port"). None atau string kosong jika tidak pakai proxy.
        global_status_list (list): Referensi ke daftar status global untuk diperbarui.
        progress_var (tk.IntVar): Variabel Tkinter untuk mengupdate nilai progress bar.
        progress_label_var (tk.StringVar): Variabel Tkinter untuk mengupdate teks label status.
        batch_info (str): String tambahan untuk label status (misal: "Batch 1/5").
        cancel_event (threading.Event or None): Event untuk memeriksa apakah proses dibatalkan.

    Returns:
        list: Daftar URL video yang gagal didownload dalam batch ini.
    """
    global current_subprocess # Deklarasikan untuk memodifikasi variabel global

    total_videos = len(metadata_list)
    failed_links_in_batch = [] # List untuk menyimpan URL yang gagal dalam batch ini

    if total_videos == 0:
        progress_label_var.set(f"{batch_info} Step 4/4: No videos to download in this batch.")
        progress_var.set(0)
        return failed_links_in_batch # Kembalikan list kosong

    print(f"{batch_info} Step 4/4: Starting download of {total_videos} videos into {output_path}...")

    for index, video_metadata in enumerate(metadata_list, start=1):
        # --- Cek Pembatalan Sebelum Memulai Download Video Berikutnya ---
        if cancel_event and cancel_event.is_set():
            print(f"{batch_info} Download cancelled by user.")
            progress_label_var.set(f"{batch_info} Download cancelled.")
            break # Keluar dari loop download jika dibatalkan
        # --- End Cek Pembatalan ---

        link = video_metadata['url'].strip() # Ambil URL dari metadata
        # Update label status sebelum memulai download
        progress_label_var.set(f"{batch_info} Step 4/4: Downloading video {index}/{total_videos}...")

        # Cari entri video ini di daftar status global untuk diperbarui
        # Asumsi URL adalah unique identifier
        video_status_entry = next((item for item in global_status_list if item['url'] == link), None)
        if video_status_entry is None:
            # Ini seharusnya tidak terjadi jika alur data benar, tapi sebagai fallback
            print(f"Warning: Video URL {link} not found in global status list. Adding it.")
            video_status_entry = {'url': link, 'title': video_metadata.get('title', 'Untitled'), 'status': 'No'}
            global_status_list.append(video_status_entry)


        try:
            # Menjalankan yt-dlp sebagai subprocess menggunakan Popen untuk control
            command = [
                'yt-dlp',
                '--quiet',
                '--no-part', # Opsional: jangan gunakan file .part
                '--retries', str(retries), # Menggunakan nilai retries dari input GUI
                '--output', os.path.join(output_path, '%(title)s.%(ext)s'),
                '--format', format_string, # Menggunakan nilai format dari input GUI
                '--no-warnings', # Suppress yt-dlp warnings in console output
            ]

            # Tambahkan opsi proxy jika disediakan
            if proxy:
                command.extend(['--proxy', proxy])

            # Tambahkan link video terakhir
            command.append(link)

            # print(f"Executing download command: {' '.join(command)}") # Debugging: tampilkan perintah lengkap

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
                 progress_label_var.set(f"{batch_info} Step 4/4: Video {index}/{total_videos} cancelled.")
                 # Status di global_status_list tetap 'No' atau 'Error' jika sudah di-set sebelumnya
                 break # Keluar dari loop download

            if return_code != 0:
                # Jika yt-dlp mengembalikan kode error non-zero (dan tidak dibatalkan)
                error_msg = f"yt-dlp failed for {link} (code {return_code}): {stderr.strip() if stderr else 'No error message'}"
                print(error_msg)
                # Cek apakah error terkait sign-in/cookies (Pesan ini tetap relevan meskipun tanpa cookies)
                if "Sign in to confirm you’re not a bot" in stderr or "confirm you're not a robot" in stderr or "Private video" in stderr or "Age-restricted video" in stderr:
                    print(f"{batch_info} Download failed for {link} due to potential access restriction (sign-in/bot/age/private).")
                    progress_label_var.set(f"{batch_info} Step 4/4: Video {index}/{total_videos} failed (Access Denied).")
                    video_status_entry['status'] = 'Error (Access Denied)' # Update status global
                else:
                    progress_label_var.set(f"{batch_info} Step 4/4: Video {index}/{total_videos} failed.") # Pesan lebih ringkas
                    video_status_entry['status'] = 'Error' # Update status global
                # --- Tambahkan URL ke daftar gagal ---
                failed_links_in_batch.append(link)
                # --- End Tambahkan URL ---
                # --- Lanjutkan ke video berikutnya meskipun gagal ---
                pass
                # --- End Lanjutkan ---
            else:
                # Update label status setelah berhasil
                progress_label_var.set(f"{batch_info} Step 4/4: Video {index}/{total_videos} downloaded.") # Pesan lebih ringkas
                print(f"{batch_info} Successfully downloaded: {link}") # Debugging/Informasi
                video_status_entry['status'] = 'Downloaded' # Update status global

        except FileNotFoundError:
             error_msg = "Error: yt-dlp command not found. Make sure yt-dlp is installed and in your system's PATH."
             print(error_msg)
             progress_label_var.set(error_msg)
             messagebox.showerror("Error", error_msg) # Tampilkan pesan error di GUI
             # Hentikan proses download jika yt-dlp tidak ditemukan
             # --- Tambahkan sisa link di batch ke daftar gagal karena proses terhenti ---
             # Ambil URL dari sisa metadata_list
             remaining_urls = [item['url'] for item in metadata_list[index-1:]]
             failed_links_in_batch.extend(remaining_urls)
             # Update status untuk sisa video yang tidak diproses di batch ini
             for remaining_video_metadata in metadata_list[index-1:]:
                 remaining_link = remaining_video_metadata['url']
                 entry_to_update = next((item for item in global_status_list if item['url'] == remaining_link), None)
                 if entry_to_update and entry_to_update['status'] == 'No': # Hanya update jika belum diproses
                     entry_to_update['status'] = 'Error (yt-dlp not found)'
             # --- End Tambahkan sisa link ---
             break # Keluar dari loop download untuk batch ini
        except Exception as e:
            error_msg = f"An unexpected error occurred while downloading {link}: {e}"
            print(error_msg)
            progress_label_var.set(f"{batch_info} Step 4/4: Video {index}/{total_videos} failed.") # Pesan lebih ringkas
            video_status_entry['status'] = 'Error (Unexpected)' # Update status global
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
            progress_var.set(int((index / total_videos) * 100))

            # --- Tambahkan Jeda Antar Download ---
            # Jeda hanya jika bukan video terakhir dalam batch dan proses belum dibatalkan
            if index < total_videos and not (cancel_event and cancel_event.is_set()):
                print(f"Waiting for {download_delay_seconds} seconds before next download...")
                time.sleep(download_delay_seconds)
            # --- End Tambahkan Jeda ---


    # Setelah loop selesai untuk batch ini (baik selesai semua, ada yang gagal, atau dibatalkan)
    if not (cancel_event and cancel_event.is_set()):
        batch_finish_status = f"{batch_info} Step 4/4: Finished processing videos for this batch."
        progress_label_var.set(batch_finish_status)
        print(batch_finish_status) # Debugging/Informasi
        # progress_var.set(100) # Opsional: Pastikan progress bar penuh di akhir batch jika tidak dibatalkan

    return failed_links_in_batch # Kembalikan daftar URL yang gagal


# --- Fungsi Penyimpanan Metadata dan Error ---

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

def save_master_status_to_excel(status_list, output_directory, channel_name="channel"):
    """
    Menyimpan daftar status download semua video ke dalam file Excel utama.

    Args:
        status_list (list): Daftar dictionary berisi status setiap video.
        output_directory (str): Path direktori utama tempat file Excel akan disimpan.
        channel_name (str): Nama channel, digunakan untuk nama file.
    Returns:
        bool: True jika berhasil menyimpan, False jika gagal.
    """
    if not status_list:
        print("No video status data to save to master Excel file.")
        return False

    # Bersihkan nama channel untuk nama file
    safe_channel_name = "".join(c for c in channel_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
    if not safe_channel_name:
        safe_channel_name = "shorts_download_status"
    else:
        safe_channel_name = f"{safe_channel_name}_shorts_download_status"

    output_filepath = os.path.join(output_directory, f"{safe_channel_name}.xlsx")

    try:
        df = pd.DataFrame(status_list)
        df = df[['url', 'title', 'status']] # Pastikan urutan kolom
        df.rename(columns={'url': 'Link URL', 'title': 'Title', 'status': 'D/N/E'}, inplace=True)
        df.to_excel(output_filepath, index=False)
        print(f"Successfully saved master download status to {output_filepath}")
        return True
    except Exception as e:
        print(f"Error saving master download status to Excel file {output_filepath}: {e}")
        return False


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


def on_start_button_click(folder_var, channel_entry, num_videos_entry, format_combobox, delay_entry, retries_entry, proxy_entry,
                          selenium_headless_var, selenium_no_sandbox_var, selenium_dev_shm_usage_var,
                          selenium_notifications_var, selenium_extensions_var, selenium_gpu_var,
                          selenium_webgl_var, selenium_smooth_scrolling_var, selenium_lang_en_US_var,
                          selenium_start_maximized_var,
                          scrolling_method_combobox,
                          progress_var, progress_label_var, start_button, cancel_button):
    """
    Fungsi yang dipanggil saat tombol 'Start Process' diklik.
    Memulai proses pengambilan URL via Selenium, pengambilan metadata via yt-dlp,
    batching, penyimpanan Excel, dan download video di thread terpisah.

    Args:
        folder_var (tk.StringVar): Variabel Tkinter yang menyimpan path folder output utama.
        channel_entry (ttk.Entry): Widget entry yang berisi URL channel.
        num_videos_entry (ttk.Entry): Widget entry yang berisi jumlah video yang diinginkan.
        format_combobox (ttk.Combobox): Widget combobox untuk pilihan format.
        delay_entry (ttk.Entry): Widget entry untuk download delay.
        retries_entry (ttk.Entry): Widget entry untuk jumlah retries.
        proxy_entry (ttk.Entry): Widget entry untuk alamat proxy.
        selenium_headless_var (tk.BooleanVar): Variabel untuk opsi headless.
        selenium_no_sandbox_var (tk.BooleanVar): Variabel untuk opsi no-sandbox.
        selenium_dev_shm_usage_var (tk.BooleanVar): Variabel untuk opsi disable-dev-shm-usage.
        selenium_notifications_var (tk.BooleanVar): Variabel untuk opsi disable-notifications.
        selenium_extensions_var (tk.BooleanVar): Variabel untuk opsi disable-extensions.
        selenium_gpu_var (tk.BooleanVar): Variabel untuk opsi disable-gpu.
        selenium_webgl_var (tk.BooleanVar): Variabel untuk opsi enable-webgl.
        selenium_smooth_scrolling_var (tk.BooleanVar): Variabel untuk opsi enable-smooth-scrolling.
        selenium_lang_en_US_var (tk.BooleanVar): Variabel untuk opsi lang=en-US.
        selenium_start_maximized_var (tk.BooleanVar): Variabel untuk opsi start-maximized.
        scrolling_method_combobox (ttk.Combobox): Widget combobox untuk metode scrolling.
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

    # Ambil konfigurasi Selenium dari GUI
    selenium_options = {
        "headless": selenium_headless_var.get(),
        "no_sandbox": selenium_no_sandbox_var.get(),
        "disable_dev_shm_usage": selenium_dev_shm_usage_var.get(),
        "disable_notifications": selenium_notifications_var.get(),
        "disable_extensions": selenium_extensions_var.get(),
        "disable_gpu": selenium_gpu_var.get(),
        "enable_webgl": selenium_webgl_var.get(),
        "enable_smooth_scrolling": selenium_smooth_scrolling_var.get(),
        "lang_en_US": selenium_lang_en_US_var.get(),
        "start_maximized": selenium_start_maximized_var.get(),
    }
    selected_scrolling_method = scrolling_method_combobox.get()
    scrolling_method_key = SCROLLING_METHODS.get(selected_scrolling_method, SCROLLING_METHODS["Send END Key"]) # Default ke Send END Key

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
    progress_label_var.set("Starting process...")
    print(f"Starting process for channel: {channel_url}, limit: {num_videos_limit if num_videos_limit is not None else 'All'}, format: {selected_format_name} ({selected_format_string}), delay: {download_delay_seconds}s, retries: {retries}, proxy: {proxy_address if proxy_address else 'None'}")
    print(f"Selenium Options: {selenium_options}, Scrolling Method: {selected_scrolling_method} ({scrolling_method_key})")

    # Reset cancel event
    cancel_event.clear()

    # Buat direktori output utama jika belum ada
    try:
        os.makedirs(main_output_directory, exist_ok=True)
        print(f"Ensured main output directory exists: {main_output_directory}")
    except Exception as e:
        error_msg = f"Error creating main output directory: {e}"
        print(error_msg)
        progress_label_var.set(error_msg)
        messagebox.showerror("Directory Error", error_msg)
        # Re-enable Start button if directory creation fails before thread starts
        root.after(100, lambda: start_button.config(state=tk.NORMAL))
        root.after(100, lambda: cancel_button.config(state=tk.DISABLED))
        return


    # Jalankan seluruh proses di thread terpisah
    def process_thread():
        """Fungsi wrapper untuk menjalankan seluruh proses batching dalam thread."""
        global all_videos_download_status # Deklarasikan untuk memodifikasi variabel global
        all_videos_download_status = [] # Reset status list untuk setiap proses baru

        try:
            # 1. Ambil Semua URL Shorts menggunakan Selenium dengan Scrolling
            print("Step 1/4: Fetching all Shorts URLs using Selenium...")
            all_shorts_urls = get_all_shorts_urls_selenium(
                channel_url,
                num_videos_limit, # Pass limit to Selenium for potential early stop
                selenium_options,
                scrolling_method_key,
                proxy_address if proxy_address else None, # Use the same proxy for Selenium
                progress_label_var,
                cancel_event
            )

            if cancel_event.is_set():
                 print("Process cancelled after Selenium URL fetching.")
                 progress_label_var.set("Process cancelled.")
                 return # Keluar jika dibatalkan

            if not all_shorts_urls:
                progress_label_var.set("Process finished: No Shorts URLs found via Selenium.")
                print("No Shorts URLs found via Selenium.")
                progress_var.set(0) # Reset progress if no links
                return

            # 2. Ambil Metadata (Title, Description) untuk URL yang Ditemukan menggunakan yt-dlp
            # Ini diperlukan untuk menyimpan ke file Excel
            # Fungsi ini sekarang mengiterasi list URL dan memanggil yt-dlp per URL
            print(f"Step 2/4: Fetching metadata for {len(all_shorts_urls)} URLs using yt-dlp...")
            all_shorts_metadata = get_metadata_for_urls(
                all_shorts_urls,
                proxy_address if proxy_address else None, # Use the same proxy for yt-dlp metadata fetch
                progress_label_var,
                cancel_event
            )

            if cancel_event.is_set():
                 print("Process cancelled during yt-dlp metadata fetching.")
                 progress_label_var.set("Process cancelled.")
                 return # Keluar jika dibatalkan

            if not all_shorts_metadata:
                 progress_label_var.set("Process finished: Failed to fetch metadata for any URLs.")
                 print("Failed to fetch metadata for any URLs.")
                 progress_var.set(0)
                 return

            # Jika num_videos_limit diberikan, pastikan metadata list juga dibatasi
            # (Meskipun Selenium sudah mencoba membatasi, ini double check)
            if num_videos_limit is not None and num_videos_limit > 0:
                 all_shorts_metadata = all_shorts_metadata[:num_videos_limit]
                 print(f"Trimmed metadata list to {len(all_shorts_metadata)} based on user limit after fetching.")

            total_videos_to_process = len(all_shorts_metadata)
            if total_videos_to_process == 0:
                 progress_label_var.set("Process finished: No Shorts found after metadata check/filtering.")
                 print("No Shorts found after metadata check/filtering.")
                 progress_var.set(0)
                 return

            # Inisialisasi daftar status global untuk semua video yang akan diproses
            # Status awal adalah 'No' (belum didownload/error)
            all_videos_download_status = [
                {'url': item['url'], 'title': item['title'], 'status': 'No'}
                for item in all_shorts_metadata
            ]
            print(f"Initialized global download status for {len(all_videos_download_status)} videos.")


            num_batches = math.ceil(total_videos_to_process / BATCH_SIZE) # Hitung jumlah batch

            progress_label_var.set(f"Step 2/4 finished. Ready to process {total_videos_to_process} videos in {num_batches} batches.")
            print(f"Ready to process {total_videos_to_process} videos in {num_batches} batches.")

            # 3. Proses per Batch (Simpan Excel & Download)
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

                progress_label_var.set(f"{batch_info_str} Step 3/4: Processing batch with {len(current_batch_metadata)} videos...")
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

                # 3a. Simpan Metadata Batch ke Excel di dalam subfolder batch
                excel_filename = f"shorts_metadata_batch_{batch_number}.xlsx"
                excel_filepath = os.path.join(batch_output_directory, excel_filename)

                progress_label_var.set(f"{batch_info_str} Step 3/4: Saving metadata to Excel...")
                print(f"{batch_info_str} Saving metadata to Excel...")
                save_metadata_to_excel(current_batch_metadata, excel_filepath)
                # Status berhasil/gagal disimpan di dalam fungsi save_metadata_to_excel

                # 3b. Mulai Proses Download Video untuk batch ini
                if current_batch_metadata: # Cek jika ada metadata untuk batch ini
                     # Status download per video diupdate di dalam download_videos_from_links
                     failed_urls_this_batch = download_videos_from_links(
                         current_batch_metadata, # Pass metadata list
                         batch_output_directory,
                         selected_format_string,
                         retries,
                         download_delay_seconds,
                         proxy_address if proxy_address else None, # Use the same proxy for download
                         all_videos_download_status, # Pass reference to global status list
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
                     progress_label_var.set(f"{batch_info_str} Step 4/4: No valid videos to download in this batch.")
                     print(f"{batch_info_str} No valid videos to download in this batch.")
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

                # --- Simpan Master Status ke Excel ---
                print("Saving overall download status to master Excel file...")
                # Coba ekstrak nama channel dari URL untuk nama file
                channel_name_for_file = "channel"
                if '/@' in channel_url:
                    channel_name_for_file = channel_url.split('/@')[1].split('/')[0]
                elif '/channel/' in channel_url:
                    channel_name_for_file = channel_url.split('/channel/')[1].split('/')[0]
                save_master_status_to_excel(all_videos_download_status, main_output_directory, channel_name_for_file)
                # --- End Simpan Master Status ---

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
            # Gunakan root.after karena ini di thread lain
            root.after(100, lambda: start_button.config(state=tk.NORMAL))
            root.after(100, lambda: cancel_button.config(state=tk.DISABLED))
            print("Process thread finished.")


    # Buat dan mulai thread untuk menjalankan seluruh proses batching
    thread = Thread(target=process_thread)
    thread.start()

def on_cancel_button_click(start_button, cancel_button, progress_label_var):
    """
    Fungsi yang dipanggil saat tombol 'Cancel Process' diklik.
    Memberi sinyal pembatalan ke thread download dan mencoba menghentikan subprocess/WebDriver.

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
            current_subprocess.kill() # Kirim sinyal kill (lebih paksa)
            print("yt-dlp subprocess terminated.")
        except Exception as e:
            print(f"Error terminating yt-dlp subprocess: {e}")

    # Coba terminasi Selenium WebDriver jika sedang berjalan
    global current_driver
    if current_driver:
        try:
            print("Attempting to quit running Selenium WebDriver...")
            current_driver.quit()
            current_driver = None
            print("Selenium WebDriver quit.")
        except Exception as e:
            print(f"Error quitting Selenium WebDriver: {e}")


    # Status GUI akan diupdate oleh thread setelah benar-benar berhenti (di blok finally)


# --- Konfigurasi GUI ---

# Membuat jendela utama
root = tk.Tk()
root.title("Shorts Bulk DL & Metadata Batcher By Sewer (with Selenium Scrolling)") # Judul aplikasi diperbarui
root.geometry("700x700") # Ukuran jendela disesuaikan setelah menghapus bagian cookies
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
style.configure("TLabelframe", background="#2E2E2E", foreground="#FFFFFF", bordercolor="#555555") # Labelframe
style.configure("TLabelframe.Label", background="#2E2E2E", foreground="#FFFFFF") # Label di Labelframe
style.configure("TCheckbutton", background="#2E2E2E", foreground="#FFFFFF") # Checkbutton

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

# Label dan Entry untuk Proxy (Digunakan oleh Selenium dan yt-dlp)
proxy_label = ttk.Label(main_frame, text="Proxy (optional, e.g., http://host:port):")
proxy_label.grid(column=0, row=6, sticky=tk.W, pady=5, padx=5)

proxy_entry = ttk.Entry(main_frame, width=30) # Entry untuk proxy
proxy_entry.grid(column=1, row=6, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)

# --- Selenium Configuration Section ---
selenium_frame = ttk.Labelframe(main_frame, text="Selenium Configuration", padding="10")
selenium_frame.grid(column=0, row=7, columnspan=3, sticky=(tk.W, tk.E), pady=10, padx=5)

# Checkbuttons untuk opsi Selenium WebDriver
selenium_headless_var = tk.BooleanVar(value=True) # Default: True
selenium_no_sandbox_var = tk.BooleanVar(value=True) # Default: True
selenium_dev_shm_usage_var = tk.BooleanVar(value=True) # Default: True
selenium_notifications_var = tk.BooleanVar(value=True) # Default: True
selenium_extensions_var = tk.BooleanVar(value=True) # Default: True
selenium_gpu_var = tk.BooleanVar(value=True) # Default: True
selenium_webgl_var = tk.BooleanVar(value=False) # Default: False
selenium_smooth_scrolling_var = tk.BooleanVar(value=False) # Default: False (Tidak relevan di headless)
selenium_lang_en_US_var = tk.BooleanVar(value=True) # Default: True
selenium_start_maximized_var = tk.BooleanVar(value=False) # Default: False (Tidak relevan di headless)

# Layout Checkbuttons dalam 2 kolom
checkbutton_col1 = ttk.Frame(selenium_frame)
checkbutton_col1.grid(column=0, row=0, sticky=tk.N, padx=5)
checkbutton_col2 = ttk.Frame(selenium_frame)
checkbutton_col2.grid(column=1, row=0, sticky=tk.N, padx=5)

ttk.Checkbutton(checkbutton_col1, text="Headless (--headless=new)", variable=selenium_headless_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col1, text="Disable Sandbox (--no-sandbox)", variable=selenium_no_sandbox_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col1, text="Disable /dev/shm usage (--disable-dev-shm-usage)", variable=selenium_dev_shm_usage_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col1, text="Disable Notifications (--disable-notifications)", variable=selenium_notifications_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col1, text="Disable Extensions (--disable-extensions)", variable=selenium_extensions_var).pack(anchor=tk.W)

ttk.Checkbutton(checkbutton_col2, text="Disable GPU (--disable-gpu)", variable=selenium_gpu_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col2, text="Enable WebGL (--enable-webgl)", variable=selenium_webgl_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col2, text="Enable Smooth Scrolling (--enable-smooth-scrolling)", variable=selenium_smooth_scrolling_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col2, text="Set Language to en-US (--lang=en-US)", variable=selenium_lang_en_US_var).pack(anchor=tk.W)
ttk.Checkbutton(checkbutton_col2, text="Start Maximized (--start-maximized)", variable=selenium_start_maximized_var).pack(anchor=tk.W)

# Label dan Combobox untuk Metode Scrolling
scrolling_method_label = ttk.Label(selenium_frame, text="Scrolling Method:")
scrolling_method_label.grid(column=0, row=1, sticky=tk.W, pady=5, padx=5)

scrolling_method_combobox = ttk.Combobox(selenium_frame, values=list(SCROLLING_METHODS.keys()), state="readonly", width=30)
scrolling_method_combobox.grid(column=1, row=1, sticky=(tk.W, tk.E), pady=5, padx=5)
scrolling_method_combobox.set("Send END Key") # Set nilai default ke metode yang terbukti efektif


# Frame untuk tombol Start dan Cancel
button_frame = ttk.Frame(main_frame)
button_frame.grid(column=0, row=8, columnspan=3, pady=15)
button_frame.columnconfigure(0, weight=1) # Agar tombol bisa di tengah
button_frame.columnconfigure(1, weight=1)

# Tombol untuk memulai proses batching
start_button = ttk.Button(button_frame, text="Start Batch Process",
                          command=lambda: on_start_button_click(
                              folder_var, channel_entry, num_videos_entry,
                              format_combobox, delay_entry, retries_entry, proxy_entry,
                              selenium_headless_var, selenium_no_sandbox_var, selenium_dev_shm_usage_var,
                              selenium_notifications_var, selenium_extensions_var, selenium_gpu_var,
                              selenium_webgl_var, selenium_smooth_scrolling_var, selenium_lang_en_US_var,
                              selenium_start_maximized_var,
                              scrolling_method_combobox,
                              progress_var, progress_label_var, start_button, cancel_button
                          ))
start_button.grid(column=0, row=0, padx=10) # Tambahkan padx antar tombol

# Tombol untuk membatalkan proses
cancel_button = ttk.Button(button_frame, text="Cancel Process",
                           command=lambda: on_cancel_button_click(start_button, cancel_button, progress_label_var),
                           state=tk.DISABLED) # Nonaktifkan secara default
cancel_button.grid(column=1, row=0, padx=10)

# Progress bar untuk menunjukkan kemajuan download (per batch)
progress_var = tk.IntVar() # Variabel untuk nilai progress bar (0-100)
progress_bar = ttk.Progressbar(main_frame, orient="horizontal", mode="determinate", variable=progress_var, style="Horizontal.TProgressbar")
progress_bar.grid(column=0, row=9, columnspan=3, pady=5, sticky=(tk.W, tk.E))

# Label untuk menampilkan status proses (termasuk info batch)
progress_label_var = tk.StringVar() # Variabel untuk teks status
progress_label = ttk.Label(main_frame, textvariable=progress_label_var, anchor=tk.CENTER) # anchor=tk.CENTER untuk teks di tengah
progress_label.grid(column=0, row=10, columnspan=3, pady=5, sticky=(tk.W, tk.E))

# Label penjelasan langkah-langkah proses
explanation_text = f"""Process Steps:
1. Fetching all Shorts URLs using Selenium with scrolling (based on element count).
2. Fetching metadata (Title, Description) for found URLs using yt-dlp (one by one).
3. Saving metadata to Excel file(s) in batch folders.
4. Downloading videos batch by batch with selected format/quality, delay, retries, and proxy.
   An overall download status Excel file (Link URL, Title, D/N/E) will be created in the main folder.
Failed video URLs will be saved to '{ERROR_FOLDER_NAME}/Batch_X_Errors/error.txt'.""" # Teks diperbarui
explanation_label = ttk.Label(main_frame, text=explanation_text, justify=tk.LEFT, foreground="#AAAAAA", background="#2E2E2E")
explanation_label.grid(column=0, row=11, columnspan=3, pady=10, padx=5, sticky=tk.W)


# --- Menjalankan Aplikasi GUI ---
root.mainloop()
