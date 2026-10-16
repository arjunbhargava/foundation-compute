"""Check how docs/conf.py handles links in the files the site includes from the root.

Each test builds a small site with Sphinx in a temporary directory, from a
copy of docs/conf.py and of the pages that include README.md and AGENTS.md,
in a repository whose README.md has the links under test. The repository is a
subdirectory of the temporary directory, so that a link can point outside it.
Run it with `mise run test:docs`, which uses the docs build's own Python, the
one that has Sphinx.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

docs_dir = Path(__file__).resolve().parent

README_WITH_EACH_KIND_OF_LINK = """# Project

[Link to a page](docs/page.md), [link to the agent instructions](AGENTS.md),
[link to a heading](AGENTS.md#commands), [link to a script](.github/script.sh),
and [link to a directory](.github/).
"""


def main() -> int:
    """Run each test, print whether it passed, and return 1 if any failed."""
    tests: list[Callable[[], None]] = [
        test_a_readme_link_into_docs_leads_to_the_page,
        test_a_readme_link_to_agents_md_leads_to_the_agent_instructions_page,
        test_a_readme_link_to_a_heading_in_agents_md_leads_to_that_heading,
        test_a_readme_link_to_another_repository_path_becomes_text,
        test_a_readme_link_to_a_missing_path_fails_the_build,
        test_a_readme_link_outside_the_repository_fails_the_build,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as error:
            print(f"FAIL: {test.__name__}: {error}", file=sys.stderr)
            failures += 1
        else:
            print(f"{test.__name__}: passed.")
    return 1 if failures else 0


def test_a_readme_link_into_docs_leads_to_the_page() -> None:
    links, _ = build_readme_page(README_WITH_EACH_KIND_OF_LINK)
    assert links.get("Link to a page") == "page.html", (
        f"links on the README page: {links}"
    )


def test_a_readme_link_to_agents_md_leads_to_the_agent_instructions_page() -> None:
    links, _ = build_readme_page(README_WITH_EACH_KIND_OF_LINK)
    assert links.get("link to the agent instructions") == "agent-instructions.html", (
        f"links on the README page: {links}"
    )


def test_a_readme_link_to_a_heading_in_agents_md_leads_to_that_heading() -> None:
    links, _ = build_readme_page(README_WITH_EACH_KIND_OF_LINK)
    assert links.get("link to a heading") == "agent-instructions.html#commands", (
        f"links on the README page: {links}"
    )


def test_a_readme_link_to_another_repository_path_becomes_text() -> None:
    links, text = build_readme_page(README_WITH_EACH_KIND_OF_LINK)
    for link_text in ("link to a script", "link to a directory"):
        assert link_text not in links, f"{link_text!r} is still a link: {links}"
        assert link_text in text, (
            f"{link_text!r} is missing from the README page: {text!r}"
        )


def test_a_readme_link_to_a_missing_path_fails_the_build() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        readme = "# Project\n\n[Missing](.github/missing.sh)\n"
        build = build_site(Path(temporary), readme)
    assert build.returncode != 0, (
        "sphinx-build passed, but the README links to a missing path"
    )
    assert "'.github/missing.sh'" in build.stderr, (
        f"sphinx-build's errors: {build.stderr}"
    )


def test_a_readme_link_outside_the_repository_fails_the_build() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        outside_file = Path(temporary) / "outside.txt"
        readme = f"# Project\n\n[Absolute]({outside_file}), [parent](../outside.txt)\n"
        build = build_site(Path(temporary), readme)
    assert build.returncode != 0, (
        "sphinx-build passed, but the README links to a file outside the repository"
    )
    for target in (str(outside_file), "../outside.txt"):
        assert f"'{target}'" in build.stderr, (
            f"no error names {target!r}; sphinx-build's errors: {build.stderr}"
        )


def build_readme_page(readme: str) -> tuple[dict[str, str], str]:
    """Build a site whose README.md is readme, and read its README page.

    Returns:
        The page's links, as a map from each link's text to its URL, and the
        page's text without its markup.

    Raises:
        AssertionError: If sphinx-build fails.
    """
    with tempfile.TemporaryDirectory() as temporary:
        build = build_site(Path(temporary), readme)
        assert build.returncode == 0, f"sphinx-build failed: {build.stderr}"
        site = Path(temporary) / "repository/docs/_build/html"
        page = (site / "project-readme.html").read_text()

    article = page.split("<article", 1)[1].split("</article>", 1)[0]
    anchors = re.findall(r'<a [^>]*href="([^"]*)"[^>]*>(.*?)</a>', article, re.DOTALL)
    links = {without_markup(text): url for url, text in anchors}
    return links, without_markup(article)


def build_site(temporary: Path, readme: str) -> subprocess.CompletedProcess[str]:
    """Build the site of a repository, temporary/repository, with this README.md.

    The repository also has AGENTS.md, with a Commands heading,
    .github/script.sh, and a page, docs/page.md. Next to the repository is
    temporary/outside.txt. Sphinx runs with -W, as docs/build.sh runs it.
    """
    (temporary / "outside.txt").write_text("")
    root = temporary / "repository"
    site_docs = root / "docs"
    site_docs.mkdir(parents=True)
    for file in ("conf.py", "project-readme.md", "agent-instructions.md"):
        shutil.copy(docs_dir / file, site_docs / file)
    (site_docs / "index.md").write_text(
        "# Index\n\n```{toctree}\nproject-readme\nagent-instructions\npage\n```\n"
    )
    (site_docs / "page.md").write_text("# Page\n")
    (root / "README.md").write_text(readme)
    (root / "AGENTS.md").write_text("# Agent instructions\n\n## Commands\n")
    (root / ".github").mkdir()
    (root / ".github/script.sh").write_text("")
    command = [sys.executable, "-m", "sphinx", "-W", "--keep-going", "-q", "-b", "html"]
    return subprocess.run(
        [*command, str(site_docs), str(site_docs / "_build/html")],
        capture_output=True,
        text=True,
        check=False,
    )


def without_markup(html: str) -> str:
    """Return html's text, with tags removed and runs of whitespace made one space."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


if __name__ == "__main__":
    sys.exit(main())
