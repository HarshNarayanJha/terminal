import datetime
import io
import sys
import urllib.request
import zipfile
from ctypes import *
from enum import Enum
from xml.etree import ElementTree


class UCPTrieType(Enum):
    UCPTRIE_TYPE_ANY = -1,
    UCPTRIE_TYPE_FAST = 0
    UCPTRIE_TYPE_SMALL = 1


class UCPTrieValueWidth(Enum):
    UCPTRIE_VALUE_BITS_ANY = -1,
    UCPTRIE_VALUE_BITS_16 = 0
    UCPTRIE_VALUE_BITS_32 = 1
    UCPTRIE_VALUE_BITS_8 = 2


U_MAX_VERSION_LENGTH = 4
U_MAX_VERSION_STRING_LENGTH = 20

icu = cdll.icu

# U_CAPI const char * U_EXPORT2
# u_errorName(UErrorCode code);
icu.u_errorName.restype = c_char_p
icu.u_errorName.argtypes = [c_int]


def check_error(error: c_int):
    if error.value > 0:
        name = icu.u_errorName(error)
        raise RuntimeError(f"failed with {name.decode()} ({error.value})")


# U_CAPI void U_EXPORT2
# u_getVersion(UVersionInfo versionArray);
icu.u_getVersion.restype = None
icu.u_getVersion.argtypes = [c_void_p]
# U_CAPI void U_EXPORT2
# u_versionToString(const UVersionInfo versionArray, char *versionString);
icu.u_versionToString.restype = None
icu.u_versionToString.argtypes = [c_void_p, c_char_p]


def u_getVersion():
    info = (c_uint8 * U_MAX_VERSION_LENGTH)()
    icu.u_getVersion(info)
    str = (c_char * U_MAX_VERSION_STRING_LENGTH)()
    icu.u_versionToString(info, str)
    return str.value.decode()


# U_CAPI UMutableCPTrie * U_EXPORT2
# umutablecptrie_open(uint32_t initialValue, uint32_t errorValue, UErrorCode *pErrorCode);
icu.umutablecptrie_open.restype = c_void_p
icu.umutablecptrie_open.argtypes = [c_uint32, c_uint32, c_void_p]


def umutablecptrie_open(initial_value: int, error_value: int) -> c_void_p:
    error = c_int()
    trie = icu.umutablecptrie_open(initial_value, error_value, byref(error))
    check_error(error)
    return trie


# U_CAPI void U_EXPORT2
# umutablecptrie_set(UMutableCPTrie *trie, UChar32 c, uint32_t value, UErrorCode *pErrorCode);
icu.umutablecptrie_set.restype = None
icu.umutablecptrie_set.argtypes = [c_void_p, c_uint32, c_uint32, c_void_p]


def umutablecptrie_set(mutable_trie: c_void_p, c: int, value: int):
    error = c_int()
    icu.umutablecptrie_set(mutable_trie, c, value, byref(error))
    check_error(error)


# U_CAPI void U_EXPORT2
# umutablecptrie_setRange(UMutableCPTrie *trie, UChar32 start, UChar32 end, uint32_t value, UErrorCode *pErrorCode);
icu.umutablecptrie_setRange.restype = None
icu.umutablecptrie_setRange.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_void_p]


def umutablecptrie_setRange(mutable_trie: c_void_p, start: int, end: int, value: int):
    error = c_int()
    icu.umutablecptrie_setRange(mutable_trie, start, end, value, byref(error))
    check_error(error)


# U_CAPI UCPTrie * U_EXPORT2
# umutablecptrie_buildImmutable(UMutableCPTrie *trie, UCPTrieType type, UCPTrieValueWidth valueWidth, UErrorCode *pErrorCode);
icu.umutablecptrie_buildImmutable.restype = c_void_p
icu.umutablecptrie_buildImmutable.argtypes = [c_void_p, c_int, c_int, c_void_p]


def umutablecptrie_buildImmutable(mutable_trie: c_void_p, typ: UCPTrieType, width: UCPTrieValueWidth) -> c_void_p:
    error = c_int()
    trie = icu.umutablecptrie_buildImmutable(mutable_trie, typ.value, width.value, byref(error))
    check_error(error)
    return trie


# U_CAPI int32_t U_EXPORT2
# ucptrie_toBinary(const UCPTrie *trie, void *data, int32_t capacity, UErrorCode *pErrorCode);
icu.ucptrie_toBinary.restype = c_int32
icu.ucptrie_toBinary.argtypes = [c_void_p, c_void_p, c_int32, c_void_p]


