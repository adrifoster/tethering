#!/usr/bin/env bash

# THESE SHOULD PROBABLY MOVE TO A CONFIG FILE
SRC_DIR=/glade/work/afoster/CTSM
PROJECT=P93300041
COMPSET=2000_DATM%1PT_CLM60%BGC_SICE_SOCN_SROF_SGLC_SWAV
RES=CLM_USRDAT
OUT_DIR=/glade/derecho/scratch/afoster/tether_testing
SITE=ABBY

if [ $# -lt 1 ]
then
  echo "ERROR: please specify a case_root"
  exit 1
fi
case_root="$1"

rm -rf ${case_root}
case_name=$(basename "$case_root")
rm -rf ${OUT_DIR}/${case_name}
rm -rf ${OUT_DIR}/archive/${case_name}

user_mods=${SRC_DIR}/cime_config/usermods_dirs/clm/NEON/${SITE}

cd "${SRC_DIR}/cime/scripts" || { echo "ERROR: Failed to change directory to ${SRC_DIR}/cime/scripts"; exit 1; }
./create_newcase --case ${case_root} --compset ${COMPSET}  --res ${RES} --project ${PROJECT} --run-unsupported --output-root ${OUT_DIR} --user-mods-dir ${user_mods}
cd "${case_root}" || { echo "ERROR: Failed to change directory to ${case_root}"; exit 1; }

./xmlchange --subgroup case.run JOB_WALLCLOCK_TIME=01:00:00
./xmlchange --subgroup case.st_archive JOB_WALLCLOCK_TIME=01:00:00
./xmlchange STOP_OPTION="ndays"
./xmlchange STOP_N=10
./xmlchange RESUBMIT=0

./xmlchange CLM_ACCELERATED_SPINUP="on"
./xmlchange CLM_FORCE_COLDSTART=on

./case.setup
./preview_namelists
./case.build

### DO NOT DO ./case.submit ####
