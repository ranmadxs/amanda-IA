from amanda_ia import __version__

#poetry run pytest tests/test_amanda_ia.py::test_version -s
def test_version():
    print(__version__)
    assert __version__ == '0.1.0'
