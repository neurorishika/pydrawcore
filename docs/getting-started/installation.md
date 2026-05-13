# Installation

## Runtime install

Install the package into your active Python environment:

```bash
pip install .
```

For editable development work:

```bash
pip install -e .[dev]
```

## Documentation toolchain

Install the documentation extras when you want to build or preview the MkDocs site locally:

```bash
pip install -e .[docs]
```

That extras group installs:

- MkDocs
- Material for MkDocs
- mkdocstrings with Python support
- markdown extensions and HTML minification used by this site

## Python requirements

PyDrawCore requires Python 3.10 or newer.

## Verify the install

Confirm the CLI is available:

```bash
pydrawcore --help
```

If you are working from source and prefer the module entry point:

```bash
python -m pydrawcore --help
```

## Build the documentation

Serve the site with live reload:

```bash
mkdocs serve
```

Build a static site into `site/`:

```bash
mkdocs build
```

## Hardware note

This package is DrawCore-only. The vendored extension code under `extensions/` is retained for compatibility with the original Inkscape ecosystem, but the installable package and this documentation focus on the standalone Python controller in `src/pydrawcore`.
