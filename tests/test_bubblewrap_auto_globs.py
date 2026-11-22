"""auto_bind_globs is read on every spawn, not once when the environment is built.

A device path can move between enumerations (``/dev/ttyACM0`` ->
``/dev/ttyACM1``). Resolving the globs only at construction leaves the vanished
path in every later bwrap argv, where bwrap refuses to start the command at all
("Can't find source path"), so these tests pin the per-spawn behaviour: a new
match is bound, a vanished one stops being bound, and a match the writable-set
check refuses is skipped with a warning instead of failing the spawn.

Unit tests only build the argv; they never spawn bwrap, so they run without a
working namespace.
"""

import shutil
from unittest.mock import patch

import pytest

from tools.environments.local import LocalEnvironment
from bubblewrap_plugin import sandbox as bubblewrap
from bubblewrap_plugin.sandbox import BubblewrapEnvironment, load_bubblewrap_config


@pytest.fixture(autouse=True)
def _bwrap_probe_passed(monkeypatch):
    """Construction never spawns: count the process-wide bwrap probe as passed."""
    monkeypatch.setattr(bubblewrap, "_probed_bwrap_path", shutil.which("bwrap") or "/usr/bin/bwrap")
    monkeypatch.setattr(bubblewrap, "_process_limit_scoped", True)


@pytest.fixture
def sandbox_root(tmp_path, monkeypatch):
    root = tmp_path / "sandboxes"
    monkeypatch.setenv("TERMINAL_SANDBOX_DIR", str(root))
    return root


@pytest.fixture
def work_dir(tmp_path):
    d = tmp_path / "work"
    d.mkdir()
    return d


def _no_session():
    return patch.object(LocalEnvironment, "init_session", autospec=True, return_value=None)


def _environment(work_dir, patterns, binds=None, *, kind="any"):
    settings: dict[str, object] = {
        "auto_bind_globs": [str(pattern) for pattern in patterns],
        "auto_bind_globs_type": kind,
    }
    if binds:
        settings["binds"] = binds
    config = load_bubblewrap_config(settings)
    with _no_session():
        return BubblewrapEnvironment(cwd=str(work_dir), timeout=10, config=config)


