#!/usr/bin/env bash

SRC_DIR=/glade/work/afoster/CTSM
COMPSET=I1850Clm60BgcCropCru
RES=f09_g17
PROJECT=P08010000
OUT_DIR=/glade/derecho/scratch/afoster/my_out_dir


if [ $# -lt 2 ]
then
  echo "ERROR: please specify root_dir and case_dir"
  exit 1
fi
root_dir="$1"
case_dir="$2"
case_root=${root_dir}/${case_dir}

cd "${SRC_DIR}/cime/scripts" || { echo "ERROR: Failed to change directory to ${SRC_DIR}/cime/scripts"; exit 1; }
./create_newcase --case ${case_root} --compset ${COMPSET}  --res ${RES} --project ${PROJECT} --run-unsupported --output-root ${OUT_DIR}
cd "${case_root}" || { echo "ERROR: Failed to change directory to ${case_root}"; exit 1; }

./xmlchange STOP_OPTION="nyears"
./xmlchange DOUT_S=TRUE
./xmlchange --subgroup case.run JOB_WALLCLOCK_TIME=12:00:00
./xmlchange --subgroup case.st_archive JOB_WALLCLOCK_TIME=01:00:00
./xmlchange STOP_N=20
./xmlchange RESUBMIT=17

./xmlchange DATM_YR_ALIGN=1
./xmlchange DATM_YR_START=1901
./xmlchange DATM_YR_END=1920
./xmlchange CLM_ACCELERATED_SPINUP="on"
./xmlchange RUN_STARTDATE="0001-01-01"
./xmlchange CLM_BLDNML_OPTS="-bgc bgc -crop -co2_ppmv 277.57"
./xmlchange MOSART_MODE=NULL
./xmlchange CONTINUE_RUN=FALSE
./xmlchange CLM_FORCE_COLDSTART=on

./case.setup
./preview_namelists
./case.build