def ucptrie_toBinary(trie: c_void_p) -> Array[c_ubyte]:
    error = c_int()
    expected_size = icu.ucptrie_toBinary(trie, c_void_p(), 0, byref(error))

    data = (c_ubyte * expected_size)()
    error = c_int()
    actual_size = icu.ucptrie_toBinary(trie, data, expected_size, byref(error))
    check_error(error)

    if actual_size != expected_size:
        raise RuntimeError("apparently ucptrie_toBinary(nullptr, 0) only returns an estimate -> fix me")

    return data


class ClusterBreak(Enum):
    OTHER = 0
    CONTROL = 1
    EXTEND = 2
    PREPEND = 3
    ZERO_WIDTH_JOINER = 4
    REGIONAL_INDICATOR = 5
    HANGUL_L = 6
    HANGUL_V = 7
    HANGUL_T = 8
    HANGUL_LV = 9
    HANGUL_LVT = 10
    CONJUNCT_LINKER = 11
    EXTENDED_PICTOGRAPHIC = 12


class CharacterWidth(Enum):
    ZeroWidth = 0
    Narrow = 1
    Wide = 2
    Ambiguous = 3


CLUSTER_BREAK_SHIFT = 0
CLUSTER_BREAK_MASK = 15

CHARACTER_WIDTH_SHIFT = 6
CHARACTER_WIDTH_MASK = 3


