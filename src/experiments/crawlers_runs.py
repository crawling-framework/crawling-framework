import logging
import os

from utils import USE_CYTHON_CRAWLERS
import time
if USE_CYTHON_CRAWLERS:
    from base.cgraph import CGraph as MyGraph
    from base.cbasic import MaximumObservedDegreeCrawler, BreadthFirstSearchCrawler, DepthFirstSearchCrawler, \
        SnowBallCrawler, PreferentialObservedDegreeCrawler, RandomCrawler, RandomWalkCrawler
    from base.cmultiseed import MultiCrawler
else:
    from base.graph import MyGraph
    from crawlers.basic import MaximumObservedDegreeCrawler, BreadthFirstSearchCrawler, DepthFirstSearchCrawler, \
        SnowBallCrawler, PreferentialObservedDegreeCrawler, RandomCrawler, RandomWalkCrawler
    from crawlers.multiseed import MultiCrawler

from graph_io import GraphCollections
from runners.animated_runner import Metric, AnimatedCrawlerRunner
from runners.crawler_runner import CrawlerRunner
from statistics import get_top_centrality_nodes, Stat
import multiprocessing


def start_runner(graph, animated=False, statistics: list = None, top_k_percent=0.1, layout_pos=None, tqdm_info=''):
    import random
    # initial_seed = random.sample([n.GetId() for n in graph.snap.Nodes()], 1)[0]
    print([stat_name.name for stat_name in statistics])
    initial_seed = graph.random_nodes(1000)
    ranges = [2, 3, 4, 5, 10, 30, 100, 1000]
    crawlers = [  ## ForestFireCrawler(graph, initial_seed=initial_seed), # FIXME fix and rewrite
                   DepthFirstSearchCrawler(graph, initial_seed=initial_seed[0]),
                   SnowBallCrawler(graph, p=0.1, initial_seed=initial_seed[0]),
                   SnowBallCrawler(graph, p=0.25, initial_seed=initial_seed[0]),
                   SnowBallCrawler(graph, p=0.5, initial_seed=initial_seed[0]),
                   SnowBallCrawler(graph, p=0.75, initial_seed=initial_seed[0]),
                   SnowBallCrawler(graph, p=0.9, initial_seed=initial_seed[0]),
                   BreadthFirstSearchCrawler(graph, initial_seed=initial_seed[0]),  # is like take SBS with p=1

                   RandomWalkCrawler(graph, initial_seed=initial_seed[0]),
                   RandomCrawler(graph, initial_seed=initial_seed[0]),

                   MaximumObservedDegreeCrawler(graph, batch=1, initial_seed=initial_seed[0]),
                   MaximumObservedDegreeCrawler(graph, batch=10, initial_seed=initial_seed[0]),
                   MaximumObservedDegreeCrawler(graph, batch=100, initial_seed=initial_seed[0]),
                   MaximumObservedDegreeCrawler(graph, batch=1000, initial_seed=initial_seed[0]),
                   MaximumObservedDegreeCrawler(graph, batch=10000, initial_seed=initial_seed[0]),

                   PreferentialObservedDegreeCrawler(graph, batch=1, initial_seed=initial_seed[0]),
                   PreferentialObservedDegreeCrawler(graph, batch=10, initial_seed=initial_seed[0]),
                   PreferentialObservedDegreeCrawler(graph, batch=100, initial_seed=initial_seed[0]),
                   PreferentialObservedDegreeCrawler(graph, batch=1000, initial_seed=initial_seed[0]),
                   PreferentialObservedDegreeCrawler(graph, batch=10000, initial_seed=initial_seed[0]),
               ] \
               + [
                   MultiCrawler(graph, crawlers=[
                       PreferentialObservedDegreeCrawler(graph, batch=1, initial_seed=initial_seed[i]) for i in
                       range(range_i)])
                   for range_i in ranges \
                   #
               ] + [MultiCrawler(graph, crawlers=[
        BreadthFirstSearchCrawler(graph, initial_seed=initial_seed[i]) for i in range(range_i)])
                    for range_i in ranges \
                    #
                    ] + [
                   MultiCrawler(graph, crawlers=[
                       MaximumObservedDegreeCrawler(graph, batch=1, initial_seed=initial_seed[i]) for i in
                       range(range_i)])
                   for range_i in ranges \
                   ]
    logging.info([c.name for c in crawlers])
    metrics = []
    target_set = {}  # {i.name: set() for i in statistics}

    for target_statistics in statistics:
        target_set = set(
            get_top_centrality_nodes(graph, target_statistics, count=int(top_k_percent * graph[Stat.NODES])))
        # creating metrics and giving callable function to it (here - total fraction of nodes)
        # metrics.append(Metric(r'observed' + target_statistics.name, lambda crawler: len(crawler.nodes_set) / graph[Stat.NODES]))
        metrics.append(Metric(r'crawled_' + target_statistics.name,  # TODO rename crawled to observed
                              lambda crawler, t: len(t.intersection(crawler.crawled_set)) / len(t), t=target_set
                              ))

        # print(metrics[-1], target_set)
    if animated == True:
        ci = 1
        # AnimatedCrawlerRunner(graph,
        #                            crawlers,
        #                            metrics,
        #                            budget=10000,
        #                            step=10)
    else:
        ci = CrawlerRunner(graph,
                           crawlers,
                           metrics,
                           budget=0,
                           top_k_percent=top_k_percent,
                           # step=ceil(10 ** (len(str(graph.nodes())) - 3)),
                           tqdm_info=tqdm_info,
                           # if 5*10^5 then step = 10**2,if 10^7 => step=10^4
                           # batches_per_pic=10,
                           # draw_mod='traversal', layout_pos=layout_pos,
                           )  # if you want gifs, draw_mod='traversal'. else: 'metric'
    ci.run()


