# import re
# import pdfplumber
# import pandas as pd
# import numpy as np
# import traceback
# from io import BytesIO
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework.parsers import MultiPartParser
# from rest_framework import status
# from django.http import FileResponse
# from pdf2image import convert_from_path
# import pytesseract
# import tempfile
#
# # ✅ Utility to convert string to float
# def to_float(x):
#     try:
#         x = str(x).replace(",", "").replace("\u20b9", "").replace("Cr", "").replace("Dr", "").strip()
#         if x.startswith("(") and x.endswith(")"): x = "-" + x[1:-1]
#         return float(re.sub(r"[^\d\.-]", "", x))
#     except:
#         return np.nan
#
# # ✅ Format Detection
# def detect_format(pdf):
#     kotak_hits = 0
#     structured_hits = 0
#     hdfc_hits = 0
#     bob_hits = 0
#     cr_dr_pattern = re.compile(r'([\d,]+\.\d{2})\s+(CR|DR)\s+([\d,]+\.\d{2})\s+(CR|DR)')
#     bob_pattern = re.compile(r'^(\d{2}/\d{2}/\d{4}).*(Cr|Dr)')
#     hdfc_pattern = re.compile(r'\d{2}[-/]\d{2}[-/]\d{2,4}.*\d[\d,]+\.\d{2}.*')
#
#     for page in pdf.pages[:3]:
#         text = page.extract_text() or ""
#         lines = text.splitlines()
#         if page.extract_table(): structured_hits += 1
#         for line in lines:
#             if cr_dr_pattern.search(line): kotak_hits += 1
#             if bob_pattern.match(line): bob_hits += 1
#             if hdfc_pattern.match(line): hdfc_hits += 1
#
#     if kotak_hits > 2: return "kotak"
#     elif bob_hits > 2: return "bob"
#     elif hdfc_hits > 2: return "hdfc"
#     elif structured_hits >= 2: return "structured"
#     return "unknown"
#
# # ✅ Structured
#
# def extract_structured(pdf):
#     all_dfs = []
#     first_table = pdf.pages[0].extract_table()
#     if not first_table:
#         return pd.DataFrame()
#
#     columns = first_table[0]
#     for page in pdf.pages:
#         table = page.extract_table()
#         if not table:
#             continue
#         for row in table[1:]:
#             while len(row) < len(columns):
#                 row.append("")
#         df = pd.DataFrame(table[1:], columns=columns)
#         all_dfs.append(df)
#
#     try:
#         df = pd.concat(all_dfs, ignore_index=True)
#     except:
#         aligned = []
#         col_set = list(set(col for df in all_dfs for col in df.columns))
#         for df_ in all_dfs:
#             for col in col_set:
#                 if col not in df_.columns:
#                     df_[col] = np.nan
#             aligned.append(df_[col_set])
#         df = pd.concat(aligned, ignore_index=True)
#
#     return df
#
# # ✅ HDFC
#
# def extract_hdfc(pdf):
#     rows = []
#     prev_balance = None
#     for page in pdf.pages:
#         lines = page.extract_text().splitlines()
#         for line in lines:
#             match = re.match(r"(\d{2}[-/]\d{2}[-/]\d{2,4})\s+(.*)", line)
#             if not match:
#                 if rows:
#                     rows[-1]["Description"] += " " + line.strip()
#                 continue
#             date = match.group(1)
#             rest = match.group(2)
#             all_amounts = re.findall(r"[\d,]*\.\d{2}", rest)
#             amounts = [to_float(a) for a in all_amounts[-3:]]
#             desc = re.sub(r"(([\d,]*\.\d{2}\s*){1,3})$", "", rest).strip()
#
#             withdraw = deposit = balance = np.nan
#             if len(amounts) == 3:
#                 withdraw, deposit, balance = amounts
#             elif len(amounts) == 2:
#                 txn, balance = amounts
#                 if prev_balance and balance:
#                     deposit = txn if balance > prev_balance else np.nan
#                     withdraw = txn if balance < prev_balance else np.nan
#                 else:
#                     if any(w in desc.lower() for w in ["credit", "deposit", "salary"]):
#                         deposit = txn
#                     else:
#                         withdraw = txn
#             elif len(amounts) == 1:
#                 balance = amounts[0]
#             prev_balance = balance if not pd.isna(balance) else prev_balance
#
#             rows.append({
#                 "Date": date,
#                 "Description": desc,
#                 "Withdrawals": withdraw,
#                 "Deposits": deposit,
#                 "Balance": balance
#             })
#     return pd.DataFrame(rows)
#
# # ✅ Kotak
#
# def extract_kotak(pdf):
#     rows = []
#     for page in pdf.pages:
#         text = page.extract_text()
#         if not text: continue
#         lines = text.splitlines()
#         i = 0
#         while i < len(lines) - 1:
#             line1 = lines[i].strip()
#             line2 = lines[i + 1].strip()
#             match = re.search(r'(.*?)\s+([\d,]+\.\d{2})\s+(DR|CR)\s+([\d,]+\.\d{2})\s+(DR|CR)', line1)
#             date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line2)
#             if match and date_match:
#                 desc = match.group(1).strip()
#                 amount = to_float(match.group(2))
#                 drcr_amt = match.group(3)
#                 balance = to_float(match.group(4))
#                 date = date_match.group(1)
#                 withdrawals = amount if drcr_amt == "DR" else np.nan
#                 deposits = amount if drcr_amt == "CR" else np.nan
#                 rows.append({
#                     "Date": date,
#                     "Description": desc,
#                     "Withdrawals": withdrawals,
#                     "Deposits": deposits,
#                     "Balance": balance
#                 })
#                 i += 2
#             else:
#                 i += 1
#     return pd.DataFrame(rows)
#
# # ✅ BOB
#
# def extract_bob(pdf):
#     rows = []
#     prev_balance = None
#     date_pattern = re.compile(r'^(\d{2}/\d{2}/\d{4})')
#     for page in pdf.pages:
#         lines = page.extract_text().split("\n")
#         for line in lines:
#             if not date_pattern.match(line): continue
#             date = date_pattern.match(line).group(1)
#             amounts = re.findall(r'([\d,]+\.\d{2})\s*(Cr|Dr|cr|dr)?', line)
#             if len(amounts) < 1: continue
#
#             balance = deposit = withdrawal = np.nan
#             balance_val = to_float(''.join(amounts[-1]))
#             txn_val = to_float(''.join(amounts[-2])) if len(amounts) >= 2 else np.nan
#             txn_flag = amounts[-2][1].lower() if len(amounts) >= 2 else ""
#
#             if txn_flag == "cr":
#                 deposit = txn_val
#             elif txn_flag == "dr":
#                 withdrawal = txn_val
#             else:
#                 if prev_balance is not None and balance_val:
#                     diff = round(balance_val - prev_balance, 2)
#                     if diff > 0: deposit = abs(diff)
#                     elif diff < 0: withdrawal = abs(diff)
#                 else:
#                     withdrawal = txn_val
#             prev_balance = balance_val
#
#             desc = re.sub(r'\d{2}/\d{2}/\d{4}', '', line)
#             desc = re.sub(r'([\d,]+\.\d{2})\s*(Cr|Dr|cr|dr)?', '', desc).strip()
#
#             rows.append({
#                 "Date": date,
#                 "Description": desc,
#                 "Withdrawals": withdrawal,
#                 "Deposits": deposit,
#                 "Balance": balance_val
#             })
#     return pd.DataFrame(rows)
#
# # ✅ OCR fallback
#
# def extract_using_ocr(file):
#     print("⚠️ OCR fallback triggered...")
#     text = ""
#     with tempfile.TemporaryDirectory() as path:
#         images = convert_from_path(file, dpi=300, output_folder=path)
#         for img in images:
#             text += pytesseract.image_to_string(img)
#
#     extracted = []
#     pattern = re.compile(r"(\d{2}[-/]\d{2}[-/]\d{2,4})\s+(.*?)\s+(\d[\d,]+\.\d{2})")
#     for line in text.splitlines():
#         match = pattern.search(line)
#         if match:
#             date, desc, amount = match.groups()
#             extracted.append({
#                 "Date": date.strip(),
#                 "Description": desc.strip(),
#                 "Withdrawals": to_float(amount),
#                 "Deposits": "",
#                 "Balance": ""
#             })
#     return pd.DataFrame(extracted)
#
# # ✅ Django API View
#
# class UploadPDFView(APIView):
#     parser_classes = [MultiPartParser]
#
#     def post(self, request):
#         try:
#             file = request.FILES.get("pdf")
#             keyword = request.data.get("keyword", "").strip().lower()
#             password = request.data.get("password", "").strip()
#
#             if not file:
#                 return Response({"error": "No PDF uploaded."}, status=400)
#
#             try:
#                 try:
#                     pdf = pdfplumber.open(file, password=password or None)
#                     if not pdf.pages or not pdf.pages[0].extract_text():
#                         raise ValueError("PDF text is empty or corrupted")
#                 except Exception:
#                     pdf = None
#                     df = extract_using_ocr(file.temporary_file_path() if hasattr(file, 'temporary_file_path') else file)
#                 else:
#                     format_type = detect_format(pdf)
#                     if format_type == "structured":
#                         df = extract_structured(pdf)
#                     elif format_type == "hdfc":
#                         df = extract_hdfc(pdf)
#                     elif format_type == "kotak":
#                         df = extract_kotak(pdf)
#                     elif format_type == "bob":
#                         df = extract_bob(pdf)
#                     else:
#                         return Response({"error": "Format detection failed."}, status=400)
#
#                 if keyword:
#                     df = df[df.apply(lambda row: any(keyword in str(cell).lower() for cell in row), axis=1)]
#
#                 if df.empty:
#                     return Response({"error": "No data extracted."}, status=400)
#
#                 # Normalize column names
#                 df.columns = [str(c).strip().capitalize() for c in df.columns]
#                 withdrawals_col = next((c for c in df.columns if "withdrawal" in c.lower()), None)
#                 deposits_col = next((c for c in df.columns if "deposit" in c.lower()), None)
#                 balance_col = next((c for c in df.columns if "balance" in c.lower()), None)
#                 date_col = next((c for c in df.columns if "date" in c.lower()), None)
#                 desc_col = next((c for c in df.columns if "desc" in c.lower()), None)
#
#                 for col in [withdrawals_col, deposits_col, balance_col]:
#                     if col:
#                         df[col] = df[col].apply(to_float)
#
#                 if date_col:
#                     df = df[df[date_col].astype(str).str.strip() != "▶ SUMMARY"]
#
#                 summary = {
#                     date_col or "Date": "▶ SUMMARY",
#                     desc_col or "Description": "",
#                     withdrawals_col or "Withdrawals": round(df[withdrawals_col].sum(skipna=True), 2) if withdrawals_col else "",
#                     deposits_col or "Deposits": round(df[deposits_col].sum(skipna=True), 2) if deposits_col else "",
#                     balance_col or "Balance": round(df[balance_col].mean(skipna=True), 2) if balance_col else ""
#                 }
#
#                 df = pd.concat([df, pd.DataFrame([summary])], ignore_index=True)
#                 output = BytesIO()
#                 with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
#                     df.to_excel(writer, index=False)
#                 output.seek(0)
#                 return FileResponse(output, as_attachment=True, filename="converted.xlsx")
#
#             except Exception as e:
#                 return Response({"error": str(e)}, status=500)
#         except Exception as e:
#             print("❗️ SERVER ERROR:", str(e))
#             traceback.print_exc()  # This will print the full error in Render logs
#             return Response({"error": "Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import re
import pdfplumber
import pandas as pd
import numpy as np
import traceback
from io import BytesIO
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework import status
from django.http import FileResponse
from pdf2image import convert_from_path
import pytesseract
import tempfile
import logging
from io import BytesIO
from tempfile import NamedTemporaryFile

