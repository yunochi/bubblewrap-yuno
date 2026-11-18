import os
from pathlib import Path
import subprocess

import pytest

from bubblewrap_plugin.sandbox import BindMount, bind_mount_flag


def test_device_access_requires_writable_bind():
    # stat only: no hardware I/O.
    with pytest.raises(ValueError, match='Read-only'):
        bind_mount_flag(BindMount('/dev/null', '/dev/null'))
    assert bind_mount_flag(BindMount('/dev/null', '/dev/null', readonly=False)) == '--dev-bind'


def test_install_and_reinstall_only_enable_plugin(tmp_path):
    cli = tmp_path / 'hermes'
    cli.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/calls"\n')
    cli.chmod(0o700)
    env = dict(os.environ, HOME=str(tmp_path), HERMES_HOME=str(tmp_path / 'profile'),
               PATH=f'{tmp_path}:{os.environ["PATH"]}')
    for _ in range(2):
        subprocess.run(['bash', str(Path(__file__).resolve().parents[1] / 'install.sh')], env=env, check=True)
    assert (tmp_path / 'calls').read_text().splitlines() == ['plugins enable bubblewrap-yuno'] * 2
