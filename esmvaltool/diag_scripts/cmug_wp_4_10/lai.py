"""
ESMValTool diagnostic for ESA CCI LST data.
The code uses the all time average monthly data.
The ouptput is a timeseries plot of the mean differnce of
CCI LST to model ensemble average, with the ensemble spread
represented by a standard deviation either side of the mean.
"""

import logging

import iris
import iris.coord_categorisation as icc

import matplotlib.pyplot as plt
import iris.plot as iplt
import numpy as np


from esmvaltool.diag_scripts.shared import (
    ProvenanceLogger,
    group_metadata,
    run_diagnostic,
)

logger = logging.getLogger(__name__)


scale_factor = 0.001 # cant find this in the files, * this by all CCI values to get actual value

def _get_input_cubes(metadata):
    """Load the data files into cubes.
    Based on the hydrology diagnostic.
    Inputs:
    metadata = List of dictionaries made from the preprocessor config
    Outputs:
    inputs = Dictionary of cubes
    ancestors = Dictionary of filename information
    """
    print('################################################')
    inputs = {}
    ancestors = {}
    print(metadata)
    for attributes in metadata:
        print(attributes)
        short_name = attributes['short_name']
        filename = attributes['filename']
        logger.info("Loading variable %s", short_name)
        cube = iris.load_cube(filename)
        cube.attributes.clear()
        
        try:
            key_name = f"{short_name}_{attributes['ensemble']}"
        except:
            key_name = short_name

        inputs[key_name] = cube
        ancestors[key_name] = [filename]
        
        print(inputs)
        print(ancestors)

    return inputs, ancestors

def _get_provenance_record(attributes, ancestor_files):
    """Create the provenance record dictionary.
    Inputs:
    attributes = dictionary of ensembles/models used, the region bounds
                 and years of data used.
    ancestor_files = list of data files used by the diagnostic.
    Outputs:
    record = dictionary of provenance records.
    """
    ### THIS ALL NEEDS CHANGING!!!
    caption = "CMUG WP4.10"

    record = {
        'caption': caption,
        'statistics': ['mean', 'stddev'],
        'domains': ['reg'],
        'plot_types': ['times'],
        'authors': ['king_robert'],
        # 'references': [],
        'ancestors': ancestor_files
    }

    return record


def _diagnostic(config):
    """Perform the control for the ESA CCI LST diagnostic
       with uncertainities included
    Parameters
    ----------
    config: dict
        the preprocessor nested dictionary holding
        all the needed information.
    Returns
    -------
    figures made by make_plots.
    """
    # this loading function is based on the hydrology diagnostic
    input_metadata = config['input_data'].values()

    loaded_data = {}
    ancestor_list = []
    for dataset, metadata in group_metadata(input_metadata, 'dataset').items():
        cubes, ancestors = _get_input_cubes(metadata)
        loaded_data[dataset] = cubes

    # loaded data is a nested dictionary
    # KEY1 model ESACCI-LST or something else
    # KEY2 is variable or variable_ensemble
    
    # The Diagnostics

    # CMIP data had 360 day calendar, CCI data has 365 day calendar
    # Assume the loaded data is all the same shape
    print('$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$')
    print('LOADED DATA:')
    print(loaded_data)


    #### REMEMBER TO APPLY FACTORS TO OBS DATA, DO THIS IN CMORIZER?????
    #### Iris seems to do this automatically for LAI

    # make ensemble mean of area average
    model_means = {}

    for KEY in loaded_data.keys():
        if KEY == 'CMUG_WP4_10': # add in LAI and Veg KEYS here as they become available
            continue # dont need to do this for CCI

        print(KEY) 
        # loop over ensembles
        ensemble_ts = iris.cube.CubeList()
        for e_number,ENSEMBLE in enumerate(loaded_data[KEY].keys()):

            print(ENSEMBLE)
            
            if ENSEMBLE[0:4] != 'lai_':
                continue
               
            this_cube_mean = loaded_data[KEY][ENSEMBLE].collapsed(['latitude','longitude'], iris.analysis.MEAN)

            ensemble_coord = iris.coords.AuxCoord(e_number, standard_name=None, 
                                                  long_name='ensemble_number', 
                                                  var_name=None,
                                                  units='1', bounds=None, 
                                                  attributes=None, coord_system=None)
            this_cube_mean.add_aux_coord(ensemble_coord)
            ensemble_ts.append(this_cube_mean)

        model_means[KEY] = ensemble_ts.merge_cube()
        model_means[KEY] = model_means[KEY].collapsed('ensemble_number', iris.analysis.MEAN)
        icc.add_year(model_means[KEY], 'time')
        icc.add_month_number(model_means[KEY], 'time')
                
    print(model_means)


   
    ### PLOT is CCI LST with bars of uncertainty
    ####     with shaded MODEL MEAN +/- std
    # Plotting
    # cci_lst = []
    # model_lst = model_means.collapsed('ensemble_number', iris.analysis.MEAN)
    # model_std = model_means.collapsed('ensemble_number', iris.analysis.STD_DEV)
    # print(model_lst.data)
    # print(model_std.data)

    colours = ['red','blue','black']
    fig = plt.figure()
    for i,KEY in enumerate(loaded_data.keys()):
        for e_number,ENSEMBLE in enumerate(loaded_data[KEY].keys()):
            this_cube_mean = loaded_data[KEY][ENSEMBLE].collapsed(['latitude','longitude'], iris.analysis.MEAN)
        
            plt.plot(this_cube_mean.data, label = f"{KEY} {ENSEMBLE}",
                      color=colours[i])

    outpath =  config['plot_dir']
    plt.legend()
    plt.savefig(f'{outpath}/lai.png')
    plt.close('all')  # Is this needed?


    # _make_plots(cci_lst, total_uncert, model_lst, model_std, ensemble_ts, config)