# ✅ Utility to convert string to float
def to_float(x):
    try:
        x = str(x).replace(",", "").replace("\u20b9", "").replace("Cr", "").replace("Dr", "").strip()
        if x.startswith("(") and x.endswith(")"): x = "-" + x[1:-1]
        return float(re.sub(r"[^\d\.-]", "", x))
    except:
        return np.nan

# ✅ Format Detection
def detect_format(pdf):
    kotak_hits = 0
    structured_hits = 0
    hdfc_hits = 0
    bob_hits = 0
    cr_dr_pattern = re.compile(r'([\d,]+\.\d{2})\s+(CR|DR)\s+([\d,]+\.\d{2})\s+(CR|DR)')
    bob_pattern = re.compile(r'^(\d{2}/\d{2}/\d{4}).*(Cr|Dr)')
    hdfc_pattern = re.compile(r'\d{2}[-/]\d{2}[-/]\d{2,4}.*\d[\d,]+\.\d{2}.*')

    for page in pdf.pages[:3]:
        text = page.extract_text() or ""
        lines = text.splitlines()
        if page.extract_table(): structured_hits += 1
        for line in lines:
            if cr_dr_pattern.search(line): kotak_hits += 1
            if bob_pattern.match(line): bob_hits += 1
            if hdfc_pattern.match(line): hdfc_hits += 1

    if kotak_hits > 2: return "kotak"
    elif bob_hits > 2: return "bob"
    elif hdfc_hits > 2: return "hdfc"
    elif structured_hits >= 2: return "structured"
    return "unknown"