class TestAutoGlobsPerSpawn:
    def test_device_mode_uses_optional_device_binds_at_the_current_path(self, sandbox_root, work_dir, tmp_path):
        # Use existing character devices without opening a real serial port.
        first = tmp_path / "ttyACM0"
        first.symlink_to("/dev/zero")
        env = _environment(work_dir, [tmp_path / "ttyACM*"], kind="device")

        def device_mounts():
            argv = env._bwrap_prefix(str(work_dir))
            return [argv[i + 1:i + 3] for i, arg in enumerate(argv) if arg == "--dev-bind-try"]

        assert ["/dev/zero", "/dev/zero"] in device_mounts()
        first.unlink()
        (tmp_path / "ttyACM1").symlink_to("/dev/full")
        (tmp_path / "ttyACM2").touch()
        assert ["/dev/full", "/dev/full"] in device_mounts()
        argv = env._bwrap_prefix(str(work_dir))
        assert "/dev/zero" not in argv
        assert str(tmp_path / "ttyACM2") not in argv

    def test_directory_matches_follow_the_host_between_spawns(self, sandbox_root, work_dir, tmp_path):
        first = tmp_path / "share0"
        second = tmp_path / "share1"
        env = _environment(work_dir, [tmp_path / "share*"])
        assert str(first) not in env._bwrap_prefix(str(work_dir))
        first.mkdir()
        argv = env._bwrap_prefix(str(work_dir))
        i = argv.index(str(first))
        assert argv[i - 1:i + 2] == ["--bind-try", str(first), str(first)]
        first.rename(second)
        argv = env._bwrap_prefix(str(work_dir))
        assert str(first) not in argv
        assert str(second) in argv
        second.rmdir()
        assert str(second) not in env._bwrap_prefix(str(work_dir))

    def test_directory_cannot_cover_another_environments_fixed_bind(self, sandbox_root, work_dir, tmp_path, caplog):
        tree = tmp_path / "share0"
        tree.mkdir()
        fixed = tree / "fixed"
        fixed.touch()
        other_cwd = tmp_path / "other"
        other_cwd.mkdir()
        _environment(other_cwd, [], binds=[{"src": str(fixed), "dest": str(tmp_path / "alias")}])
        safe = tmp_path / "share1"
        safe.mkdir()
        env = _environment(work_dir, [tmp_path / "share*"])
        argv = env._bwrap_prefix(str(work_dir))
        assert str(tree) not in argv
        assert str(safe) in argv
        assert "overlaps a fixed mount or protected path" in caplog.text

    def test_directory_cannot_cover_an_absent_hidden_path(self, sandbox_root, work_dir, tmp_path, caplog):
        candidate = tmp_path / "shared"
        settings = {"auto_bind_globs": [str(candidate)], "hide": [str(candidate / "private")]}
        with _no_session():
            env = BubblewrapEnvironment(cwd=str(work_dir), config=load_bubblewrap_config(settings))
        candidate.mkdir()
        assert str(candidate) not in env._bwrap_prefix(str(work_dir))
        assert "not auto-binding" in caplog.text
        assert str(candidate / "private") in caplog.text

    @pytest.mark.parametrize("match_directory", [True, False])
    def test_match_cannot_make_home_dot_link_target_writable(
        self, sandbox_root, work_dir, tmp_path, monkeypatch, match_directory,
    ):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(bubblewrap, "get_real_home", lambda: str(home))
        tree = tmp_path / "dotfiles"
        startup = tree / "bashrc"
        match = tree if match_directory else startup
        env = _environment(work_dir, [match])
        (home / ".bashrc").symlink_to(startup)
        tree.mkdir()
        startup.touch()
        # HOME layout can refer to the same path independently of an auto mount.
        assert all(bind.src != str(match) for bind in env._spawn_binds())

    def test_auto_match_preserves_home_dot_link_directory_descendants(
        self, sandbox_root, work_dir, tmp_path, monkeypatch,
    ):
        home = tmp_path / "home"
        (home / ".config").mkdir(parents=True)
        monkeypatch.setattr(bubblewrap, "get_real_home", lambda: str(home))
        tree = tmp_path / "dotfiles"
        tree.mkdir()
        (home / ".config" / "example").symlink_to(tree, target_is_directory=True)
        candidate = tree / "settings"
        env = _environment(work_dir, [candidate])
        candidate.touch()
        assert not env._spawn_binds()

    def test_auto_match_preserves_private_proc(self, sandbox_root, work_dir):
        env = _environment(work_dir, ["/proc/version", "/proc/sys"])
        assert not env._spawn_binds()

    def test_auto_file_does_not_override_explicit_readonly_tree(self, sandbox_root, work_dir, tmp_path):
        tree = tmp_path / "shared"
        tree.mkdir()
        file = tree / "data"
        file.touch()
        env = _environment(work_dir, [file], binds=[{"src": str(tree)}])
        argv = env._bwrap_prefix(str(work_dir))
        assert str(file) not in argv
        assert str(tree) in argv

    def test_auto_directory_does_not_replace_private_tmp(self, sandbox_root, work_dir):
        env = _environment(work_dir, ["/tmp"])
        argv = env._bwrap_prefix(str(work_dir))
        assert argv.count("/tmp") == 1
        assert argv[argv.index("/tmp") - 1] == "--tmpfs"

    def test_auto_match_checks_the_entire_symlink_chain(self, sandbox_root, work_dir, tmp_path):
        data = tmp_path / "data"
        data.touch()
        intermediate = work_dir / "intermediate"
        intermediate.symlink_to(data)
        alias = tmp_path / "alias"
        alias.symlink_to(intermediate)
        env = _environment(work_dir, [alias])
        assert str(data) not in env._bwrap_prefix(str(work_dir))

    def test_auto_device_keeps_the_validated_mount_flag(self, sandbox_root, work_dir, tmp_path):
        alias = tmp_path / "ttyACM0"
        alias.symlink_to("/dev/full")
        env = _environment(work_dir, [alias], kind="device")
        binds = env._spawn_binds()
        with patch.object(bubblewrap.os, "stat", side_effect=FileNotFoundError):
            assert bubblewrap.bind_mount_flag(binds[-1]) == "--dev-bind-try"

    def test_reenumerated_device_is_picked_up_without_rebuilding(self, sandbox_root, work_dir, tmp_path):
        device_dir = tmp_path / "dev"
        device_dir.mkdir()
        first = device_dir / "ttyACM0"
        first.write_text("")
        env = _environment(work_dir, [device_dir / "ttyACM*"])

        assert str(first) in env._bwrap_prefix(str(work_dir))

        first.unlink()
        second = device_dir / "ttyACM1"
        second.write_text("")

        argv = env._bwrap_prefix(str(work_dir))

        assert str(second) in argv
        assert str(first) not in argv

    def test_vanished_device_leaves_no_source_that_can_fail_a_spawn(self, sandbox_root, work_dir, tmp_path):
        device_dir = tmp_path / "dev"
        device_dir.mkdir()
        device = device_dir / "ttyACM0"
        device.write_text("")
        env = _environment(work_dir, [device_dir / "ttyACM*"])
        assert str(device) in env._bwrap_prefix(str(work_dir))

        device.unlink()

        # A frozen path here is what made every later command die with
        # "Can't find source path": building the argv must simply drop it.
        argv = env._bwrap_prefix(str(work_dir))
        assert str(device) not in argv
        assert str(work_dir) in argv

    def test_match_inside_a_writable_root_is_skipped_with_a_warning(
        self, sandbox_root, work_dir, tmp_path, caplog,
    ):
        device_dir = tmp_path / "dev"
        device_dir.mkdir()
        safe = device_dir / "ttyACM0"
        safe.write_text("")
        # One level deeper than the writable cwd the parent directory is a
        # plain directory a command can rename, so this match must be dropped.
        nested = work_dir / "sub"
        nested.mkdir()
        swappable = nested / "ttyACM1"
        swappable.write_text("")
        env = _environment(work_dir, [device_dir / "ttyACM*", nested / "ttyACM*"])

        with caplog.at_level("WARNING"):
            argv = env._bwrap_prefix(str(work_dir))

        assert str(safe) in argv
        assert str(swappable) not in argv
        assert any("not auto-binding" in record.message for record in caplog.records)

    def test_operator_binds_survive_the_per_spawn_list(self, sandbox_root, work_dir, tmp_path):
        device_dir = tmp_path / "dev"
        device_dir.mkdir()
        shared = tmp_path / "shared"
        shared.mkdir()
        env = _environment(
            work_dir, [device_dir / "ttyACM*"],
            binds=[{"src": str(shared), "readonly": False}],
        )

        argv = env._bwrap_prefix(str(work_dir))

        assert str(shared) in argv
        assert any(bind.src == str(shared) for bind in env._spawn_binds())
