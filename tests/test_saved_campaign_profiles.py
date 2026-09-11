import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
SAVED_ROOT = ROOT / "generated_harnesses"
LIBRARIES = {
    "c-ares",
    "cjson",
    "cpu_features",
    "libdwarf",
    "libhtp",
    "libpcap",
    "libplist",
    "libsndfile",
    "libtiff",
    "minijail",
    "pthreadpool",
}


def test_saved_campaign_profiles_are_complete_and_self_contained() -> None:
    assert {path.name for path in SAVED_ROOT.iterdir() if path.is_dir()} == LIBRARIES

    for library in sorted(LIBRARIES):
        library_dir = SAVED_ROOT / library
        profile = json.loads((library_dir / "campaign.json").read_text())
        archive = library_dir / profile["initial_corpus"]["archive"]

        assert profile["version"] == 1
        assert (library_dir / "harness.cc").is_file()
        assert (library_dir / f"{library}.v2.proto").is_file()
        assert archive.is_file()
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == profile["initial_corpus"]["sha256"]

        with tarfile.open(archive, "r:gz") as corpus_tar:
            files = [member for member in corpus_tar.getmembers() if member.isfile()]
            assert len(files) == profile["initial_corpus"]["files"]
            for member in files:
                member_path = PurePosixPath(member.name)
                assert not member_path.is_absolute()
                assert ".." not in member_path.parts


def test_saved_campaign_runtime_is_deterministic() -> None:
    forks = {}
    for library in sorted(LIBRARIES):
        profile = json.loads((SAVED_ROOT / library / "campaign.json").read_text())
        runtime = profile["runtime"]
        forks[library] = runtime["fork"]

        assert runtime["jobs"] == 1
        assert runtime["workers"] == 1
        assert runtime["seed"] == 1337
        assert runtime["max_len"] == 4096
        assert runtime["timeout_sec"] == 25
        assert runtime["max_actions"] == 64
        assert profile["recommended_duration_sec"] == 86400
        assert profile["use_minimum_apis"] is False

    assert forks["cjson"] == 1
    assert {fork for library, fork in forks.items() if library != "cjson"} == {2}