# ✅ Structured

def extract_structured(pdf):
    all_dfs = []
    first_table = pdf.pages[0].extract_table()
    if not first_table:
        return pd.DataFrame()

    columns = first_table[0]
    for page in pdf.pages:
        table = page.extract_table()
        if not table:
            continue
        for row in table[1:]:
            while len(row) < len(columns):
                row.append("")
        df = pd.DataFrame(table[1:], columns=columns)
        all_dfs.append(df)

    try:
        df = pd.concat(all_dfs, ignore_index=True)
    except:
        aligned = []
        col_set = list(set(col for df in all_dfs for col in df.columns))
        for df_ in all_dfs:
            for col in col_set:
                if col not in df_.columns:
                    df_[col] = np.nan
            aligned.append(df_[col_set])
        df = pd.concat(aligned, ignore_index=True)

    return df

# ✅ HDFC

def extract_hdfc(pdf):
    rows = []
    prev_balance = None
    for page in pdf.pages:
        lines = page.extract_text().splitlines()
        for line in lines:
            match = re.match(r"(\d{2}[-/]\d{2}[-/]\d{2,4})\s+(.*)", line)
            if not match:
                if rows:
                    rows[-1]["Description"] += " " + line.strip()
                continue
            date = match.group(1)
            rest = match.group(2)
            all_amounts = re.findall(r"[\d,]*\.\d{2}", rest)
            amounts = [to_float(a) for a in all_amounts[-3:]]
            desc = re.sub(r"(([\d,]*\.\d{2}\s*){1,3})$", "", rest).strip()

            withdraw = deposit = balance = np.nan
            if len(amounts) == 3:
                withdraw, deposit, balance = amounts
            elif len(amounts) == 2:
                txn, balance = amounts
                if prev_balance and balance:
                    deposit = txn if balance > prev_balance else np.nan
                    withdraw = txn if balance < prev_balance else np.nan
                else:
                    if any(w in desc.lower() for w in ["credit", "deposit", "salary"]):
                        deposit = txn
                    else:
                        withdraw = txn
            elif len(amounts) == 1:
                balance = amounts[0]
            prev_balance = balance if not pd.isna(balance) else prev_balance

            rows.append({
                "Date": date,
                "Description": desc,
                "Withdrawals": withdraw,
                "Deposits": deposit,
                "Balance": balance
            })
    return pd.DataFrame(rows)

