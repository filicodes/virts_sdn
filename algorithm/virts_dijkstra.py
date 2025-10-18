#!/usr/bin/env python3
# dijkstra_paths.py
# Simplified version: loads links.json and prints the shortest path between two nodes.
# Usage:
#   python3 nx.py pc1 pc2

import argparse
import json
import os
import sys
from typing import List, Tuple
import networkx as nx


# ---------- Load links directly from links.json ----------
def default_links_path() -> str:
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_dir, "..", "topology", "links.json"))

def load_links_from_json(path: str = None) -> list:
    """Reads links.json and returns a list of dicts"""
    if path is None:
        path = default_links_path()

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] links.json not found at: {path}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"[ERROR] Failed to read {path}: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(data, list):
        print("[ERROR] links.json must be a JSON array", file=sys.stderr)
        sys.exit(2)

    # Validate fields
    for L in data:
        for key in ("name", "u", "v", "delay_ms"):
            if key not in L:
                print(f"[ERROR] Missing key '{key}' in entry: {L}", file=sys.stderr)
                sys.exit(2)

    return data


# ---------- Build Graph ----------
def build_graph(links: List[dict]):
    """
    Build an undirected graph with delay as weight.
    """
    G = nx.Graph()
    for L in links:
        G.add_edge(
            L["u"],
            L["v"],
            weight=float(L["delay_ms"]),
            name=L["name"],
            delay_ms=float(L["delay_ms"]),
        )
    return G


def node_path_to_link_names(G, node_path: List[str]) -> List[str]:
    """Convert node path to link names"""
    names = []
    for a, b in zip(node_path, node_path[1:]):
        data = G.get_edge_data(a, b)
        if data is None:
            raise RuntimeError(f"No edge from {a} to {b} in graph.")
        names.append(data["name"])
    return names


# ---------- Shortest Path ----------
def shortest_path_links(G, src: str, dst: str) -> Tuple[List[str], float, List[str]]:
    """Run Dijkstra to find shortest path"""
    node_path = nx.shortest_path(G, src, dst, weight="weight")
    total = nx.path_weight(G, node_path, weight="weight")
    link_names = node_path_to_link_names(G, node_path)
    return link_names, total, node_path


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(
        description="Find shortest path (by delay) using Dijkstra algorithm."
    )
    ap.add_argument("src", help="Source node (e.g., pc1)")
    ap.add_argument("dst", help="Destination node (e.g., pc2)")
    args = ap.parse_args()

    # Load links
    links = load_links_from_json()

    # Build graph
    G = build_graph(links)

    # Compute shortest path
    try:
        lp, total, nodes = shortest_path_links(G, args.src, args.dst)
    except nx.NetworkXNoPath:
        print(f"No path exists between {args.src} and {args.dst}.")
        sys.exit(1)
    except nx.NodeNotFound as e:
        print(str(e))
        sys.exit(1)

    total_str = int(total) if float(total).is_integer() else total
    # print(f"{args.src} -> {args.dst}: {' -> '.join(lp)}  (total: {total_str} ms)")
    print(f"nodes: {','.join(nodes)} (total: {total_str} ms)")


if __name__ == "__main__":
    main()
