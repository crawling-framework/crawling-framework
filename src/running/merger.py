import glob
import json
import logging
import os
import re
import shutil
from bisect import bisect_left, bisect_right
from math import sqrt, ceil
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt
from tqdm import tqdm

from crawlers.cbasic import Crawler
from crawlers.declarable import declaration_to_filename
from running.metrics import Metric
from utils import RESULT_DIR


def compute_aucc(xs, ys):
    # from sklearn.metrics import auc
    # return auc(xs, ys)
    assert len(xs) == len(ys) > 0
    xs = xs / xs[-1]
    res = xs[0] * ys[0] / 2
    for i in range(1, len(xs)):
        res += (xs[i] - xs[i-1]) * (ys[i-1] + ys[i]) / 2
    return res


def compute_waucc(xs, ys):
    # res = compute_aucc(np.log(xs), ys)
    assert len(xs) == len(ys) > 0
    xs = xs / xs[-1]
    res = 0 if xs[0] == 0 else ys[0]
    norm = 0 if xs[0] == 0 else 1
    for i in range(1, len(xs)):
        res += (xs[i] - xs[i-1]) * (ys[i-1] + ys[i]) / 2 / xs[i]
        norm += (xs[i] - xs[i-1]) / xs[i]
    return res / norm


def compute_targets_crawled(xs, ys):
    assert len(xs) == len(ys) > 0
    return ys[-1]


def average(array, median=False, **kwargs):
    if len(array) == 0:
        return np.nan
    return (np.median if median else np.mean)(array, **kwargs)


def variance(array, **kwargs):
    if len(array) == 0:
        return np.nan
    return np.var(array, **kwargs)


LINESTYLES = ['-', '--', ':', '-.']
COLORS = ['black', 'b', 'g', 'r', 'c', 'm', 'y',
          'darkblue', 'darkgreen', 'darkred', 'darkmagenta', 'darkorange', 'darkcyan',
          'pink', 'lime', 'wheat', 'lightsteelblue']


