"""Joern implementation of GraphExtractor (D1, D2).

Pipeline per sample (same commands as tests/fixtures/joern/README.md):
    joern-parse <file> --language <frontend> -o cpg.bin
    joern-export cpg.bin --repr all --format graphml --out export   ->  export/export.xml
then export.xml is parsed into a CodeGraph.

Joern runs either locally (joern-parse on PATH) or inside the shield-joern Docker image.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from shield_core.extraction.graph_extractor import (
    CodeGraph,
    ExtractionError,
    GraphEdge,
    GraphExtractor,
    GraphNode,
    normalize_code,
    resolve_extension,
)
from shield_core.languages import registry

DEFAULT_JOERN_VERSION = "4.0.647"  # must match ARG JOERN_VERSION in docker/joern/Dockerfile
DEFAULT_DOCKER_IMAGE = "shield-joern"
_GRAPHML = "{http://graphml.graphdrawing.org/xmlns}"


def parse_graphml(source: str | Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Parse a Joern GraphML export (path or XML text) without extra dependencies."""
    text = str(source)
    root = ET.fromstring(text) if text.lstrip().startswith("<") else ET.parse(source).getroot()

    # <key id="labelV" for="node" attr.name="labelV"/>: map key id -> attribute name
    names = {k.get("id"): k.get("attr.name") for k in root.iter(f"{_GRAPHML}key")}

    def data(el: ET.Element) -> dict[str, str]:
        return {
            names.get(d.get("key"), d.get("key")): (d.text or "")
            for d in el.iter(f"{_GRAPHML}data")
        }

    nodes: list[GraphNode] = []
    for el in root.iter(f"{_GRAPHML}node"):
        d = data(el)
        line = d.get("LINE_NUMBER", "")
        nodes.append(
            GraphNode(
                id=int(el.get("id")),
                type=d.get("labelV", ""),
                code=d.get("CODE", ""),
                name=d.get("NAME", ""),
                line=int(line) if line.lstrip("-").isdigit() else None,
            )
        )
    edges = [
        GraphEdge(int(el.get("source")), int(el.get("target")), data(el).get("labelE", ""))
        for el in root.iter(f"{_GRAPHML}edge")
    ]
    nodes.sort(key=lambda n: n.id)  # deterministic order (graph_schema.md "Row order")
    edges.sort(key=lambda e: (e.src, e.dst, e.type))
    return nodes, edges


class JoernExtractor(GraphExtractor):
    def __init__(
        self,
        joern_version: str = DEFAULT_JOERN_VERSION,
        docker_image: str | None = None,
        timeout: int = 300,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self._version = joern_version
        self.timeout = timeout
        self._run = runner
        # Local Joern if installed, otherwise Docker. docker_image forces Docker.
        self.use_docker = docker_image is not None or shutil.which("joern-parse") is None
        self.docker_image = docker_image or DEFAULT_DOCKER_IMAGE

    @property
    def name(self) -> str:
        return "joern"

    @property
    def version(self) -> str:
        return self._version

    def extract(self, code: str, language: str, extension: str | None = None) -> CodeGraph:
        spec = registry.require_enabled(language)  # no hard-coded languages (plan section 4.2)
        ext = resolve_extension(language, extension)
        frontend = spec.joern_frontend.lower()  # "PYTHONSRC" -> "pythonsrc"

        with tempfile.TemporaryDirectory(prefix="shield_joern_") as tmp:
            work = Path(tmp)
            os.chmod(work, 0o777)  # the container user is not root; it must be able to write
            (work / f"code{ext}").write_text(normalize_code(code), encoding="utf-8")
            self._run_joern(work, f"code{ext}", frontend)
            export = work / "export" / "export.xml"
            if not export.exists():
                found = list((work / "export").glob("*.xml")) if (work / "export").exists() else []
                if not found:
                    raise ExtractionError("joern-export produced no GraphML file")
                export = found[0]
            try:
                nodes, edges = parse_graphml(export)
            except (ET.ParseError, ValueError) as exc:
                raise ExtractionError(f"cannot parse Joern GraphML: {exc}") from exc

        return CodeGraph(language, self.name, self.version, self.schema_version, nodes, edges)

    # ------------------------------------------------------------------ running Joern

    def _run_joern(self, work: Path, filename: str, frontend: str) -> None:
        parse = ["joern-parse", filename, "--language", frontend, "-o", "cpg.bin"]
        export = [
            "joern-export",
            "cpg.bin",
            "--repr",
            "all",
            "--format",
            "graphml",
            "--out",
            "export",
        ]
        if self.use_docker:
            script = " && ".join(" ".join(c) for c in (parse, export))
            self._exec(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{work}:/workspace/sample",
                    "-w",
                    "/workspace/sample",
                    self.docker_image,
                    "bash",
                    "-c",
                    script,
                ],
                cwd=None,
            )
        else:
            self._exec(parse, cwd=work)
            self._exec(export, cwd=work)

    def _exec(self, cmd: list[str], cwd: Path | None) -> None:
        try:
            proc = self._run(cmd, cwd=cwd, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(f"Joern timed out after {self.timeout}s") from exc
        except FileNotFoundError as exc:
            raise ExtractionError(
                f"command not found: {cmd[0]} (is Joern/Docker installed?)"
            ) from exc
        if proc.returncode != 0:
            raise ExtractionError(
                f"{cmd[0]} failed ({proc.returncode}): {(proc.stderr or '')[-500:]}"
            )
