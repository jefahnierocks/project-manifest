"""Origin-only candidate assembly; no approval, install, tag or publication."""

import argparse
import ctypes
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

ROOT = Path(__file__).absolute().parent.parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / "bootstrap"), str(ROOT / "src")]
import release_verifier as binding
from project_manifest import acquire as acquisition


@dataclass(frozen=True)
class AssemblyResult:
    exit_code: int
    code: str
    source_revision: str | None = None
    tree_oid: str | None = None
    table_sha256: str | None = None
    bundle_name: str | None = None

    def diagnostics(self):
        return {
            "scope": "origin-candidate-bundle-assembly", "exit_code": self.exit_code,
            "code": self.code, "source_revision": self.source_revision,
            "tree_oid": self.tree_oid, "table_sha256": self.table_sha256,
            "bundle_name": self.bundle_name, "release_approval": "not_checked",
            "complete_v1_validity": "not_checked",
        }


class Refusal(Exception):
    def __init__(self, code, exit_code=1):
        self.code, self.exit_code = code, exit_code


def require(condition, code):
    if not condition:
        raise Refusal(code)


def _output_directory_identity(info):
    # Own file/directory creation changes size and timestamps, not this identity.
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


def _close_owned_fds(descriptors):
    """Attempt each transferred descriptor once; never expose raw close errors."""
    failed = False
    for fd in dict.fromkeys(descriptors):
        try:
            os.close(fd)
        except OSError:
            failed = True
    return failed


def _close_owned_store(store):
    # Transfer this owned instance's descriptors before attempting any close.
    descriptors, store.fds = list(reversed(store.fds)), []
    return _close_owned_fds(descriptors)


def _regular_modes(entries):
    leaves = {}
    for entry in entries:
        if entry.kind == "directory":
            continue
        require(entry.kind == "file", "SOURCE_FILE_TYPE")
        leaves[entry.path] = entry.executable
    return leaves


def _ignore_projection(source, root):
    for name, data in source.items():
        if name.rsplit("/", 1)[-1] == ".gitignore":
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def _namespace_clean(store, view, projection, source):
    expected = set(source)
    directories = {"/".join(name.split("/")[:i]) for name in source
                   for i in range(1, len(name.split("/")))}
    def ignored(name, directory):
        value = name + ("/" if directory else "")
        raw = value.encode("utf-8", "surrogateescape") + b"\0"
        observed = view.run(["--no-literal-pathspecs", "-C", str(projection),
                             "--work-tree=" + str(projection), "check-ignore",
                             "--no-index", "-z", "--stdin"], data=raw, optional=True)
        return observed == raw
    def walk(fd, prefix=""):
        for name in acquisition._names(fd, store.budget):
            if not prefix and name == ".git":
                continue
            path = prefix + name
            acquisition._parts(path)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if path in expected:
                continue
            if path not in directories:
                require(ignored(path, stat.S_ISDIR(info.st_mode)), "SOURCE_UNTRACKED")
                continue
            require(stat.S_ISDIR(info.st_mode), "SOURCE_DIRTY")
            child = acquisition._open_at(fd, [name], directory=True)
            try:
                walk(child, path + "/")
            finally:
                os.close(child)
    walk(store.root_fd)


def _literal_clean(store, source, modes):
    for name, data in source.items():
        parts = acquisition._parts(name)
        parent = acquisition._open_at(store.root_fd, parts[:-1], directory=True) if len(parts) > 1 else os.dup(store.root_fd)
        try:
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode), "SOURCE_FILE_TYPE")
            require(bool(info.st_mode & 0o111) == modes[name], "SOURCE_DIRTY")
        finally:
            os.close(parent)
        require(store.read(store.root_fd, parts, binding.MAX_FILE_BYTES) == data, "SOURCE_DIRTY")


