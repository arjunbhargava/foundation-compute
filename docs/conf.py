"""Sphinx configuration for the documentation site, which docs/build.sh builds.

Each language's block applies only when the language's manifest exists, as
its block in docs/build.sh does, so a project without the language leaves out
its extensions and settings.
"""

from pathlib import Path
from typing import Any

project = "foundation-compute"
repository_root = Path(__file__).resolve().parent.parent

extensions = ["myst_parser"]

# Python: parsed from source without importing it.
if (repository_root / "pyproject.toml").is_file():
    extensions += ["autoapi.extension", "sphinx.ext.intersphinx", "sphinx.ext.napoleon"]
    autoapi_dirs = ["../src"]
    autoapi_root = "api/python"
    autoapi_options = [
        "members",
        "show-inheritance",
        "show-module-summary",
        "imported-members",
    ]
    autoapi_add_toctree_entry = False
    # Links standard-library names in signatures, such as
    # collections.abc.Sequence, to the Python docs. nitpicky fails the build on
    # any it can't resolve. Each build downloads this inventory, so it needs
    # network access.
    intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# Rust: docs/build.sh copies rustdoc's HTML into _generated/html, and Sphinx
# publishes it unchanged, without reading it as sources.
if (repository_root / "Cargo.toml").is_file():
    html_extra_path = ["_generated/html"]

# C and C++: docs/build.sh runs Doxygen, whose XML Breathe reads.
if (repository_root / "CMakeLists.txt").is_file():
    extensions.append("breathe")
    breathe_projects = {"foundation": "_generated/doxygen"}
    breathe_default_project = "foundation"

nitpicky = True
myst_heading_anchors = 3

html_theme = "furo"
html_title = project
# NOTICE holds the copyright line; without this the footer shows an empty one.
html_show_copyright = False
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#b4532f",
        "color-brand-content": "#b4532f",
    },
    "dark_css_variables": {
        "color-brand-primary": "#d97757",
        "color-brand-content": "#d97757",
    },
}
# .venv is the environment of the docs build's own uv project, docs/pyproject.toml.
exclude_patterns = ["_build", ".venv"]

# The page that includes each of these root files, which a link to the file
# from another root file leads to. docs/conf_test.py checks the page names.
pages_of_root_files = {
    Path("README.md"): "project-readme",
    Path("AGENTS.md"): "agent-instructions",
}


# The parameters are Sphinx and docutils objects, typed Any because the root
# environment, whose pyright checks this file, doesn't have Sphinx.
def setup(app: Any) -> None:
    """Connect this file's event handlers to Sphinx.

    Args:
        app: The Sphinx application.
    """
    app.connect("doctree-read", _resolve_root_file_links)


def _resolve_root_file_links(app: Any, doctree: Any) -> None:
    """Point links in root files, such as README.md, at site pages or turn them into text.

    README.md and AGENTS.md are written for GitHub, where a link to a
    repository file or directory opens it. Their links into docs/ already work,
    through the include's relative-docs option: a link to a page leads to it,
    and a link to another file downloads it. A link to one of
    pages_of_root_files leads to that file's page, and to the heading its
    #fragment names, if any. Any other path in the repository has no page, so
    the strict build would fail on the link, and it becomes text. A link to a
    path that doesn't exist, or that is outside the repository, such as an
    absolute path or one through .., is left alone, so it still fails the
    build.
    """
    for node in list(doctree.findall()):
        is_unresolved_link = (
            node.tagname == "pending_xref"
            and node.get("reftype") == "myst"
            and node.get("refdomain") is None
        )
        if not is_unresolved_link:
            continue
        is_in_root_file = Path(node.source).resolve().parent == repository_root
        if not is_in_root_file:
            continue

        linked_path_text, _, fragment = node["reftarget"].partition("#")
        linked_path = (repository_root / linked_path_text).resolve()
        if not linked_path.is_relative_to(repository_root):
            continue

        page = pages_of_root_files.get(linked_path.relative_to(repository_root))
        if page is not None:
            node["refdomain"] = "doc"
            node["reftarget"] = page
            node["reftargetid"] = fragment or None
        elif linked_path.exists():
            node.replace_self(node.children)
