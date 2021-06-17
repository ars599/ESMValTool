"""
Mpas's plotting tool. PAS
============================

Basically the same as time series, just with a few additions.

Diagnostic to produce figures of the time development of a field from
cubes. These plost show time on the x-axis and cube value (ie temperature) on
the y-axis.

Two types of plots are produced: individual model timeseries plots and
multi model time series plots. The inidivual plots show the results from a
single cube, even if this is a mutli-model mean made by the _multimodel.py
preproccessor. The multi model time series plots show several models
on the same axes, where each model is represented by a different line colour.

Note that this diagnostic assumes that the preprocessors do the bulk of the
hard work, and that the cube received by this diagnostic (via the settings.yml
and metadata.yml files) has a time component, no depth component, and no
latitude or longitude coordinates.

An approproate preprocessor for a 3D+time field would be::

  preprocessors:
    prep_timeseries_1:# For Global Volume Averaged
      volume_statistics:
        operator: mean


An approproate preprocessor for a 3D+time field at the surface would be::

    prep_timeseries_2: # For Global surface Averaged
      extract_levels:
        levels:  [0., ]
        scheme: linear_extrap
      area_statistics:
        operator: mean


An approproate preprocessor for a 2D+time field would be::

    prep_timeseries_2: # For Global surface Averaged
      area_statistics:
        operator: mean


This tool is part of the ocean diagnostic tools package in the ESMValTool.

Author: Lee de Mora (PML)
        ledm@pml.ac.uk
"""

import logging
import os

import iris
import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from esmvalcore.preprocessor._time import extract_time
from esmvalcore.preprocessor._volume import extract_levels



from esmvaltool.diag_scripts.ocean import diagnostic_tools as diagtools
from esmvaltool.diag_scripts.shared import run_diagnostic

# This part sends debug statements to stdout
logger = logging.getLogger(os.path.basename(__file__))

ipcc_colours={
    'historical':'blue',
    'ssp126': 'green',
    'ssp245': 'gold',
    'ssp370': 'orange',
    'ssp585': 'red',}

long_name_dict = {
    'thetao': 'Temperature',
    'tos': 'Surface Temperature',
    'tob': 'Seafloor Temperature',
    'sos': 'Surface Salinity',
    'uo': 'Zonal Velocity',
    'vo': 'Meridional Velocity',
    'ph': 'Surface pH',
    'chl': 'Surface chlorophyll',
    'zos': 'Sea Surface Height',
    'no3': 'Dissolved Nitrate',
    'o2': 'Dissolved Oxygen',
    'intpp': 'Integrated Primary production'}

def timeplot(cube, **kwargs):
    """
    Create a time series plot from the cube.

    Note that this function simple does the plotting, it does not save the
    image or do any of the complex work. This function also takes and of the
    key word arguments accepted by the matplotlib.plt.plot function.
    These arguments are typically, color, linewidth, linestyle, etc...

    If there's only one datapoint in the cube, it is plotted as a
    horizontal line.

    Parameters
    ----------
    cube: iris.cube.Cube
        Input cube

    """
    cubedata = np.ma.array(cube.data)
    if len(cubedata.compressed()) == 1:
        plt.axhline(cubedata.compressed(), **kwargs)
        return

    times = diagtools.cube_time_to_float(cube)
    plt.plot(times, cubedata, **kwargs)


