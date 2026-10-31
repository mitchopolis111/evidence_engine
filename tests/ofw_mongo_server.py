"""Own the entire lifecycle of a disposable server; never use app configuration."""

import socket
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


@pytest.fixture(scope="session")
def isolated_mongo(request):
    binary = request.config.getoption("--ofw-mongod")
    if binary is None:
        pytest.skip("use --ofw-mongod to start a disposable real MongoDB")
    executable = Path(binary).expanduser().resolve()
    if not binary or not executable.is_file():
        pytest.fail("--ofw-mongod must name a MongoDB server executable", pytrace=False)
    parent = request.config.getoption("--ofw-mongo-work-dir")
    if parent is not None:
        parent = Path(parent).expanduser().resolve()
        if not parent.is_dir() or parent.is_relative_to(Path(__file__).resolve().parents[1]):
            pytest.fail("MongoDB work parent must be an existing directory outside the repository", pytrace=False)
    with tempfile.TemporaryDirectory(prefix="ofw-mongo-", dir=parent) as temporary:
        root = Path(temporary)
        data = root / "data"
        data.mkdir(mode=0o700)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        command = [
            str(executable), "--bind_ip", "127.0.0.1", "--port", str(port),
            "--nounixsocket", "--dbpath", str(data), "--logpath", str(root / "mongod.log"),
            "--setParameter", "diagnosticDataCollectionEnabled=false",
        ]
        with (root / "process.log").open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            client = MongoClient(
                "127.0.0.1", port, directConnection=True, tz_aware=True,
                serverSelectionTimeoutMS=500, connectTimeoutMS=500,
            )
            try:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        pytest.fail("disposable MongoDB exited during startup", pytrace=False)
                    try:
                        client.admin.command("ping")
                        break
                    except ConnectionFailure:
                        if time.monotonic() >= deadline:
                            pytest.fail("disposable MongoDB did not become ready", pytrace=False)
                        time.sleep(0.1)
                options = client.admin.command("getCmdLineOpts")["parsed"]
                assert options["storage"]["dbPath"] == str(data)
                assert options["net"]["bindIp"] == "127.0.0.1"
                yield client
            finally:
                client.close()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


@pytest.fixture
def mongo_collection(isolated_mongo):
    name = "ofw_pr7_test_" + uuid4().hex
    try:
        yield isolated_mongo[name].messages
    finally:
        isolated_mongo.drop_database(name)
