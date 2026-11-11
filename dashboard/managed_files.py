"""Immutable, fsynced copies backing versions in the existing shelf catalog.

Only opaque generated IDs name storage. Source policy remains the API's safe
open_file implementation; managed downloads never reopen the original source.
"""
from contextlib import contextmanager
import hashlib
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid

from fastapi import HTTPException


class ManagedFiles:
    def __init__(self, directory, max_file):
        self.directory = Path(directory)
        self.max_file = max_file

    @contextmanager
    def root_fd(self):
        # Refuse linked/non-directory roots, including their ancestors.
        self.directory.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(self.directory.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in self.directory.parts[1:]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def fingerprint(meta):
        return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns,
                meta.st_ctime_ns, meta.st_mode, meta.st_nlink)

    def copy_version(self, refs, opener, retained=None):
        version_id = uuid.uuid4().hex
        try:
            with self.root_fd() as root:
                os.mkdir(version_id, mode=0o700, dir_fd=root)
                folder = os.open(version_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                try:
                    files = []
                    for ref in refs:
                        kept = (retained or {}).get((ref.root, ref.path))
                        if kept:
                            _, content, _ = self.read(kept[0], kept[1])
                        else:
                            with opener(ref) as stream:
                                before = self.fingerprint(os.fstat(stream.fileno()))
                                content = stream.read(self.max_file + 1)
                                after = self.fingerprint(os.fstat(stream.fileno()))
                            if len(content) > self.max_file:
                                raise HTTPException(413, 'File exceeds the 10 MiB delivery limit')
                            if before != after or len(content) != after[2]:
                                raise HTTPException(409, 'File changed while saving; choose it again')
                        file_id = uuid.uuid4().hex
                        fd = os.open(file_id, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=folder)
                        with os.fdopen(fd, 'wb') as output:
                            output.write(content)
                            output.flush()
                            os.fchmod(output.fileno(), 0o400)
                            os.fsync(output.fileno())
                        name = PurePosixPath(ref.path).name
                        files.append({'id': file_id, 'name': name, 'size': len(content),
                                      'sha256': hashlib.sha256(content).hexdigest(),
                                      'media_type': mimetypes.guess_type(name)[0] or 'application/octet-stream'})
                    os.fsync(folder)
                finally:
                    os.close(folder)
                os.fsync(root)
            # Persist the managed root's directory entry as well as its contents.
            parent = os.open(self.directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            return version_id, files
        except BaseException:
            self.discard(version_id)
            raise

    def discard(self, version_id):
        try:
            self.purge(version_id)
        except (OSError, ValueError):
            pass

    def purge(self, version_id):
        """Remove only an opaque managed directory, never follow ancestors/links."""
        if not re.fullmatch(r'[a-f0-9]{32}', version_id):
            raise ValueError('Invalid managed version ID')
        with self.root_fd() as root:
            try:
                shutil.rmtree(version_id, dir_fd=root)
            except FileNotFoundError:
                pass  # Crash after unlink but before queue acknowledgement.
            os.fsync(root)

    def read(self, version_id, item):
        if not re.fullmatch(r'[a-f0-9]{32}', version_id) or not re.fullmatch(r'[a-f0-9]{32}', item['id']):
            raise HTTPException(404, 'Saved file not found')
        try:
            with self.root_fd() as root:
                folder = os.open(version_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                try:
                    fd = os.open(item['id'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
                finally:
                    os.close(folder)
                with os.fdopen(fd, 'rb') as stream:
                    meta = os.fstat(stream.fileno())
                    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > self.max_file:
                        raise HTTPException(409, 'Saved file failed integrity validation')
                    content = stream.read(self.max_file + 1)
            if len(content) != item['size'] or hashlib.sha256(content).hexdigest() != item['sha256']:
                raise HTTPException(409, 'Saved file failed integrity validation')
            return item['name'], content, item['media_type']
        except OSError:
            raise HTTPException(503, 'Saved file storage is unavailable') from None