def moving_average(cube, window):
    """
    Calculate a moving average.

    The window is a string which is a number and a measuremet of time.
    For instance, the following are acceptable window strings:

    * ``5 days``
    * ``12 years``
    * ``1 month``
    * ``5 yr``

    Also note the the value used is the total width of the window.
    For instance, if the window provided was '10 years', the the moving
    average returned would be the average of all values within 5 years
    of the central value.

    In the case of edge conditions, at the start an end of the data, they
    only include the average of the data available. Ie the first value
    in the moving average of a ``10 year`` window will only include the average
    of the five subsequent years.

    Parameters
    ----------
    cube: iris.cube.Cube
        Input cube
    window: str
        A description of the window to use for the

    Returns
    ----------
    iris.cube.Cube:
        A cube with the movinage average set as the data points.

    """
    if window  in ['annual', ]:
        window = '1 year'
    window = window.split()
    window_len = int(window[0]) / 2.
    win_units = str(window[1])

    if win_units not in [
            'days', 'day', 'dy', 'months', 'month', 'mn', 'years', 'yrs',
            'year', 'yr'
    ]:
        raise ValueError("Moving average window units not recognised: " +
                         "{}".format(win_units))

    times = cube.coord('time').units.num2date(cube.coord('time').points)

    datetime = diagtools.guess_calendar_datetime(cube)

    output = []

    times = np.array([
        datetime(time_itr.year, time_itr.month, time_itr.day, time_itr.hour,
                 time_itr.minute) for time_itr in times
    ])

    for time_itr in times:
        if win_units in ['years', 'yrs', 'year', 'yr']:
            tmin = datetime(time_itr.year - window_len, time_itr.month,
                            time_itr.day, time_itr.hour, time_itr.minute)
            tmax = datetime(time_itr.year + window_len, time_itr.month,
                            time_itr.day, time_itr.hour, time_itr.minute)

        if win_units in ['months', 'month', 'mn']:
            tmin = datetime(time_itr.year, time_itr.month - window_len,
                            time_itr.day, time_itr.hour, time_itr.minute)
            tmax = datetime(time_itr.year, time_itr.month + window_len,
                            time_itr.day, time_itr.hour, time_itr.minute)

        if win_units in ['days', 'day', 'dy']:
            tmin = datetime(time_itr.year, time_itr.month,
                            time_itr.day - window_len, time_itr.hour,
                            time_itr.minute)
            tmax = datetime(time_itr.year, time_itr.month,
                            time_itr.day + window_len, time_itr.hour,
                            time_itr.minute)

        arr = np.ma.masked_where((times < tmin) + (times > tmax), cube.data)
        output.append(arr.mean())
    cube.data = np.array(output)
    return cube



def multi_model_time_series(
        cfg,
        metadatas,
        ts_dict = {},
        moving_average_str='',
        colour_scheme = 'IPCC',
        fig = None,
        ax = None,
        save = False
):
    """
    Make a time series plot showing several preprocesssed datasets.

    This tool loads several cubes from the files, checks that the units are
    sensible BGC units, checks for layers, adjusts the titles accordingly,
    determines the ultimate file name and format, then saves the image.

    Parameters
    ----------
    cfg: dict
        the opened global config dictionairy, passed by ESMValTool.
    metadata: dict
        The metadata dictionairy for a specific model.

    """
    ####
    # Load the data for each layer as a separate cube
    model_cubes = {}
    model_cubes_paths = {}

    for variable_group, filenames  in ts_dict.items():
        for fn in sorted(filenames):
            print(variable_group, fn)
            #assert 0
            if metadatas[fn]['mip'] in ['Ofx', 'fx']: continue
            print('loading', fn)

            cube = iris.load_cube(fn)
            cube = diagtools.bgc_units(cube, metadatas[fn]['short_name'])

            model_cubes = add_dict_list(model_cubes, variable_group, cube)
            model_cubes_paths = add_dict_list(model_cubes_paths, variable_group, fn)

    if fig is None or ax is None:
        fig = plt.figure()
        ax = fig.add_subplot(111)
        save = True
    else:
        plt.sca(ax)

    title = ''
    z_units = ''
    plot_details = {}
    if colour_scheme in ['viridis', 'jet']:
        cmap = plt.cm.get_cmap(colour_scheme)

    # Plot individual model in the group
    plotting = [ 'means',  '5-95'] #'medians', 'all_models', 'range',
    for variable_group, cubes in model_cubes.items():
        data_values = {}
        for i, cube in enumerate(cubes):
            path = model_cubes_paths[variable_group][i]
            metadata = metadatas[path]
            scenario = metadata['exp']
            dataset = metadata['dataset']
            times = diagtools.cube_time_to_float(cube)
            for t, d in zip(times, cube.data):
                data_values = add_dict_list(data_values, t, d)
            if colour_scheme in ['viridis', 'jet']:
                if len(metadata) > 1:
                    color = cmap(index / (len(metadata) - 1.))
                else:
                    color = 'blue'
                label = dataset
            if colour_scheme in 'IPCC':
                color = ipcc_colours[scenario]
                label =  scenario
            # Take a moving average, if needed.
            if moving_average_str:
                    cube = moving_average(cube,
                          moving_average_str)

            if 'all_models' in plotting:
                timeplot(
                    cube,
                    c=color,
                    ls='-',
                    lw=0.6,
                )
        if 'means' in plotting:
            times = sorted(data_values.keys())
            mean = [np.mean(data_values[t]) for t in times]
            plt.plot(times, mean, ls='-', c=color, lw=2.)
            plot_details[path] = {
                'c': color,
                'ls': '-',
                'lw': 2.,
                'label': label,
            }

        if 'medians' in plotting:
            times = sorted(data_values.keys())
            mean = [np.median(data_values[t]) for t in times]
            plt.plot(times, mean, ls='-', c=color, lw=2.)
            plot_details[path] = {
                'c': color,
                'ls': '-',
                'lw': 2.,
                'label': label,
            }

        if 'range' in plotting:
            times = sorted(data_values.keys())
            mins = [np.min(data_values[t]) for t in times]
            maxs = [np.max(data_values[t]) for t in times]
            plt.fill_between(times, mins, maxs, color= ipcc_colours[scenario], alpha=0.5)

        if '5-95' in plotting:
            times = sorted(data_values.keys())
            mins = [np.percentile(data_values[t], 5.) for t in times]
            maxs = [np.percentile(data_values[t], 95.) for t in times]
            plt.fill_between(times, mins, maxs, color= ipcc_colours[scenario], alpha=0.5)