def _capture(store, view, expected_revision, projection):
    actual = view.resolve("HEAD")
    require(actual.decode() == expected_revision, "SOURCE_REVISION")
    require(view.resolve(expected_revision) == actual, "SOURCE_REVISION")
    commit = view.raw(b"commit", actual, acquisition.MAX_METADATA)
    first = commit.split(b"\n", 1)[0]
    require(first.startswith(b"tree ") and acquisition.OID.fullmatch(first[5:]), "SOURCE_COMMIT")
    tree_oid = first[5:]
    view.raw(b"tree", tree_oid, acquisition.MAX_METADATA)
    entries, objects = acquisition._tree(view.run(
        ["ls-tree", "-r", "-t", "-z", "--full-tree", tree_oid.decode()]), store.budget)
    view.verify_trees([tree_oid] + [objects[e.path] for e in entries if e.kind == "directory"])
    indexed, index_objects = acquisition._index(
        view.run(["ls-files", "--stage", "--debug", "-z"]), store.budget)
    modes = _regular_modes(entries)
    require(_regular_modes(indexed) == modes, "SOURCE_INDEX")
    require(index_objects == {name: objects[name] for name in modes}, "SOURCE_INDEX")
    require(set(binding.PAYLOAD_FILES) <= set(modes), "SOURCE_PAYLOAD")
    source = {}
    total = 0
    for name in sorted(modes):
        store.budget.check()
        source[name] = view.raw(b"blob", objects[name], binding.MAX_FILE_BYTES)
        total += len(source[name])
        if total > acquisition.MAX_WORKING_BYTES:
            raise Refusal("SOURCE_BOUND", 2)
    _ignore_projection(source, projection)
    _literal_clean(store, source, modes)
    _namespace_clean(store, view, projection, source)
    store.recheck()
    payload = {name: source[name] for name in binding.PAYLOAD_FILES}
    require(sum(len(data) for data in payload.values()) <= binding.MAX_TOTAL_BYTES, "PAYLOAD_BOUND")
    return actual.decode(), tree_oid.decode(), source, modes, payload


def _write_new(root_fd, parts, data):
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current)
            except FileExistsError:
                pass
            child = acquisition._open_at(current, [part], directory=True)
            os.close(current)
            current = child
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=current)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(current)


