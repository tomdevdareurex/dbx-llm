"""Dev launcher for the Streamlit GUI.

The real GUI lives in ``dbx_llm/gui.py`` so it ships inside the installed
package and runs anywhere via ``python -m dbx_llm --gui``. This thin wrapper
just executes that packaged module, so ``streamlit run app.py`` keeps working
from this repo without duplicating the GUI code.

We ``exec`` the module's source (rather than ``import`` it) so it re-runs fresh
on every Streamlit rerun, exactly as Streamlit expects of its entry script.
"""

from pathlib import Path

import dbx_llm

_gui = Path(dbx_llm.__file__).resolve().parent / "gui.py"
exec(compile(_gui.read_text(encoding="utf-8"), str(_gui), "exec"))