#   # Add title, legend to plots
    plt.title(title)
    plt.legend(loc='best')
    #plt.ylabel(str(model_cubes[filename][layer].units))

    # Saving files:
    if save:
        path = diagtools.folder(cfg['plot_dir']+'/individual_panes')
        path += '_'.join(['multi_model_ts', ] )
        path += '_'.join(plotting)
        path += diagtools.get_image_format(cfg)

        # Resize and add legend outside thew axes.
        fig.set_size_inches(9., 6.)
        diagtools.add_legend_outside_right(
            plot_details, plt.gca(), column_width=0.15)

        logger.info('Saving plots to %s', path)
        plt.savefig(path)
        plt.close()
    else:
        return fig, ax



def multi_model_clim_figure(
        cfg,
        metadatas,
        ts_dict = {},
        figure_style = 'plot_all_years',
        hist_time_range = [1990., 2000.],
        ssp_time_range = [2040., 2050.],
        fig = None,
        ax = None,
        save=False
    ):
    """
    produce a monthly climatology figure.
    """
    if fig is None or ax is None:
        fig = plt.figure()
        ax = fig.add_subplot(111)
        save=True

    ####
    # Load the data for each layer as a separate cube
    model_cubes = {}
    model_cubes_paths = {}

    for variable_group, filenames  in ts_dict.items():
        for fn in sorted(filenames):
            print(variable_group, fn)
            #assert 0
            if metadatas[fn]['mip'] in ['Ofx', 'fx']: continue
            scenario = metadatas[fn]['exp']

            print('loading', fn)

            cube = iris.load_cube(fn)
            cube = diagtools.bgc_units(cube, metadatas[fn]['short_name'])

            if not cube.coords('year'):
                iris.coord_categorisation.add_year(cube, 'time')

            if not cube.coords('month_number'):
                iris.coord_categorisation.add_month_number(cube, 'time', name='month_number')

            if scenario == 'historical':
                cube = extract_time(cube, hist_time_range[0], 1, 1, hist_time_range[1], 12, 31)
            else:
                cube = extract_time(cube, ssp_time_range[0], 1, 1, ssp_time_range[1], 12, 31)

            # Only interested in the mean over the time range provided.
            cube = cube.aggregated_by(['month_number', ], iris.analysis.MEAN)
            #cube_min = cube.copy().aggregated_by(['month_number', ], iris.analysis.MIN)
            #cube_max = cube.copy().aggregated_by(['month_number', ], iris.analysis.MAX)

            model_cubes = add_dict_list(model_cubes, variable_group, cube)
            model_cubes_paths = add_dict_list(model_cubes_paths, variable_group, fn)


    #labels = []
    plotting = [ 'means',  '5-95', ] #'all_models'] #'medians', , 'range',
    for variable_group, cubes in model_cubes.items():
        data_values = {}
        scenario = ''
        for i, cube in enumerate(cubes):
            fn = model_cubes_paths[variable_group][i]
            if metadatas[fn]['mip'] in ['Ofx', 'fx']: continue
            scenario = metadatas[fn]['exp']

            months =  cube.coord('month_number').points
            for t, d in zip(months, cube.data):
                data_values = add_dict_list(data_values, t, d)
                #years_range = sorted({yr:True for yr in cube.coord('year').points}.keys())
            color = ipcc_colours[scenario]
            label =  scenario

            if 'all_models' in plotting:
                plt.plot(months, cube.data, ls='-', c=color, lw=0.6)

        times = sorted(data_values.keys())
        if 'means' in plotting:
            mean = [np.mean(data_values[t]) for t in times]
            plt.plot(times, mean, ls='-', c=color, lw=2.)

        if 'medians' in plotting:
            mean = [np.median(data_values[t]) for t in times]
            plt.plot(times, mean, ls='-', c=color, lw=2.)
