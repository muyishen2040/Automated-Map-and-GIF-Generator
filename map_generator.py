import folium
from PIL import Image
import os
import time
import pandas as pd
import webbrowser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from threading import Lock

CSV_FILE = "locations.csv"
GIF_FILE = "animation.gif"
MAP_FILE = "map.html"
SCREENSHOT_DIR = "screenshots"
DRIVER = None
PROCESS_LOCK = Lock()

class CSVHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.last_modified_time = None
        self.locations = []
        self.timestamps = []
        self.ensure_csv_file_exists()
        self.update_csv_data()
        

    def on_modified(self, event):
        if event.src_path.endswith(CSV_FILE):
            print(f"Detected modification in {CSV_FILE}")
            current_time = os.path.getmtime(CSV_FILE)
            if self.last_modified_time is None or current_time != self.last_modified_time:
                print(f"Processing updated CSV file: {CSV_FILE}")
                self.last_modified_time = current_time
                self.update_csv_data()
    
    def ensure_csv_file_exists(self):
        if not os.path.exists(CSV_FILE):
            print(f"CSV file {CSV_FILE} does not exist. Creating a new file with required columns.")
            df = pd.DataFrame(columns=['latitude', 'longitude', 'timestamp'])
            df.to_csv(CSV_FILE, index=False)

    def update_csv_data(self):
        if PROCESS_LOCK.locked():
            print("Rendering process is currently running. Waiting for it to complete.")
            return

        with PROCESS_LOCK:
            try:
                df = pd.read_csv(CSV_FILE)
                if df.empty:
                    raise ValueError("CSV file is empty")
                new_locations = list(zip(df['latitude'], df['longitude']))
                new_timestamps = df['timestamp'].tolist()
            except (pd.errors.EmptyDataError, ValueError) as e:
                print(f"CSV file is empty or invalid. Adding required columns: {e}")
                df = pd.DataFrame(columns=['latitude', 'longitude', 'timestamp'])
                df.to_csv(CSV_FILE, index=False)
                new_locations = []
                new_timestamps = []

            if not new_locations:
                print("No locations found in CSV file. Skipping processing.")
                return
            if new_locations != self.locations or new_timestamps != self.timestamps:
                self.locations = new_locations
                self.timestamps = new_timestamps
                process_data(self.locations, self.timestamps)

def initialize_driver():
    global DRIVER
    if DRIVER is None:
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1200x800')
            DRIVER = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        except Exception as e:
            print(f"Error initializing WebDriver: {e}")

def capture_map_as_image(driver, map_file, image_file):
    try:
        driver.get(f"file://{os.path.abspath(map_file)}")
        time.sleep(1)  # Adjust if necessary
        driver.save_screenshot(image_file)
    except Exception as e:
        print(f"Error capturing map as image: {e}")

def process_data(locations, timestamps):
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)

    if os.path.exists(GIF_FILE):
        os.remove(GIF_FILE)

    create_map(locations, timestamps)

    if os.path.exists(MAP_FILE):
        os.remove(MAP_FILE)
    create_map_html(locations, timestamps)

def create_map(locations, timestamps):
    global DRIVER
    
    images = []

    # Calculate the map bounds to fit all locations
    latitudes = [lat for lat, lon in locations]
    longitudes = [lon for lat, lon in locations]
    bounds = [[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]]

    initialize_driver()

    for i in range(len(locations)):
        m = folium.Map(location=locations[0], zoom_start=5)
        m.fit_bounds(bounds)  # Fit the map to the calculated bounds

        # Add markers with timestamps and lines between locations
        for j in range(i + 1):
            folium.Marker(
                location=locations[j],
                popup=f"{timestamps[j]}",
                icon=folium.Icon(color='blue')
            ).add_to(m)
            if j > 0:
                folium.PolyLine([locations[j-1], locations[j]], color="blue").add_to(m)

        map_file = f"{SCREENSHOT_DIR}/map_{i}.html"
        image_file = f"{SCREENSHOT_DIR}/map_{i}.png"
        m.save(map_file)
        
        capture_map_as_image(DRIVER, map_file, image_file)
        with Image.open(image_file) as img:
            images.append(img.copy())
        os.remove(map_file)
        os.remove(image_file)
    
    DRIVER.quit()  # Quit the WebDriver after processing all maps
    DRIVER = None

    images[0].save(GIF_FILE, save_all=True, append_images=images[1:], duration=500, loop=0)

def create_map_html(locations, timestamps):
    # Initialize the map centered at the first location
    m = folium.Map(location=locations[0], zoom_start=5)

    # Calculate the map bounds to fit all locations
    latitudes = [lat for lat, lon in locations]
    longitudes = [lon for lat, lon in locations]
    bounds = [[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]]
    m.fit_bounds(bounds)

    # Add markers with timestamps and lines between locations
    for i in range(len(locations)):
        folium.Marker(
            location=locations[i],
            popup=f"{timestamps[i]}",
            icon=folium.Icon(color='blue')
        ).add_to(m)
        if i > 0:
            folium.PolyLine([locations[i-1], locations[i]], color="blue").add_to(m)

    # Save the map to an HTML file
    m.save(MAP_FILE)
    webbrowser.open(f"file://{os.path.abspath(MAP_FILE)}")

if __name__ == "__main__":
    print("Starting observer...")
    event_handler = CSVHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
