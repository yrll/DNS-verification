#!/bin/bash
home="/home/groot/groot"
groot="$home/build/bin/groot"

dir="test_8_all"

test_data="$home/shared/xmu_dataset/$dir"
job_path="$home/shared/xmu_dataset/${dir}_jobs.json"



$groot $test_data --jobs=$job_path --output=results_$dir.json -l


