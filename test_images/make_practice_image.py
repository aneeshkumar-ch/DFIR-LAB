import struct
import datetime
from pathlib import Path

def create_fat12_practice_image(output_path: Path):
    """
    Synthesize an authentic 1.44MB FAT12 disk image (practice_evidence.dd).
    Populated per BCSSL Lab 14 specification:
    - 4 Active files (documents, JPEG, config)
    - 4 Deleted files (marked with 0xE5 deletion flag):
        1. FLAG.TXT (Contains sensitive credentials and flag)
        2. SECRET.TXT (Contains 'CONFIDENTIAL' and 'CASE-TEST-014')
        3. PASSWD.TXT (Contains 'admin', 'password')
        4. EVIL_DOC.TXT (Real PNG image disguised as .txt -- extension mismatch deception)
    """
    SECTOR_SIZE = 512
    TOTAL_SECTORS = 2880  # Standard 1.44 MB floppy image
    SECTORS_PER_CLUSTER = 1
    RESERVED_SECTORS = 1
    NUM_FATS = 2
    ROOT_ENTRIES = 224
    FAT_SIZE_SECTORS = 9
    
    ROOT_DIR_SECTORS = (ROOT_ENTRIES * 32 + (SECTOR_SIZE - 1)) // SECTOR_SIZE  # 14 sectors
    DATA_START_SECTOR = RESERVED_SECTORS + (NUM_FATS * FAT_SIZE_SECTORS) + ROOT_DIR_SECTORS # 1 + 18 + 14 = 33

    disk = bytearray(TOTAL_SECTORS * SECTOR_SIZE)

    # 1. Boot Sector (Sector 0)
    boot = bytearray(SECTOR_SIZE)
    boot[0:3] = b'\xeb\x3c\x90'  # JMP short
    boot[3:11] = b'MSDOS5.0'     # OEM Name
    struct.pack_into('<H', boot, 11, SECTOR_SIZE)          # Bytes per sector
    boot[13] = SECTORS_PER_CLUSTER                         # Sectors per cluster
    struct.pack_into('<H', boot, 14, RESERVED_SECTORS)     # Reserved sectors
    boot[16] = NUM_FATS                                    # Number of FATs
    struct.pack_into('<H', boot, 17, ROOT_ENTRIES)         # Root dir entries
    struct.pack_into('<H', boot, 19, TOTAL_SECTORS)        # Total sectors
    boot[21] = 0xF0                                        # Media descriptor (3.5" 1.44MB)
    struct.pack_into('<H', boot, 22, FAT_SIZE_SECTORS)     # Sectors per FAT
    struct.pack_into('<H', boot, 24, 18)                   # Sectors per track
    struct.pack_into('<H', boot, 26, 2)                    # Number of heads
    struct.pack_into('<I', boot, 28, 0)                    # Hidden sectors
    boot[36] = 0x00                                        # Drive number
    boot[38] = 0x29                                        # Extended boot signature
    struct.pack_into('<I', boot, 39, 0x14051980)           # Volume serial
    boot[43:54] = b'LAB14_EVID '                           # Volume label
    boot[54:62] = b'FAT12   '                              # Filesystem type
    boot[510:512] = b'\x55\xaa'                            # Boot signature
    disk[0:SECTOR_SIZE] = boot

    # 2. File Allocation Table (FAT12)
    # FAT Entry 0: Media byte (0xF0), FAT Entry 1: End-of-cluster (0xFF)
    fat = bytearray(FAT_SIZE_SECTORS * SECTOR_SIZE)
    fat[0] = 0xF0
    fat[1] = 0xFF
    fat[2] = 0xFF

    def set_fat12_entry(cluster, value):
        offset = (cluster * 3) // 2
        if cluster % 2 == 0:
            fat[offset] = (fat[offset] & 0x00) | (value & 0xFF)
            fat[offset + 1] = (fat[offset + 1] & 0xF0) | ((value >> 8) & 0x0F)
        else:
            fat[offset] = (fat[offset] & 0x0F) | ((value << 4) & 0xF0)
            fat[offset + 1] = (value >> 4) & 0xFF

    # 3. Create Files & Clusters
    # Timestamp: 2026-09-25 14:30:00
    dos_time = (14 << 11) | (30 << 5) | (0 >> 1)
    dos_date = ((2026 - 1980) << 9) | (9 << 5) | 25

    def make_dir_entry(name8, ext3, attr, start_cluster, file_size, is_deleted=False):
        entry = bytearray(32)
        full_name = (name8.ljust(8)[:8] + ext3.ljust(3)[:3]).encode('ascii')
        entry[0:11] = full_name
        if is_deleted:
            entry[0] = 0xE5  # Standard FAT deletion marker!
        entry[11] = attr     # 0x20 = Archive
        struct.pack_into('<H', entry, 22, dos_time)
        struct.pack_into('<H', entry, 24, dos_date)
        struct.pack_into('<H', entry, 26, start_cluster)
        struct.pack_into('<I', entry, 28, file_size)
        return entry

    root_dir_offset = (RESERVED_SECTORS + NUM_FATS * FAT_SIZE_SECTORS) * SECTOR_SIZE
    data_start_offset = DATA_START_SECTOR * SECTOR_SIZE

    # File Definitions
    # Deliberate extension mismatch: EVIL_DOC.TXT has a PNG header!
    png_header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00\x1f\xf3\xffa'
    png_payload = png_header + b' This is a hidden malware stage disguised as a TXT file! CASE-TEST-014'

    files = [
        # Normal active files
        ("REPORT", "TXT", 0x20, False, b"BCSSL Lab 14 Digital Forensics Examination Notes.\nEvidence acquired from suspicious workstation.\n"),
        ("IMAGE1", "JPG", 0x20, False, b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07"),
        ("CONFIG", "INI", 0x20, False, b"[Settings]\nEnvironment=ForensicLab\nDebug=False\nCase=CASE-TEST-014\n"),
        ("README", "TXT", 0x20, False, b"Please review the recovered items in the case package.\n"),

        # Deleted files (shifted to unallocated/deleted state)
        ("FLAG", "TXT", 0x20, True, b"TOP SECRET FLAG: Flag{CASE-TEST-014-FORENSICS-CHAMPION}\nSensitive evidence recovered successfully!\n"),
        ("SECRET", "TXT", 0x20, True, b"CONFIDENTIAL: Master credentials list.\nadmin:SuperSecretPassword123!\nroot:toor2026\n"),
        ("PASSWD", "TXT", 0x20, True, b"Local backup passwords: user1=password123, admin=adminPass987\n"),
        ("DISGUISE", "TXT", 0x20, True, png_payload),  # PNG disguised as .TXT!
    ]

    current_cluster = 2
    root_dir = bytearray(ROOT_DIR_SECTORS * SECTOR_SIZE)
    entry_index = 0

    # Volume label entry in root directory
    vol_entry = bytearray(32)
    vol_entry[0:11] = b'LAB14_EVID '
    vol_entry[11] = 0x08 # Volume label attribute
    struct.pack_into('<H', vol_entry, 22, dos_time)
    struct.pack_into('<H', vol_entry, 24, dos_date)
    root_dir[0:32] = vol_entry
    entry_index = 1

    for name8, ext3, attr, is_deleted, content in files:
        file_size = len(content)
        start_cluster = current_cluster
        
        # Write directory entry
        d_entry = make_dir_entry(name8, ext3, attr, start_cluster, file_size, is_deleted)
        root_dir[entry_index * 32 : (entry_index + 1) * 32] = d_entry
        entry_index += 1

        # Write cluster data
        cluster_offset = data_start_offset + (current_cluster - 2) * SECTOR_SIZE
        disk[cluster_offset : cluster_offset + file_size] = content

        # In FAT: Active files have allocated cluster in FAT table;
        # For deleted files, the OS frees the FAT entry (sets to 0x000), but cluster data remains on disk!
        if not is_deleted:
            set_fat12_entry(current_cluster, 0xFFF)  # EOF
        else:
            set_fat12_entry(current_cluster, 0x000)  # Free cluster (deleted!)

        current_cluster += 1

    # Copy FAT1 and FAT2 into disk
    fat1_offset = RESERVED_SECTORS * SECTOR_SIZE
    fat2_offset = fat1_offset + FAT_SIZE_SECTORS * SECTOR_SIZE
    disk[fat1_offset : fat1_offset + len(fat)] = fat
    disk[fat2_offset : fat2_offset + len(fat)] = fat

    # Copy Root Directory into disk
    disk[root_dir_offset : root_dir_offset + len(root_dir)] = root_dir

    # Write out disk image
    with open(output_path, "wb") as f:
        f.write(disk)

    print(f"Successfully synthesized practice disk image: {output_path} ({len(disk)} bytes)")

if __name__ == "__main__":
    out_file = Path(r"D:\PROJECTS\ForensicsAnalyzer\test_images\practice_evidence.dd")
    create_fat12_practice_image(out_file)
