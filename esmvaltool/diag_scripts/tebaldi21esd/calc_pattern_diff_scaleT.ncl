; #############################################################################
; Computes the pattern maps of multi-model change between historical and
; scenarios  scaled by global T change
; Derived and adapted from
; diag_scripts/ipcc_ar5/ch12_calc_map_diff_scaleT_mmm_stipp.ncl
; Author: Debeire Kevin (DLR, Germany)
; #############################################################################
;
;  Description
;     Pattern scaling. Annual mean or seasonal change scaled by global T
;     change per multi-model mean with significance in different
;     periods (e.g. 2081-2100 with respect to 1995-2014)
;
;  Required diag_script_info attributes (diagnostics specific)
;     scenarios: list with scenarios to be included in the
;                figure, e.g (/"ssp245","ssp585"/)
;     periods: list with start years of periods to be included
;              e.g. (/"2046","2081"/)
;     time_avg: list with seasons or annual to be included
;               e.g (/"annualclim"/)
;     label: label of periods (ex. 2081-2100 relative to 1995-2014)
;
;  Optional diag_script_info attributes (diagnostic specific)
;     seasons: list with seasons index to be included if
;              averagetime is "seasonalclim" (required for
;              seasonalclim), DJF:0, MAM:1, JJA:2, SON:3
;     percent: 0 or 1, difference in percent = 1, default = 0
;     units: unit string in ncl formatting for legend title
;
;  Modification history
;     20220803-A_debe_kevin: written for ESMValTool
;
; #############################################################################
; A temporary file written by the invoking Python script
; Passes on a number of variables from Python to NCL
load "$diag_scripts/../interface_scripts/interface.ncl"

load "$diag_scripts/shared/statistics.ncl"
load "$diag_scripts/shared/ensemble.ncl"
load "$diag_scripts/shared/scaling.ncl"

load "$diag_scripts/shared/plot/style.ncl"

begin
  enter_msg(DIAG_SCRIPT, "")

  ; 'datasets', 'variables' are fetched from the above 'interface.ncl' file
  var0 = variable_info[0]@short_name
  info_items = select_metadata_by_name(input_file_info, var0)
  dim_MOD = ListCount(info_items)
  dim_VAR = ListCount(variable_info)

  if (dim_VAR .eq. 2) then
    var0 = variable_info[0]@short_name
    var1 = variable_info[1]@short_name
    info_items2 = select_metadata_by_name(input_file_info, var1)
  else
    var0 = variable_info[0]@short_name
    var1 = var0
    info_items2 = info_items
  end if

  if (var1 .ne. "tas") then
    error_msg("f", DIAG_SCRIPT, "", "first variable must be tas " + \
              "to scale by global mean tas change")
  end if

  ; Save some dataset attributes as arrays for index-based selection below
  dataset_names = metadata_att_as_array(info_items, "dataset")
  dataset_exps = metadata_att_as_array(info_items, "exp")
  dataset_ensembles = metadata_att_as_array(info_items, "ensemble")
  dataset_startyears = metadata_att_as_array(info_items, "start_year")

  if (isatt(diag_script_info, "seasons")) then
    dim_seas = dimsizes(diag_script_info@seasons)
  else
    dim_seas = 1
  end if

  ; Check required diag_script_info attributes
  req_atts = (/"scenarios", "periods", "time_avg"/)
  exit_if_missing_atts(diag_script_info, req_atts)

end

begin
  ; Output netcdf directory
  work_dir = config_user_info@work_dir
  system("mkdir -p " + work_dir)
end

