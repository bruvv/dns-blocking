import requests
import os
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
        # Consider successful if the status code is less than 400
        return response.status_code < 400
    except requests.exceptions.RequestException as e:
        # Log only failed requests
        logging.error(f"Error accessing {url}: {e}")
        return False


def process_file(file_path, output_dir):
    with open(file_path, "r") as file:
        lines = file.readlines()

    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, os.path.basename(file_path))

    with open(output_file_path, "w") as file:
        for line in lines:
            if line.strip() and not line.strip().startswith("#"):
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


# Directory setup
input_folder = "domains"
output_folder = "cleaned"

# Processing
process_all_files(input_folder, output_folder)
