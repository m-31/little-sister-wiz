"""What every module of this suite shares: the library's settings file.

An issue's line says when WIZ detected the issue and when it is due, and the library
writes both in the zone its settings name. With no settings file named, the library
looks for a configuration root — a `config/` directory, which a deployment has and
this repository does not — and refuses, so a run that came to such a line would end
there. It reads its settings once, the first time it needs them, so the suite names
its own file here, before anything imports the library: every run can write its
lines, and a test states a clock time as the text it is and reads the same one on
every machine. Set, and not defaulted: a deployment's own settings in the
environment would change what every such test reads. The file and the reason are
`little-sister-github`'s.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ["LITTLE_SISTER_CONFIG"] = str(Path(__file__).with_name("settings.yaml"))
