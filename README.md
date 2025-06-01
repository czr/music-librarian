# music-librarian

Music Librarian is CZR's opinionated music manager.

## Installation

Install this tool using `pip`:
```bash
pip install music-librarian
```
## Usage

For help, run:
```bash
music-librarian --help
```
You can also use:
```bash
python -m music_librarian --help
```
## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:
```bash
cd music-librarian
python -m venv venv
source venv/bin/activate
```
Now install the dependencies and test dependencies:
```bash
pip install -e '.[test]'
```
To run the tests:
```bash
python -m pytest
```
