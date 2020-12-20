import sys
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d import Axes3D
import matplotlib
import matplotlib.colors
from matplotlib import cm
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import markers

from .util import stderr, get_irf_name


class MidpointNormalize(matplotlib.colors.Normalize):
    def __init__(self, vcenter=0., vmin=None, vmax=None, clip=False):
        self.vcenter = vcenter
        matplotlib.colors.Normalize.__init__(self, vmin, vmax, clip)

    def __call__(self, value, clip=None):
        # I'm ignoring masked values and all kinds of edge cases to make a
        # simple example...
        x, y = [self.vmin, self.vcenter, self.vmax], [0, 0.5, 1]
        return np.ma.masked_array(np.interp(value, x, y))


def plot_irf(
        plot_x,
        plot_y,
        irf_names,
        lq=None,
        uq=None,
        sort_names=True,
        prop_cycle_length=None,
        prop_cycle_ix=None,
        dir='.',
        filename='irf_plot.png',
        irf_name_map=None,
        plot_x_inches=6,
        plot_y_inches=4,
        ylim=None,
        cmap='gist_rainbow',
        legend=True,
        xlab=None,
        ylab=None,
        use_line_markers=False,
        transparent_background=False,
        dpi=300,
        dump_source=False
):
    """
    Plot impulse response functions.

    :param plot_x: ``numpy`` array with shape (T,1); time points for which to plot the response. For example, if the plots contain 1000 points from 0s to 10s, **plot_x** could be generated as ``np.linspace(0, 10, 1000)``.
    :param plot_y: ``numpy`` array with shape (T, N); response of each IRF at each time point.
    :param irf_names: ``list`` of ``str``; CDR ID's of IRFs in the same order as they appear in axis 1 of **plot_y**.
    :param lq: ``numpy`` array with shape (T, N), or ``None``; lower bound of credible interval for each time point. If ``None``, no credible interval will be plotted.
    :param uq: ``numpy`` array with shape (T, N), or ``None``; upper bound of credible interval for each time point. If ``None``, no credible interval will be plotted.
    :param sort_names: ``bool``; alphabetically sort IRF names.
    :param prop_cycle_length: ``int`` or ``None``; Length of plotting properties cycle (defines step size in the color map). If ``None``, inferred from **irf_names**.
    :param prop_cycle_ix: ``list`` of ``int``, or ``None``; Integer indices to use in the properties cycle for each entry in **irf_names**. If ``None``, indices are automatically assigned.
    :param dir: ``str``; output directory.
    :param filename: ``str``; filename.
    :param irf_name_map: ``dict`` of ``str`` to ``str``; map from CDR IRF ID's to more readable names to appear in legend. Any plotted IRF whose ID is not found in **irf_name_map** will be represented with the CDR IRF ID.
    :param plot_x_inches: ``float``; width of plot in inches.
    :param plot_y_inches: ``float``; height of plot in inches.
    :param ylim: 2-element ``tuple`` or ``list``; (lower_bound, upper_bound) to use for y axis. If ``None``, automatically inferred.
    :param cmap: ``str``; name of ``matplotlib`` ``cmap`` object (determines colors of plotted IRF).
    :param legend: ``bool``; include a legend.
    :param xlab: ``str`` or ``None``; x-axis label. If ``None``, no label.
    :param ylab: ``str`` or ``None``; y-axis label. If ``None``, no label.
    :param use_line_markers: ``bool``; add markers to IRF lines.
    :param transparent_background: ``bool``; use a transparent background. If ``False``, uses a white background.
    :param dpi: ``int``; dots per inch.
    :param dump_source: ``bool``; Whether to dump the plot source array to a csv file.
    :return: ``None``
    """

    cm = plt.get_cmap(cmap)
    plt.rcParams["font.family"] = "sans-serif"
    if prop_cycle_length:
        n_colors = prop_cycle_length
    else:
        n_colors = len(irf_names)
    if not prop_cycle_ix:
        prop_cycle_ix = list(range(n_colors))
    prop_cycle_kwargs = {'color': [cm(1. * prop_cycle_ix[i] / n_colors) for i in range(len(irf_names))]}
    if use_line_markers:
        markers_keys = list(markers.MarkerStyle.markers.keys())[:-3]
        prop_cycle_kwargs['marker'] = [markers_keys[prop_cycle_ix[i]] for i in range(len(irf_names))]
    plt.gca().set_prop_cycle(**prop_cycle_kwargs)
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['bottom'].set_visible(False)
    plt.gca().spines['left'].set_visible(False)
    plt.gca().tick_params(top='off', bottom='off', left='off', right='off', labelleft='on', labelbottom='on')
    plt.grid(b=True, which='major', axis='both', ls='--', lw=.5, c='k', alpha=.3)
    plt.axhline(y=0, lw=1, c='gray', alpha=1)
    plt.axvline(x=0, lw=1, c='gray', alpha=1)

    irf_names_processed = irf_names[:]
    if irf_name_map is not None:
        for i in range(len(irf_names_processed)):
            irf_names_processed[i] = ':'.join([get_irf_name(x, irf_name_map) for x in irf_names_processed[i].split(':')])
    if sort_names:
        sort_ix = [i[0] for i in sorted(enumerate(irf_names_processed), key=lambda x:x[1])]
    else:
        sort_ix = range(len(irf_names_processed))
    for i in range(len(sort_ix)):
        if plot_y[1:,sort_ix[i]].sum() == 0:
            plt.plot(plot_x[:2], plot_y[:2,sort_ix[i]], label=irf_names_processed[sort_ix[i]], lw=2, alpha=0.8, linestyle='-', solid_capstyle='butt')
        else:
            markevery = int(len(plot_y) / 10)
            plt.plot(plot_x, plot_y[:,sort_ix[i]], label=irf_names_processed[sort_ix[i]], lw=2, alpha=0.8, linestyle='-', markevery=markevery, solid_capstyle='butt')
        if uq is not None and lq is not None:
            plt.fill_between(plot_x[:,0], lq[:,sort_ix[i]], uq[:,sort_ix[i]], alpha=0.25)

    if xlab:
        plt.xlabel(xlab, weight='bold')
    if ylab:
        plt.ylabel(ylab, weight='bold')
    if legend:
        plt.legend(fancybox=True, framealpha=0.75, frameon=True, facecolor='white', edgecolor='gray')
        
    if ylim is not None:
        plt.ylim(ylim)

    plt.gcf().set_size_inches(plot_x_inches, plot_y_inches)
    plt.tight_layout()
    try:
        plt.savefig(dir+'/'+filename, dpi=dpi, transparent=transparent_background)
    except:
        stderr('Error saving plot to file %s. Skipping...\n' %(dir+'/'+filename))
    plt.close('all')

    if dump_source:
        csvname = '.'.join(filename.split('.')[:-1]) + '.csv'
        if irf_name_map is not None:
            names_cur = [get_irf_name(x, irf_name_map) for x in irf_names]
        df = pd.DataFrame(np.concatenate([plot_x, plot_y], axis=1), columns=['time'] + names_cur)
        
        if lq is not None:
            for i, name in enumerate(names_cur):
                df[name + 'LB'] = lq[:,i]
        if uq is not None:
            for i, name in enumerate(names_cur):
                df[name + 'UB'] = uq[:,i]

        df.to_csv(dir + '/' + csvname, index=False)

