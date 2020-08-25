import logging
import os
import subprocess
from argparse import ArgumentError
from enum import Enum
from operator import itemgetter

from base.cgraph import MyGraph

from graph_io import GraphCollections
from utils import USE_NETWORKIT, USE_LIGRA, LIGRA_DIR

if USE_NETWORKIT:  # Use networkit library for approximate centrality calculation
    from networkit._NetworKit import PLM, Modularity


class Stat(Enum):
    """
    Common class for all graph statistics. Contains both global (calculated on all graph)
    and local (calculated for every node.
    To add new graph_stat write it in cyth/cstatistics.pyx, and add name remap here
    """

    def __init__(self, short: str, description: str):
        self.short = short
        self.description = description

    def __str__(self):
        return self.short

    NODES = 'n', "number of nodes"
    # NODES = 'n', "number of nodes"
    EDGES = 'e', "number of edges"
    AVG_DEGREE = 'avg-deg', "average (out)degree"
    MAX_DEGREE = 'max-deg', "maximal degree"
    # RECIPROCITY = 'reciprocity', "edge reciprocity"
    ASSORTATIVITY = 'ass', "nodes degree assortativity"
    # GINI = 'gini', "degree distribution Gini"
    # DRE = 'dre', "degree distr. rel. entropy"
    AVG_CC = 'avg-cc', "average local clustering coeff."
    # TRANSITIVITY = 'trans', "transitivity (global clustering coeff.)"  # FIXME how to implement
    # SPEC_NORM = 'spec-norm', r"spectral norm, $||A||_2$"
    # ALGEBRAIC_CONNECTIVITY = 'alg-conn', r"algebraic connectivity of largest WCC, $\lambda_2[\mathbf{L}]$"
    # ASSORTATIVITY_IN_IN = 'ass-in-in', "in-in degree assortativity"
    # ASSORTATIVITY_IN_OUT = 'ass-in-out', "in-out degree assortativity"
    # ASSORTATIVITY_OUT_IN = 'ass-out-in', "out-in degree assortativity"
    # ASSORTATIVITY_OUT_OUT = 'ass-out-out', "out-out degree assortativity"
    # DRE_IN = 'dre-in', "in degree distr. rel. entropy"
    # DRE_OUT = 'dre-out', "out degree distr. rel. entropy"
    # GINI_IN = 'gini-in', "in degree distr. Gini"
    # GINI_OUT = 'gini-out', "out degree distr. Gini"
    # WCC_COUNT = 'wcc', "number of WCCs"
    # SCC_COUNT = 'scc', "number of SCCs"
    MAX_WCC = 'wcc-max', "relative size of largest WCC"
    # MAX_SCC = 'scc-max', "relative size of largest SCC"
    # RADIUS = 'rad', "radius of largest WCC"
    # DIAMETER = 'diam', "diameter of largest WCC"
    DIAMETER_90 = 'diam90', "90%eff. diam. of largest WCC"
    # RADIUS_DIR = 'rad-dir', "directed radius of largest SCC"
    # DIAMETER_DIR = 'diam-dir', "directed diameter of largest SCC"
    # DIAMETER_90_DIR = 'diam90-dir', "90%eff. dir. diam. of largest SCC"

    DEGREE_DISTR = 'DegDistr', 'degree centrality'
    BETWEENNESS_DISTR = 'BtwDistr', 'betweenness centrality'
    ECCENTRICITY_DISTR = 'EccDistr', 'eccentricity centrality'
    CLOSENESS_DISTR = 'ClsnDistr', 'closeness centrality'
    PAGERANK_DISTR = 'PgrDistr', 'pagerank centrality'
    # CLUSTERING_DISTR = 'ClustDistr', 'clustering centrality'
    K_CORENESS_DISTR = 'KCorDistr', 'k-coreness centrality'

    PLM_COMMUNITIES = 'PLM-comms', 'PLM communities'
    PLM_MODULARITY = 'PLM-modularity', 'PLM communities modularity'

    LFR_COMMUNITIES = 'LFR-comms', 'LFR communities'


def get_top_centrality_nodes(graph: MyGraph, centrality, count=None, threshold=False):
    """
    Get top-count node ids of the graph sorted by centrality.
    :param graph: MyGraph
    :param centrality: centrality name, one of utils.CENTRALITIES
    :param count: number of nodes with top centrality to return. If None, return all nodes
    :param threshold # TODO make threshold cut
    :return: sorted list with top centrality
    """
    node_cent = list(graph[centrality].items())
    if centrality in [Stat.ECCENTRICITY_DISTR]:  # , Stat.CLOSENESS_DISTR
        reverse = False
    else:
        reverse = True
    sorted_node_cent = sorted(node_cent, key=itemgetter(1), reverse=reverse)

    # TODO how to choose nodes at the border centrality value?
    if not count:
        count = graph.nodes()
    return [n for (n, d) in sorted_node_cent[:count]]