begin
  if(isvar("MyParam")) then
      delete(MyParam)
  end if
  if(isatt(variable_info[0], "long_name")) then
    MyParam = variable_info[0]@long_name
    log_info(" MyParam = " + MyParam)
  else
    error_msg("f", DIAG_SCRIPT, "", "missing variable attribute " + \
              "'long_name'")
  end if

  ; ###########################################
  ; # Get data and average time               #
  ; ###########################################
  ; get data from first model
  imod = 0  ; NCL array indices start from zero
  log_info("processing " + info_items[imod]@dataset + "_" \
           + info_items[imod]@exp + "_" \
           + info_items[imod]@ensemble)

  ; See ./interface_scripts/data_handling.ncl
  A0 = read_data(info_items[imod])
  Fill = default_fillvalue(typeof(A0))  ; 1e20

  ; Check dimensions
  dims = getvardims(A0)
  if (dimsizes(dims) .lt. 2) then
    error_msg("f", DIAG_SCRIPT, "", dimsizes(dims) + " dimensions, " + \
              "need 2 or 3")
  end if
  idx = ind(dims .eq. "lat")
  if (ismissing(idx)) then
    error_msg("f", DIAG_SCRIPT, "", "no lat dimension")
  end if
  nlat = dimsizes(A0&lat)
  idx = ind(dims .eq. "lon")
  if (ismissing(idx)) then
    error_msg("f", DIAG_SCRIPT, "", "no lon dimension")
  end if
  nlon = dimsizes(A0&lon)

  temp_avg = new((/dim_MOD/), typeof(A0), Fill)
  temp_avg!0 = "models"
  data1 = new((/dim_MOD,  dim_seas, nlat, nlon/), \
              typeof(A0), Fill)
  ; Average over time (function in ./diag_scripts/lib/ncl/statistics.ncl)
  if ((diag_script_info@time_avg .eq. "seasonalclim") .and. \
      (dim_seas .ne. 4)) then
    tmp_seas = time_operations(A0, -1, -1, "average", \
                               diag_script_info@time_avg, True)
    if (dim_seas .eq. 1) then
      data1(imod, 0, :, :) = tmp_seas(diag_script_info@seasons, :, :)
    else
      data1(imod, :, :, :) = tmp_seas(diag_script_info@seasons, :, :)
    end if
  elseif ((diag_script_info@time_avg .eq. "seasonalclim") .and. \
          (dim_seas .eq. 4)) then
    data1(imod, :, :, :) = time_operations(A0, -1, -1, "average", \
                                           diag_script_info@time_avg, True)
  else
    data1(imod, 0, :, :) = time_operations(A0, -1, -1, "average", \
                                           diag_script_info@time_avg, True)
  end if
  rad = (4.0 * atan(1.0) / 180.0)
  do imod = 0, dim_MOD - 1
    A0_temp = read_data(info_items2[imod])
    temp_tavg = dim_avg_n_Wrap(A0_temp, 0)
    latw = cos(data1&lat * rad)
    temp_avg(imod) = wgt_areaave_Wrap(temp_tavg, latw, 1.0, 0)
    delete(temp_tavg)
    delete(latw)
    if (imod .ne. 0) then
      A0 = read_data(info_items[imod])
      ; Average over time,
      ; function in ./diag_scripts/lib/ncl/statistics.ncl)
      if ((diag_script_info@time_avg .eq. "seasonalclim") .and. \
          (dim_seas .ne. 4)) then
        tmp_seas = time_operations(A0, -1, -1, "average", \
                                   diag_script_info@time_avg, True)
        if (dim_seas .eq. 1) then
          data1(imod, 0, :, :) = tmp_seas(diag_script_info@seasons, :, :)
        else
          data1(imod, :, :, :) = tmp_seas(diag_script_info@seasons, :, :)
        end if
        delete(tmp_seas)
      elseif ((diag_script_info@time_avg .eq. "seasonalclim") .and. \
              (dim_seas .eq. 4)) then
        data1(imod, :, :, :) = time_operations(A0, -1, -1, "average", \
                                               diag_script_info@time_avg, True)
      else
        data1(imod, 0, :, :) = time_operations(A0, -1, -1, "average", \
                                               diag_script_info@time_avg, True)
      end if
    end if
    delete(A0_temp)
    delete(A0)
  end do
  delete(imod)

  ; ##############################################
  ; # Calculate change from hist to periods      #
  ; ##############################################
  if (isatt(diag_script_info, "reference_run")) then
    reference_run_name = diag_script_info@reference_run
  else
    log_info("No reference run name given, set to default 'historical'")
    reference_run_name = "historical"
  end if

  ; loop over ssps and periods
  dim_scen = dimsizes(diag_script_info@scenarios)
  dim_per = dimsizes(diag_script_info@periods)

  to_plot = new((/dim_per * dim_seas, nlat, nlon/), typeof(data1), Fill)
  if (isatt(diag_script_info, "percent")) then
    percent = diag_script_info@percent
  else
    percent = 0
  end if
  i = 0
  do seas = 0, dim_seas - 1  ; loop over seasons
    do per = 0, dim_per - 1  ; loop over periods
      do ssp = 0, dim_scen - 1  ; loop over ssps
        idx_ssp = ind((dataset_exps .eq. diag_script_info@scenarios(ssp)) \
                      .and. (dataset_startyears .eq. \
                      diag_script_info@periods(per)))
        proj = data1(idx_ssp, seas, :, :)
        temp_proj = temp_avg(idx_ssp)
        ; Cut low values
        proj = where(abs(proj) .gt. 1.e-14, proj, proj@_FillValue)
        ; find historical runs from same models as in ssp
        do jj = 0, dimsizes(idx_ssp) - 1
          tmp_idx = ind(dataset_names .eq. dataset_names(idx_ssp(jj)) .and. \
                        dataset_exps .eq. reference_run_name .and. \
                        dataset_ensembles .eq. dataset_ensembles(idx_ssp(jj)))
          if (isdefined("idx_hist")) then
            idx_hist := array_append_record(idx_hist, tmp_idx, 0)
          else
            idx_hist = tmp_idx
          end if
          delete(tmp_idx)
        end do

        base = data1(idx_hist, seas, :, :)
        temp_base = temp_avg(idx_hist)
        ; Cut low values
        base = where(abs(base) .gt. 1.e-14, base, base@_FillValue)
        ; scale each model by global T change
        log_debug("Scale each model by global T change")
        dim_mod = dimsizes(idx_ssp)
        if (dim_mod .lt. 2) then
          error_msg("f", DIAG_SCRIPT, "", \
                    "Only one model found, multi-model needs at least two.")
        end if
        var_diff_scal = new((/dim_mod, nlat, nlon/), typeof(data1), Fill)
        do imod = 0, dim_mod - 1
          if (percent .eq. 1) then
            var_diff_scal(imod, :, :) = \
              ((100 * (proj(imod, :, :) - base(imod, :, :))) / \
               where(base(imod, :, :) .ne. 0., \
               base(imod, :, :), base@_FillValue)) / \
              (temp_proj(imod) - temp_base(imod))
          else
            var_diff_scal(imod, :, :) = (proj(imod, :, :) - \
                                         base(imod, :, :)) / \
                                        (temp_proj(imod) - temp_base(imod))
          end if
        end do
        delete([/base, proj, temp_proj, temp_base/])
        if ssp .eq. 0 then
          var_diff_scal_all_mod = var_diff_scal
        else
          tmp_scal_all_mod = var_diff_scal_all_mod
          delete(var_diff_scal_all_mod)
          var_diff_scal_all_mod = \
            array_append_record(tmp_scal_all_mod, var_diff_scal, 0)
          delete(tmp_scal_all_mod)
        end if
        delete([/idx_hist, idx_ssp, var_diff_scal/])
      end do  ; ssp
      var_diff_scal_all_mod!0 = "models"
      var_diff_scal_all_mod!1 = "lat"
      var_diff_scal_all_mod!2 = "lon"
      var_diff_scal_all_mod&lat = data1&lat
      var_diff_scal_all_mod&lon = data1&lon
      ; average over ssps
      log_debug("Average over models and ssps")
      to_plot(i, :, :) = dim_avg_n_Wrap(var_diff_scal_all_mod, 0)
      i = i + 1
      delete([/var_diff_scal_all_mod/])
    end do  ; per
  end do  ; seas
  to_plot!0 = "panel"
  to_plot&panel = diag_script_info@label
  to_plot!1 = "lat"
  to_plot&lat = data1&lat
  to_plot!2 = "lon"
  to_plot&lon = data1&lon
  to_plot@units     = variable_info[0]@units
  if (percent .eq. 1) then
    to_plot@units     = "%"
  end if

  ; ###########################################
  ; # Other Metadata: diag_script, var        #
  ; ###########################################
  ; Add to to_plot, as attributes without prefix
  if (isatt(to_plot, "diag_script")) then  ; Add to existing entries
    tmp = to_plot@diag_script
    delete(to_plot@diag_script)
    to_plot@diag_script = array_append_record(tmp, (/DIAG_SCRIPT/), 0)
    delete(tmp)
  else  ; Add as new attribute
    to_plot@diag_script = (/DIAG_SCRIPT/)
  end if
  to_plot@var = var0  ; Overwrite existing entry
  if (isatt(variable_info, "long_name")) then
    to_plot@var_long_name = variable_info@long_name
  end if

  ; Check units and adjust for plotting if necessary
  ; difference in K is the same as difference in degC, only change label
  if (to_plot@units.eq."K") then
    to_plot@units = "degC"
  end if
  if (isatt(diag_script_info, "plot_units")) then
    to_plot = convert_units(to_plot, diag_script_info@plot_units)
  end if
  tmp_unit = to_plot@units
  to_plot@units = tmp_unit + " per degC"

  ; ###########################################
  ; # Output to netCDF                        #
  ; ###########################################
  to_plot@ncdf = variable_info[0]@diagnostic + ".nc"
  ncdf_file = work_dir + "/" + to_plot@ncdf
  ncdf_file@existing = "overwrite"
  ; Function in ~/interface_scripts/auxiliary.ncl
  ncdf_outfile = ncdf_write(to_plot, ncdf_file)

  leave_msg(DIAG_SCRIPT, "")
end