def build_trie_value(cb: ClusterBreak, width: CharacterWidth) -> int:
    assert cb.value <= CLUSTER_BREAK_MASK
    assert width.value <= CHARACTER_WIDTH_MASK
    return cb.value << CLUSTER_BREAK_SHIFT | width.value << CHARACTER_WIDTH_SHIFT


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    match len(sys.argv):
        case 1:
            ucd_url = "https://www.unicode.org/Public/UCD/latest/ucdxml/ucd.nounihan.grouped.zip"
            with urllib.request.urlopen(ucd_url) as r:
                with zipfile.ZipFile(io.BytesIO(r.read())) as z:
                    with z.open("ucd.nounihan.grouped.xml") as f:
                        source = io.BytesIO(f.read())
        case 2:
            source = sys.argv[1]
        case _:
            print("CodepointWidthDetector_triegen.py <path to ucd.nounihan.grouped.xml> <path to unicode_width_overrides.xml>")
            exit(1)

    root = ElementTree.parse(source).getroot()
    ns = {"ns": "http://www.unicode.org/ns/2003/ucd/1.0"}
    initial_value = build_trie_value(ClusterBreak.OTHER, CharacterWidth.Narrow)
    error_value = build_trie_value(ClusterBreak.OTHER, CharacterWidth.Ambiguous)
    mutable_trie = umutablecptrie_open(initial_value, error_value)

    for group in root.findall("./ns:repertoire/ns:group", ns):
        group_gc = group.get("gc")  # general category
        group_gcb = group.get("GCB")  # grapheme cluster break
        group_incb = group.get("InCB")  # indic conjunct break
        group_emoji = group.get("Emoji")  # emoji
        group_epres = group.get("EPres")  # emoji presentation
        group_extpict = group.get("ExtPict")  # extended pictographic
        group_ea = group.get("ea")  # east-asian (width)

        for char in group:
            char_gc = char.get("gc") or group_gc
            char_gcb = char.get("GCB") or group_gcb
            char_incb = char.get("InCB") or group_incb
            char_emoji = char.get("Emoji") or group_emoji
            char_epres = char.get("EPres") or group_epres
            char_extpict = char.get("ExtPict") or group_extpict
            char_ea = char.get("ea") or group_ea
            cb = ClusterBreak.OTHER
            width = CharacterWidth.Narrow
            cp = char.get("cp")  # codepoint

            match char_gcb:
                case "XX":  # Anything else
                    cb = ClusterBreak.OTHER
                case "CR" | "LF" | "CN":  # Carriage Return, Line Feed, Control
                    # We ignore GB3 which demands that CR × LF do not break apart, because
                    # a) these control characters won't normally reach our text storage
                    # b) otherwise we're in a raw write mode and historically conhost stores them in separate cells
                    cb = ClusterBreak.CONTROL
                case "EX" | "SM":  # Extend, SpacingMark
                    cb = ClusterBreak.EXTEND
                case "PP":  # Prepend
                    cb = ClusterBreak.PREPEND
                case "ZWJ":  # Zero Width Joiner
                    cb = ClusterBreak.ZERO_WIDTH_JOINER
                case "RI":  # Regional Indicator
                    cb = ClusterBreak.REGIONAL_INDICATOR
                case "L":  # Hangul Syllable Type L
                    cb = ClusterBreak.HANGUL_L
                case "V":  # Hangul Syllable Type V
                    cb = ClusterBreak.HANGUL_V
                case "T":  # Hangul Syllable Type T
                    cb = ClusterBreak.HANGUL_T
                case "LV":  # Hangul Syllable Type LV
                    cb = ClusterBreak.HANGUL_LV
                case "LVT":  # Hangul Syllable Type LVT
                    cb = ClusterBreak.HANGUL_LVT
                case _:
                    raise RuntimeError(f"unrecognized GCB: {char_gcb}")

            if char_extpict == "Y":
                # Currently every single Extended_Pictographic codepoint happens to be GCB=XX.
                # This is fantastic for us because it means we can stuff it into the ClusterBreak enum
                # and treat it as an alias of EXTEND, but with the special GB11 properties.
                assert cb == ClusterBreak.OTHER
                cb = ClusterBreak.EXTENDED_PICTOGRAPHIC

            if char_incb == "Linker":
                # Similarly here, we can treat it as an alias for EXTEND, but with the GB9c properties.
                assert cb == ClusterBreak.EXTEND
                cb = ClusterBreak.CONJUNCT_LINKER

            if char_gc.startswith("M"):
                # Mc: Mark, spacing combining
                # Me: Mark, enclosing
                # Mn: Mark, non-spacing
                width = CharacterWidth.ZeroWidth
            elif char_emoji == "Y" and char_epres == "Y":
                width = CharacterWidth.Wide
            else:
                match char_ea:
                    case "N" | "Na" | "H":  # neutral, narrow, half-width
                        width = CharacterWidth.Narrow
                    case "F" | "W":  # full-width, wide
                        width = CharacterWidth.Wide
                    case "A":  # ambiguous
                        width = CharacterWidth.Ambiguous
                    case _:
                        raise RuntimeError(f"unrecognized ea: {char_ea}")

            value = build_trie_value(cb, width)
            if value == initial_value:
                continue

            cp = char.get("cp")  # codepoint
            if cp is not None:
                cp = int(cp, 16)
                umutablecptrie_set(mutable_trie, cp, value)
            else:
                cp_first = int(char.get("first-cp"), 16)
                cp_last = int(char.get("last-cp"), 16)
                umutablecptrie_setRange(mutable_trie, cp_first, cp_last, value)

    # For the following ranges to be narrow, because we're a terminal:
    # box-drawing and block elements require 1-cell alignment
    umutablecptrie_setRange(mutable_trie, 0x2500, 0x259F, 1)
    # hexagrams are historically narrow
    umutablecptrie_setRange(mutable_trie, 0x4DC0, 0x4DFF, 1)
    # narrow combining ligatures (split into left/right halves, which take 2 columns together)
    umutablecptrie_setRange(mutable_trie, 0xFE20, 0xFE2F, 1)

    trie_type = UCPTrieType.UCPTRIE_TYPE_FAST
    trie_width = UCPTrieValueWidth.UCPTRIE_VALUE_BITS_8
    trie = umutablecptrie_buildImmutable(mutable_trie, trie_type, trie_width)
    data = ucptrie_toBinary(trie)

    timestamp = datetime.datetime.utcnow().isoformat(timespec='seconds')
    ucd_version = root.find("./ns:description", ns).text
    icu_version = u_getVersion()
    # This generates a C string literal because on contemporary IDEs
    # and compilers it lags less and compiles faster respectively.
    string = ''.join('\\x{:02x}'.format(c) for c in data)

    print("// Generated by CodepointWidthDetector_triegen.py")
    print(f"// on {timestamp}Z from {ucd_version}")
    print(f"// with ICU {icu_version}, {trie_type.name}, {trie_width.name}")
    print(f"// {len(data)} bytes")
    print("// clang-format off")
    print("enum ClusterBreak {")
    for kv in ClusterBreak:
        print(f"    CB_{kv.name} = {kv.value},")
    print(f"    CB_COUNT = {len(ClusterBreak)},")
    print("};")
    print(f"#define INTO_CLUSTER_BREAK(x) (ClusterBreak)((x >> {CLUSTER_BREAK_SHIFT}) & {CLUSTER_BREAK_MASK})")
    print(f"#define INTO_CHARACTER_WIDTH(x) ((x >> {CHARACTER_WIDTH_SHIFT}) & {CHARACTER_WIDTH_MASK})")
    print("static constexpr uint8_t s_ucpTrieData[] =")
    for chunk in chunked(string, 256):
        print(f"    \"{chunk}\"")
    print(";")
    print("// clang-format on")


if __name__ == '__main__':
    main()
