#!/usr/bin/env python3
"""
Physlr: Physical Mapping of Linked Reads
"""

import argparse
import itertools
import multiprocessing
import os
import sys
import timeit

import networkx as nx
import tqdm

from physlr.minimerize import minimerize
from physlr.benv.graph import Graph
from physlr.read_fasta import read_fasta

t0 = timeit.default_timer()

def quantile(quantiles, xs):
    "Return the specified quantiles p of xs."
    sorted_xs = sorted(xs)
    return [sorted_xs[round(p * (len(sorted_xs)-1))] for p in quantiles]

def progress_bar_for_file(fin):
    "Return a progress bar for a file."
    return tqdm.tqdm(
        total=os.fstat(fin.fileno()).st_size,
        mininterval=1, smoothing=0.1,
        bar_format="{percentage:4.1f}% {elapsed} ETA {remaining} {bar}")

def progress(iterator):
    "Return an iterator that displays a progress bar."
    return tqdm.tqdm(
        iterator, mininterval=1, smoothing=0.1,
        bar_format="{percentage:4.1f}% {elapsed} ETA {remaining} {bar}")

class Physlr:
    """
    Physlr: Physical Mapping of Linked Reads
    """

    @staticmethod
    def write_tsv(g, fout):
        "Write a graph in TSV format."
        if "m" in next(iter(g.nodes.values())):
            print("U\tn\tm", file=fout)
        else:
            print("U\tn", file=fout)
        for u, prop in g.nodes.items():
            if "m" in prop:
                print(u, prop["n"], prop["m"], sep="\t", file=fout)
            else:
                print(u, prop["n"], sep="\t", file=fout)
        print("\nU\tV\tn", file=fout)
        for e, prop in g.edges.items():
            u, v = sorted(e)
            print(u, v, prop["n"], sep="\t", file=fout)

    @staticmethod
    def write_graph(g, fout, graph_format):
        "Write a graph."
        if graph_format == "gv":
            nx.drawing.nx_agraph.write_dot(g, sys.stdout)
        elif graph_format == "tsv":
            Physlr.write_tsv(g, fout)
        else:
            print("Unknown graph format:", graph_format, file=sys.stderr)
            exit(1)

    @staticmethod
    def read_tsv(g, filename):
        "Read a graph in TSV format."
        with open(filename) as fin:
            progressbar = progress_bar_for_file(fin)
            line = fin.readline()
            progressbar.update(len(line))
            if line not in ["U\tn\n", "U\tn\tm\n"]:
                print("Unexpected header:", line, file=sys.stderr)
                exit(1)
            reading_vertices = True
            for line in fin:
                progressbar.update(len(line))
                if line == "\n":
                    line = fin.readline()
                    progressbar.update(len(line))
                    if line == "U\tV\tn\n":
                        reading_vertices = False
                    else:
                        print("Unexpected header:", line, file=sys.stderr)
                        exit(1)
                    line = fin.readline()
                    progressbar.update(len(line))
                xs = line.split()
                if reading_vertices:
                    if len(xs) == 2:
                        g.add_node(xs[0], n=int(xs[1]))
                    elif len(xs) == 3:
                        g.add_node(xs[0], n=int(xs[1]), m=int(xs[2]))
                    else:
                        print("Unexpected row:", line, file=sys.stderr)
                        exit(1)
                else:
                    if len(xs) == 3:
                        g.add_edge(xs[0], xs[1], n=int(xs[2]))
                    else:
                        print("Unexpected row:", line, file=sys.stderr)
                        exit(1)
        progressbar.close()
        return g

    @staticmethod
    def read_graphviz(g, filename):
        "Read a GraphViz file."
        graph = nx.drawing.nx_agraph.read_dot(filename)
        for vprop in graph.nodes().values():
            vprop["n"] = int(vprop["n"])
        for _, _, eprop in graph.edges.data():
            eprop["n"] = int(eprop["n"])
        return nx.algorithms.operators.binary.compose(g, graph)

    @staticmethod
    def sort_vertices(g):
        """
        Sort the vertices of a graph by name.
        There may be more than one tree with the same minimum or maximum weight.
        Which spanning tree is chosen depends on the order of the vertices.
        Sort the vertices of a graph by name to ensure consistent results.
        """
        gsorted = nx.Graph()
        gsorted.add_nodes_from(sorted(g.nodes().items()))
        gsorted.add_edges_from((e[0], e[1], eprops) for e, eprops in g.edges().items())
        return gsorted

    @staticmethod
    def read_graph(filenames):
        "Read a graph in either GraphViz or TSV format."
        print(int(timeit.default_timer() - t0), "Reading", *filenames, file=sys.stderr)
        read_gv = False
        g = nx.Graph()
        for filename in filenames:
            with open(filename) as fin:
                c = fin.read(1)
                if c == "s":
                    g = Physlr.read_graphviz(g, filename)
                    read_gv = True
                elif c == "U":
                    g = Physlr.read_tsv(g, filename)
                else:
                    print("Unexpected graph format", c + fin.readline(), file=sys.stderr)
                    sys.exit(1)
        print(int(timeit.default_timer() - t0), "Read", *filenames, file=sys.stderr)
        if read_gv:
            print(int(timeit.default_timer() - t0), "Sorting the vertices", file=sys.stderr)
            g = Physlr.sort_vertices(g)
            print(int(timeit.default_timer() - t0), "Sorted the vertices", file=sys.stderr)
        return g

    @staticmethod
    def remove_singletons(g):
        "Remove singletons (isolated vertices) and return the number removed."
        singletons = [u for u, deg in g.degree if deg == 0]
        g.remove_nodes_from(singletons)
        return len(singletons)

    @staticmethod
    def filter_edges(g, arg_n):
        "Remove edges with n < arg_n."
        if arg_n == 0:
            return
        edges = [(u, v) for u, v, n in progress(g.edges(data="n")) if n < arg_n]
        g.remove_edges_from(edges)
        n_singletons = Physlr.remove_singletons(g)
        print(
            int(timeit.default_timer() - t0),
            "Removed", len(edges), "edges with fewer than", arg_n, "common markers.",
            "Removed", n_singletons, "isolated vertices.",
            file=sys.stderr)

    @staticmethod
    def read_minimizers(filenames):
        "Read minimizers in TSV format."
        bxtomin = {}
        for filename in filenames:
            print(int(timeit.default_timer() - t0), "Reading", filename, file=sys.stderr)
            with open(filename) as fin:
                progressbar = progress_bar_for_file(fin)
                for line in fin:
                    progressbar.update(len(line))
                    fields = line.split(None, 1)
                    if len(fields) < 2:
                        continue
                    bx = fields[0]
                    if bx not in bxtomin:
                        bxtomin[bx] = set()
                    bxtomin[bx].update(int(x) for x in fields[1].split())
                progressbar.close()
            print(int(timeit.default_timer() - t0), "Read", filename, file=sys.stderr)
        return bxtomin

    @staticmethod
    def construct_minimizers_to_barcodes(bxtomin):
        "Construct a dictionary of minimizers to barcodes."
        mintobx = {}
        for bx, minimizers in progress(bxtomin.items()):
            for x in minimizers:
                if x not in mintobx:
                    mintobx[x] = set()
                mintobx[x].add(bx)
        print(int(timeit.default_timer() - t0), "Indexed minimizers", file=sys.stderr)
        return mintobx

    @staticmethod
    def triconnected_components(g):
        "Return the triconnected components of the graph."
        components = []
        for component in nx.biconnected_components(g):
            if len(component) < 3:
                components.append(component)
                continue
            try:
                cuts = next(nx.all_node_cuts(g.subgraph(component), k=2))
                if len(cuts) > 2:
                    components.append(component)
                    continue
                assert len(cuts) == 2
                subcomponents = list(nx.connected_components(g.subgraph(component - cuts)))
                if len(subcomponents) == 1:
                    components.append(component)
                    continue
                components += subcomponents
                components.append(cuts)
            except StopIteration:
                components.append(component)
        return components

    @staticmethod
    def diameter_of_tree(g, weight=None):
        """
        Compute the diameter of a tree.
        The diameter of an arbitrary component is returned if there are multiple components."
        """
        u = next(iter(g.nodes))
        paths = nx.shortest_path_length(g, u, weight=weight)
        u, _ = max(paths.items(), key=lambda x: x[1])
        paths = nx.shortest_path_length(g, u, weight=weight)
        v, diameter = max(paths.items(), key=lambda x: x[1])
        return (u, v, diameter)

    @staticmethod
    def determine_backbones_of_trees(g):
        "Determine the backbones of the maximum spanning trees."
        paths = []
        for component in nx.connected_components(g):
            gcomponent = g.subgraph(component)
            u, v, _ = Physlr.diameter_of_tree(gcomponent, weight="n")
            path = nx.shortest_path(gcomponent, u, v, weight="n")
            paths.append(path)
        paths.sort(key=len, reverse=True)
        return paths

    @staticmethod
    def determine_backbones(g):
        "Determine the backbones of the graph."
        g = g.copy()
        backbones = []
        while not nx.is_empty(g):
            gmst = nx.maximum_spanning_tree(g, weight="n")
            paths = Physlr.determine_backbones_of_trees(gmst)
            backbones.extend(paths)
            vertices = [u for path in paths for u in path]
            neighbors = [v for u in vertices for v in g.neighbors(u)]
            g.remove_nodes_from(vertices)
            g.remove_nodes_from(neighbors)
            Physlr.remove_singletons(g)
        backbones.sort(key=len, reverse=True)
        print(int(timeit.default_timer() - t0), "Determined the backbone paths", file=sys.stderr)
        return backbones

    def physlr_filter(self):
        "Filter a graph."
        g = self.read_graph(self.args.FILES)
        Physlr.filter_edges(g, self.args.n)
        if self.args.M is not None:
            vertices = [u for u, prop in g.nodes().items() if prop["m"] >= self.args.M]
            g.remove_nodes_from(vertices)
            print(
                int(timeit.default_timer() - t0),
                "Removed", len(vertices), "vertices with", self.args.M, "or more molecules.",
                file=sys.stderr)
        if self.args.min_component_size > 0:
            ncomponents, nvertices = 0, 0
            vertices = set()
            for component in nx.connected_components(g):
                if len(component) < self.args.min_component_size:
                    vertices.update(component)
                    ncomponents += 1
                    nvertices += len(component)
            g.remove_nodes_from(vertices)
            print(
                int(timeit.default_timer() - t0),
                "Removed", nvertices, "vertices in", ncomponents, "components",
                "with fewer than", self.args.min_component_size, "vertices in a component.",
                file=sys.stderr)
        self.write_graph(g, sys.stdout, self.args.graph_format)

    def physlr_subgraph(self):
        "Extract a vertex-induced subgraph."
        if self.args.d not in (0, 1):
            exit("error: Only -d0 and -d1 are currently supported.")
        vertices = set(self.args.v.split())
        exclude_vertices = set(self.args.exclude_vertices.split())
        g = self.read_graph(self.args.FILES)
        if self.args.d == 1:
            vertices.update(v for u in vertices for v in g.neighbors(u))
        subgraph = g.subgraph(vertices - exclude_vertices)
        print(int(timeit.default_timer() - t0), "Extracted subgraph", file=sys.stderr)
        self.write_graph(subgraph, sys.stdout, self.args.graph_format)
        print(int(timeit.default_timer() - t0), "Wrote graph", file=sys.stderr)

    def physlr_indexfa(self):
        "Index a set of sequences. The output file format is TSV."
        for filename in self.args.FILES:
            with open(filename) as fin:
                for name, seq, _ in read_fasta(fin):
                    print(name, "\t", sep="", end="")
                    print(*minimerize(self.args.k, self.args.w, seq.upper()))

    def physlr_indexlr(self):
        "Index a set of linked reads. The output file format is TSV."
        for filename in self.args.FILES:
            with open(filename) as fin:
                for _, seq, bx in read_fasta(fin):
                    print(bx, "\t", sep="", end="")
                    print(*minimerize(self.args.k, self.args.w, seq.upper()))

    def physlr_count_markers(self):
        "Count the frequency of each minimizer."
        bxtomin = self.read_minimizers(self.args.FILES)
        freq = {}
        for xs in bxtomin.values():
            for x in xs:
                if x in freq:
                    freq[x] += 1
                else:
                    freq[x] = 1
        print("Marker\tCount")
        for x, c in sorted(freq.items(), key=lambda x: x[1]):
            if c >= 2:
                print(x, c, sep="\t")

    def physlr_intersect(self):
        "Print the minimizers in the intersection of each pair of barcodes."
        if self.args.n == 0:
            self.args.n = 1
        bxtomin = self.read_minimizers(self.args.FILES)
        mintobx = self.construct_minimizers_to_barcodes(bxtomin)
        if self.args.v:
            pairs = itertools.combinations(self.args.v.split(), 2)
        else:
            pairs = {(u, v) for bxs in mintobx.values() for u, v in itertools.combinations(bxs, 2)}
        for u, v in pairs:
            common = bxtomin[u] & bxtomin[v]
            if len(common) >= self.args.n:
                print(u, v, "", sep="\t", end="")
                print(*common)

    def physlr_overlap(self):
        "Read a sketch of linked reads and find overlapping barcodes."
        bxtomin = self.read_minimizers(self.args.FILES)
        mintobx = self.construct_minimizers_to_barcodes(bxtomin)

        # Remove markers that occur only once.
        num_markers = len(mintobx)
        singletons = {x for x, bxs in progress(mintobx.items()) if len(bxs) < 2}
        for x in progress(singletons):
            del mintobx[x]
        for markers in progress(bxtomin.values()):
            markers -= singletons
        print(
            int(timeit.default_timer() - t0),
            "Removed", len(singletons), "minimizers that occur only once of", num_markers,
            f"({round(100 * len(singletons) / num_markers, 2)}%)", file=sys.stderr)

        # Identify repetitive markers.
        q1, q2, q3 = quantile([0.25, 0.5, 0.75], (len(bxs) for bxs in mintobx.values()))
        whisker = int(q3 + self.args.coef * (q3 - q1))
        if self.args.C is None:
            self.args.C = whisker
        print(
            int(timeit.default_timer() - t0),
            " Minimizer frequency: Q1=", q1, " Q2=", q2, " Q3=", q3,
            " Q3+", self.args.coef, "*(Q3-Q1)=", whisker,
            " C=", self.args.C, sep="", file=sys.stderr)

        # Remove frequent (likely repetitive) minimizers.
        repetitive = {x for x, bxs in mintobx.items() if len(bxs) >= self.args.C}
        for xs in progress(bxtomin.values()):
            xs -= repetitive
        print(
            int(timeit.default_timer() - t0),
            "Removed", len(repetitive), "most frequent minimizers of", len(mintobx),
            f"({round(100 * len(repetitive) / len(mintobx), 2)}%)",
            file=sys.stderr)

        # Add the vertices.
        g = nx.Graph()
        for u, minimizers in sorted(progress(bxtomin.items())):
            g.add_node(u, n=len(minimizers))
        print(int(timeit.default_timer() - t0), "Sorted the vertices", file=sys.stderr)

        # Add the overlap edges.
        for x, bxs in progress(mintobx.items()):
            if x in repetitive:
                continue
            for u, v in itertools.combinations(bxs, 2):
                if not g.has_edge(u, v):
                    g.add_edge(u, v, n=len(bxtomin[u] & bxtomin[v]))
        print(int(timeit.default_timer() - t0), "Constructed the similarity graph", file=sys.stderr)

        # Write the graph.
        self.write_tsv(g, sys.stdout)
        print(int(timeit.default_timer() - t0), "Wrote graph", file=sys.stderr)

    def physlr_mst(self):
        "Determine the maximum spanning tree."
        g = self.read_graph(self.args.FILES)
        gmst = nx.algorithms.tree.mst.maximum_spanning_tree(g, weight="n")
        self.write_graph(gmst, sys.stdout, self.args.graph_format)

    def physlr_backbone(self):
        "Determine the backbone path of the graph."
        g = self.read_graph(self.args.FILES)
        backbones = self.determine_backbones(g)
        for backbone in backbones:
            print(*backbone)

    def physlr_backbone_graph(self):
        "Determine the backbone-induced subgraph."
        g = self.read_graph(self.args.FILES)
        Physlr.remove_singletons(g)
        backbones = self.determine_backbones(g)
        backbone = (u for path in backbones for u in path)
        subgraph = self.sort_vertices(g.subgraph(backbone))
        self.write_graph(subgraph, sys.stdout, self.args.graph_format)
        print(int(timeit.default_timer() - t0), "Output the backbone subgraph", file=sys.stderr)

    def physlr_biconnected_components(self):
        "Separate a graph into its biconnected components by removing its cut vertices."
        g = self.read_graph(self.args.FILES)
        cut_vertices = list(nx.articulation_points(g))
        g.remove_nodes_from(cut_vertices)
        print(
            int(timeit.default_timer() - t0),
            "Removed", len(cut_vertices), "cut vertices.", file=sys.stderr)
        self.write_graph(g, sys.stdout, self.args.graph_format)
        print(int(timeit.default_timer() - t0), "Wrote graph", file=sys.stderr)

    def physlr_tiling_graph(self):
        "Determine the minimum-tiling-path-induced subgraph."
        g = self.read_graph(self.args.FILES)
        Physlr.filter_edges(g, self.args.n)
        backbones = self.determine_backbones(g)
        tiling = {u for path in backbones for u in nx.shortest_path(g, path[0], path[-1])}
        subgraph = g.subgraph(tiling)
        self.write_graph(subgraph, sys.stdout, self.args.graph_format)

    def physlr_count_molecules(self):
        "Estimate the nubmer of molecules per barcode."
        g = self.read_graph(self.args.FILES)
        Physlr.filter_edges(g, self.args.n)
        print(
            int(timeit.default_timer() - t0),
            "Separating barcodes into molecules", file=sys.stderr)

        for u, prop in progress(g.nodes.items()):
            subgraph = g.subgraph(g.neighbors(u))
            # Ignore K3 (triangle) components.
            prop["m"] = sum(
                1 for component in nx.biconnected_components(subgraph)
                if len(component) >= 4)
        self.write_graph(g, sys.stdout, self.args.graph_format)

    @staticmethod
    def determine_molecules(g, u):
        "Assign the neighbours of this vertex to molecules."
        cut_vertices = set(nx.articulation_points(g.subgraph(g.neighbors(u))))
        components = list(nx.connected_components(g.subgraph(set(g.neighbors(u)) - cut_vertices)))
        components.sort(key=len, reverse=True)
        return u, {v: i for i, vs in enumerate(components) for v in vs}

    @staticmethod
    def determine_molecules_process(u):
        """
        Assign the neighbours of this vertex to molecules.
        The graph is passed in the class variable Physlr.graph.
        """
        return Physlr.determine_molecules(Physlr.graph, u)

    def physlr_molecules(self):
        "Separate barcodes into molecules."
        gin = self.read_graph(self.args.FILES)
        Physlr.filter_edges(gin, self.args.n)
        print(
            int(timeit.default_timer() - t0),
            "Separating barcodes into molecules", file=sys.stderr)

        # Parition the neighbouring vertices of each barcode into molecules.
        if self.args.threads == 1:
            molecules = dict(self.determine_molecules(gin, u) for u in progress(gin))
        else:
            Physlr.graph = gin
            with multiprocessing.Pool(self.args.threads) as pool:
                molecules = dict(pool.map(
                    self.determine_molecules_process, progress(gin), chunksize=100))
            Physlr.graph = None
        print(int(timeit.default_timer() - t0), "Identified molecules", file=sys.stderr)

        # Add vertices.
        gout = nx.Graph()
        for u, vs in sorted(molecules.items()):
            n = gin.nodes[u]["n"]
            nmolecules = 1 + max(vs.values()) if vs else 0
            for i in range(nmolecules):
                gout.add_node(f"{u}_{i}", n=n)

        print(
            int(timeit.default_timer() - t0),
            "Identified", gout.number_of_nodes(), "molecules in",
            gin.number_of_nodes(), "barcodes.",
            round(gout.number_of_nodes() / gin.number_of_nodes(), 2), "mean molecules per barcode",
            file=sys.stderr)

        # Add edges.
        for (u, v), prop in gin.edges.items():
            # Skip singleton and cut vertices, which are excluded from the partition.
            if v not in molecules[u] or u not in molecules[v]:
                continue
            u_molecule = molecules[u][v]
            v_molecule = molecules[v][u]
            gout.add_edge(f"{u}_{u_molecule}", f"{v}_{v_molecule}", n=prop["n"])
        print(int(timeit.default_timer() - t0), "Separated molecules", file=sys.stderr)

        self.write_graph(gout, sys.stdout, self.args.graph_format)
        print(int(timeit.default_timer() - t0), "Wrote graph", file=sys.stderr)

    def physlr_graph(self, fmt):
        "Generate a graph from the minimizer index."
        graph = Graph()
        for filename in self.args.FILES:
            with open(filename) as fin:
                graph.read_index(fin)
                graph.output_graph(pmin=0, fmt=fmt)

    @staticmethod
    def parse_arguments():
        "Parse the command line arguments."
        argparser = argparse.ArgumentParser()
        argparser.add_argument(
            "-t", "--threads", action="store", dest="threads", type=int,
            default=min(16, os.cpu_count()),
            help="number of threads [16 or number of CPU]")
        argparser.add_argument(
            "-k", "--k", action="store", type=int,
            help="size of a k-mer (bp)")
        argparser.add_argument(
            "-w", "--window", action="store", dest="w", type=int,
            help="number of k-mers in a window of size k + w - 1 bp")
        argparser.add_argument(
            "-c", "--coef", action="store", dest="coef", type=float, default=1.5,
            help="ignore markers that occur in Q3+c*(Q3-Q1) or more barcodes [0]")
        argparser.add_argument(
            "-C", "--max-count", action="store", dest="C", type=int,
            help="ignore markers that occur in C or more barcodes [None]")
        argparser.add_argument(
            "-M", "--max-molecules", action="store", dest="M", type=int,
            help="remove barcodes with M or more molecules [None]")
        argparser.add_argument(
            "-n", "--min-n", action="store", dest="n", type=int, default=0,
            help="remove edges with fewer than n shared markers [0]")
        argparser.add_argument(
            "--min-component-size", action="store", dest="min_component_size", type=int, default=0,
            help="remove components with fewer than N vertices [0]")
        argparser.add_argument(
            "-v", "--vertices", action="store", dest="v",
            help="list of vertices")
        argparser.add_argument(
            "-V", "--exclude-vertices", action="store", dest="exclude_vertices",
            help="list of vertices to exclude")
        argparser.add_argument(
            "-d", "--distance", action="store", dest="d", type=int, default=0,
            help="include vertices within d edges away")
        argparser.add_argument(
            "-O", "--output-format", action="store", dest="graph_format", default="tsv",
            help="the output graph file format [tsv]")
        argparser.add_argument(
            "command",
            help="A command")
        argparser.add_argument(
            "FILES", nargs="+",
            help="FASTA/FASTQ, TSV, or GraphViz format")
        return argparser.parse_args()

    def __init__(self):
        "Create a new instance of Physlr."
        self.args = self.parse_arguments()
        self.args.FILES = ["/dev/stdin" if s == "-" else s for s in self.args.FILES]

    def main(self):
        "Run Physlr."
        if self.args.command == "backbone":
            self.physlr_backbone()
        elif self.args.command == "backbone-graph":
            self.physlr_backbone_graph()
        elif self.args.command == "biconnected-components":
            self.physlr_biconnected_components()
        elif self.args.command == "count-markers":
            self.physlr_count_markers()
        elif self.args.command == "count-molecules":
            self.physlr_count_molecules()
        elif self.args.command == "filter":
            self.physlr_filter()
        elif self.args.command == "indexfa":
            self.physlr_indexfa()
        elif self.args.command == "indexlr":
            self.physlr_indexlr()
        elif self.args.command == "graphtsv":
            self.physlr_graph("tsv")
        elif self.args.command == "graphgv":
            self.physlr_graph("graphviz")
        elif self.args.command == "intersect":
            self.physlr_intersect()
        elif self.args.command == "molecules":
            self.physlr_molecules()
        elif self.args.command == "mst":
            self.physlr_mst()
        elif self.args.command == "overlap":
            self.physlr_overlap()
        elif self.args.command == "subgraph":
            self.physlr_subgraph()
        elif self.args.command == "tiling-graph":
            self.physlr_tiling_graph()
        else:
            print("Unrecognized command:", self.args.command, file=sys.stderr)
            exit(1)

def main():
    "Run Physlr."
    Physlr().main()

if __name__ == "__main__":
    main()