def plot_surface(
        plot_x,
        plot_y,
        plot_z,
        irf_names,
        lq=None,
        uq=None,
        bounds_as_surface=False,
        sort_names=True,
        dir='.',
        prefix='surface_plot',
        suffix='.png',
        irf_name_map=None,
        plot_x_inches=6,
        plot_y_inches=4,
        ylim='infer',
        plot_type='wireframe',
        cmap='coolwarm',
        xlab='Time',
        ylab='infer',
        zlab='Response',
        transparent_background=False,
        dpi=300,
        dump_source=False
):
    """
    Plot an IRF or interaction surface.

    :param plot_x: ``numpy`` array with shape (M,N); x locations for each plot point, copied N times.
    :param plot_y: ``numpy`` array with shape (M,N); y locations for each plot point, copied M times.
    :param plot_z: ``numpy`` array with shape (M,N); z locations for each plot point.
    :param irf_names: ``list`` of ``str``; CDR ID's of IRFs in the same order as they appear in axis 1 of **plot_y**.
    :param lq: ``numpy`` array with shape (M,N), or ``None``; lower bound of credible interval for each plot point. If ``None``, no credible interval will be plotted.
    :param uq: ``numpy`` array with shape (M,N), or ``None``; upper bound of credible interval for each plot point. If ``None``, no credible interval will be plotted.
    :param bounds_as_surface: ``bool``; whether to plot interval bounds using additional surfaces. If ``False``, bounds are plotted with vertical error bars instead. Ignored if lq, uq are ``None``.
    :param sort_names: ``bool``; alphabetically sort IRF names.
    :param prop_cycle_length: ``int`` or ``None``; Length of plotting properties cycle (defines step size in the color map). If ``None``, inferred from **irf_names**.
    :param prop_cycle_ix: ``list`` of ``int``, or ``None``; Integer indices to use in the properties cycle for each entry in **irf_names**. If ``None``, indices are automatically assigned.
    :param dir: ``str``; output directory.
    :param filename: ``str``; filename.
    :param irf_name_map: ``dict`` of ``str`` to ``str``; map from CDR IRF ID's to more readable names to appear in legend. Any plotted IRF whose ID is not found in **irf_name_map** will be represented with the CDR IRF ID.
    :param plot_x_inches: ``float``; width of plot in inches.
    :param plot_y_inches: ``float``; height of plot in inches.
    :param ylim: 2-element ``tuple`` or ``list``; (lower_bound, upper_bound) to use for y axis. If ``None``, automatically inferred.
    :param plot_type: ``str``; name of plot type to generate. One of ``["contour", "surf", "trisurf"]``.
    :param cmap: ``str``; name of ``matplotlib`` ``cmap`` object (determines colors of plotted IRF).
    :param legend: ``bool``; include a legend.
    :param xlab: ``str`` or ``None``; x-axis label. If ``None``, no label.
    :param ylab: ``str`` or ``None``; y-axis label. If ``None``, no label.
    :param use_line_markers: ``bool``; add markers to IRF lines.
    :param transparent_background: ``bool``; use a transparent background. If ``False``, uses a white background.
    :param dpi: ``int``; dots per inch.
    :param dump_source: ``bool``; Whether to dump the plot source array to a csv file.
    :return: ``None``
    """

    plt.rcParams["font.family"] = "sans-serif"

    fig = plt.figure()
    fig.set_size_inches(plot_x_inches, plot_y_inches)
    ax = fig.gca(projection='3d')
    ax.view_init(50, 215)
    ax.w_xaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))
    ax.w_yaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))
    ax.w_zaxis.set_pane_color((1.0, 1.0, 1.0, 0.0))

    irf_names_processed = irf_names[:]
    if irf_name_map is not None:
        for i in range(len(irf_names_processed)):
            irf_names_processed[i] = ':'.join([get_irf_name(x, irf_name_map) for x in irf_names_processed[i].split(':')])
    if sort_names:
        sort_ix = [i[0] for i in sorted(enumerate(irf_names_processed), key=lambda x:x[1])]
    else:
        sort_ix = range(len(irf_names_processed))
    for i in range(len(sort_ix)):
        filename = (prefix + '_' + '%s_' % irf_names_processed[sort_ix[i]] + suffix).replace(':', '_by_').replace(' ', '_')
        x = plot_x[..., sort_ix[i]]
        y = plot_y[..., sort_ix[i]]
        z = plot_z[..., sort_ix[i]]
        if lq is None:
            lq_cur = None
        else:
            lq_cur = lq[..., sort_ix[i]]
        if uq is None:
            uq_cur = None
        else:
            uq_cur = uq[..., sort_ix[i]]
        try:
            rcount, ccount = z.shape
            if plot_type.lower() == 'surf':
                if bounds_as_surface and lq_cur is not None:
                    ax.plot_surface(
                        x,
                        y,
                        lq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        color=(0.5, 0.5, 0.5, 0.5),
                        linewidth=2,
                        alpha=0.1,
                        antialiased=False,
                        zorder=1
                    )
                ax.plot_surface(
                    x,
                    y,
                    z,
                    rcount=rcount,
                    ccount=ccount,
                    cmap=cmap,
                    linewidth=2,
                    alpha=0.7,
                    antialiased=False,
                    norm=matplotlib.colors.TwoSlopeNorm(vcenter=0.)
                )
                if bounds_as_surface and uq_cur is not None:
                    ax.plot_surface(
                        x,
                        y,
                        uq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        color=(0.5, 0.5, 0.5, 0.5),
                        linewidth=2,
                        alpha=0.1,
                        antialiased=False,
                        zorder=3
                    )
            elif plot_type.lower() == 'trisurf':
                if bounds_as_surface and lq_cur is not None:
                    ax.plot_trisurf(
                        x,
                        y,
                        lq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        color=(0.5, 0.5, 0.5, 0.5),
                        linewidth=2,
                        alpha=0.1,
                        antialiased=False,
                        zorder=1
                    )
                ax.plot_trisurf(
                    x,
                    y,
                    z,
                    rcount=rcount,
                    ccount=ccount,
                    cmap=cmap,
                    linewidth=2,
                    alpha=0.7,
                    antialiased=False,
                    norm=matplotlib.colors.TwoSlopeNorm(vcenter=0.)
                )
                if bounds_as_surface and uq_cur is not None:
                    ax.plot_trisurf(
                        x,
                        y,
                        uq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        color=(0.5, 0.5, 0.5, 0.5),
                        linewidth=2,
                        alpha=0.1,
                        antialiased=False,
                        zorder=3
                    )
            elif plot_type.lower() == 'contour':
                if bounds_as_surface and lq_cur is not None:
                    ax.contour3D(
                        x,
                        y,
                        lq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        color=(0.5, 0.5, 0.5, 0.5),
                        alpha=0.1,
                        zorder=1
                    )
                ax.contour3D(
                    x,
                    y,
                    z,
                    rcount=rcount,
                    ccount=ccount,
                    cmap=cmap,
                    norm=matplotlib.colors.TwoSlopeNorm(vcenter=0.)
                )
                if bounds_as_surface and uq_cur is not None:
                    ax.contour3D(
                        x,
                        y,
                        uq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        color=(0.5, 0.5, 0.5, 0.5),
                        alpha=0.1,
                        zorder=3
                    )
            elif plot_type.lower() == 'wireframe':
                vcenter = 0
                vmin = z.min() - 1e-8
                vmax = z.max() + 1e-8
                if vmin < 0 and vmax > 0:
                    bound = max(abs(vmin), vmax)
                    vmin = -bound
                    vmax = bound
                elif vmin < 0.:
                    vmax = 1e-8
                else: # vmax > 0
                    vmin = -1e-8
                norm = matplotlib.colors.TwoSlopeNorm(
                    vmin=vmin,
                    vcenter=vcenter,
                    vmax=vmax
                )

                facecolors = getattr(cm, cmap)(norm(z))
                facecolors_bounds = np.ones(z.shape + (4,)) * 0.5
                if bounds_as_surface and lq_cur is not None:
                    surf = ax.plot_surface(
                        x,
                        y,
                        lq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        facecolors=facecolors_bounds,
                        alpha=0.1,
                        linewidth=2,
                        antialiased=False,
                        shade=False,
                        zorder=1
                    )
                    surf.set_facecolor((0, 0, 0, 0))
                surf = ax.plot_surface(
                    x,
                    y,
                    z,
                    rcount=rcount,
                    ccount=ccount,
                    facecolors=facecolors,
                    linewidth=2,
                    antialiased=False,
                    shade=False
                )
                surf.set_facecolor((0, 0, 0, 0))
                if bounds_as_surface and uq_cur is not None:
                    surf = ax.plot_surface(
                        x,
                        y,
                        uq_cur,
                        rcount=rcount,
                        ccount=ccount,
                        facecolors=facecolors_bounds,
                        alpha=0.1,
                        linewidth=2,
                        antialiased=False,
                        shade=False,
                        zorder=3
                    )
                    surf.set_facecolor((0, 0, 0, 0))

            else:
                raise ValueError('Unrecognized surface plot type: %s.' % plot_type)

            if not bounds_as_surface and lq_cur is not None:
                for _x, _y, _z, _lq, in zip(*[arr.flatten() for arr in (x, y, z, lq_cur)]):
                    ax.plot([_x, _x], [_y, _y], [_lq, _z], c='black', alpha=0.2, zorder=1)
            if not bounds_as_surface and uq_cur is not None:
                for _x, _y, _z, _uq in zip(*[arr.flatten() for arr in (x, y, z, uq_cur)]):
                    ax.plot([_x, _x], [_y, _y], [_z, _uq], c='black', alpha=0.2, zorder=3)

            fig.suptitle(irf_names_processed[sort_ix[i]])
            if ylab is not None and ylab.lower() == 'infer' and xlab is not None and xlab.lower() == 'infer':
                xlab_cur, ylab_cur = irf_names_processed[sort_ix[i]].split(':')
            elif ylab is not None and ylab.lower() == 'infer':
                xlab_cur = xlab
                ylab_cur = irf_names_processed[sort_ix[i]]
            else:
                ylab_cur = ylab
                xlab_cur = xlab
            zlab_cur = zlab

            if xlab_cur:
                ax.set_xlabel(xlab_cur, weight='bold')
            if ylab_cur:
                ax.set_ylabel(ylab_cur, weight='bold')
            if zlab_cur:
                ax.set_zlabel(zlab_cur, weight='bold')

            fig.savefig(
                dir + '/' + filename,
                dpi=dpi,
                transparent=transparent_background
            )
        except TypeError as e:
            stderr('Error saving plot to file %s. Description:\n%s\nSkipping...\n' % (dir + '/' + filename, e))
        ax.clear()

    plt.close('all')


