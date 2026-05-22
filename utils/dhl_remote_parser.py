import re


RANGE_RE = re.compile(r'(\d{3,10})\s*(?:[-–—]\s*(\d{3,10}))?')

def expand_postal_tokens(text: str) -> list[str]:
    """
    DHLの遠隔地郵便番号テキスト（PDFコピペ）から
    単票と範囲を展開して1列リストにする。
    ・先頭ゼロ保持
    ・重複排除
    ・昇順（桁→数値）
    """
    norm = (text or "").replace('–', '-').replace('—', '-')
    codes: set[str] = set()

    for m in RANGE_RE.finditer(norm):
        start, end = m.group(1), m.group(2)
        if not end:
            codes.add(start)
            continue

        # 桁不一致レンジは安全側で単票扱い
        if len(start) != len(end):
            codes.add(start)
            codes.add(end)
            continue

        a, b = int(start), int(end)
        if a > b:
            a, b = b, a

        width = len(start)
        for n in range(a, b + 1):
            codes.add(f"{n:0{width}d}")

    return sorted(codes, key=lambda s: (len(s), int(s)))