#
        if 'range' in plotting:
            times = sorted(data_values.keys())
            mins = [np.min(data_values[t]) for t in times]
            maxs = [np.max(data_values[t]) for t in times]
            plt.fill_between(times, mins, maxs, color=color, alpha=0.5)

        if '5-95' in plotting:
            times = sorted(data_values.keys())
            mins = [np.percentile(data_values[t], 5.) for t in times]
            maxs = [np.percentile(data_values[t], 95.) for t in times]
            plt.fill_between(times, mins, maxs, color=color, alpha=0.5)

    plt.legend()

    time_str = '_'.join(['-'.join([str(t) for t in hist_time_range]), 'vs',
                         '-'.join([str(t) for t in ssp_time_range])])

    #plt.suptitle(' '.join([long_name_dict[short_name], 'in Ascension'
    #                       ' Island MPA \n Historical', '-'.join([str(t) for t in hist_time_range]),
    #                       'vs SSP', '-'.join([str(t) for t in ssp_time_range]) ]))

    units = cube.units
    ax.set_xlabel('Months')
    #ax.set_ylabel(' '.join([short_name+',', str(units)]))

    if save:
        # save and close.
        path = diagtools.folder(cfg['plot_dir']+'/multi_model_clim')
        path += '_'.join(['multi_model_clim', time_str])
        path += '_'.join(plotting)
        path += diagtools.get_image_format(cfg)

        logger.info('Saving plots to %s', path)
        plt.savefig(path)
        plt.close()
    else:
        return fig, ax





###################################

def extract_depth_range(data, depths, drange='surface', threshold=1000.):
    """
    Extract either the top 1000m or everything below there.

    drange can be surface or depths.

    Assuming everything is 1D at this stage!
    """
    if drange == 'surface':
        data = np.ma.masked_where(depths >= threshold, data)
    elif drange == 'depths':
        data = np.ma.masked_where(depths < threshold, data)

    return data


def plot_z_line(depths, data, ax0, ax1, ls='-', c='blue', lw=2., label = label):
    for ax, drange in zip([ax0, ax1], ['surface', 'depths']):
        data = extract_depth_range(data, depths, drange=drange)
        ax.plot(data, depths,
            lw=lw,
            ls=ls,
            c=c,
            label= label)
    return ax0, ax1

def plot_z_area(depths, data_min, data_max, ax0, ax1, ls='-', c='blue', lw=2., label = label):
    for ax, drange in zip([ax0, ax1], ['surface', 'depths']):
        data_min = extract_depth_range(data_min, depths, drange=drange)
        data_max = extract_depth_range(data_max, depths, drange=drange)

        ax.fill_betweenx(depths, data_min, data_max,
            color=c,
            alpha = 0.5,
            label= label)
    return ax0, ax1


