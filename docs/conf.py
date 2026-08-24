project = "ottu"
author = "Infineon Technologies AG"
copyright = "- The ottu Documentation is Copyright © 2026, Infineon Technologies AG"


source_suffix = ".rst"
highlight_language = "python"
primary_domain = "py"

extensions = [
    "sphinx.ext.extlinks",
]

extlinks = {
    "gh_main": ("https://github.com/Infineon/ottu/blob/main/%s", "%s"),
}

templates_path = ["_templates"]
exclude_patterns = ["build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
master_doc = "index"
