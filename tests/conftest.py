def pytest_addoption(parser):
    parser.addoption(
        "--ofw-oct16-export",
        metavar="PDF",
        help="Path to an isolated copy of the private October 16 OFW export",
    )