def plm(graph: MyGraph):
    """
    Detect communities via PLM - Parallel Louvain Method and compute modularity.
    Set both the stats of the graph via setter.
    """
    node_map = {}
    nk = graph.networkit(node_map)
    plm = PLM(nk, refine=False, gamma=1)
    plm.run()
    partition = plm.getPartition()
    # for p in partition:
    comms_list = []
    for i in range(partition.numberOfSubsets()):
        nk_comm = partition.getMembers(i)
        comm = []
        for nk_i in nk_comm:
            i = node_map[nk_i]
            if i is not None:
                comm.append(i)
        if len(comm) > 0:
            comms_list.append(comm)

    mod = Modularity().getQuality(partition, nk)
    graph[Stat.PLM_COMMUNITIES] = comms_list
    graph[Stat.PLM_MODULARITY] = mod

    return comms_list, mod


def test():
    # # 1.
    # g = MyGraph(name='test', directed=False)
    # g.add_node(1)
    # g.add_node(2)
    # g.add_node(3)
    # g.add_node(4)
    # g.add_node(5)
    # g.add_edge(1, 2)
    # g.add_edge(3, 2)
    # g.add_edge(4, 2)
    # g.add_edge(4, 3)
    # g.add_edge(5, 4)
    # g.save()
    # print("N=%s E=%s" % (g.nodes(), g.edges()))
    #
    # # for stat in Stat:
    # #     print("%s = %s" % (stat.short, g[stat]))

    # 2.
    from graph_io import GraphCollections
    # graph = GraphCollections.get('test', 'other', giant_only=True)
    # graph = GraphCollections.get('petster-hamster', giant_only=True)
    # graph = GraphCollections.get('advogato', giant_only=True)
    # graph = GraphCollections.get('loc-brightkite_edges', giant_only=True)
    # graph = GraphCollections.get('dolphins', giant_only=True)
    # graph = GraphCollections.get('digg-friends', giant_only=True)
    # graph = GraphCollections.get('douban', giant_only=True)
    graph = GraphCollections.get('Pokec', giant_only=True)
    # graph = GraphCollections.get('GP', giant_only=True)
    # graph = GraphCollections.get('Lj', giant_only=True)
    # graph = GraphCollections.get('com-youtube', giant_only=True)

    # graph = GraphCollections.get('karate', 'netrepo', giant_only=True)
    # graph = GraphCollections.get('ca-MathSciNet', 'netrepo', giant_only=True)

    stat = Stat.PLM_MODULARITY

    print(graph.name, graph.nodes(), graph.edges(), stat)
    node_prop = graph[stat]
    print(str(node_prop))

    # test_approx_stat(graph, stat)


def test_stats():
    from graph_io import GraphCollections
    graph = GraphCollections.get('dolphins', giant_only=True)

    for stat in Stat:
        print("%s = %s" % (stat.short, graph[stat]))


