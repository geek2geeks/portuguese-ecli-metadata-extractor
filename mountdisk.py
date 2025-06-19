# mountdisk.py (Version 5 - Using AWE to Overcome Fragmentation)
import os
import sys
import subprocess
import argparse
import shutil
import time
import psutil

# --- Configuration ---
SOURCE_DIR = "D:\\pdfs"
RAMDISK_SIZE = "69G" 
RAMDISK_DRIVE = "R"
RAMDISK_DRIVE_WITH_COLON = f"{RAMDISK_DRIVE}:"

def get_available_memory_gb():
    return psutil.virtual_memory().available / (1024**3)

def check_prerequisites():
    print("--- Step 1: Checking prerequisites ---")
    if not shutil.which("imdisk"):
        print("\nERROR: 'imdisk.exe' not found in your system's PATH.")
        sys.exit(1)
    if not shutil.which("robocopy"):
        print("\nERROR: 'robocopy.exe' not found. This script is intended for Windows.")
        sys.exit(1)
    print("✓ ImDisk and Robocopy are available.")
    return True

def run_command(command, input_data=None):
    try:
        subprocess.run(
            command, input=input_data, check=True, capture_output=True, text=True, shell=True
        )
    except subprocess.CalledProcessError as e:
        print(f"\nERROR executing command: {e.cmd}")
        print(f"Return Code: {e.returncode}\nOutput:\n{e.stdout}\nError Output:\n{e.stderr}")
        sys.exit(1)

def mount():
    if not check_prerequisites():
        return

    available_gb = get_available_memory_gb()
    print(f"\n--- Step 2a: Checking available memory ---")
    print(f"Available system memory: {available_gb:.2f} GB")
    
    if available_gb < 65:
        print(f"\nERROR: Not enough available memory. Found {available_gb:.2f} GB, but need at least 65 GB.")
        print("Please close other memory-intensive applications and try again.")
        sys.exit(1)

    print(f"\n--- Step 2b: Creating {RAMDISK_SIZE} raw RAM disk on drive {RAMDISK_DRIVE_WITH_COLON} using AWE ---")
    # --- THE FIX: Added the '-o awe' flag to the command ---
    imdisk_create_cmd = f'imdisk -a -s {RAMDISK_SIZE} -m {RAMDISK_DRIVE_WITH_COLON} -o awe'
    run_command(imdisk_create_cmd)
    
    print("✓ Raw RAM Disk created. Waiting for OS to recognize it...")
    time.sleep(3) 

    print(f"\n--- Step 2c: Formatting {RAMDISK_DRIVE_WITH_COLON} as NTFS ---")
    format_cmd = f'echo. | format {RAMDISK_DRIVE_WITH_COLON} /FS:NTFS /Q /Y'
    run_command(format_cmd)
    print(f"✓ RAM Disk {RAMDISK_DRIVE_WITH_COLON} formatted.")

    print(f"\n--- Step 3: Copying files from {SOURCE_DIR} to {RAMDISK_DRIVE_WITH_COLON} ---")
    print("This will take several minutes...")
    destination_dir = os.path.join(RAMDISK_DRIVE_WITH_COLON, os.path.sep, "pdfs")
    robocopy_cmd = f'robocopy "{SOURCE_DIR}" "{destination_dir}" /E /MT:32 /R:2 /W:5'
    
    print(f"Running: {robocopy_cmd}")
    subprocess.run(robocopy_cmd, shell=True, check=True)

    print("\n✓ File copy complete.")
    print(f"\nSUCCESS: Your corpus is now available at {destination_dir}")

def unmount():
    print(f"--- Unmounting RAM disk on drive {RAMDISK_DRIVE_WITH_COLON} ---")
    imdisk_unmount_cmd = f"imdisk -d -m {RAMDISK_DRIVE_WITH_COLON}"
    try:
        run_command(imdisk_unmount_cmd)
        print(f"✓ RAM Disk {RAMDISK_DRIVE_WITH_COLON} successfully unmounted.")
    except SystemExit:
        print(f"\nINFO: Could not unmount {RAMDISK_DRIVE_WITH_COLON}. It may not be mounted or may be in use.")

# (The main parser function remains the same)
def main():
    parser = argparse.ArgumentParser(
        description="A script to manage a high-performance RAM disk for PDF processing.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.epilog = """
Examples:
  # Create the RAM disk and copy all files
  python mountdisk.py mount

  # Unmount the RAM disk when you are finished
  python mountdisk.py unmount
"""
    parser.add_argument(
        "action", 
        choices=['mount', 'unmount'],
        help="The action to perform: 'mount' to create and copy, 'unmount' to remove."
    )
    args = parser.parse_args()
    if args.action == 'mount':
        mount()
    elif args.action == 'unmount':
        unmount()

if __name__ == "__main__":
    main()