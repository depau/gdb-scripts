import os
import sys
import warnings

import gdb
from ptpython import embed

from _commons_lib.utils import (
    ExtendedCommand,
    UserError,
    register_command,
)


@register_command
class PtPythonCommand(ExtendedCommand):
    name = "ptpython"

    def invoke(self, arg: str, from_tty: bool):
        self.dont_repeat()

        history_filename = "~/.gdb_ptpython_history"
        history_val = gdb.convenience_variable("ptpython_history_filename")
        if history_val is not None:
            try:
                history_filename = history_val.string()
            except gdb.error:
                warnings.warn("$ptpython_history_filename is not a string, using default value")
        history_filename = os.path.expanduser(history_filename)

        if not from_tty:
            raise UserError("PtPython can only be launched from the TTY")

        stdout = sys.stdout
        stderr = sys.stderr
        stdin = sys.stdin

        def inject_globals():
            import _commons_lib.all

            globals().update(_commons_lib.all.__dict__)

        inject_globals()

        try:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            sys.stdin = sys.__stdin__

            user_ns = globals()
            embed(user_ns, history_filename=history_filename)

        except SystemExit as e:
            if e.code != 0:
                print("ptpython exited with code", e.code)

        finally:
            sys.stdout = stdout
            sys.stderr = stderr
            sys.stdin = stdin