def make_multi_model_profiles_plots(
        cfg,
        metadatas,
        profile_fns = {}
        #short_name,
        obs_metadata={},
        obs_filename='',
        hist_time_range = [1990., 2000.],
        ssp_time_range = [2040., 2050.],
        figure_style = 'difference',
        fig = None,
        ax = None,
        save = False,
        draw_legend=True
    ):
    """
    Make a profile plot for an individual model.

    The optional observational dataset can also be added.

    Parameters
    ----------
    cfg: dict
        the opened global config dictionairy, passed by ESMValTool.
    metadata: dict
        The metadata dictionairy for a specific model.
    filename: str
        The preprocessed model file.
    obs_metadata: dict
        The metadata dictionairy for the observational dataset.
    obs_filename: str
        The preprocessed observational dataset file.

    """
    # Load cube and set up units
    if fig is None or ax is None:
        save = True
        fig = plt.figure()
        gs = matplotlib.gridspec.GridSpec(ncols=1, nrows=1) # master
        gs0 =gs[0,0].subgridspec(ncols=1, nrows=2, height_ratios=[2, 1], hspace=0.)
    else:
        single_pane = False

    #gs0 = gs[0].subgridspec(2, 1, hspace=0.35) # scatters
    #gs1 = gs[1].subgridspec(3, 1, hspace=0.06 ) # maps
        #scatters
    ax0=fig.add_subplot(gs0[0,0]) # surface
    ax1=fig.add_subplot(gs0[1,0]) # depths

    model_cubes = {}
    model_cubes_paths = {}
    for variable_group, filenames in profile_fns.items():
        for i, fn in enumerate(filenames):
            cube = iris.load_cube(fn)
            cube = diagtools.bgc_units(cube, metadata['short_name'])

            scenario = metadatas[fn]['exp']
            if scenario == 'historical':
                cube = extract_time(cube, hist_time_range[0], 1, 1, hist_time_range[1], 12, 31)
            else:
                cube = extract_time(cube, ssp_time_range[0], 1, 1, ssp_time_range[1], 12, 31)

            # Only interested in the mean over the time range provided for each model.
            cube = cube.collapsed('time', iris.analysis.MEAN)

            # ensure everyone uses the same levels:
            cube = extract_levels(cube,
                scheme='linear',
                levels =  [0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0,
                           600.0, 700.0, 800.0, 900.0, 999.0, 1001., 1500.0, 2000.0, 2500.0, 3000.0, 3500.0,
                           4000.0, 4500.0, 5000.0]
                )

            model_cubes = add_dict_list(model_cubes, variable_group, cube)
            model_cubes_paths = add_dict_list(model_cubes_paths, variable_group, fn)

    plotting = [ 'means',  '5-95', 'all_models'] #'medians', , 'range',

    for variable_group, cubes in model_cubes.items():
        data_values = {}
        scenario = ''
        color = ''
        for i, cube in enumerate(cubes):
            fn = model_cubes_paths[variable_group][i]
            metadata = metadatas[fn]
            scenario = metadata['exp']
            color = ipcc_colours[scenario]

            depths = cube.coord('depth').points
            for z, d in zip(depths, cube.data):
                data_values = add_dict_list(data_values, z, d)

            if 'all_models'  in plotting:
                 ax0, ax1 = plot_z_line(depths, cube.data, ax0, ax1, ls='-', c=color, lw=2., label = scenario)

        depths = sorted(data_values.keys())
        if 'means' in plotting:
            mean = [np.mean(data_values[z]) for z in depths]
            ax0, ax1 = plot_z_line(depths, mean, ax0, ax1, ls='-', c=color, lw=2., label = scenario)

        if 'medians' in plotting:
            medians = [np.median(data_values[z]) for z in depths]
            ax0, ax1 = plot_z_line(depths, medians, ax0, ax1, ls='-', c=color, lw=2., label = scenario)

        if 'range' in plotting:
            mins = [np.min(data_values[z]) for z in depths]
            maxs = [np.max(data_values[z]) for z in depths]
            ax0, ax1 =  plot_z_area(depths, mins, maxs, color= ipcc_colours[scenario], alpha=0.5)

        if '5-95' in plotting:
            mins = [np.percentile(data_values[z], 5.) for z in depths]
            maxs = [np.percentile(data_values[z], 95.) for z in depths]
            ax0, ax1 =  plot_z_area(depths, mins, maxs, color= ipcc_colours[scenario], alpha=0.5)




    # for (dataset, scenario, ensemble, metric), cube_mean in cubes.items():
    #     if metric != 'mean': continue
    #
    #     cube_min = cubes[(dataset, scenario, ensemble, 'min')]
    #     cube_max = cubes[(dataset, scenario, ensemble, 'max')]
    #     cube_hist = cubes[(dataset, 'historical', ensemble, 'mean')]
    #
    #     color = diagtools.ipcc_colours[scenario]
    #     plot_details = {}
    #
    #     for ax, drange in zip([ax0, ax1], ['surface', 'depths']):
    #
    #         if figure_style == 'difference':
    #             z_hist, z_cube_hist = extract_depth_range(cube_hist, cube_hist.coord('depth').points, drange=drange)
    #             z_min, z_cube_min = extract_depth_range(cube_min, cube_hist.coord('depth').points, drange=drange)
    #             z_max, z_cube_max = extract_depth_range(cube_max, cube_hist.coord('depth').points, drange=drange)
    #             z_mean, z_cube_mean = extract_depth_range(cube_mean, cube_hist.coord('depth').points, drange=drange)
    #
    #             ax.plot(z_cube_mean.data - z_cube_hist.data, -1.*z_hist,
    #                 lw=2,
    #                 c=color,
    #                 label= scenario)
    #
    #             ax.fill_betweenx(-1.*z_hist,
    #                 z_cube_min.data - z_cube_hist.data,
    #                 x2=z_cube_max.data - z_cube_hist.data,
    #                 alpha = 0.2,
    #                 color=color)
    #
    #         if figure_style == 'compare':
    #             z_min, z_cube_min = extract_depth_range(cube_min, cube_mean.coord('depth').points, drange=drange)
    #             z_max, z_cube_max = extract_depth_range(cube_max, cube_mean.coord('depth').points, drange=drange)
    #             z_mean, z_cube_mean = extract_depth_range(cube_mean, cube_mean.coord('depth').points, drange=drange)
    #
    #             ax.plot(z_cube_mean.data, -1.*z_mean,
    #                 lw=2,
    #                 c=color,
    #                 label=scenario)
    #
    #             ax.fill_betweenx(-1.*z_mean,
    #                 z_cube_min.data,
    #                 x2=z_cube_max.data,
    #                 alpha = 0.2,
    #                 color=color)
    #
    #     plot_details[scenario] = {'c': color, 'ls': '-', 'lw': 1,
    #                                          'label': scenario}
    #
    # # Add units:
    # units = cubes[(dataset, scenario, ensemble,'mean')].units
    # if figure_style == 'difference':
    #     ax.set_xlabel(r'$\Delta$ ' +str(units))
    # if figure_style == 'compare':
    #     ax.set_xlabel(str(units))

    # Add observational data.
    if obs_filename:
        obs_cube = iris.load_cube(obs_filename)
        obs_cube = diagtools.bgc_units(obs_cube, metadata['short_name'])
        obs_cube = obs_cube.collapsed('time', iris.analysis.MEAN)

        obs_key = obs_metadata['dataset']
        qplt.plot(obs_cube, obs_cube.coord('depth'), c='black')

        plot_details[obs_key] = {'c': 'black', 'ls': '-', 'lw': 1,
                                 'label': obs_key}

    time_str = '_'.join(['-'.join([str(t) for t in hist_time_range]), 'vs',
                         '-'.join([str(t) for t in ssp_time_range])])

    # set x axis limits:
    xlims = np.array([ax0.get_xlim(), ax1.get_xlim()])
    ax0.set_xlim([xlims.min(), xlims.max()])
    ax1.set_xlim([xlims.min(), xlims.max()])

    ylims = np.array([ax0.get_ylim(), ax1.get_ylim()])
    ax0.set_ylim([-1000., ylims.max()])
    ax1.set_ylim([ylims.min(), -1001.])

    # hide between pane axes and ticks:
    ax0.spines['bottom'].set_visible(False)
    ax0.xaxis.set_ticks_position('none')
    ax0.xaxis.set_ticklabels([])
    ax1.spines['top'].set_visible(False)