# ✅ Kotak

def extract_kotak(pdf):
    rows = []
    for page in pdf.pages:
        text = page.extract_text()
        if not text: continue
        lines = text.splitlines()
        i = 0
        while i < len(lines) - 1:
            line1 = lines[i].strip()
            line2 = lines[i + 1].strip()
            match = re.search(r'(.*?)\s+([\d,]+\.\d{2})\s+(DR|CR)\s+([\d,]+\.\d{2})\s+(DR|CR)', line1)
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line2)
            if match and date_match:
                desc = match.group(1).strip()
                amount = to_float(match.group(2))
                drcr_amt = match.group(3)
                balance = to_float(match.group(4))
                date = date_match.group(1)
                withdrawals = amount if drcr_amt == "DR" else np.nan
                deposits = amount if drcr_amt == "CR" else np.nan
                rows.append({
                    "Date": date,
                    "Description": desc,
                    "Withdrawals": withdrawals,
                    "Deposits": deposits,
                    "Balance": balance
                })
                i += 2
            else:
                i += 1
    return pd.DataFrame(rows)

# ✅ BOB

def extract_bob(pdf):
    rows = []
    prev_balance = None
    date_pattern = re.compile(r'^(\d{2}/\d{2}/\d{4})')
    for page in pdf.pages:
        lines = page.extract_text().split("\n")
        for line in lines:
            if not date_pattern.match(line): continue
            date = date_pattern.match(line).group(1)
            amounts = re.findall(r'([\d,]+\.\d{2})\s*(Cr|Dr|cr|dr)?', line)
            if len(amounts) < 1: continue

            balance = deposit = withdrawal = np.nan
            balance_val = to_float(''.join(amounts[-1]))
            txn_val = to_float(''.join(amounts[-2])) if len(amounts) >= 2 else np.nan
            txn_flag = amounts[-2][1].lower() if len(amounts) >= 2 else ""

            if txn_flag == "cr":
                deposit = txn_val
            elif txn_flag == "dr":
                withdrawal = txn_val
            else:
                if prev_balance is not None and balance_val:
                    diff = round(balance_val - prev_balance, 2)
                    if diff > 0: deposit = abs(diff)
                    elif diff < 0: withdrawal = abs(diff)
                else:
                    withdrawal = txn_val
            prev_balance = balance_val

            desc = re.sub(r'\d{2}/\d{2}/\d{4}', '', line)
            desc = re.sub(r'([\d,]+\.\d{2})\s*(Cr|Dr|cr|dr)?', '', desc).strip()

            rows.append({
                "Date": date,
                "Description": desc,
                "Withdrawals": withdrawal,
                "Deposits": deposit,
                "Balance": balance_val
            })
    return pd.DataFrame(rows)

