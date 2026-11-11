"""Offline, bounded document previews; never open mutable source paths here.

PDF first pages use Poppler's rasterizer (no scripts, attachments or URL loading).
Office previews read only a bounded existing raster thumbnail from OOXML; no
Office converter, document XML, macros or external relationships are executed.
The cache is expendable, content-addressed, profile-local and not catalog state.
"""
from contextlib import contextmanager
from io import BytesIO
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import struct
import zlib
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED, BadZipFile

from fastapi import HTTPException

OFFICE_TYPES = {'.docx': 'word/document.xml', '.pptx': 'ppt/presentation.xml', '.xlsx': 'xl/workbook.xml'}
TYPES = {'.pdf', *OFFICE_TYPES}
MAX_MEMBER = 1024 * 1024
MAX_MEMBERS = 512
MAX_INPUT = 10 * 1024 * 1024
EDGE = 384
MAX_PNG = 512 * 1024
CACHE_ITEMS = 64
CACHE_BYTES = 16 * 1024 * 1024
TIMEOUT = 6
_SLOTS = threading.BoundedSemaphore(2)
_CACHE_NAME = re.compile(r'[a-f0-9]{64}\.png')


def unavailable():
    return HTTPException(415, 'Document preview unavailable; use the file type icon')


def normalize(content):
    # Decode only bounded raster bytes; never SVG/WMF/EMF or arbitrary plugins.
    from PIL import Image
    if not (content.startswith(b'\x89PNG\r\n\x1a\n') or content.startswith(b'\xff\xd8\xff')):
        raise unavailable()
    try:
        with Image.open(BytesIO(content), formats=('PNG', 'JPEG')) as image:
            if image.width * image.height > 4_000_000:
                raise unavailable()
            image.thumbnail((EDGE, EDGE))
            output = BytesIO()
            image.convert('RGB').save(output, format='PNG')
    except Image.DecompressionBombError:
        raise unavailable() from None
    result = output.getvalue()
    if not result or len(result) > MAX_PNG:
        raise unavailable()
    return result


def pdf_page(content, directory):
    renderer, limits = shutil.which('pdftoppm'), shutil.which('prlimit')
    if not renderer or not limits or not content.startswith(b'%PDF-'):
        raise unavailable()
    # Fixed arguments, private input/output, no shell or source path passed to a
    # converter. prlimit applies hard limits before parsing untrusted document data.
    # Unlinked temporary files leave no source copy or abandoned render folder
    # even if the host dies. The child sees only the explicitly passed input FD;
    # PNG stdout is a size-limited regular file, not an unbounded captured pipe.
    with tempfile.TemporaryFile(dir=directory) as source, tempfile.TemporaryFile(dir=directory) as output:
        source.write(content)
        source.flush()
        source.seek(0)
        command = [limits, '--as=536870912', '--cpu=3', '--fsize=1048576', '--nofile=64', '--core=0',
                   '--', renderer, '-f', '1', '-l', '1', '-singlefile', '-scale-to', str(EDGE),
                   '-hide-annotations', '-png', '-q', f'/proc/self/fd/{source.fileno()}']
        subprocess.run(command, check=True, stdin=subprocess.DEVNULL, stdout=output,
                       stderr=subprocess.DEVNULL, timeout=TIMEOUT, cwd=directory,
                       pass_fds=(source.fileno(),),
                       env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'TMPDIR': str(directory), 'LANG': 'C'})
        output.seek(0)
        result = output.read(MAX_PNG + 1)
        if len(result) > MAX_PNG:
            raise unavailable()
        return normalize(result)


def office_thumbnail(suffix, content):
    # Check EOCD BEFORE ZipFile materializes a potentially huge central directory.
    # ZIP64, spanning, excessive members and ambiguous directory counts fail closed.
    index = content.rfind(b'PK\x05\x06', max(0, len(content)-65557))
    if index < 0 or len(content)-index < 22:
        raise unavailable()
    _, disk, start_disk, local_count, count, size, offset, comment = struct.unpack_from('<4s4H2LH', content, index)
    if (disk or start_disk or local_count != count or not 1 <= count <= MAX_MEMBERS or
            size > 512 * 1024 or offset + size != index or index + 22 + comment != len(content)):
        raise unavailable()
    with ZipFile(BytesIO(content)) as package:
        members = package.infolist()
        if len(members) != count or len({member.filename for member in members}) != count:
            raise unavailable()
        if OFFICE_TYPES[suffix] not in package.namelist():
            raise unavailable()
        for name in ('docProps/thumbnail.png', 'docProps/thumbnail.jpeg', 'docProps/thumbnail.jpg'):
            try:
                member = package.getinfo(name)
            except KeyError:
                continue
            mode = member.external_attr >> 16
            if (member.flag_bits & 1 or member.compress_type not in (ZIP_STORED, ZIP_DEFLATED) or
                    stat.S_ISLNK(mode) or member.file_size > MAX_MEMBER or
                    member.file_size > max(1, member.compress_size) * 100):
                raise unavailable()
            # Read this one fixed raster member into memory; NEVER extract paths,
            # XML, macros, relationships or other attachments, nor fetch any URL.
            with package.open(member) as stream:
                image = stream.read(MAX_MEMBER + 1)
            if len(image) > MAX_MEMBER:
                raise unavailable()
            return normalize(image)
    raise unavailable()


@contextmanager
def cache_root(directory):
    import fcntl
    fd = os.open(directory.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in directory.parts[1:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        try:
            os.mkdir(directory.name, mode=0o700, dir_fd=fd)
        except FileExistsError:
            pass
        nxt = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        os.close(fd)
        fd = nxt
        # An advisory lock on the actual directory needs no mutable lock file.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd
    finally:
        os.close(fd)


def read_cache(root, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > MAX_PNG:
            raise unavailable()
        content = stream.read(MAX_PNG + 1)
    if len(content) > MAX_PNG:
        raise unavailable()
    try:
        normalize(content)
    except Exception:
        os.unlink(name, dir_fd=root)
        return None
    return content


def prune(root, incoming):
    entries = []
    # Never follow/delete non-cache paths. Stop on an unexpectedly large folder.
    with os.scandir(root) as scan:
        for count, entry in enumerate(scan):
            if count >= 256:
                raise unavailable()
            if _CACHE_NAME.fullmatch(entry.name):
                meta = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
                    raise unavailable()
                entries.append((meta.st_mtime_ns, entry.name, meta.st_size))
    entries.sort()
    total = sum(item[2] for item in entries)
    while entries and (len(entries) >= CACHE_ITEMS or total + incoming > CACHE_BYTES):
        _, name, size = entries.pop(0)
        os.unlink(name, dir_fd=root)
        total -= size


def thumbnail(home, name, content):
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES or len(content) > MAX_INPUT:
        raise unavailable()
    if not _SLOTS.acquire(blocking=False):
        raise unavailable()
    try:
        directory = home/'plugin-data/delivery-shelf/thumbnail-cache'
        key = hashlib.sha256(b'shelf-preview-v1\0'+suffix.encode()+b'\0'+content).hexdigest()+'.png'
        with cache_root(directory) as root:
            cached = read_cache(root, key)
            if cached is not None:
                return cached
            rendered = pdf_page(content, directory) if suffix == '.pdf' else office_thumbnail(suffix, content)
            prune(root, len(rendered))
            fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(rendered)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                os.unlink(key, dir_fd=root)
                raise
            return rendered
    except (OSError, ValueError, ImportError, subprocess.SubprocessError, BadZipFile, RuntimeError, zlib.error):
        raise unavailable() from None
    finally:
        _SLOTS.release()
