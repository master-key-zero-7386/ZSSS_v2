import re

# 貼り付けテキスト（タブ区切り 2列: from<TAB>to）を1行ずつパースする。
# 内部にスペースを含む郵便番号（例: カナダDHLの "A0A 1A0"）を壊さないよう、
# 区切りは必ずタブのみとする（空白全般での分割はしない）。
LINE_RE = re.compile(r'^(.+?)\t+(.+?)$')


def parse_paste(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip("\r\n")
        if not line.strip():
            continue

        m = LINE_RE.match(line)
        if not m:
            continue

        postal_from = normalize_postal(m.group(1))
        postal_to = normalize_postal(m.group(2))

        if not postal_from or not postal_to:
            continue

        pairs.append((postal_from, postal_to))

    return pairs


# カナダ形式（英数字6文字: 例 T1P2G8 / T1P 2G8）は、スペース有無に関わらず
# 「T1P 2G8」の形に統一する。DHLはスペースあり、FedExはスペースなしで貼られる、
# セラセン注文情報はスペースありで表記される、という表記ゆれを吸収するため。
_CA_POSTAL_RE = re.compile(r'^([A-Z]\d[A-Z])(\d[A-Z]\d)$')


def normalize_postal(code: str) -> str:
    raw = (code or "").strip().upper()
    compact = raw.replace(" ", "")

    m = _CA_POSTAL_RE.match(compact)
    if m:
        return f"{m.group(1)} {m.group(2)}"

    return raw


def is_in_range(postal_code: str, postal_from: str, postal_to: str) -> bool:
    code = normalize_postal(postal_code)
    a = normalize_postal(postal_from)
    b = normalize_postal(postal_to)

    if len(a) != len(b) or len(code) != len(a):
        return code == a or code == b

    if a > b:
        a, b = b, a

    return a <= code <= b


# カナダ形式（正規化後 "A1A 1A1"：英字・数字・英字 数字・英字・数字）専用の展開。
# 各桁ごとに本来の文字種（英字26種 or 数字10種）だけを回すことで、
# "T1P 1 0" のようなスペース位置ズレ・存在しない構造の文字列を作らないようにする。
_CA_LOCAL_RE = re.compile(r'^([A-Z])(\d)([A-Z]) (\d)([A-Z])(\d)$')
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
_CA_ALPHABETS = (_LETTERS, _DIGITS, _LETTERS, _DIGITS, _LETTERS, _DIGITS)
_ALNUM_EXPAND_LIMIT = 200_000  # 暴走防止の安全上限


def _ca_expand(a: str, b: str):
    ma, mb = _CA_LOCAL_RE.match(a), _CA_LOCAL_RE.match(b)
    if not ma or not mb:
        return None

    try:
        idx_a = [alphabet.index(ch) for alphabet, ch in zip(_CA_ALPHABETS, ma.groups())]
        idx_b = [alphabet.index(ch) for alphabet, ch in zip(_CA_ALPHABETS, mb.groups())]
    except ValueError:
        return None

    radices = [len(alphabet) for alphabet in _CA_ALPHABETS]

    def to_int(idx):
        value = 0
        for i, r in zip(idx, radices):
            value = value * r + i
        return value

    def from_int(value):
        parts = []
        for r in reversed(radices):
            value, rem = divmod(value, r)
            parts.append(rem)
        parts.reverse()
        return parts

    lo, hi = sorted((to_int(idx_a), to_int(idx_b)))
    if hi - lo + 1 > _ALNUM_EXPAND_LIMIT:
        return None

    codes = []
    for n in range(lo, hi + 1):
        parts = from_int(n)
        chars = [_CA_ALPHABETS[i][parts[i]] for i in range(6)]
        codes.append(f"{chars[0]}{chars[1]}{chars[2]} {chars[3]}{chars[4]}{chars[5]}")
    return codes


# from〜toのレンジを1件ずつ展開する。数字のみのレンジは10進数で展開し、
# カナダ形式は構造を保った桁ごとの展開を行う（実在するかどうかは問わない・ユーザー指示）。
# それ以外（桁数不一致・未対応形式）は、安全側でfrom/toをそのまま返す。
def expand_range(postal_from: str, postal_to: str) -> list[str]:
    a = normalize_postal(postal_from)
    b = normalize_postal(postal_to)

    if not a or not b:
        return [c for c in (a, b) if c]

    if len(a) == len(b) and a.isdigit() and b.isdigit():
        lo, hi = sorted((int(a), int(b)))
        width = len(a)
        return [f"{n:0{width}d}" for n in range(lo, hi + 1)]

    ca_result = _ca_expand(a, b)
    if ca_result is not None:
        return ca_result

    return sorted({a, b})
