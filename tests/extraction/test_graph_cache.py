import subprocess

import pytest

from shield_core.extraction import (
    CachedGraphExtractor,
    CacheKey,
    CodeGraph,
    ExtractionError,
    GraphCache,
    GraphEdge,
    GraphExtractor,
    GraphNode,
)
from shield_core.extraction.graph_extractor import GRAPH_SCHEMA_VERSION
from shield_core.extraction.joern_extractor import JoernExtractor, parse_graphml


class FakeExtractor(GraphExtractor):
    def __init__(self, version="1.0", fail=False):
        self._version = version
        self.fail = fail
        self.calls = 0

    name = "fake"

    @property
    def version(self):
        return self._version

    def extract(self, code, language, extension=None):
        self.calls += 1
        if self.fail:
            raise ExtractionError("boom")
        return CodeGraph(
            language, self.name, self.version, self.schema_version,
            [GraphNode(1, "METHOD", code, "f", 1), GraphNode(2, "CALL", "g()", "g", None)],
            [GraphEdge(1, 2, "AST")],
        )  # fmt: skip


def test_key_ignores_line_endings():
    fx = FakeExtractor()
    a = CacheKey.for_code("a = 1\r\nb = 2\r\n", "python", fx)
    b = CacheKey.for_code("a = 1\nb = 2\n", "python", fx)
    assert a == b


def test_key_changes_with_each_part():
    fx = FakeExtractor()
    base = CacheKey.for_code("x", "python", fx)
    assert base != CacheKey.for_code("y", "python", fx)
    assert base != CacheKey.for_code("x", "cpp", fx)
    assert base != CacheKey.for_code("x", "python", FakeExtractor(version="2.0"))
    assert base.relative_path() != CacheKey.for_code("x", "cpp", fx).relative_path()


def test_miss_then_hit(tmp_path):
    ex = CachedGraphExtractor(FakeExtractor(), GraphCache(tmp_path))
    g1 = ex.extract("code", "python")
    g2 = ex.extract("code", "python")
    assert ex.inner.calls == 1
    assert g1 == g2
    assert ex.cache.stats() == {"hits": 1, "misses": 1, "hit_rate": 0.5}


def test_version_bump_invalidates(tmp_path):
    cache = GraphCache(tmp_path)
    CachedGraphExtractor(FakeExtractor("1.0"), cache).extract("code", "python")
    second = FakeExtractor("2.0")
    CachedGraphExtractor(second, cache).extract("code", "python")
    assert second.calls == 1


def test_corrupted_file_is_a_miss(tmp_path):
    ex = CachedGraphExtractor(FakeExtractor(), GraphCache(tmp_path))
    ex.extract("code", "python")
    path = ex.cache.path_for(CacheKey.for_code("code", "python", ex.inner))
    path.write_bytes(b"not gzip")
    ex.extract("code", "python")
    assert ex.inner.calls == 2
    assert path.exists()  # rewritten


def test_failures_are_not_cached(tmp_path):
    ex = CachedGraphExtractor(FakeExtractor(fail=True), GraphCache(tmp_path))
    with pytest.raises(ExtractionError):
        ex.extract("code", "python")
    assert not list(tmp_path.rglob("*.json.gz"))


GRAPHML = """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
<key id="labelV" for="node" attr.name="labelV" attr.type="string"/>
<key id="CODE" for="node" attr.name="CODE" attr.type="string"/>
<key id="NAME" for="node" attr.name="NAME" attr.type="string"/>
<key id="LINE_NUMBER" for="node" attr.name="LINE_NUMBER" attr.type="int"/>
<key id="labelE" for="edge" attr.name="labelE" attr.type="string"/>
<graph id="g" edgedefault="directed">
<node id="20">
<data key="labelV">CALL</data><data key="CODE">escape(x)</data>
<data key="LINE_NUMBER">2</data></node>
<node id="10">
<data key="labelV">METHOD</data><data key="NAME">f</data>
<data key="CODE">def f(x)</data><data key="LINE_NUMBER">1</data></node>
<edge source="10" target="20"><data key="labelE">AST</data></edge>
</graph></graphml>"""


def test_parse_graphml():
    nodes, edges = parse_graphml(GRAPHML)
    assert [n.id for n in nodes] == [10, 20]  # sorted
    assert nodes[0] == GraphNode(10, "METHOD", "def f(x)", "f", 1)
    assert edges == [GraphEdge(10, 20, "AST")]


def test_joern_extractor_with_fake_runner(tmp_path):
    seen = []

    def runner(cmd, cwd=None, **kw):
        seen.append(cmd[0])
        if cmd[0] == "joern-export":
            out = cwd / "export"
            out.mkdir()
            (out / "export.xml").write_text(GRAPHML, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ex = JoernExtractor(runner=runner)
    ex.use_docker = False
    graph = ex.extract("def f(x):\r\n    escape(x)\r\n", "python")
    assert seen == ["joern-parse", "joern-export"]
    assert graph.schema_version == GRAPH_SCHEMA_VERSION
    assert len(graph.nodes) == 2


def test_joern_failure_raises(tmp_path):
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "parse error")

    ex = JoernExtractor(runner=runner)
    ex.use_docker = False
    with pytest.raises(ExtractionError, match="parse error"):
        ex.extract("x", "python")


def test_disabled_language_rejected():
    from shield_core.languages.registry import DisabledLanguageError

    with pytest.raises(DisabledLanguageError):
        JoernExtractor().extract("class A {}", "java")


def test_default_extension_for_cpp_is_cpp():
    from shield_core.extraction.graph_extractor import resolve_extension

    assert resolve_extension("cpp") == ".cpp"
    assert resolve_extension("cpp", "C") == ".c"
    assert resolve_extension("python") == ".py"
    with pytest.raises(ExtractionError):
        resolve_extension("cpp", ".py")


def test_c_and_cpp_files_get_different_keys():
    fx = FakeExtractor()
    c = CacheKey.for_code("x", "cpp", fx, ".c")
    cpp = CacheKey.for_code("x", "cpp", fx, ".cpp")
    assert c != cpp
    assert c.relative_path() != cpp.relative_path()
    assert CacheKey.for_code("x", "cpp", fx) == cpp


def test_joern_gets_the_right_file_name():
    names = []

    def runner(cmd, cwd=None, **kw):
        if cmd[0] == "joern-parse":
            names.append(cmd[1])
        if cmd[0] == "joern-export":
            (cwd / "export").mkdir()
            (cwd / "export" / "export.xml").write_text(GRAPHML, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ex = JoernExtractor(runner=runner)
    ex.use_docker = False
    ex.extract("int x;", "cpp")
    ex.extract("int x;", "cpp", ".c")
    assert names == ["code.cpp", "code.c"]
