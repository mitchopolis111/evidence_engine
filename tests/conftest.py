def pytest_addoption(parser):
    parser.addoption(
        "--ofw-oct16-export",
        metavar="PDF",
        help="Path to an isolated copy of the private October 16 OFW export",
    )
    parser.addoption("--ofw-mongod", metavar="BINARY", help="Start a disposable loopback-only MongoDB for OFW tests")
    parser.addoption("--ofw-mongo-work-dir", metavar="DIR", help="Private parent for disposable MongoDB files, outside Git")
