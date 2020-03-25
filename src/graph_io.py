import os
import shutil
import urllib
import igraph
import logging
import patoolib

from utils import GRAPHS_DIR

COLLECTIONS = ['konect', 'networkrepository']


class MyGraph(object):
    def __init__(self, path, name, directed=False, weighted=False, format='ij'):
        self.snap_graph = None
        self.igraph_graph = None
        self.networkit_graph = None
        self.path = path
        self.name = name
        self.directed = directed
        self.weighted = weighted
        self.format = format
        # self.collection = collection
        # self.category = category
        # TODO add properties maps

    @property
    def snap(self):
        if not self.snap_graph:
            import snap
            self.snap_graph = snap.LoadEdgeList(
                snap.PNGraph if self.directed else snap.PUNGraph, self.path, 0, 1)
        return self.snap_graph

    @property
    def igraph(self):
        if not self.igraph_graph:
            from igraph import summary
            g = igraph.Graph()
            g = g.Read_Edgelist(self.path, directed=self.directed)
            logging.info("Read igraph %s" % summary(g))
            self.igraph_graph = g
        return self.igraph_graph

    @property
    def networkit(self):
        if not self.networkit_graph:
            import networkit as nk
            # XXX suppose numbering from 1
            self.networkit_graph = nk.readGraph(
                self.path, nk.Format.EdgeListSpaceOne, directed=self.directed)

        return self.networkit_graph


def reformat_graph_file(path, out_path, out_format='ij', ignore_lines_starting_with='#%',
                        remove_original=False):
    """

    :param path:
    :param out_path:
    :param out_format: 'ij', 'ijw', 'ijwt'
    :param ignore_lines_starting_with:
    :param remove_original:
    :return:
    """
    in_format = None
    with open(out_path, 'w') as out_file:
        for line in open(path, 'r'):
            if line[0] in ignore_lines_starting_with:  # Filter comments
                continue
            line = line.rstrip('\n')
            assert line[0].isdigit(), "expected alpha-numeric line: '%s'" % line
            if not in_format:
                # Define format
                items = line.split()
                in_format = 'ijwt'[:len(items)]
                if len(out_format) > len(in_format):
                    raise Exception("Could not reformat from '%s' to '%s'" % (in_format, out_format))
                logging.info("Reformatting %s->%s for '%s' ..." % (in_format, out_format, path))

            items = line.split()
            # TODO format depending on each symbol of 'ijwt'
            res_line = ' '.join(items[:len(out_format)]) + '\n'
            out_file.write(res_line)

    if remove_original:
        os.remove(path)
    logging.info("Reformatting finished '%s'." % out_path)


class GraphCollections(object):
    konect_url_pattern = 'http://konect.uni-koblenz.de/downloads/tsv/%s.tar.bz2'
    networkrepository_url_pattern = 'http://nrvis.com/download/data/%s/%s.zip'

    @staticmethod
    def get(name, collection='konect', directed=False, format='ij') -> MyGraph:
        """
        Read graph from storage or download it from the specified collection.
        :param name:
        :param collection: 'konect', 'networkrepository'
        :param directed: undirected by default
        :param format: output will be in this format, 'ij' by default
        :return: MyGraph with snap graph
        """
        assert collection in COLLECTIONS
        path = os.path.join(GRAPHS_DIR, collection, "%s.%s" % (name, format))
        # category = ''

        # TODO let collection be not specified, try Konect then Netrepo, etc

        if not os.path.exists(path):
            temp_path = os.path.join(GRAPHS_DIR, collection, '%s.tmp' % name)

            if collection == 'konect':
                GraphCollections._download_konect(
                    temp_path, GraphCollections.konect_url_pattern % name)

            elif collection == 'networkrepository':
                raise NotImplementedError()
                category = name.split('-')[0]
                GraphCollections._download_networkrepository(
                    temp_path, GraphCollections.networkrepository_url_pattern % (category, name))

            reformat_graph_file(temp_path, path, out_format=format, remove_original=True)

        return MyGraph(path, name, directed, format=format)

    @staticmethod
    def _download_konect(graph_path, url_konect):
        """
        Downloads graph data from Konect http://konect.uni-koblenz.de

        :param graph_path: full path to edge list file
        :param url_konect: URL of graph data
        :return:
        """
        # Convert "url_konect.tar.*" -> "filename.tar"
        if (url_konect.rsplit('/', 1)[1]).rsplit('.', 2)[1] == "tar":
            archive_name = (url_konect.rsplit('/', 1)[1]).rsplit('.', 1)[0]
        else:
            archive_name = (url_konect.rsplit('/', 1)[1])

        graph_dir = os.path.dirname(graph_path)
        if not os.path.exists(graph_dir):
            os.makedirs(graph_dir)

        # Download archive and extract graph file
        logging.info("Downloading graph archive from Konect...")
        filename = os.path.join(graph_dir, archive_name)
        urllib.request.urlretrieve(url_konect, filename=filename)
        logging.info("done.")
        patoolib.extract_archive(filename, outdir=graph_dir)

        # Rename extracted graph file
        archive_dir_name = archive_name.split('.', 1)[0]
        konect_file_name = os.path.join(graph_dir, archive_dir_name,
                                        "out." + archive_dir_name)
        out_file_name = os.path.join(graph_dir, os.path.basename(graph_path))
        os.rename(konect_file_name, out_file_name)

        os.remove(os.path.join(graph_dir, archive_name))
        shutil.rmtree(os.path.join(graph_dir, archive_dir_name))

    @staticmethod
    def _download_networkrepository(graph_path, url):
        """
        Downloads graph data from http://networkrepository.com/networks.php

        :param graph_path: full path to edge list file
        :param url: URL of graph data
        :return:
        """
        # 'http://nrvis.com/download/data/eco/eco-florida.zip'
        # Convert "url_konect.tar.*" -> "filename.tar"
        if (url.rsplit('/', 1)[1]).rsplit('.', 2)[1] == "tar":
            archive_name = (url.rsplit('/', 1)[1]).rsplit('.', 1)[0]
        else:
            archive_name = (url.rsplit('/', 1)[1])

        graph_dir = os.path.dirname(graph_path)
        if not os.path.exists(graph_dir):
            os.makedirs(graph_dir)

        # Download archive and extract graph file
        logging.info("Downloading graph archive from networkrepository...")
        filename = os.path.join(graph_dir, archive_name)
        urllib.request.urlretrieve(url, filename=filename)
        logging.info("done.")
        archive_dir_name = archive_name.split('.', 1)[0]
        patoolib.extract_archive(filename, outdir=os.path.join(graph_dir, archive_dir_name))

        # Rename extracted graph file
        # FIXME files are in various formats '.edges', '.mtx' etc
        netwrepo_file_name = os.path.join(graph_dir, archive_dir_name, archive_dir_name + ".edges")
        out_file_name = os.path.join(graph_dir, os.path.basename(graph_path))
        os.rename(netwrepo_file_name, out_file_name)

        os.remove(os.path.join(graph_dir, archive_name))
        shutil.rmtree(os.path.join(graph_dir, archive_dir_name))


def test():
    # name = 'soc-pokec-relationships'
    # name = 'petster-friendships-cat'
    # name = 'petster-hamster'
    # name = 'twitter'
    # name = 'libimseti'
    g = GraphCollections.get('advogato').snap
    # g = GraphCollections.get('eco-florida', collection='networkrepository').snap
    print("N=%s E=%s" % (g.GetNodes(), g.GetEdges()))


if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)

    test()
