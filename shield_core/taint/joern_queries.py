# ruff: noqa: E501  (the Scala template lines below are long on purpose)
"""Build the Joern (CPGQL) taint script for one language from its LanguageSpec.

The YAML files in languages/ hold the sources, sinks and sanitizers. This module turns them
into Scala text, so no query is written by hand. Evidence for every rule: docs/taint_spike.md.

The generated script prints machine-readable lines that start with "@@":

    @@SRC <n>                                  number of source nodes
    @@SNK <n>                                  number of sink nodes
    @@SINK <file> <method> <line> <call code>  one per sink node (fields separated by TAB)
    @@FLOW <file> <method> <line> <call code> <sanitizer 0|1> <path>

A path is a list of elements joined by RS (0x1e); one element is label, line, code joined by
US (0x1f). Both separators are control characters that cannot appear in source code lines.

STATUS: the generated Scala follows the one-line `def` rules learned in the spike, but the
`@main` wrapper and `--param` use of `joern --script` are VERIFIED in 11/10/2026 and joern 4.0.647 in our image. If the script
mode fails, paste the output of `run_taint_spike.py --print-script` into the interactive shell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from languages.registry import LanguageSpec, SinkSpec, SourceSpec

FIELD_SEP = "\t"
STEP_SEP = "\x1f"  # between label, line and code of ONE path element
PATH_SEP = "\x1e"  # between path elements
# The same three separators as ESCAPE SEQUENCES, for the Scala source text (never raw control
# characters inside a Scala string literal).
_SCALA_FIELD = "\\t"
_SCALA_STEP = "\\u001f"
_SCALA_PATH = "\\u001e"

# joern_frontend (YAML) -> accessor of `importCode`. Python's accessor is `python`, NOT
# `pythonsrc` (docs/taint_spike.md, section 2).
IMPORT_ACCESSORS = {"NEWC": "c", "PYTHONSRC": "python", "JAVASRC": "java"}


def scala_string(text: str) -> str:
    """A Scala string literal: backslashes and double quotes escaped."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _call_selector(name: str | None, code: str | None) -> str:
    selector = "cpg.call"
    if name is not None:
        selector += f".name({scala_string(name)})"
    if code is not None:
        selector += f".code({scala_string(code)})"
    return selector


def source_expression(source: SourceSpec) -> str:
    if source.kind == "call":
        return _call_selector(source.name, source.code)
    if source.kind == "argument":
        return f"{_call_selector(source.name, source.code)}.argument({source.arg})"
    if source.kind == "parameter":
        return f"cpg.method.parameter.name({scala_string(source.name or '')})"
    raise ValueError(f"unknown source kind {source.kind!r}")


def sink_expression(sink: SinkSpec) -> str:
    selector = _call_selector(sink.name, sink.code)
    if sink.arg is not None:
        return f"{selector}.argument({sink.arg})"
    return f"{selector}.argument.filter(_.argumentIndex >= {sink.arg_from})"


def _definition(name: str, expressions: list[str]) -> str:
    # ONE line: a multi-line `def` with `++` at the line ends fails in the Scala 3 shell.
    body = " ++ ".join(expressions) if expressions else "Iterator.empty"
    return f"def {name}: Iterator[CfgNode] = {body}"


def source_definition(spec: LanguageSpec) -> str:
    return _definition("src", [source_expression(s) for s in spec.sources])


def sink_definition(spec: LanguageSpec) -> str:
    return _definition("snk", [sink_expression(s) for s in spec.sinks])


def sanitizer_pattern(spec: LanguageSpec) -> str:
    """One regex that matches a call name equal to any sanitizer pattern (whole-name match)."""
    return "|".join(f"(?:{pattern})" for pattern in spec.sanitizers) or "(?!)"


