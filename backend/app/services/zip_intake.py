"""Unpack the two upload ZIPs and work out what's inside them.

Template ZIP: a flat-ish archive of the blank exam's page images.
Students ZIP: the semester tree the teacher already keeps on disk, e.g.

    HKI2025_2026/Made_1/Bai_lam/HS_10/page1.png

Nothing here assumes that exact depth — the student folder is simply the
directory an image sits in, and the exam-code folder is recognised by name
(`Made_1`, `Ma_de_2`, `Mã đề 3`, …). That keeps the intake working for a
teacher whose tree has one more or one fewer wrapper directory.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

# "Made_1", "ma_de_2", "Mã đề 3" — the trailing token is the exam code.
_MA_DE_RE = re.compile(r"^(?:made|ma[_\-\s]?de)[_\-\s]?(.+)$", re.IGNORECASE)
_BAI_LAM_RE = re.compile(r"^bai[_\-\s]?lam$", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    """Fold Vietnamese diacritics so a label can be matched case/accent-blind.

    `đ`/`Đ` (U+0111/U+0110) must be handled separately: unlike every other
    Vietnamese letter they are single codepoints with a stroke, not a base
    letter plus a combining mark, so NFD leaves them untouched and "MÃ ĐỀ"
    folds to "MA ĐE" — which no ASCII pattern for "ma de" can match.
    """
    folded = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFD", folded) if not unicodedata.combining(c)
    )


def _natural_key(name: str) -> tuple:
    """Sort page_2 before page_10 (plain lexicographic does the opposite)."""
    return tuple(
        int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)
    )


def _decoded_name(info: zipfile.ZipInfo) -> str:
    """Recover the real entry name from a ZIP written without the UTF-8 flag.

    Windows' built-in "Send to > Compressed folder" stores names in the OEM
    codepage and leaves flag bit 0x800 clear; `zipfile` then hands them back
    decoded as cp437, which mangles Vietnamese folder names like "Mã đề 1".
    Round-tripping through cp437 recovers the original bytes to try UTF-8 on.
    """
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def extract_zip(zip_path: Path, dest: Path) -> list[Path]:
    """Extract image entries only, flatly rejecting path traversal. Returns files written."""
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = _decoded_name(info)
            rel = PurePosixPath(name.replace("\\", "/"))
            if rel.is_absolute() or any(part == ".." for part in rel.parts):
                continue  # zip-slip
            if rel.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            # macOS archives carry a parallel __MACOSX/._name resource fork.
            if any(part == "__MACOSX" for part in rel.parts) or rel.name.startswith("._"):
                continue

            target = dest / Path(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as out:
                out.write(src.read())
            written.append(target)

    return written


@dataclass
class StudentEntry:
    hs_key: str
    folder: str
    pages: list[Path] = field(default_factory=list)


@dataclass
class MaDeEntry:
    ma_de: str
    label: str
    students: list[StudentEntry] = field(default_factory=list)


def list_template_pages(root: Path) -> list[Path]:
    pages = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    return sorted(pages, key=lambda p: _natural_key(str(p.relative_to(root))))


# Sentinel key of `group_template_pages`: pages that belong to no particular
# exam code and therefore serve every one of them.
SHARED_TEMPLATE = "*"


def group_template_pages(root: Path) -> dict[str, list[Path]]:
    """Group the blank exam's pages by exam code, mirroring group_students().

    A template archive laid out `Made_1/*.png`, `Made_2/*.png` grades several
    codes in one session, each against its own pages. An archive with no such
    folders returns everything under `SHARED_TEMPLATE`: exam codes usually
    differ in their answers, not their layout, so one set of pages covering
    every code is the common case and should not need extra folders.
    """
    pages = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]

    groups: dict[str, list[Path]] = {}
    for page in pages:
        parts = page.relative_to(root).parts
        ma_de = _ma_de_of(parts[:-1]) or SHARED_TEMPLATE
        groups.setdefault(ma_de, []).append(page)

    for found in groups.values():
        found.sort(key=lambda p: _natural_key(str(p.relative_to(root))))
    return groups


def template_pages_for(grouped: dict[str, list[Path]], ma_de: str) -> list[Path]:
    """Pages for one exam code, falling back to the shared set."""
    return grouped.get(ma_de) or grouped.get(SHARED_TEMPLATE) or []


def _ma_de_of(relative_parts: tuple[str, ...]) -> str | None:
    """Find the exam code in a path, as the code itself — not the folder name.

    `Made_1/` yields `"1"`, not `"Made_1"`. The code is now the join key
    against the barem library, where rubrics are written `"ma_de": "1"`, so
    returning the decorated folder name would match nothing and every run
    would fail with "kho barem không có mã đề Made_1". Folders that carry no
    recognisable prefix (the `…/<something>/Bai_lam/…` shape) are returned
    as-is, since there is nothing to strip.
    """
    for index, part in enumerate(relative_parts):
        match = _MA_DE_RE.match(_strip_accents(part).strip())
        if match:
            return match.group(1).strip()
        # "…/<ma_de>/Bai_lam/<hs>/…" — accept the folder just above Bai_lam
        # even when it isn't named in the Made_N style.
        if _BAI_LAM_RE.match(_strip_accents(part).strip()) and index > 0:
            parent = relative_parts[index - 1]
            parent_match = _MA_DE_RE.match(_strip_accents(parent).strip())
            return parent_match.group(1).strip() if parent_match else parent
    return None


def group_students(root: Path) -> list[MaDeEntry]:
    """Group every extracted student image by exam code, then by student folder."""
    images = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]

    groups: dict[str, MaDeEntry] = {}
    for image in images:
        parts = image.relative_to(root).parts
        # The student folder is whichever directory the image sits in; when the
        # archive is flat (images straight at the root) fall back to the
        # filename stem so each page still becomes its own student.
        student_folder = parts[-2] if len(parts) >= 2 else image.stem
        ma_de = _ma_de_of(parts[:-1]) or "1"

        group = groups.setdefault(ma_de, MaDeEntry(ma_de=ma_de, label=ma_de))
        student = next((s for s in group.students if s.folder == student_folder), None)
        if student is None:
            student = StudentEntry(hs_key=student_folder, folder=student_folder)
            group.students.append(student)
        student.pages.append(image)

    for group in groups.values():
        group.students.sort(key=lambda s: _natural_key(s.folder))
        for student in group.students:
            student.pages.sort(key=lambda p: _natural_key(p.name))

    return sorted(groups.values(), key=lambda g: _natural_key(g.ma_de))


def normalise_hs_key(folder: str, index: int) -> str:
    """Turn a student folder name into pipeline.py's `HS_<n>` convention.

    `convert_results_to_samples()` keys students by `HS_<number>` and
    `summarize_by_student()` sorts on `int(hs.split("_")[-1])`, so a folder
    named "HS_10" must stay HS_10 — and one named "Nguyen Van A" still needs
    *some* number, which is where the positional index comes in.
    """
    digits = re.findall(r"\d+", folder)
    if digits:
        return f"HS_{int(digits[-1])}"
    return f"HS_{index}"