def plot_qq(
        theoretical,
        actual,
        actual_color='royalblue',
        expected_color='firebrick',
        dir='.',
        filename='qq_plot.png',
        plot_x_inches=6,
        plot_y_inches=4,
        legend=True,
        xlab='Theoretical',
        ylab='Empirical',
        ticks=True,
        as_lines=False,
        transparent_background=False,
        dpi=300
):
    """
    Generate quantile-quantile plot.

    :param theoretical: ``numpy`` array with shape (T,); theoretical error quantiles.
    :param actual: ``numpy`` array with shape (T,); empirical errors.
    :param actual_color: ``str``; color for actual values.
    :param expected_color: ``str``; color for expected values.
    :param dir: ``str``; output directory.
    :param filename: ``str``; filename.
    :param plot_x_inches: ``float``; width of plot in inches.
    :param plot_y_inches: ``float``; height of plot in inches.
    :param legend: ``bool``; include a legend.
    :param xlab: ``str`` or ``None``; x-axis label. If ``None``, no label.
    :param ylab: ``str`` or ``None``; y-axis label. If ``None``, no label.
    :param as_lines: ``bool``; render QQ plot using lines. Otherwise, use points.
    :param transparent_background: ``bool``; use a transparent background. If ``False``, uses a white background.
    :param dpi: ``int``; dots per inch.
    :return: ``None``
    """

    plt.rcParams["font.family"] = "sans-serif"
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['bottom'].set_visible(False)
    plt.gca().spines['left'].set_visible(False)
    plt.gca().tick_params(top='off', bottom='off', left='off', right='off', labelleft='on' if ticks else 'off', labelbottom='on' if ticks else 'off')
    plt.grid(b=True, which='major', axis='both', ls='--', lw=.5, c='k', alpha=.3)
    plt.axhline(y=0, lw=1, c='gray', alpha=1)
    plt.axvline(x=0, lw=1, c='gray', alpha=1)

    if as_lines:
        plt.plot(theoretical, actual, label='Actual', lw=2, alpha=0.8, color=actual_color)
    else:
        plt.scatter(theoretical, actual, label='Actual', lw=2, alpha=0.8, facecolors='none', edgecolors=actual_color)
    plt.plot(theoretical, theoretical, label='Expected', lw=2, alpha=0.8, color=expected_color)

    if xlab:
        plt.xlabel(xlab, weight='bold')
    if ylab:
        plt.ylabel(ylab, weight='bold')
    if legend:
        plt.legend(fancybox=True, framealpha=0.75, frameon=True, facecolor='white', edgecolor='gray')

    plt.gcf().set_size_inches(plot_x_inches, plot_y_inches)
    plt.tight_layout()
    try:
        plt.savefig(dir+'/'+filename, dpi=dpi, transparent=transparent_background)
    except e:
        stderr('Error saving plot to file %s\n. \s\nSkipping...\n' %(dir+'/'+filename, e))
    plt.close('all')