#     # Provenance
#     # Get this information form the data cubes
#     # data_attributes = {}
#     # data_attributes['start_year'] = lst_diff_cube.coord('time').units.num2date(
#     #     lst_diff_cube.coord('time').points)[0].year
#     # data_attributes['end_year'] = lst_diff_cube.coord('time').units.num2date(
#     #     lst_diff_cube.coord('time').points)[-1].year
#     # data_attributes['lat_south'] = lst_diff_cube.coord('latitude').bounds[0][0]
#     # data_attributes['lat_north'] = lst_diff_cube.coord('latitude').bounds[0][1]
#     # data_attributes['lon_west'] = lst_diff_cube.coord('longitude').bounds[0][0]
#     # data_attributes['lon_east'] = lst_diff_cube.coord('longitude').bounds[0][1]
#     # data_attributes['ensembles'] = ''

#     # for item in input_metadata:
#     #     if 'ESACCI' in item['alias'] or 'MultiModel' in item[
#     #             'alias'] or 'OBS' in item['alias']:
#     #         continue
#     #     data_attributes['ensembles'] += "%s " % item['alias']

#     # record = _get_provenance_record(data_attributes, ancestor_list)
#     # for file in ['%s/timeseries.png' % config['plot_dir']]:
#     #     with ProvenanceLogger(config) as provenance_logger:
#     #         provenance_logger.log(file, record)



def _make_plots(cci_lst, total_uncert, model_lst, model_std, ensemble_ts, config):
    """Create and save the output figure.
    PLOT 1
    The plot is CMIP model LST  with +/- one standard deviation
    of the model spread, and the mean CCI LST with +/- one total
    error
    PLOT 2
    The plot is all CMIP model LST  ensembles
    and the mean CCI LST with +/- one total
    error
    Inputs:
   
    config = The config dictionary from the preprocessor
    Outputs:
    Saved figure
    """

    for i in [0,1]:

        fig, ax = plt.subplots(figsize=(20, 15))

        if i == 0:
            model_low = (model_lst-model_std).data
            model_high = (model_lst+model_std).data

            ax.plot(model_lst.data, color='black', linewidth=4)
            ax.plot(model_low, '--', color='blue', linewidth=3)
            ax.plot(model_high, '--', color='blue', linewidth=3)
            ax.fill_between(range(len(model_lst.data)),
                            model_low,
                            model_high,
                            color='blue',
                            alpha=0.25)

        elif i==1:
            maxes = []
            mins = []
            for item in ensemble_ts.keys():
                ax.plot(ensemble_ts[item].data, color='black', linewidth=1)
                
                mins.append(np.min(ensemble_ts[item].data))
                maxes.append(np.max(ensemble_ts[item].data))

            model_low = np.min(mins)
            model_high = np.max(maxes)

        # make X ticks
        x_tick_list = []
        time_list = model_lst.coord('time').units.num2date(
            model_lst.coord('time').points)
        for item in time_list:
            if item.month == 1:
                x_tick_list.append(item.strftime('%Y %b'))
            elif item.month == 7:
                x_tick_list.append(item.strftime('%b'))
            else:
                x_tick_list.append('')

        ax.set_xticks(range(len(model_lst.data)))
        ax.set_xticklabels(x_tick_list, fontsize=18, rotation=45)

        # make Y ticks
        y_lower = np.floor(model_low.min())
        y_upper = np.ceil(model_high.max())
        ax.set_yticks(np.arange(y_lower, y_upper + 0.1, 2))
        ax.set_yticklabels(np.arange(y_lower, y_upper + 0.1, 2), fontsize=18)
        ax.set_ylim((y_lower - 0.1, y_upper + 0.1))

        ax.set_xlabel('Date', fontsize=20)
        ax.set_ylabel('LST / K', fontsize=20)

        ax.grid()

        lons = model_lst.coord('longitude').bounds
        lats = model_lst.coord('latitude').bounds

        ax.set_title('Area: lon %s lat %s' % (lons[0], lats[0]), fontsize=22)

        fig.suptitle('ESACCI LST and CMIP6 LST', fontsize=24)
    
        outpath =  config['plot_dir']

        plt.savefig(f'{outpath}/timeseries_{i}.png')
        plt.close('all')  # Is this needed?


if __name__ == '__main__':
    # always use run_diagnostic() to get the config (the preprocessor
    # nested dictionary holding all the needed information)
    with run_diagnostic() as config:
        _diagnostic(config)