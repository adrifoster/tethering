#!/usr/bin/env bash

# THESE SHOULD PROBABLY MOVE TO A CONFIG FILE
SRC_DIR=/glade/work/afoster/CTSM
PROJECT=P93300041
COMPSET=2000_DATM%1PT_CLM60%BGC_SICE_SOCN_SROF_SGLC_SWAV
RES=CLM_USRDAT
OUT_DIR=/glade/derecho/scratch/afoster/tether_testing
SITE=ABBY
USER=afoster

if [ $# -lt 2 ]
then
  echo "ERROR: please specify case_root and prior_case_dir"
  exit 1
fi
case_root="$1"
prior_case_dir="$2"

rm -rf ${case_root}
case_name=$(basename "$case_root")
rm -rf ${OUT_DIR}/${case_name}
rm -rf ${OUT_DIR}/archive/${case_name}

user_mods=${SRC_DIR}/cime_config/usermods_dirs/clm/NEON/${SITE}

cd "${SRC_DIR}/cime/scripts" || { echo "ERROR: Failed to change directory to ${SRC_DIR}/cime/scripts"; exit 1; }
./create_newcase --case ${case_root} --compset ${COMPSET}  --res ${RES} --project ${PROJECT} --run-unsupported --output-root ${OUT_DIR} --user-mods-dir ${user_mods}
cd "${case_root}" || { echo "ERROR: Failed to change directory to ${case_root}"; exit 1; }

# need to set up reference case
archive_dir=${OUT_DIR}/archive
ref_rest_dir=${archive_dir}/${prior_case_dir}/rest
last_date=$(ls ${ref_rest_dir} | tail -n1)
ref_dir=${ref_rest_dir}/${last_date}
ref_date=${last_date%-*}

./xmlchange RUN_TYPE=hybrid
./xmlchange RUN_REFCASE=${prior_case_dir}
./xmlchange GET_REFCASE="True"
./xmlchange RUN_REFDIR=${ref_dir}
./xmlchange RUN_REFDATE=${ref_date}

./xmlchange --subgroup case.run JOB_WALLCLOCK_TIME=01:00:00
./xmlchange --subgroup case.st_archive JOB_WALLCLOCK_TIME=01:00:00
./xmlchange STOP_OPTION="ndays"
./xmlchange STOP_N=100
./xmlchange RESUBMIT=1

./xmlchange CLM_ACCELERATED_SPINUP="sasu"
./xmlchange CLM_FORCE_COLDSTART=off

./case.setup
./preview_namelists
./case.build

### DO NOT DO ./case.submit ####
