# Typed dependency graph kernel draft

Private experimental lower layer, not a stable model classifier. It consumes an
already supplied typed graph, never certifies the history-to-edge derivation,
INT/G1a/G1b, predicate completeness, transaction outcomes or source authenticity.
Six proposed model IDs remain unfrozen until the source and abstract-SI gates pass.

Input: JSON `{nodes:[id],edges:[{id,from,to,kind,source?}],complete:boolean,budgets?}`.
Kinds are ww, wr, rw-item, rw-predicate and rt. Nodes/edges have unique identities;
parallel types remain distinct and self dependencies are invalid. RT must be an
acyclic strict relation. Structural limits: 512 nodes, 100000 original edges,
8,388,608 UTF-16 input units; identities use the existing 1..256 identifier bounds.
Calculation budget maxEdgeScans defaults to 1000000 and may only be lowered.
Every original-edge filter visit, generated-state arc traversal and witness BFS
arc visit counts. Parent-chain proof recovery, expanded-edge materialization,
rotation tests and macro grouping also charge every visited edge. Input parsing
and final JSON encoding are excluded from this edge-scan count; input parsing is
subject to the structural input bounds above. No separate output-byte limit is
claimed by this prototype. Budget exhaustion
cannot produce graph absence. Incomplete supplied graphs do not yield absence.

Kernel categories: WW cycle, WR/WW cycle, full ordinary cycle containing an item
RW, full ordinary cycle containing any RW, a nonadjacent-RW closed walk, and any
cycle after including RT. Category searches are independent of the global shortest
cycle. No shortest flag is emitted. Mixed predicate/item paths are allowed in the
item category. Original edge JSON and IDs remain in witnesses.

Nonadjacency uses a bounded product graph: state (vertex,previousWasRW); D=WW/WR
resets the bit, and RW is allowed only when the bit is zero. A marked-RW arc in a
cyclic SCC supplies a closed walk with a RW and no adjacent RW even across the
wraparound. Keep repeated original vertices. Partition its rotated original walk
into D or D;RW macro steps for independent H=D union D;RW verification. Product
states are internal search state, never capture facts. This linear-size alternative
to materializing all H pairs needs the frozen independent elementary/H corpus and
an independent witness checker before promotion. No SO/RT enters generalized SI.

Graph-only constraint mapping: PL1=WW; PL2=D; PL2.99=D or itemRW; generalized
SI=D or nonadjacentRW; PL3=D or anyRW; strict=full graph including RT. A graph
absence result is not model acceptance. Missing direct-source/internal-consistency
obligations remain explicit and block any stable six-model conclusion.

References: frozen classification-v3-draft contract and independent corpus
frozen-511cad34d74743f5a93563fdc930d3ab; Jepsen G-nonadjacent and Cerone/Gotsman
Theorem 9 independently rechecked on 2026-10-21. This draft changes no public API.
