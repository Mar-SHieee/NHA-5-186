import sys
import time
from pathlib import Path

from shield_core.extraction import CachedGraphExtractor
from shield_core.extraction.joern_extractor import JoernExtractor

path, lang = Path(sys.argv[1]), sys.argv[2]
ex = CachedGraphExtractor(JoernExtractor(docker_image="shield-joern"))
code = path.read_text(encoding="utf-8")

for attempt in (1, 2):
    t = time.time()
    g = ex.extract(code, lang)
    print(f"call {attempt}: {time.time() - t:.2f}s, {len(g.nodes)} nodes, {len(g.edges)} edges")

print(ex.cache.stats())
print("Node types:", {n.type for n in g.nodes})
print("Cache stats:", ex.cache.stats())

stubs = {n.id for n in g.nodes if n.type == "METHOD" and n.name.startswith("<operator>")}
parts = {e.dst for e in g.edges if e.src in stubs and e.type == "AST"}

print("Operator stubs:", len(stubs))
print("Operator parts:", len(parts))
print("Extraction test completed.")
