import os
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

print("=== FINAL WORD PAGE COUNT AUDIT ===")
all_ok = True

for fname, min_p, max_p in files:
    fpath = os.path.abspath(os.path.join(docs_dir, fname))
    doc = word.Documents.Open(fpath, ReadOnly=True, ConfirmConversions=False)
    doc.Repaginate()
    p = doc.ComputeStatistics(2) # wdStatisticPages
    doc.Close(False)

    passed = min_p <= p <= max_p
    status = "PASS" if passed else f"FAIL (Must be {min_p}-{max_p})"
    if not passed:
        all_ok = False
    print(f"  {fname:<42}: {p} pages [{status}] (Target: {min_p} to {max_p})")

word.Quit()
print("\nAUDIT RESULT: " + ("ALL 4 PASSED STRICT LIMITS!" if all_ok else "SOME FAILED"))