def _finalize_noreplace(container_fd):
    """Atomic local directory finalization; never replace a competing destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        rename = libc.renameatx_np
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        code = rename(container_fd, b"staging", container_fd, b"bundle", 4)  # RENAME_EXCL
    elif hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        code = rename(container_fd, b"staging", container_fd, b"bundle", 1)  # RENAME_NOREPLACE
    else:
        raise Refusal("FINALIZATION_UNAVAILABLE", 2)
    if code:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise Refusal("OUTPUT_COLLISION")
        raise Refusal("FINALIZATION_UNAVAILABLE", 2)


def assemble_candidate(source_root, *, expected_revision, output_parent, common_dir=None):
    """Capture the clean current commit; finalize only an unapproved local candidate."""
    if (type(expected_revision) is not str
            or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_revision) is None):
        return AssemblyResult(2, "REVISION_INPUT")
    store = None
    parent_fd = container_fd = None
    container = None
    token = None
    finalized = False
    result = warning_result = None
    try:
        if any(os.environ.get(name) for name in acquisition.BAD_ENV):
            raise Refusal("INHERITED_GIT_CONTEXT", 2)
        budget = acquisition.Budget()
        store = acquisition.FrozenStore(source_root, common_dir, budget, include_index=True)
        require(not store.bare, "SOURCE_WORKTREE")
        parent_path = os.fspath(output_parent)
        require(type(parent_path) is str and parent_path in
                (os.path.join(store.root_path, "build"), os.path.join(store.root_path, "dist")),
                "OUTPUT_SCOPE")
        parent_fd, parent_path = acquisition._open_directory(parent_path)
        parent_identity = _output_directory_identity(os.fstat(parent_fd))
        with tempfile.TemporaryDirectory(prefix="project-manifest-assembly-capture-") as temporary:
            mirror = Path(temporary) / "git"
            projection = Path(temporary) / "ignore"
            projection.mkdir()
            store.materialize(mirror)
            view = acquisition.GitView(store, mirror, budget)
            revision, tree_oid, source, modes, payload = _capture(store, view, expected_revision, projection)
            table = {**binding.RELEASE_HEADERS, "source_revision": revision,
                     "files": [{"path": name, "bytes": len(payload[name]),
                                "sha256": hashlib.sha256(payload[name]).hexdigest()}
                               for name in binding.PAYLOAD_FILES]}
            data = binding.canonical_table_bytes(table)
            require(len(data) <= binding.MAX_TABLE_BYTES, "TABLE_BOUND")
            digest = hashlib.sha256(binding.DOMAIN + data).hexdigest()
            token = uuid.uuid4().hex.encode("ascii")
            name = "assembly-" + uuid.uuid4().hex
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            container = Path(parent_path) / name
            container_fd = acquisition._open_at(parent_fd, [name], directory=True)
            identity = _output_directory_identity(os.fstat(container_fd))
            _write_new(container_fd, [".owner"], token)
            os.mkdir("staging", mode=0o700, dir_fd=container_fd)
            stage = container / "staging"
            staging_fd = acquisition._open_at(container_fd, ["staging"], directory=True)
            staging_identity = _output_directory_identity(os.fstat(staging_fd))
            try:
                for path, content in payload.items():
                    _write_new(staging_fd, path.split("/"), content)
                _write_new(staging_fd, [binding.TABLE_NAME], data)
            finally:
                os.close(staging_fd)
            checked = binding.verify_release(str(stage), expected_digest=digest,
                                             expected_format="project-manifest-release-1")
            require(checked.exit_code == 0, "ASSEMBLY_VERIFY")
            _literal_clean(store, source, modes)
            _namespace_clean(store, view, projection, source)
            store.recheck()
            require(view.resolve("HEAD").decode() == revision, "SOURCE_REVISION")
        # Capture cleanup and source-descriptor closes precede the commit point.
        source_close_failed = _close_owned_store(store)
        store = None
        if source_close_failed:
            raise Refusal("ASSEMBLY_UNAVAILABLE", 2)
        current_fd, _ = acquisition._open_directory(parent_path)
        try:
            require(_output_directory_identity(os.fstat(current_fd)) == parent_identity, "OUTPUT_CHANGED")
        finally:
            os.close(current_fd)
        require(_output_directory_identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) == identity,
                "OUTPUT_CHANGED")
        owner_fd = acquisition._open_at(container_fd, [".owner"])
        try:
            require(acquisition._read_fd(owner_fd, 64, budget) == token, "OUTPUT_CHANGED")
        finally:
            os.close(owner_fd)
        require(set(os.listdir(container_fd)) == {".owner", "staging"}, "OUTPUT_CHANGED")
        require(_output_directory_identity(os.stat("staging", dir_fd=container_fd,
                follow_symlinks=False)) == staging_identity, "OUTPUT_CHANGED")
        closing_parent, parent_fd = parent_fd, None
        if _close_owned_fds([closing_parent]):
            raise Refusal("ASSEMBLY_UNAVAILABLE", 2)
        checked = binding.verify_release(str(stage), expected_digest=digest,
                                         expected_format="project-manifest-release-1")
        require(checked.exit_code == 0, "ASSEMBLY_VERIFY")
        require(_output_directory_identity(os.stat("staging", dir_fd=container_fd,
                follow_symlinks=False)) == staging_identity, "OUTPUT_CHANGED")
        result = AssemblyResult(0, "CANDIDATE_FINALIZED", revision, tree_oid, digest, name + "/bundle")
        warning_result = AssemblyResult(0, "CANDIDATE_FINALIZED_CLEANUP_WARNING",
                                        revision, tree_oid, digest, name + "/bundle")
        _finalize_noreplace(container_fd)
        finalized = True
    except Refusal as error:
        result = AssemblyResult(error.exit_code, error.code)
    except (acquisition.AcquisitionFailure, OSError, ValueError, TypeError):
        result = AssemblyResult(2, "ASSEMBLY_UNAVAILABLE")
    finally:
        descriptors = [fd for fd in (container_fd, parent_fd) if fd is not None]
        if store is not None:
            descriptors.extend(reversed(store.fds))
            store.fds = []
        cleanup_failed = _close_owned_fds(descriptors)
        if finalized and cleanup_failed:
            result = warning_result
        # Partial output is preserved; never recursively delete unknown changes.
        # An ordinary postcommit close failure cannot undo the completed candidate.
    return result


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise Refusal("ARGUMENTS", 2)
    parser = Parser(prog="assemble-release", allow_abbrev=False,
                    description="Origin-only unapproved candidate assembly")
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-parent", required=True)
    parser.add_argument("--git-common-dir")
    try:
        args = parser.parse_args(argv)
        result = assemble_candidate(str(ROOT), expected_revision=args.source_revision,
            output_parent=args.output_parent, common_dir=args.git_common_dir)
    except Refusal as error:
        result = AssemblyResult(error.exit_code, error.code)
    print(json.dumps(result.diagnostics(), sort_keys=True))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