#    ax0.fill_bewteen([xlims.min(), xlims.max()],[-1000., -1000.], [-975., -975.], color= 'k', alpha=0.2)
#    ax1.fill_bewteen([xlims.min(), xlims.max()],[-1100., -1100.],[-1000., -1000.], color= 'k', alpha=0.2)

    # draw a line between figures
    ax0.axhline(-999., ls='--', lw=1.5, c='black')
    ax1.axhline(-1001., ls='--', lw=1.5, c='black')

    if single_pane:
        # Add title to plot
        title = ' '.join([
            # short_name,
            # figure_style,
            time_str
            ])
        # ax0.set_title(title)
    else:
        #ax0.yaxis.set_ticks_position('both')
        #ax1.yaxis.set_ticks_position('both')
        if figure_style == 'difference':
           ax0.yaxis.set_ticks_position('right')
           ax1.yaxis.set_ticks_position('right')
           ax0.yaxis.set_ticklabels([])
           ax1.yaxis.set_ticklabels([])
           ax0.set_title('Difference against historical')

        else:
             ax0.set_title('Mean and Range')


    # Add Legend outside right.
    if draw_legend:
        ax1.legend(loc='lower left')
    #diagtools.add_legend_outside_right(plot_details, plt.gca())

    if not single_pane:
        return fig, ax
    # Saving files:

    # Load image format extention
    image_extention = diagtools.get_image_format(cfg)

    # Determine image filename:
    path = diagtools.folder(cfg['plot_dir']+'/profiles')
    path += '_'.join(['multi_model_profile', time_str])
    path += '_'.join(plotting)
    path += diagtools.get_image_format(cfg)

    logger.info('Saving plots to %s', path)
    plt.savefig(path)
    plt.close()