class ResultsMerger:
    """
    ResultsMerger can aggregate and plot results saved in files.
    Process all combinations of G graphs x C crawlers x M metrics. Averages over n instances of each.
    All missed instances are just ignored.

    Plotting functions:

    * draw_by_crawler - Draw M x G table of plots with C lines each. Ox - crawling step, Oy - metric value.
    * draw_by_metric_crawler - Draw G plots with C x M lines each. Ox - crawling step, Oy - metric value.
    * draw_by_metric - Draw C x G table of plots with M lines each. Ox - crawling step, Oy - metric value.
    * draw_aggregated - Draw G plots with M lines. Ox - C crawlers, Oy - (w)AUCC value (M curves with error bars).
    * draw_winners - Draw C stacked bars (each of M elements). Ox - C crawlers, Oy - number of wins (among G) by (w)AUCC
      value.

    Additional functions:

    * missing_instances - Calculate how many instances of all configurations are missing.
    * move_folders - Move/remove/copy saved instances for current graphs, crawlers, metrics.

    NOTES:

    * x values must be the same for all files and are the ones generated by `exponential_batch_generator()` from
      running/runner.py
    * it is supposed that for all instances values lists are of equal lengthes (i.e. budgets). Otherwise normalisation
      and aggregation may fail. If so, use `x_lims` parameter for the control.

    """
    def __init__(self, graph_full_names, crawler_decls, metric_decls, budget,
                 n_instances=None, x_lims=None,
                 result_dir=RESULT_DIR, numeric_only=True):
        """
        :param graph_full_names: list of graphs full names.
        :param crawler_decls: list of crawlers declarations.
        :param metric_decls: list of metrics declarations. Non-numeric metrics will be ignored.
        :param budget: results with this budget will be taken.
        :param n_instances: number of instances to average over, None for all.
        :param x_lims: use only specified x-limits for all plots unless another value is specified
         in plotting function.
        :param result_dir: specify if want to use non-default directory where results are stored.
        """
        self.graph_full_names = graph_full_names
        self.crawler_names = []  # list(map(declaration_to_filename, crawler_decls))
        self.metric_names = []  # list(map(declaration_to_filename, metric_decls))
        self.labels = {}  # pretty short names to draw in plots

        # Generate pretty names for crawlers and metrics for plots
        for md in metric_decls:
            m = Metric.from_declaration(md, graph=None)
            if numeric_only and not m.is_numeric:
                # Ignore non-numeric metrics
                continue
            f = declaration_to_filename(m.declaration)
            self.metric_names.append(f)
            self.labels[f] = m.name
        for cd in crawler_decls:
            c = Crawler.from_declaration(cd, graph=None)
            f = declaration_to_filename(c.declaration)
            self.crawler_names.append(f)
            self.labels[f] = c.name

        self.budget = budget
        self.n_instances = n_instances
        self.x_lims = x_lims
        self.instances = {}  # instances[graph][crawler][metric] -> count of instances
        # contents[graph][crawler][metric]:
        # 'x' -> [nums of steps],
        # 'ys' -> [[y for each step] for each instance],
        # 'avy' -> [avg y for each step]
        self.contents = {}
        # auccs[graph][crawler][metric]:
        # 'AUCC' -> [AUCC for each instance],
        # 'wAUCC' -> [wAUCC for each instance]
        self.auccs = {}

        self.result_dir = result_dir
        self._read()
        plt.style.use('seaborn')

    @staticmethod
    def names_to_path(graph_full_name: tuple, crawler_name: str, metric_name: str, budget: int,
                      result_dir=RESULT_DIR):
        """ Returns file pattern e.g.
        '/home/misha/workspace/crawling/results/ego-gplus/POD(batch=1)/TopK(centrality=BtwDistr,measure=Re,part=crawled,top=0.01)/\*.json'
        """
        # TODO apply
        # path = Path(
        #     result_dir, *graph_full_name, crawler_name, metric_name, f"budget={budget}", "*.json")
        path = Path(result_dir, *graph_full_name, crawler_name, metric_name, "*.json")
        return path

    def _read(self):
        total = len(self.graph_full_names) * len(self.crawler_names) * len(self.metric_names)
        pbar = tqdm(total=total, desc='Reading history')
        self.instances.clear()
        # self.contents.clear()
        for g in self.graph_full_names:
            self.instances[g] = {}
            self.contents[g] = {}
            for c in self.crawler_names:
                self.instances[g][c] = {}
                self.contents[g][c] = {}
                for m in self.metric_names:
                    # TODO apply
                    # path = ResultsMerger.names_to_path(g, c, m, self.budget, self.result_dir)
                    # fn_pattern = re.compile(f'(\d+)\.json')
                    # paths = []
                    # for file in path.parent.iterdir():
                    #     m = re.findall(fn_pattern, file.name)
                    #     if m:
                    #         print(file.name, m[0][0])
                    #         paths.append(file)
                    # paths = sorted(paths)[:self.n_instances]

                    path_pattern = ResultsMerger.names_to_path(g, c, m, self.result_dir)
                    # FIXME workaround for glob since '[' is a special symbol for it
                    path_pattern = str(path_pattern).replace('[', '[[]')
                    paths = glob.glob(path_pattern)[:self.n_instances]
                    paths = sorted(paths)

                    self.instances[g][c][m] = len(paths)
                    self.contents[g][c][m] = contents = {}

                    count = len(paths)
                    contents['x'] = []
                    contents['ys'] = ys = [[]]*count
                    contents['avy'] = []

                    i0 = 0
                    i1 = None
                    for inst, p in enumerate(paths):
                        with open(p, 'r') as f:
                            imported = json.load(f)
                        if len(contents['x']) == 0:
                            xs = np.array(sorted([int(x) for x in list(imported.keys())]))[i0: i1]
                            if self.x_lims:  # Cut over x_lims
                                x0, x1 = self.x_lims
                                i0 = bisect_left(xs, x0)
                                i1 = bisect_right(xs, x1)+1
                            contents['x'] = xs
                        if inst == 0:
                            contents['avy'] = np.zeros(len(xs))
                        try:
                            # Convert to float and compute average if possible
                            ys[inst] = np.array([float(x) for x in list(imported.values())])[i0: i1]
                            contents['avy'] += np.array(ys[inst]) / count
                        except TypeError:
                            # Non-numeric values - as is
                            ys[inst] = np.array(list(imported.values()))[i0: i1]

                    pbar.update(1)
        pbar.close()

    def move_folders(self, path_from=None, path_to=None, copy=False):
        """ Move/remove/copy all saved instances for current [graphs X crawlers X metrics].
        Specify `path_to` parameter to move files instead of removing.

        :param path_from: this folder is root for all folders to be (re)moved,
         must be contained in path to folders
        :param path_to: this folder is the destination for all folders to be moved.
         If None (which is default), all folders will be removed.
        :param copy: set to True if want to copy folders
        """
        if path_from is None:
            path_from = self.result_dir
        path_from = str(path_from)
        path_to = str(path_to)
        move_or_copy = shutil.copytree if copy else shutil.move
        total = len(self.graph_full_names) * len(self.crawler_names) * len(self.metric_names)
        pbar = tqdm(total=total, desc='(Re)moving history')
        folder = None
        removed = 0
        removed_empty = 0
        moved = 0
        from os.path import dirname as parent
        from os.path import exists as exist
        for g in self.graph_full_names:
            for c in self.crawler_names:
                for m in self.metric_names:
                    folder = str(ResultsMerger.names_to_path(g, c, m, self.budget, self.result_dir).parent)
                    if not exist(folder):
                        continue
                    if path_to is None:  # remove
                        shutil.rmtree(folder, ignore_errors=True)
                        removed += 1
                    else:  # move
                        assert path_from in folder
                        dst = folder.replace(path_from, path_to)
                        move_or_copy(folder, dst)
                        moved += 1
                    pbar.update(1)

                # Remove parent folder if exists and empty
                if exist(parent(folder)) and not os.listdir(parent(folder)):
                    os.rmdir(parent(folder))
                    removed_empty += 1

            # Remove parent folder if exists and empty
            if exist(parent(parent(folder))) and not os.listdir(parent(parent(folder))):
                os.rmdir(parent(parent(folder)))
                removed_empty += 1
        pbar.close()
        print("Moved %s folders, removed %s folders including %s empty ones" %
              (moved, removed, removed_empty))
        self.instances.clear()
        self.contents.clear()

    def missing_instances(self) -> dict:
        """ Return dict of instances where computed < n_instances.

        :return: result[graph][crawler][metric] -> missing count
        """
        missing = {}
        for g in self.graph_full_names:
            missing[g] = {}
            for c in self.crawler_names:
                missing[g][c] = {}
                for m in self.metric_names:
                    present = self.instances[g][c][m]
                    if self.n_instances > present:
                        missing[g][c][m] = self.n_instances - present

                if len(missing[g][c]) == 0:
                    del missing[g][c]

            if len(missing[g]) == 0:
                del missing[g]

        # print(json.dumps(missing, indent=2))
        return missing

    def draw_by_crawler(self, x_lims=None, x_normalize=True, sharey=True, draw_error=True,
                        draw_each_instance=False, scale=3, title="By crawler"):
        """
        Draw M x G table of plots with C lines each, where
        M - num of metrics, G - num of graphs, C - num of crawlers.
        Ox - crawling step, Oy - metric value.

        :param x_lims: x-limits for plots. Overrides x_lims passed in constructor
        :param x_normalize: if True, x values are normalized to be from 0 to 1
        :param draw_error: if True, fill standard deviation area around the averaged crawling curve
        :param draw_each_instance: if True, show each instance
        :param scale: size of plots (default 3)
        :param title: figure title
        """
        x_lims = x_lims or self.x_lims

        G = len(self.graph_full_names)
        M = len(self.metric_names)
        nrows, ncols = M, G
        if M == 1:
            nrows = int(sqrt(G))
            ncols = ceil(G / nrows)
        if G == 1:
            nrows = int(sqrt(M))
            ncols = ceil(M / nrows)
        fig, axs = plt.subplots(nrows, ncols, sharex=x_normalize, sharey=sharey, num=title, figsize=(1 + scale * ncols, scale * nrows))

        total = len(self.graph_full_names) * len(self.crawler_names) * len(self.metric_names)
        pbar = tqdm(total=total, desc='Plotting by crawler')
        aix = 0
        for i, m in enumerate(self.metric_names):
            for j, g in enumerate(self.graph_full_names):
                if nrows > 1 and ncols > 1:
                    plt.sca(axs[aix // ncols, aix % ncols])
                elif nrows * ncols > 1:
                    plt.sca(axs[aix])
                if aix % G == 0:
                    plt.ylabel(self.labels[m])
                if i == 0:
                    plt.title(g[-1])
                if aix // ncols == nrows-1:
                    plt.xlabel('Nodes fraction crawled' if x_normalize else 'Nodes crawled')
                aix += 1

                if x_lims:
                    plt.xlim(x_lims)
                for k, c in enumerate(self.crawler_names):
                    contents = self.contents[g][c][m]
                    # Draw each instance
                    if draw_each_instance:
                        for inst in range(len(contents['ys'])):
                            plt.plot(contents['x'], contents['ys'][inst], color=COLORS[k % len(COLORS)], linewidth=1, linestyle=':')
                    # Draw variance
                    xs = contents['x']
                    if x_normalize and len(xs) > 0:
                        xs = xs / xs[-1]
                    if len(xs) > 0 and draw_error:
                        error = variance(contents['ys'], axis=0) ** 0.5
                        plt.fill_between(xs, contents['avy'] - error, contents['avy'] + error, color=COLORS[k % len(COLORS)], alpha=0.2)
                    plt.plot(xs, contents['avy'], color=COLORS[k % len(COLORS)], linewidth=1,
                             label="[%s] %s" % (self.instances[g][c][m], self.labels[c]))

                    pbar.update(1)
        pbar.close()
        plt.legend()
        plt.tight_layout()

    def draw_by_metric(self, x_lims=None, x_normalize=True, sharey=True, draw_error=True, scale=3,
                       title="By metric"):
        """
        Draw C x G table of plots with M lines each, where
        M - num of metrics, G - num of graphs, C - num of crawlers
        Ox - crawling step, Oy - metric value.
        """
        x_lims = x_lims or self.x_lims

        G = len(self.graph_full_names)
        C = len(self.crawler_names)
        nrows, ncols = C, G
        if C == 1:
            nrows = int(sqrt(G))
            ncols = ceil(G / nrows)
        if G == 1:
            nrows = int(sqrt(C))
            ncols = ceil(C / nrows)
        fig, axs = plt.subplots(nrows, ncols, sharex=x_normalize, sharey=sharey, num=title, figsize=(1 + scale * ncols, scale * nrows))

        total = len(self.graph_full_names) * len(self.crawler_names) * len(self.metric_names)
        pbar = tqdm(total=total, desc='Plotting by crawler')
        aix = 0
        for i, c in enumerate(self.crawler_names):
            for j, g in enumerate(self.graph_full_names):
                if nrows > 1 and ncols > 1:
                    plt.sca(axs[aix // ncols, aix % ncols])
                elif nrows * ncols > 1:
                    plt.sca(axs[aix])
                if aix % G == 0:
                    plt.ylabel(self.labels[c])
                if i == 0:
                    plt.title(g[-1])
                if aix // ncols == nrows-1:
                    plt.xlabel('Nodes fraction crawled' if x_normalize else 'Nodes crawled')
                aix += 1

                if x_lims:
                    plt.xlim(x_lims)
                for k, m in enumerate(self.metric_names):
                    contents = self.contents[g][c][m]
                    # Draw each instance
                    # for inst in range(len(contents['ys'])):
                    #     plt.plot(contents['x'], contents['ys'][inst], color=colors[k % len(colors)], linewidth=0.5, linestyle=':')
                    # Draw variance
                    xs = contents['x']
                    if x_normalize and len(xs) > 0:
                        xs = xs / xs[-1]
                    if len(xs) > 0 and draw_error:
                        error = variance(contents['ys'], axis=0) ** 0.5
                        plt.fill_between(xs, contents['avy'] - error, contents['avy'] + error, color=COLORS[k % len(COLORS)], alpha=0.2)
                    plt.plot(xs, contents['avy'], color=COLORS[k % len(COLORS)], linewidth=1,
                             label="[%s] %s" % (self.instances[g][c][m], self.labels[m]))
                    pbar.update(1)
        pbar.close()
        plt.legend()
        plt.tight_layout()

    def draw_by_metric_crawler(self, x_lims=None, x_normalize=True, sharey=True,
                               swap_coloring_scheme=False, draw_error=True, scale=3,
                               title="By metric and crawler"):
        """
        Draw G plots with CxM lines each, where
        M - num of metrics, G - num of graphs, C - num of crawlers.
        Ox - crawling step, Oy - metric value.

        :param x_lims: x-limits for plots. Overrides x_lims passed in constructor
        :param x_normalize: if True, x values are normalized to be from 0 to 1
        :param sharey: if True, share properties among or y axes
        :param swap_coloring_scheme: by default metrics differ in linestyle, crawlers differ in color. Set True to swap
        :param draw_error: if True, fill standard deviation area around the averaged crawling curve
        :param scale: size of plots (default 3)
        :param title: figure title
        """
        x_lims = x_lims or self.x_lims

        G = len(self.graph_full_names)
        nrows = int(sqrt(G))
        ncols = ceil(G / nrows)
        fig, axs = plt.subplots(nrows, ncols, sharex=x_normalize, sharey=sharey, num=title,
                                figsize=(1 + scale * ncols, scale * nrows))

        total = len(self.graph_full_names) * len(self.crawler_names) * len(self.metric_names)
        pbar = tqdm(total=total, desc='Plotting by metric crawler')
        aix = 0
        for j, g in enumerate(self.graph_full_names):
            if nrows > 1 and ncols > 1:
                plt.sca(axs[aix // ncols, aix % ncols])
            elif nrows * ncols > 1:
                plt.sca(axs[aix])
            if aix % ncols == 0:
                plt.ylabel('Metrics value')
            plt.title(g[-1])
            if aix // ncols == nrows-1:
                plt.xlabel('Nodes fraction crawled' if x_normalize else 'Nodes crawled')
            aix += 1

            if x_lims:
                plt.xlim(x_lims)
            for k, c in enumerate(self.crawler_names):
                for i, m in enumerate(self.metric_names):
                    contents = self.contents[g][c][m]
                    ls, col = (k, i) if swap_coloring_scheme else (i, k)
                    # Draw variance
                    xs = contents['x']
                    if x_normalize and len(xs) > 0:
                        xs = xs / xs[-1]
                    if len(xs) > 0 and draw_error:
                        error = variance(contents['ys'], axis=0) ** 0.5
                        plt.fill_between(xs, contents['avy'] - error, contents['avy'] + error, alpha=0.2,
                                         color=COLORS[col % len(COLORS)])
                    plt.plot(xs, contents['avy'], linewidth=1,
                             linestyle=LINESTYLES[ls % len(LINESTYLES)],
                             color=COLORS[col % len(COLORS)],
                             label="[%s] %s, %s" % (self.instances[g][c][m], self.labels[c], self.labels[m]))
                    pbar.update(1)
        pbar.close()
        plt.legend()
        plt.tight_layout()

    def _compute_aggregated(self, x_lims=None):
        """
        :param x_lims: if specified as (x_from, x_to), compute AUCC for an interval containing the specified one
        """
        x_lims = x_lims or self.x_lims
        if len(self.auccs) > 0:
            return
        # Compute AUCCs
        G = len(self.graph_full_names)
        C = len(self.crawler_names)
        M = len(self.metric_names)
        self.auccs.clear()
        pbar = tqdm(total=G*C*M, desc='Computing AUCCs')
        for g in self.graph_full_names:
            self.auccs[g] = {}
            for c in self.crawler_names:
                self.auccs[g][c] = {}
                for m in self.metric_names:
                    self.auccs[g][c][m] = aucc = {}
                    contents = self.contents[g][c][m]
                    xs = contents['x']
                    ys = contents['ys']
                    i0 = 0
                    i1 = None
                    if x_lims:
                        x0, x1 = self.x_lims
                        i0 = bisect_left(xs, x0)
                        i1 = bisect_right(xs, x1) + 1

                    aucc['AUCC'] = [compute_aucc(xs[i0: i1], ys[inst][i0: i1]) for inst in range(len(ys))]
                    aucc['wAUCC'] = [compute_waucc(xs[i0: i1], ys[inst][i0: i1]) for inst in range(len(ys))]
                    aucc['TC'] = [compute_targets_crawled(xs[i0: i1], ys[inst][i0: i1]) for inst in range(len(ys))]
                    pbar.update(1)
        pbar.close()

    def get_aggregated(self, aggregator='AUCC', x_lims=None, median=False, print_results=False):
        """ Get results according to an aggregatro (AUCC, wAUCC, TC)
        :param x_lims: x-limits passed to aggregator. Overrides x_lims passed in constructor
        :param median: if True, compute median instead of mean
        :param print_results: if True, print results
        :return: list of results as tuple (num_instances, Graph, Crawler, Metric, mean, error)
        """
        assert aggregator in ['AUCC', 'wAUCC', 'TC']
        x_lims = x_lims or self.x_lims
        self._compute_aggregated(x_lims=x_lims)
        results = []
        for g in self.graph_full_names:
            for i, m in enumerate(self.metric_names):
                errors = [variance(self.auccs[g][c][m][aggregator]) ** 0.5 for c in self.crawler_names]
                avgs = [average(self.auccs[g][c][m][aggregator], median) for c in self.crawler_names]
                for ix, c in enumerate(self.crawler_names):
                    results.append(
                        (len(self.contents[g][c][m]['ys']),
                         '/'.join(g),
                         self.labels[c],
                         self.labels[m], avgs[ix], errors[ix]))

        if print_results:
            for n, g, c, m, avg, err in results:
                string = "[%s] " % n + ', '.join([g, c, m, "%.1f+-%.1f" % (avg, err)])
                print(string)

        return results

    def draw_aggregated(self, aggregator='AUCC', x_lims=None, scale=3, sharey=True,
                        boxplot=True, xticks_rotation=90, title=None, draw_count=True):
        """
        Draw G plots with M lines. Ox - C crawlers, Oy - AUCC value (M curves with error bars).
        M - num of metrics, G - num of graphs, C - num of crawlers

        :param aggregator: function translating crawling curve into 1 number. AUCC (default) or wAUCC
        :param x_lims: x-limits passed to aggregator. Overrides x_lims passed in constructor
        :param scale: size of plots (default 3)
        :param sharey: if True, share properties among or y axes
        :param xticks_rotation: rotate x-ticks (default 90 degrees)
        :param title: figure title
        :param draw_count: if True, prepend number of instances to label
        """
        assert aggregator in ['AUCC', 'wAUCC', 'TC']
        x_lims = x_lims or self.x_lims

        self._compute_aggregated(x_lims=x_lims)
        G = len(self.graph_full_names)
        C = len(self.crawler_names)
        M = len(self.metric_names)
        if M > 1:
            boxplot = False

        # Draw
        nrows = int(sqrt(G))
        ncols = ceil(G / nrows)
        fig, axs = plt.subplots(nrows, ncols, sharex=True, sharey=sharey, num=title,
                                figsize=(1 + scale * ncols, 1 + scale * nrows))
        aix = 0
        pbar = tqdm(total=G*M, desc='Plotting %s' % aggregator)
        xs = list(range(1, 1 + C))
        for g in self.graph_full_names:
            if nrows > 1 and ncols > 1:
                plt.sca(axs[aix // ncols, aix % ncols])
            elif nrows * ncols > 1:
                plt.sca(axs[aix])
            if aix == 0:
                plt.ylabel('%s value' % aggregator)
            plt.title(g[-1])

            # for each crawler a list of instances for each metris
            labels = [[] for _ in self.crawler_names]
            for i, m in enumerate(self.metric_names):
                errors = [variance(self.auccs[g][c][m][aggregator]) ** 0.5 for c in self.crawler_names]

                ys = [self.auccs[g][c][m][aggregator] for c in self.crawler_names]
                means = [average(self.auccs[g][c][m][aggregator]) for c in self.crawler_names]
                # meds = [np.median(self.auccs[g][c][m][aggregator]) for c in self.crawler_names]
                if boxplot:
                    box_plot = plt.boxplot(ys)
                    for median in box_plot['medians']:
                        median.set_color('red')
                else:
                    plt.errorbar(xs, means, errors, label=self.labels[m], marker='.', capsize=5,
                                 color=COLORS[i % len(COLORS)])

                for ix, c in enumerate(self.crawler_names):
                    print(f"[{len(self.contents[g][c][m]['ys'])}]", g, self.labels[c],
                          self.labels[m], "%.1f+-%.1f" % (means[ix], errors[ix]))
                for j, c in enumerate(self.crawler_names):
                    labels[j].append(len(self.contents[g][c][m]['ys']))
                pbar.update(1)
            labels = [(f"[{','.join(str(l) for l in ls)}] " if draw_count else "") + self.labels[c]
                      for c, ls in zip(self.crawler_names, labels)]
            plt.xticks(xs, labels, rotation=xticks_rotation)
            aix += 1
        pbar.close()
        if not boxplot:
            plt.legend()
        plt.tight_layout()

    def draw_winners(self, aggregator='AUCC', x_lims=None, scale=8, xticks_rotation=90, title=None):
        """
        Draw C stacked bars (each of M elements). Ox - C crawlers, Oy - number of wins (among G) by (w)AUCC value.
        Miss graphs where not all configurations are present.

        :param aggregator: function translating crawling curve into 1 number. AUCC (default) or wAUCC
        :param x_lims: x-limits passed to aggregator. Overrides x_lims passed in constructor
        :param scale: size of plots (default 8)
        :param xticks_rotation: rotate x-ticks (default 90 degrees)
        :param title: figure title
        """
        assert aggregator in ['AUCC', 'wAUCC', 'TC']
        x_lims = x_lims or self.x_lims

        self._compute_aggregated(x_lims=x_lims)
        G = len(self.graph_full_names)
        C = len(self.crawler_names)
        M = len(self.metric_names)

        # Computing winners
        winners = {}  # winners[crawler][metric] -> count
        for c in self.crawler_names:
            winners[c] = {}
            for m in self.metric_names:
                winners[c][m] = 0

        for m in self.metric_names:
            for g in self.graph_full_names:
                ca = [average(self.auccs[g][c][m][aggregator]) for c in self.crawler_names]
                if any(np.isnan(ca)):
                    continue
                winner = self.crawler_names[np.argmax(ca)]
                winners[winner][m] += 1

        # Draw
        plt.figure(num=title or "Winners by %s" % aggregator, figsize=(1 + scale, scale))
        xs = list(range(1, 1 + C))
        prev_bottom = np.zeros(C)
        for i, m in enumerate(self.metric_names):
            h = [winners[c][m] for c in self.crawler_names]
            plt.bar(xs, h, width=0.8, bottom=prev_bottom, color=COLORS[i % len(COLORS)], label=self.labels[m])
            prev_bottom += h

        plt.ylabel('Wins by %s value' % aggregator)
        plt.xticks(xs, [self.labels[c] for c in self.crawler_names], rotation=xticks_rotation)
        plt.legend()
        plt.tight_layout()

    def show_plots(self):
        """ Show drawn matplotlib plots """
        plt.show()

    @staticmethod
    def next_file(folder: Path):
        """ Return a path with a smallest number not present in the folder.
        E.g. if folder has 0.json and 2.json, it returns path for 1.json
        """
        ix = 0
        while True:
            path = folder / f"{ix}.json"
            if not path.exists():  # if name exists, adding number to it
                return path
            ix += 1

    @staticmethod
    def merge_folders(*path, not_earlier_than=None, not_later_than=None, check_identical=False,
                      copy=False):
        """ Merge all results into 1 folder: path[1], path[2], etc into path[0].
        Name collisions resolved via assigning new smallest numbers, e.g. when 0.json is added to a
        folder with 0.json and 2.json, it becomes 1.json.

        Args:
            *path: list of paths each of those is analog to original results/ in terms of structure.
            not_earlier_than: look for files with modify datetime not earlier than specified.
            not_later_than: look for files with modify datetime not later than specified.
            check_identical: before renaming check whether equally named files are identical.
            copy: if True, copy all moved elements.
        """
        if len(path) < 2:
            raise RuntimeError("Specify more than 1 paths to be merged")

        import filecmp

        if not_earlier_than is not None:
            not_earlier_than = not_earlier_than.timestamp()

        if not_later_than is not None:
            not_later_than = not_later_than.timestamp()

        def check_datetime(path: Path):
            """ Check modify time """
            if not_earlier_than is not None:
                if path.stat().st_mtime < not_earlier_than:
                    return False
            if not_later_than is not None:
                if path.stat().st_mtime > not_later_than:
                    return False
            return True

        def merge(dst_path: Path, src_path: Path):
            src_content = os.listdir(src_path)
            for name in src_content:
                src_subpath = src_path / name
                dst_subpath = dst_path / name
                if src_subpath.is_file():  # file
                    if check_datetime(src_subpath):
                        if dst_subpath.exists():  # Rename
                            if check_identical and filecmp.cmp(src_subpath, dst_subpath):
                                # If files are the same, avoid duplication
                                rname_move_dirmove_ident[3] += 1
                                if not copy:
                                    os.remove(src_subpath)
                            else:
                                new_path = ResultsMerger.next_file(dst_subpath.parent)
                                (shutil.copy if copy else shutil.move)(src_subpath, new_path)
                                rname_move_dirmove_ident[0] += 1

                        else:  # just move
                            dst_subpath.parent.mkdir(parents=True, exist_ok=True)
                            (shutil.copy if copy else shutil.move)(src_subpath, dst_subpath)
                            rname_move_dirmove_ident[1] += 1

                else:  # directory
                    merge(dst_subpath, src_subpath)

        dst = Path(path[0])
        for i in range(1, len(path)):
            print("Merging", path[i], "->", dst)
            rname_move_dirmove_ident = [0, 0, 0, 0]
            merge(dst, Path(path[i]))
            print(rname_move_dirmove_ident[0], "files renamed")
            print(rname_move_dirmove_ident[1], "files as is")
            print(rname_move_dirmove_ident[2], "directories as is")
            print(rname_move_dirmove_ident[3], "files coincide")