def plot_heatmap(
        m,
        row_names,
        col_names,
        dir='.',
        filename='eigenvectors.png',
        plot_x_inches=7,
        plot_y_inches=5,
        cmap='Blues'
):
    """
    Plot a heatmap. Used in CDR for visualizing eigenvector matrices in principal components models.

    :param m: 2D ``numpy`` array; source data for plot.
    :param row_names: ``list`` of ``str``; row names.
    :param col_names: ``list`` of ``str``; column names.
    :param dir: ``str``; output directory.
    :param filename: ``str``; filename.
    :param plot_x_inches: ``float``; width of plot in inches.
    :param plot_y_inches: ``float``; height of plot in inches.
    :param cmap: ``str``; name of ``matplotlib`` ``cmap`` object (determines colors of plotted IRF).
    :return: ``None``
    """

    cm = plt.get_cmap(cmap)
    plt.gca().set_xticklabels(col_names)
    plt.gca().set_xticks(np.arange(len(col_names)) + 0.5, minor=False)
    plt.gca().set_yticklabels(row_names)
    plt.gca().set_yticks(np.arange(len(row_names)) + 0.5, minor=False)
    heatmap = plt.pcolor(m, cmap=cm)
    plt.colorbar(heatmap)
    plt.gcf().set_size_inches(plot_x_inches, plot_y_inches)
    plt.gcf().subplots_adjust(bottom=0.25,left=0.25)
    try:
        plt.savefig(dir+'/'+filename)
    except:
        stderr('Error saving plot to file %s. Skipping...\n' %(dir+'/'+filename))
    plt.close('all')