#####################################


def do_gridspec():
    #fig = None
    fig = plt.figure()
    fig.set_size_inches(12., 9.) #, 6.)

    gs = matplotlib.gridspec.GridSpec(ncols=1, nrows=2)
    gs0 =gs[0,0].subgridspec(ncols=4, nrows=2, ) #ght_ratios=[2, 1], hspace=0.)
    subplots = {}
    subplots['timeseries'] = fig.add_subplot(gs0[0:2,0:2])
    subplots['climatology'] = fig.add_subplot(gs0[0, 2:4])
    #subplots['clim_diff'] = fig.add_subplot(gs0[0, 3])
    subplots['profile'] = fig.add_subplot(gs0[1, 2:4])
    #subplots['prof_diff'] = fig.add_subplot(gs0[1, 3])
    #
    # maps:
    gs1 =gs[1,0].subgridspec(ncols=3, nrows=2, )
    subplots['map_hist'] = fig.add_subplot(gs1[0,0])
    subplots['map_obs'] = fig.add_subplot(gs1[1,0])
    subplots['map_ssp125'] = fig.add_subplot(gs1[0,1])
    subplots['map_ssp245'] = fig.add_subplot(gs1[1,1])
    subplots['map_ssp379'] = fig.add_subplot(gs1[0,2])
    subplots['map_ssp585'] = fig.add_subplot(gs1[1,2])
    #plt.show()
    #plt.savefig('tmp.png')

    return fig, subplots


def add_dict_list(dic, key, item):
   try: dic[key].append(item)
   except: dic[key]= [item, ]
   return dic

