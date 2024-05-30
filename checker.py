import requests
import os
import shutil
import logging

# Set up logging
logging.basicConfig(
    level=logging.ERROR,
    filename="error.log",
    filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def check_url(url):
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code < 400:
            print(f"URL resolves: {url} - Status code: {response.status_code}")
            return True
        else:
            print(f"URL does not resolve: {url} - Status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Error accessing {url}: {e}")
        print(f"Failed to access URL: {url}")
        return False


def process_file(file_path, output_dir):
    print(f"Processing file: {file_path}")
    with open(file_path, "r") as file:
        lines = file.readlines()

    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, os.path.basename(file_path))

    with open(output_file_path, "w") as file:
        for line in lines:
            if (
                line.strip()
                and not line.strip().startswith("#")
                and not line.strip().startswith("/")
            ):
                url = (
                    f"http://{line.strip()}"
                    if not line.strip().startswith("http")
                    else line.strip()
                )
                if check_url(url):
                    file.write(line)


def process_all_files(folder, output_folder):
    for filename in os.listdir(folder):
        if filename.endswith(".txt"):
            process_file(os.path.join(folder, filename), output_folder)


def sync_files(source_dir, backup_dir):
    print(f"Syncing files from {source_dir} to {backup_dir}")
    os.makedirs(backup_dir, exist_ok=True)
    for file_name in os.listdir(source_dir):
        source_file = os.path.join(source_dir, file_name)
        backup_file = os.path.join(backup_dir, file_name)
        shutil.copy2(source_file, backup_file)
    print("Backup complete.")


# Directory setup
input_folder = "domains"
output_folder = "cleaned"
backup_folder = "backup"

# Start processing
print("Starting the URL checking process...")
process_all_files(input_folder, output_folder)
sync_files(output_folder, backup_folder)
print("Processing completed.")
