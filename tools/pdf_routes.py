from flask import Blueprint, request, send_file, Response
from io import BytesIO
import zipfile
from PyPDF2 import PdfReader, PdfWriter  # pip install PyPDF2

pdf_bp = Blueprint("pdf_bp", __name__)

@pdf_bp.route("/split_chunks", methods=["POST"])
def split_chunks():
    f = request.files.get("file")
    if not f:
        return Response("file is required", 400)

    try:
        per = int(request.form.get("per", "60"))
        if per <= 0:
            per = 60
    except ValueError:
        per = 60

    data = f.read()
    reader = PdfReader(BytesIO(data))
    total = len(reader.pages)

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        start = 0
        part = 1
        while start < total:
            end = min(start + per, total)
            writer = PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])
            out_buf = BytesIO()
            writer.write(out_buf)
            writer.close()
            out_buf.seek(0)
            fname = f"split_{part:03d}_{start+1:03d}-{end:03d}.pdf"
            zf.writestr(fname, out_buf.getvalue())
            start = end
            part += 1

    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True, download_name="pdf_splits.zip")

