import os
import shutil


def clean_and_save_file(original_file, output_dir):
    with open(original_file, "r") as file:
        lines = file.readlines()

    cleaned_lines = [
        line for line in lines if not line.strip().startswith("#") and line.strip()
    ]

    os.makedirs(output_dir, exist_ok=True)
    cleaned_file_path = os.path.join(output_dir, os.path.basename(original_file))

    with open(cleaned_file_path, "w") as file:
        file.writelines(cleaned_lines)


def process_all_txt_files(input_folder, output_folder):
    for filename in os.listdir(input_folder):
        if filename.endswith(".txt"):
            file_path = os.path.join(input_folder, filename)
            clean_and_save_file(file_path, output_folder)


def sync_files(source_dir, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    for file_name in os.listdir(source_dir):
        source_file = os.path.join(source_dir, file_name)
        backup_file = os.path.join(backup_dir, file_name)
        shutil.copy2(source_file, backup_file)


# Example usage
input_folder = "domains"  # Folder where the original .txt files are located
output_folder = "cleaned"  # Folder where the cleaned files will be saved
backup_folder = "backup"  # Folder where the cleaned files will be backed up

process_all_txt_files(input_folder, output_folder)
sync_files(output_folder, backup_folder)