# ✅ OCR fallback

def extract_using_ocr(file):
    print("⚠️ OCR fallback triggered...")
    text = ""
    with tempfile.TemporaryDirectory() as path:
        images = convert_from_path(file, dpi=300, output_folder=path)
        for img in images:
            text += pytesseract.image_to_string(img)

    extracted = []
    pattern = re.compile(r"(\d{2}[-/]\d{2}[-/]\d{2,4})\s+(.*?)\s+(\d[\d,]+\.\d{2})")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            date, desc, amount = match.groups()
            extracted.append({
                "Date": date.strip(),
                "Description": desc.strip(),
                "Withdrawals": to_float(amount),
                "Deposits": "",
                "Balance": ""
            })
    return pd.DataFrame(extracted)

# ✅ Django API View

logger = logging.getLogger(__name__)
class UploadPDFView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        try:
            logger.info("📥 Received upload request")

            file = request.FILES.get("pdf")
            keyword = request.data.get("keyword", "").strip().lower()
            password = request.data.get("password", "").strip()

            logger.info(f"🔍 keyword: '{keyword}', password: '{password}'")
            logger.info(f"📁 File: {file.name if file else 'No file received'}")

            if not file:
                logger.warning("⚠️ No PDF uploaded in request.")
                return Response({"error": "No PDF uploaded."}, status=400)

            try:
                # Try opening PDF normally
                try:
                    pdf = pdfplumber.open(file, password=password or None)
                    if not pdf.pages or not pdf.pages[0].extract_text():
                        raise ValueError("PDF text is empty or corrupted")
                    logger.info("✅ PDF opened and has text")
                except Exception as e:
                    logger.warning(f"⚠️ Falling back to OCR: {str(e)}")
                    pdf = None
                    if hasattr(file, 'temporary_file_path'):
                        pdf_path = file.temporary_file_path()
                    else:
                        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(file.read())
                            pdf_path = tmp.name

                    df = extract_using_ocr(pdf_path)
                # Choose parser
                if pdf:
                    format_type = detect_format(pdf)
                    logger.info(f"📄 Detected format: {format_type}")
                    if format_type == "structured":
                        df = extract_structured(pdf)
                    elif format_type == "hdfc":
                        df = extract_hdfc(pdf)
                    elif format_type == "kotak":
                        df = extract_kotak(pdf)
                    elif format_type == "bob":
                        df = extract_bob(pdf)
                    else:
                        logger.warning("❌ Unknown format")
                        return Response({"error": "Format detection failed."}, status=400)

                if keyword:
                    logger.info("🔎 Filtering by keyword")
                    df = df[df.apply(lambda row: any(keyword in str(cell).lower() for cell in row), axis=1)]

                if df.empty:
                    logger.warning("⚠️ No data extracted from PDF.")
                    return Response({"error": "No data extracted."}, status=400)

                df.columns = [str(c).strip().capitalize() for c in df.columns]
                withdrawals_col = next((c for c in df.columns if "withdrawal" in c.lower()), None)
                deposits_col = next((c for c in df.columns if "deposit" in c.lower()), None)
                balance_col = next((c for c in df.columns if "balance" in c.lower()), None)
                date_col = next((c for c in df.columns if "date" in c.lower()), None)
                desc_col = next((c for c in df.columns if "desc" in c.lower()), None)

                for col in [withdrawals_col, deposits_col, balance_col]:
                    if col:
                        df[col] = df[col].apply(to_float)

                if date_col:
                    df = df[df[date_col].astype(str).str.strip() != "▶ SUMMARY"]

                summary = {
                    date_col or "Date": "▶ SUMMARY",
                    desc_col or "Description": "",
                    withdrawals_col or "Withdrawals": round(df[withdrawals_col].sum(skipna=True), 2) if withdrawals_col else "",
                    deposits_col or "Deposits": round(df[deposits_col].sum(skipna=True), 2) if deposits_col else "",
                    balance_col or "Balance": round(df[balance_col].mean(skipna=True), 2) if balance_col else ""
                }

                df = pd.concat([df, pd.DataFrame([summary])], ignore_index=True)

                output = BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False)
                output.seek(0)

                logger.info("✅ Successfully created Excel file from PDF")
                return FileResponse(output, as_attachment=True, filename="converted.xlsx")

            except Exception as e:
                logger.error(f"🔥 Processing error: {str(e)}")
                traceback.print_exc()
                return Response({"error": str(e)}, status=500)

        except Exception as e:
            logger.critical(f"❗ SERVER ERROR: {str(e)}")
            traceback.print_exc()
            return Response({"error": "Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