def big_run():

    logging.basicConfig(format='%(name)s:%(levelname)s:%(message)s', level=logging.INFO)
    logging.getLogger().setLevel(logging.INFO)
    # graph_name = 'digg-friends'       # with 261489 nodes and 1536577 edges
    # graph_name = 'douban'             # with 154908 nodes and  327162 edges
    # graph_name = 'facebook-wosn-links'# with  63392 nodes and  816831 edges
    # graph_name = 'slashdot-threads'   # with  51083 nodes and  116573 edges
    # graph_name = 'ego-gplus'          # with  23613 nodes and   39182 edges
    # graph_name = 'petster-hamster'    # with   2000 nodes and   16098 edges
    for graph_name in ['petster-friendships-dog', 'munmun_twitter_social', 'com-youtube',
                       'soc-pokec-relationships', 'flixster', 'youtube-u-growth', 'petster-friendships-cat', ]:
        g = GraphCollections.get(graph_name, giant_only=True)

    graphs = [
        # # # # 'livejournal-links', toooo large need all metrics
        # 'soc-pokec-relationships',  # with 1632803 nodes and 22301964 edges, davg=27.32  4/10 all but POD,Multi    no ecc
        # 6x all but POD,Multi - cloud1

        # 'youtube-u-growth',         # with 3216075 nodes and  9369874 edges, davg= 5.83     no ecc
        # 'petster-friendships-dog',  # with  426485 nodes and  8543321 edges, davg=40.06  10/10

        # 'flixster',                 # with 2523386 nodes and  7918801 edges, davg= 6.28  fails   no ecc
        'com-youtube',              # with 1134890 nodes and  2987624 edges, davg= 5.27  2/10 - RW,RC,MOD, 0/10 - POD, 9/10 - others     no ecc
        # 8x RW,RC,MOD,POD - local
        # 2x POD - cloud2
        # 1x others - ?

        # 'munmun_twitter_social',    # with  465017 nodes and   833540 edges, davg= 3.58  10/10

        # 'petster-friendships-cat',  # with  148826 nodes and  5447464 edges, davg=73.21 10/10
        # 'digg-friends',           # with  261489 nodes and  1536577 edges, davg=11.75
        # 'douban',                 # with  154908 nodes and   327162 edges, davg= 4.22
        # 'facebook-wosn-links',    # with   63392 nodes and   816831 edges, davg=25.77
        # 'slashdot-threads',       # with   51083 nodes and   116573 edges, davg= 4.56
        # 'ego-gplus',              # with   23613 nodes and    39182 edges, davg= 3.32
        # 'mipt',                   # with   14313 nodes and   488852 edges, davg=68.31
        # 'petster-hamster',        # with    2000 nodes and    16098 edges, davg=16.10


        # netrepo from Guidelines
        #
        # 'socfb-Bingham82',         # N=10004, E=362894, d_avg=72.55
        # 'soc-brightkite',          # N=56739, E=212945, d_avg=7.51
        # 'ca-citeseer',             # N=227320, E=814134, d_avg=7.16
        # 'ca-dblp-2010',            # N=226413, E=716460, d_avg=6.33
        # 'rec-amazon',              # N=91813, E=125704, d_avg=2.74
        # 'rec-github',              # N=121706, E=439849, d_avg=7.23
        # 'socfb-OR',                # N=63392, E=816886, d_avg=25.77
        # 'socfb-Penn94',            # N=41536, E=1362220, d_avg=65.59
        # 'socfb-wosn-friends',      # N=63731, E=817090, d_avg=25.64
        # 'tech-p2p-gnutella',       # N=62561, E=147878, d_avg=4.73
        # 'tech-RL-caida',           # N=190914, E=607610, d_avg=6.37
        # 'web-arabic-2005',         # N=163598, E=1747269, d_avg=21.36
        # 'soc-slashdot',            # N=70068, E=358647, d_avg=10.24
        # 'soc-themarker',           # ? N=69413, E=1644843, d_avg=47.39
        # 'soc-BlogCatalog',         # N=88784, E=2093195, d_avg=47.15
        # 'sc-pkustk13',             # N=94893, E=3260967, d_avg=68.73
        # # 10x all - cloud2

        # 'web-uk-2005',             # N=129632, E=11744049, d_avg=181.19
        # 'web-italycnr-2000',       # N=325557, E=2738969, d_avg=16.83
        # 'ca-dblp-2012',            # N=317080, E=1049866, d_avg=6.62
        # 'sc-pwtk',                 # N=217891, E=5653221, d_avg=51.89
        # 'web-sk-2005',             # N=121422, E=334419, d_avg=5.51
        # 'sc-shipsec1',             # N=140385, E=1707759, d_avg=24.33
        # 'ca-MathSciNet',           # N=332689, E=820644, d_avg=4.93
        # 'sc-shipsec5',             # N=179104, E=2200076, d_avg=24.57
    ]
    big_graphs = ['youtube-u-growth', 'flixster', 'soc-pokec-relationships', 'com-youtube', ]

    for graph_name in graphs[::-1]:
        if graph_name == 'mipt':
            g = GraphCollections.get(graph_name, 'other', giant_only=True)
        else:
            g = GraphCollections.get(graph_name, 'netrepo', giant_only=True)
        print('Graph {} with {} nodes and {} edges, davg={:02.2f}'.format(graph_name, g.nodes(), g.edges(),
                                                                          2.0 * g.edges() / g.nodes()))
        if graph_name in big_graphs:
            big_graph_no_ecc = 'ECC'  # FIXME костыль пока не посчитан ECC  у больших
        else:
            big_graph_no_ecc = '----'

        # TODO: to check and download graph before multiprocessing
        msg = "Did not finish"
        iterations = 4
        # iterations = multiprocessing.cpu_count() - 2
        for iter in range(int(12 // iterations)):
            start_time = time.time()
            processes = []
            # making parallel itarations. Number of processes
            for exp in range(iterations):
                logging.info('Running iteration {}/{}'.format(exp, iterations))
                # little multiprocessing magic, that calculates several iterations in parallel
                p = multiprocessing.Process(target=start_runner, args=(g,),
                                            kwargs={'animated': False,
                                                    'statistics': [s for s in Stat if 'DISTR' in s.name
                                                                   if big_graph_no_ecc not in s.name
                                                                   ],
                                                    'top_k_percent': 0.01,
                                                    # 'layout_pos':layout_pos,
                                                    'tqdm_info': 'core-' + str(exp + 1)
                                                    })
                p.start()

            p.join()

            msg = "Completed graph {} with {} nodes and {} edges. time elapsed: {:.2f}s, {}". \
                format(graph_name, g.nodes(), g.edges(), time.time() - start_time, processes)
            # except Exception as e:
            #     msg = "Failed graph %s after %.2fs with error %s" % (graph_name, time.time() - start_time, e)

            print(msg)

        # send to my vk
        import os
        from utils import rel_dir
        bot_path = os.path.join(rel_dir, "src", "experiments", "vk_signal.py")
        command = "python3 %s -m '%s'" % (bot_path, msg)
        exit_code = os.system(command)

    # from experiments.merger import merge
    # merge(graph_name,
    #       show=True,
    #       filter_only='MOD', )


def test_runner():
    g = GraphCollections.get('digg-friends')
    kwargs = {'animated': False,
              'statistics': [s for s in Stat if 'DISTR' in s.name],
              'top_k_percent': 0.01,
              }
    start_runner(g, **kwargs)


netrepo_names = [
    # Graphs used in https://dl.acm.org/doi/pdf/10.1145/3201064.3201066
    # Guidelines for Online Network Crawling: A Study of DataCollection Approaches and Network Properties

    'socfb-Bingham82',  # N=10004, E=362894, d_avg=72.55
    'soc-brightkite',  # N=56739, E=212945, d_avg=7.51

    # Collaboration
    'ca-citeseer',  # N=227320, E=814134, d_avg=7.16
    'ca-dblp-2010',  # N=226413, E=716460, d_avg=6.33
    'ca-dblp-2012',  # N=317080, E=1049866, d_avg=6.62
    'ca-MathSciNet',  # N=332689, E=820644, d_avg=4.93

    # Recommendation
    'rec-amazon',  # N=91813, E=125704, d_avg=2.74
    'rec-github',  # N=121706, E=439849, d_avg=7.23

    # FB
    'socfb-OR',  # N=63392, E=816886, d_avg=25.77
    'socfb-Penn94',  # N=41536, E=1362220, d_avg=65.59
    'socfb-wosn-friends',  # N=63731, E=817090, d_avg=25.64

    # Tech
    'tech-p2p-gnutella',  # N=62561, E=147878, d_avg=4.73
    'tech-RL-caida',  # N=190914, E=607610, d_avg=6.37

    # Web
    'web-arabic-2005',  # N=163598, E=1747269, d_avg=21.36
    'web-italycnr-2000',  # N=325557, E=2738969, d_avg=16.83
    'web-sk-2005',  # N=121422, E=334419, d_avg=5.51
    'web-uk-2005',  # N=129632, E=11744049, d_avg=181.19

    # OSNs
    'soc-slashdot',  # N=70068, E=358647, d_avg=10.24
    'soc-themarker',  # ? N=69413, E=1644843, d_avg=47.39
    'soc-BlogCatalog',  # N=88784, E=2093195, d_avg=47.15

    # Scientific
    'sc-pkustk13',  # N=94893, E=3260967, d_avg=68.73
    'sc-pwtk',  # N=217891, E=5653221, d_avg=51.89
    'sc-shipsec1',  # N=140385, E=1707759, d_avg=24.33
    'sc-shipsec5',  # N=179104, E=2200076, d_avg=24.57
]


def cloud_manager():
    import subprocess, sys

    cloud1 = 'ubuntu@83.149.198.220'
    cloud2 = 'ubuntu@83.149.198.231'

    local_dir = '/home/misha/workspace/crawling'
    remote_dir = '/home/ubuntu/workspace/crawling'
    ssh_key = '~/.ssh/drobyshevsky_home_key.pem'

    # Copy stats to remote

    # with ecc
    names = ['ca-citeseer', 'ca-dblp-2010', 'rec-amazon', 'rec-github', 'sc-pkustk13', 'soc-BlogCatalog',
             'soc-brightkite', 'soc-slashdot', 'soc-themarker', 'socfb-Bingham82', 'socfb-OR',
             'socfb-Penn94', 'socfb-wosn-friends', 'tech-RL-caida', 'tech-p2p-gnutella', 'web-arabic-2005']
    cloud = cloud2
    collection = 'netrepo'
    for name in ['ca-MathSciNet', 'sc-shipsec5']:
    # for name in ['web-uk-2005', 'web-italycnr-2000', 'ca-dblp-2012', 'sc-pwtk']:
        # if not os.path.exists('%s/data/%s/%s.ij_stats/EccDistr' % (local_dir, collection, name)):
        #     continue

        # copy_command = 'scp -i %s -r %s/data/%s/%s.ij_stats/ %s:%s/data/%s/' % (
        #     ssh_key, local_dir, collection, name, cloud, remote_dir, collection)

        copy_command = 'scp -i %s -r %s:%s/data/%s/%s.ij_stats/EccDistr %s/data/%s/%s.ij_stats/' % (
            ssh_key, cloud, remote_dir, collection, name, local_dir, collection, name)

        command = copy_command

        logging.info("Executing command: '%s' ..." % command)
        retcode = subprocess.Popen(command, shell=True, stdout=sys.stdout, stderr=sys.stderr).wait()
        if retcode != 0:
            logging.error("returned code =", retcode)
            raise RuntimeError("unsuccessful: '%s'" % command)
        else:
            logging.info("OK")


def prepare_netrepo_graphs():
    for name in netrepo_names:
        g = GraphCollections.get(name, 'netrepo')
        print("N=%s, E=%s, d_avg=%.2f" % (g['NODES'], g['EDGES'], g[Stat.AVG_DEGREE]))


if __name__ == '__main__':
    import logging
    logging.basicConfig(format='%(levelname)s:%(message)s')
    logging.getLogger('matplotlib.font_manager').setLevel(logging.INFO)
    logging.getLogger().setLevel(logging.DEBUG)

    big_run()
    # test_runner()
    # prepare_netrepo_graphs()
    # cloud_manager()