def test_approx_stat(graph: MyGraph, stat: Stat):
    """ Measure the intersection of top-set centrality nodes found by snap vs networkit
    """
    if stat in [Stat.CLOSENESS_DISTR, Stat.BETWEENNESS_DISTR]:
        node_map = {}
        g = graph.networkit(node_map)
        # centrality = Betweenness(g, normalized=False)
        # centrality = DegreeCentrality(g, normalized=False)
        # centrality = ApproxBetweenness(g, epsilon=0.01, delta=0.1)
        # centrality = EstimateBetweenness(g, nSamples=1000, normalized=False, parallel=True)
        # centrality.run()

        # print(g.nodes())
        # print(node_map)
        # print(centrality.scores())
        count = int(0.1*graph.nodes())
        snap = sorted(list(eval(open(graph.path + '_stats/%s (snap)' % stat.short, 'r').read()).items()), key=itemgetter(1), reverse=True)
        top_snap = set([n for (n, d) in snap[:count]])
        nk = sorted(list(eval(open(graph.path + '_stats/%s' % stat.short, 'r').read()).items()), key=itemgetter(1), reverse=True)
        top_nk = set([n for (n, d) in nk[:count]])

        # scores = centrality.scores()
        # print(scores)
        # node_cent = {node_map[i+1]: score for i, score in enumerate(scores)}
        # sorted_node_cent = sorted(list(node_cent.items()), key=itemgetter(1), reverse=True)
        # print(node_cent)
        # top = set([n for (n, d) in sorted_node_cent[:count]])
        print("counted")
        print(len(top_snap.intersection(top_nk))/count)

        # print({i+1: val for i, val in enumerate(centrality.scores())})

    elif stat == Stat.ECCENTRICITY_DISTR:
        assert USE_LIGRA

        # duplicate edges
        path = graph.path
        path_dup = path + '_dup'
        with open(path_dup, 'w') as out_file:
            for line in open(path, 'r'):
                if len(line) < 3:
                    break
                i, j = line.split()
                out_file.write('%s %s\n' % (i, j))
                out_file.write('%s %s\n' % (j, i))

        # convert to Adj
        path_lig = path + '_ligra'
        ligra_converter_command = "./utils/SNAPtoAdj '%s' '%s'" % (path_dup, path_lig)
        retcode = subprocess.Popen(ligra_converter_command, cwd=LIGRA_DIR, shell=True, stdout=sys.stdout, stderr=sys.stderr).wait()
        if retcode != 0:
            raise RuntimeError("Ligra converter failed: '%s'" % ligra_converter_command)

        # Run Ligra kBFS
        path_lig_ecc = path + '_ecc'
        ligra_ecc_command = "./apps/eccentricity/kBFS-Ecc -s -rounds 0 -out '%s' '%s'" % (path_lig_ecc, path_lig)
        # ligra_ecc_command = "./apps/eccentricity/kBFS-Exact -s -rounds 0 -out '%s' '%s'" % (path_lig_ecc, path_lig)
        retcode = subprocess.Popen(ligra_ecc_command, cwd=LIGRA_DIR, shell=True, stdout=sys.stdout, stderr=sys.stderr).wait()
        if retcode != 0:
            raise RuntimeError("Ligra kBFS-Ecc failed: %s" % ligra_ecc_command)

        # read and convert ecc
        node_ecc = {}
        for n, line in enumerate(open(path_lig_ecc)):
            if graph.has_node(n):
                node_ecc[n] = int(line)
        assert len(node_ecc) == graph.nodes()
        with open(graph.path + '_stats/%s' % stat.short, 'w') as f:
            f.write(str(node_ecc))

        # print(node_ecc)
        os.remove(path_dup)
        os.remove(path_lig)
        os.remove(path_lig_ecc)

        # compare
        count = int(0.35*graph.nodes())
        snap = sorted(list(eval(open(graph.path + '_stats/%s (snap)' % stat.short, 'r').read()).items()), key=itemgetter(1), reverse=True)
        top_snap = set([n for (n, d) in snap[:count]])
        lig = sorted(list(eval(open(graph.path + '_stats/%s' % stat.short, 'r').read()).items()), key=itemgetter(1), reverse=True)
        top_lig = set([n for (n, d) in lig[:count]])

        print("counted")
        print(len(top_snap.intersection(top_lig))/count)


def main():
    import argparse
    stats = [s.name for s in Stat]
    parser = argparse.ArgumentParser(
        description='Compute statistics for graphs. Graph is specified via path (-p) or name in Konect (-n).')
    parser.add_argument('-p', '--path', required=False, nargs='+', help='path to input graphs as edgelist')
    parser.add_argument('-n', '--name', required=False, nargs='+', help='names/codes of input graphs in Konect')
    parser.add_argument('-c', '--collection', required=False, help="graphs collection: 'konect' or 'netrepo'")
    # parser.add_argument('-d', action='store_true', help='specify if graph is directed')
    parser.add_argument('-f', '--full', action='store_true', help='print full statistics value')
    parser.add_argument('-s', '--stats', required=True, nargs='+', choices=stats,
                        help='node statistics to compute')

    args = parser.parse_args()
    # print(args)
    if (1 if args.path else 0) + (1 if args.name else 0) != 1:
        raise ArgumentError("Exactly one of '-p' and '-n' args must be specified.")

    for s in args.stats:
        assert s in stats, "Unknown statistics %s, available are: %s" % (s, stats)

    if args.path:
        graphs = [MyGraph(path=p, name='', directed=args.d) for p in args.path]
    else:
        collection = args.collection if args.collection else None
        graphs = [GraphCollections.get(n, collection, giant_only=True) for n in args.name]

    for graph in graphs:
        for s in args.stats:
            # print("Computing %s centrality for %s..." % (c, args.path))
            v = graph[s]
            if not args.full:  # short print
                v = (str(v)[:100] + '...') if len(str(v)) > 100 else str(v)
            logging.info("%s: %s" % (s, v))


if __name__ == '__main__':
    logging.basicConfig(format='%(name)s:%(levelname)s:%(message)s')
    logging.getLogger('matplotlib.font_manager').setLevel(logging.INFO)
    logging.getLogger('matplotlib').setLevel(logging.INFO)
    logging.getLogger().setLevel(logging.DEBUG)

    # # imports workaround https://stackoverflow.com/questions/26589805/python-enums-across-modules
    import sys
    sys.modules['statistics'] = sys.modules['__main__']

    # test_stats()
    # test()
    main()