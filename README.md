# 🚀 YT-Shorts-Bulk-Scraper

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![GUI](https://img.shields.io/badge/GUI-Tkinter-blue?style=for-the-badge)
![Web Scraping](https://img.shields.io/badge/Web%20Scraping-Selenium-green?style=for-the-badge&logo=selenium)
[![GitHub followers](https://img.shields.io/github/followers/MuchoRio?style=social)](https://github.com/MuchoRio)
[![GitHub stars](https://img.shields.io/github/stars/MuchoRio/YT-Shorts-Bulk-Scraper?style=social)](https://github.com/MuchoRio/YT-Shorts-Bulk-Scraper)

---
## English

This is a powerful and user-friendly Python application with a Graphical User Interface (GUI) designed to **bulk scrape YouTube Shorts video URLs and their metadata (Title, Description)** from any specified YouTube channel, and then **download these videos in batches**. It leverages Selenium for robust URL collection and `yt-dlp` for efficient downloading and metadata extraction.

**Important Note:** Downloading content from YouTube may violate YouTube's Terms of Service. The use of this tool is entirely at your own risk. Please use this tool responsibly and adhere to all applicable laws and copyright regulations.

### ✨ Features

* **Intuitive GUI:** Built with Tkinter for an easy-to-navigate and user-friendly experience.
* **Comprehensive Data Collection:**
    * **Automated URL Scraping:** Uses Selenium with intelligent scrolling logic to fetch all available YouTube Shorts URLs from a given channel.
    * **Rich Metadata Extraction:** Leverages `yt-dlp` to obtain video titles and descriptions for each Short.
* **Flexible Download Management:**
    * **Bulk Downloading:** Efficiently downloads multiple Shorts videos in configurable batches.
    * **Targeted Processing:** Option to limit the number of videos to process (e.g., download only the latest 100 Shorts).
    * **Configurable Download Quality:** Select your preferred video format and quality (e.g., Best Quality, 1080p MP4, 720p MP4).
    * **Randomized Delays:** Incorporates customizable, random delays between downloads to mimic human behavior and reduce detection risk.
    * **Retry Mechanism:** Automatically retries failed downloads for improved reliability.
* **Advanced Browser & Network Options:**
    * **Selenium Customization:** Configure headless mode, disable sandbox, notifications, GPU, and more for optimized scraping performance and stealth.
    * **Multiple Scrolling Methods:** Choose between "Send END Key", "Scroll to Bottom (JS)", or "Scroll by Viewport (JS)" for robust content loading on YouTube.
    * **Proxy Support:** Option to use a proxy for both Selenium scraping and `yt-dlp` downloads, enhancing privacy and potentially bypassing geo-restrictions or IP blocks.
    * **Random User-Agent Rotation:** Uses a rotating list of User-Agents for both Selenium and `yt-dlp` to further evade bot detection.
* **Detailed Output & Error Handling:**
    * **Batch-wise Output:** Organizes downloaded videos and their corresponding metadata (in `.xlsx` format) into separate, numbered batch folders.
    * **Comprehensive Status Tracking:** Maintains an overall download status (`Link URL`, `Title`, `D/N/E` - Downloaded/Not Downloaded/Error) saved as a master Excel file.
    * **Error Logging:** Automatically saves URLs of failed downloads to a dedicated `error.txt` file within a `batching_error` subfolder for easy review.
* **Process Control:** Real-time progress bar and status updates within the GUI, along with a "Cancel Process" button to gracefully stop ongoing operations.
* **Persistent Settings:** Saves and loads your last-used GUI configurations (output folder, channel URL, options) for convenience.

  ### ⚙️ Installation

1.  **Ensure Python is installed:** Python 3.6 or higher is required.
2.  **Clone the repository:**
    ```bash
    git clone [https://github.com/MuchoRio/YT-Shorts-Bulk-Scraper.git](https://github.com/MuchoRio/YT-Shorts-Bulk-Scraper.git)
    cd YT-Shorts-Bulk-Scraper
    ```
3.  **Create a virtual environment (highly recommended):**
    ```bash
    python -m venv venv
    ```
    * On Windows:
        ```bash
        .\venv\Scripts\activate
        ```
    * On macOS/Linux:
        ```bash
        source venv/bin/activate
        ```
4.  **Install the required Python libraries:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: `tkinter` is typically included with standard Python installations, but `openpyxl` is required by `pandas` for `.xlsx` file handling, and `yt-dlp`, `selenium`, `webdriver-manager` are crucial for functionality.)*

### 🚀 Usage

1.  **Run the application:**
    ```bash
    python gui.py
    ```
2.  **Configure Settings in the GUI:**
    * **Select the MAIN folder to save batches:** Click "Browse" to choose the primary directory where batch folders (e.g., `Batch_1`, `Batch_2`) and the master status file will be created.
    * **Enter the YouTube channel URL:** Input the full URL of the YouTube channel whose Shorts you wish to process (e.g., `https://www.youtube.com/@NamaChannel` or `https://www.youtube.com/channel/ID_Channel`).
    * **Number of videos to process (empty for all):** Enter the maximum number of Shorts you want to scrape and download. Leave it empty to process all Shorts found on the channel.
    * **Select Video Format/Quality:** Choose your desired video format and quality from the dropdown menu.
    * **Download Delay (seconds):** Specify the maximum delay (in seconds) between individual video downloads. The script will apply a random delay between 1 second and this value.
    * **Number of Retries:** Define how many times `yt-dlp` should retry a failed download for a single video.
    * **Proxy (optional):** Enter your proxy details (e.g., `http://host:port` or `user:pass@ip:port`) if you want to use one.
    * **Selenium Configuration:** Tick the checkboxes for various Selenium browser options like `Headless Mode` (runs the browser without a visible window), `Disable Sandbox`, `Disable Notifications`, etc., to customize browser behavior.
    * **Scrolling Method:** Select the method Selenium will use to scroll the YouTube Shorts page to load more content.
3.  **Start the Process:** Click the **"Start Batch Process"** button to begin the scraping and downloading.
4.  **Monitor Progress:** Observe the real-time `Progress` bar and `Status` label in the GUI for updates on the process, including current step, batch information, and video counts.
5.  **Cancel:** Click the **"Cancel Process"** button at any time to gracefully stop the ongoing operations.
6.  **Review Output:** Once the process is complete (or cancelled), navigate to your chosen main output folder to find the organized batch folders and the master status Excel file.
   
### 📁 Output Structure

Within the main output folder you selected, the script will create:

* **Numbered Batch Subfolders:** (e.g., `Batch_1`, `Batch_2`, etc.)
    * Each subfolder will contain:
        * An Excel file (`shorts_metadata_batch_X.xlsx`) with `Link URL`, `Title`, and `Description` for all Shorts in that batch.
        * The downloaded Shorts video files.
* **Error Logging:** A dedicated `batching_error` folder at the main output level.
    * Inside `batching_error`, subfolders like `Batch_X_Errors` will be created for each batch that encountered download failures.
    * Each `Batch_X_Errors` folder will contain an `error.txt` file listing the URLs that failed to download within that specific batch.
* **Master Status File:** A main Excel file (e.g., `[ChannelName]_shorts_download_status.xlsx`) in the root of your main output folder, providing an overview of all processed videos with their `Link URL`, `Title`, and final `D/N/E` (Downloaded/Not Downloaded/Error) status.

### ⚙️ Advanced Configuration (in Code)

You can adjust the batch size by modifying the `BATCH_SIZE` variable at the beginning of the `gui.py` script:

```python
# --- Konfigurasi Default ---
BATCH_SIZE = 100 # Jumlah video Shorts per batch/folder. Bisa diubah sesuai kebutuhan.
```

### 🙏 Support Me

If you find this script useful, please consider giving it a star ⭐️ on GitHub! Your support encourages me to create more open-source tools.

### 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