def build_script(spec: LanguageSpec, max_call_depth: int = 4) -> str:
    """The complete Scala script for `joern --script`. Parameter: inputPath (code folder)."""
    accessor = IMPORT_ACCESSORS.get(spec.joern_frontend)
    if accessor is None:
        raise ValueError(f"no importCode accessor known for frontend {spec.joern_frontend!r}")
    lines = [
        "import io.shiftleft.codepropertygraph.generated.nodes.{AstNode, Call, CfgNode}",
        "import io.joern.dataflowengineoss.language.*",
        "import io.joern.dataflowengineoss.queryengine.{EngineConfig, EngineContext}",
        "",
        "@main def exec(inputPath: String): Unit = {",
        f"  importCode.{accessor}(inputPath)",
        f"  {source_definition(spec)}",
        f"  {sink_definition(spec)}",
        f"  val sanitizers = {scala_string(sanitizer_pattern(spec))}",
        f"  val ctx = EngineContext(config = EngineConfig(maxCallDepth = {max_call_depth}))",
        '  def firstLine(s: String): String = s.split("\\n").head',
        "  def sinkCall(n: AstNode): String = n.astParent match {",
        "    case c: Call => firstLine(c.code)",
        "    case o => firstLine(o.code)",
        "  }",
        "  def where(n: AstNode): (String, String, String) = n match {",
        '    case c: CfgNode => (c.method.filename, c.method.name, c.lineNumber.map(_.toString).getOrElse("?"))',
        '    case _ => ("?", "?", "?")',
        "  }",
        # sanitizer test: the element IS a call, or it is an argument of one (c22a vs c22b)
        "  def callNames(e: AstNode): List[String] = e match {",
        "    case c: Call => List(c.name)",
        "    case _ => e.astParent match { case c: Call => List(c.name); case _ => Nil }",
        "  }",
        f'  println("@@SRC" + "{_SCALA_FIELD}" + src.size)',
        f'  println("@@SNK" + "{_SCALA_FIELD}" + snk.size)',
        "  snk.l.foreach { n => val w = where(n); "
        f'println(List("@@SINK", w._1, w._2, w._3, sinkCall(n)).mkString("{_SCALA_FIELD}")) }}',
        "  val flows = snk.reachableByFlows(src)(using ctx).l",
        "  flows.foreach { f =>",
        "    val last = f.elements.last; val w = where(last)",
        '    val san = if (f.elements.exists(e => callNames(e).exists(_.matches(sanitizers)))) "1" else "0"',
        f'    val path = f.elements.map(e => List(e.label, e.lineNumber.map(_.toString).getOrElse("?"), firstLine(e.code)).mkString("{_SCALA_STEP}")).mkString("{_SCALA_PATH}")',
        f'    println(List("@@FLOW", w._1, w._2, w._3, sinkCall(last), san, path).mkString("{_SCALA_FIELD}"))',
        "  }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ parsing the output


@dataclass(frozen=True)
class Step:
    label: str
    line: str
    code: str


@dataclass(frozen=True)
class Sink:
    file: str
    method: str
    line: str
    call: str


@dataclass(frozen=True)
class Flow:
    sink: Sink
    sanitizer_present: bool
    steps: tuple[Step, ...]


@dataclass
class Report:
    sources: int | None = None
    sinks_found: int | None = None
    sinks: list[Sink] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)


_TEMP_RE = re.compile(r"^tmp\d+(\s*=.*)?$")


def clean_steps(steps: list[Step]) -> tuple[Step, ...]:
    """Drop `tmpN` temporaries and collapse consecutive duplicates (spike rule 8)."""
    kept: list[Step] = []
    for step in steps:
        if _TEMP_RE.match(step.code.strip()):
            continue
        if kept and (kept[-1].code, kept[-1].line) == (step.code, step.line):
            continue
        kept.append(step)
    return tuple(kept)


def parse_output(text: str) -> Report:
    """Read the `@@` lines out of Joern's console output (all other lines are noise)."""
    report = Report()
    for raw in text.splitlines():
        marker = raw.find("@@")
        if marker < 0:
            continue
        parts = raw[marker:].rstrip("\r").split(FIELD_SEP)
        tag = parts[0]
        if tag == "@@SRC" and len(parts) == 2:
            report.sources = int(parts[1])
        elif tag == "@@SNK" and len(parts) == 2:
            report.sinks_found = int(parts[1])
        elif tag == "@@SINK" and len(parts) == 5:
            report.sinks.append(Sink(*parts[1:5]))
        elif tag == "@@FLOW" and len(parts) == 7:
            sink = Sink(*parts[1:5])
            steps = []
            for element in parts[6].split(PATH_SEP):
                pieces = element.split(STEP_SEP)
                if len(pieces) == 3:
                    steps.append(Step(*pieces))
            report.flows.append(Flow(sink, parts[5] == "1", clean_steps(steps)))
    return report
