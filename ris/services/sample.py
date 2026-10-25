"""Load the clearly labelled fictional sample profile into a (sample) workspace."""

from __future__ import annotations

from ris.domain.enums import Origin
from ris.errors import RISError
from ris.resources import sample_data_dir
from ris.services import portable

SAMPLE_FILE = "fictional_sample_profile.ris.json"


def load_sample_profile(workspace) -> portable.ImportReport:
    if not getattr(workspace, "is_sample", False):
        raise RISError("The fictional sample can only be loaded into the sample workspace.")
    data = portable.load_payload(sample_data_dir() / SAMPLE_FILE)
    prev = portable.preview(workspace.repo, data, detect_duplicates=False)
    bad = [c for c in prev.candidates if not c.valid]
    if bad:
        raise RISError("The bundled sample profile is invalid: " + "; ".join(e for c in bad for e in c.errors))
    return portable.commit(workspace.repo, prev, origin=Origin.SAMPLE, preserve_status=True)
