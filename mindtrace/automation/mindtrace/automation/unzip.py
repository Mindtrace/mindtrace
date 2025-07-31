import os
import zipfile
import concurrent.futures

def unzip_file(zip_path, extract_dir):
    """
    Unzips a single zip file to a specified directory.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            print(f"Extracting {os.path.basename(zip_path)} to {extract_dir}...")
            zip_ref.extractall(extract_dir)
            print(f"Extraction of {os.path.basename(zip_path)} complete.")
    except zipfile.BadZipFile:
        print(f"Error: {os.path.basename(zip_path)} is a bad zip file and cannot be extracted.")
    except Exception as e:
        print(f"An error occurred while extracting {os.path.basename(zip_path)}: {e}")

def unzip_all_in_folder(folder_path):
    """
    Unzips all .zip files in a specified folder using multiple threads.
    """
    if not os.path.isdir(folder_path):
        print(f"Error: Directory not found at {folder_path}")
        return

    zip_files_to_extract = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".zip"):
            zip_path = os.path.join(folder_path, filename)
            extract_dir = os.path.join(folder_path, os.path.splitext(filename)[0])
            
            if not os.path.exists(extract_dir):
                os.makedirs(extract_dir)
            
            zip_files_to_extract.append((zip_path, extract_dir))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(lambda p: unzip_file(*p), zip_files_to_extract)

if __name__ == "__main__":
    zip_folder = "/data/nfs/datasets/laser/New Set"
    unzip_all_in_folder(zip_folder)
