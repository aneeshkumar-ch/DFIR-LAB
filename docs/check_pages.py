import os
import sys
import win32com.client

docs_dir = r"D:\PROJECTS\ForensicsAnalyzer\docs"
files = [
    ("1_Project_Building_Guide.docx", 8, 10),
    ("2_Project_Student_Guide.docx", 6, 8),
    ("3_Project_Student_Worksheet.docx", 3, 4),
    ("4_Project_Student_Worksheet_Solutions.docx", 3, 4)
]

word = win32com.client.Dispatch("Word.Application")
word.Visible = False
word.DisplayAlerts = 0

print("=== VERIFYING WORD COM PAGE COUNTS ===\n")
all_passed = True

for fname, min_p, max_p in files:
    fpath = os.path.join(docs_dir, fname)
    doc = word.Documents.Open(fpath, ReadOnly=True)
    doc.Repaginate()
    pages = doc.ComputeStatistics(2) # wdStatisticPages
    doc.Close(False)

    in_range = min_p <= pages <= max_p
    status = "PASS" if in_range else f"FAIL (Must be {min_p}-{max_p})"
    if not in_range:
        all_passed = False

    sz = os.path.getsize(fpath)
    print(f"{fname}:")
    print(f"  Target: {min_p} to {max_p} pages")
    print(f"  Actual: {pages} pages [{status}]")
    print(f"  Size:   {sz:,} bytes\n")

word.Quit()
print("FINAL PAGE AUDIT: " + ("ALL 4 DOCUMENTS PASSED!" if all_passed else "SOME CRITERIA FAILED"))