def main(cfg):
    """
    Load the config file and some metadata, then pass them the plot making
    tools.

    Parameters
    ----------
    cfg: dict
        the opened global config dictionairy, passed by ESMValTool.

    """
    # Here is plan the parts of the plot:
    # Plot A:
    # top left: time series
    # top right: climatology
    # middle: profile:
    # right: maps

    # Strategy is to get all the individual plots made.
    # individual plots of the ensemble mean
    # Then stitch them together into a big single plot.
    metadatas = diagtools.get_input_files(cfg, )

    time_series_fns = {}
    profile_fns = {}
    maps_fns = {}

    for fn, metadata in metadatas.items():
        #print(os.path.basename(fn),':',metadata['variable_group'])
        variable_group = metadata['variable_group']
        if variable_group.find('_ts_')>-1:
            time_series_fns = add_dict_list(time_series_fns, variable_group, fn)
        if variable_group.find('_profile_')>-1:
            profile_fns = add_dict_list(profile_fns, variable_group, fn)
        if variable_group.find('_map_')>-1:
            maps_fns = add_dict_list(maps_fns, variable_group, fn)
    # Individual plots - standalone

    def make_multi_model_profiles_plots(
            cfg,
            metadatas,
            profile_fns = profile_fns,
            #short_name,
            #obs_metadata={},
            #obs_filename='',
            hist_time_range = [1990., 2015.],
            ssp_time_range = [2015., 2050.],
            #figure_style = 'difference',
            fig = None,
            ax = None,
            save = False,
            draw_legend=True
        )

    do_standalone = False
    if do_standalone:
        multi_model_clim_figure(
            cfg,
            metadatas,
            time_series_fns,
            hist_time_range = [1990., 2015.],
            ssp_time_range = [2015., 2050.],
        )

        multi_model_time_series(
                cfg,
                metadatas,
                ts_dict = time_series_fns,
                #moving_average_str='',
                #colour_scheme = 'viridis',
                #fig = fig,
                #ax =  subplots['timeseries'],
        )

    #print(time_series_fns)
    #print(profile_fns)
    #print(maps_fns)
    fig, subplots = do_gridspec()
    fig, subplots['timeseries'] = multi_model_time_series(
            cfg,
            metadatas,
            ts_dict = time_series_fns,
            #moving_average_str='',
            #colour_scheme = 'viridis',
            fig = fig,
            ax =  subplots['timeseries'],
    )

    fig, subplots['climatology'] =  multi_model_clim_figure(
        cfg,
        metadatas,
        time_series_fns,
        hist_time_range = [1990., 2015.],
        ssp_time_range = [2015., 2050.],
        fig = fig,
        ax =  subplots['climatology'],
    )


    # save and close.
    path = diagtools.folder(cfg['plot_dir']+'/whole_plot')
    path += '_'.join(['multi_model_whole_plot'])
    path += diagtools.get_image_format(cfg)

    logger.info('Saving plots to %s', path)
    plt.savefig(path)
    plt.close()

    return


    assert 0
    #moving_average_str = cfg.get('moving_average', None)
    # short_names = {}
    # metadatas = diagtools.get_input_files(cfg, )
    # for fn, metadata in metadatas.items():
    #     short_names[metadata['short_name']] = True
    #
    # for short_name in short_names.keys():
    #     hist_time_ranges = [[1850, 2015], [1850, 1900], [1950, 2000], [1990, 2000], [1990, 2000]]
    #     ssp_time_ranges  = [[2015, 2100], [2050, 2100], [2050, 2100], [2040, 2050], [2090, 2100]]
    #     for hist_time_range, ssp_time_range in zip(hist_time_ranges, ssp_time_ranges):
    #
    #         for figure_style in ['plot_all_years', 'mean_and_range']:
    #
    #             multi_model_clim_figure(
    #                 cfg,
    #                 metadatas,
    #                 short_name,
    #                 figure_style=figure_style,
    #                 hist_time_range=hist_time_range,
    #                 ssp_time_range=ssp_time_range,
    #             )
    return

    moving_average_strs = ['', 'annual', '5 years', '10 years', '20 years']
    for moving_average_str in moving_average_strs:
        for index, metadata_filename in enumerate(cfg['input_files']):
            logger.info('metadata filename:\t%s', metadata_filename)

            metadatas = diagtools.get_input_files(cfg, index=index)

            #######
            # Multi model time series
            multi_model_time_series(
                cfg,
                metadatas,

                moving_average_str=moving_average_str,
                colour_scheme = 'IPCC',
            )
            continue
            for filename in sorted(metadatas):
                if metadatas[filename]['frequency'] != 'fx':
                    logger.info('-----------------')
                    logger.info(
                        'model filenames:\t%s',
                        filename,
                    )

    logger.info('Success')


if __name__ == '__main__':
    with run_diagnostic() as config:
        main(config)