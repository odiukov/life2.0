"""A synthetic Payoneer statement (same layout as the real one) and a PDF built from it."""

from __future__ import annotations

STATEMENT = """Account Statement
Jane Doe
Account
USD balance
Period
10/01/2026 - 10/31/2026
Issuing Date
11/01/2026
Date
Description
Amount
Currency
Running Balance
01 Oct, 2026
Client payment ACME
4,000.00
USD
4,000.00
03 Oct, 2026
Rent October
-1,200.00
USD
2,800.00
08 Oct, 2026
Pingo Doce 1234
-45.50
USD
2,754.50
bad date
Broken row
-1.00
USD
2,753.50
© 2005-2026 Payoneer Inc. All rights reserved.
10 Oct, 2026
Netflix 9981
-15.99
USD
2,738.51
"""

NOT_A_STATEMENT = "Body fat rate\nViHealth\nWeight 81.4 kg\n"


def pdf_from(text: str = STATEMENT) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((36, 36), text, fontsize=8)
    try:
        return bytes(doc.tobytes())
    finally:
        doc.close()
