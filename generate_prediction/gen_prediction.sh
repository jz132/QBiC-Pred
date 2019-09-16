#!/bin/bash

#SBATCH -o vm_%A_%a.out
#SBATCH -e vm_%A_%a.err

#SBATCH --array=0-665%80
#SBATCH --mem=20G
#SBATCH --mail-type=END
#SBATCH --mail-user=vm76@duke.edu

# Directory setting -- parallelize per TF
#output="test-out"
output="/data/gordanlab/vincentius/predmodel"
#input=(test-in/*)
input=(/data/gordanlab/vincentius/pbmdata/*)
# Parameter configuration
#kmer=3
#chunk=1
kmer=6
chunk=32

# TO RUN: sbatch gen_prediction.sh
#------------End of Configuration-----------------

filein=${input[SLURM_ARRAY_TASK_ID]}
echo $filein
echo "task_id: $SLURM_ARRAY_TASK_ID"

# read gap parameters
#array=()
#while read line ; do
#  array+=($line)
#done < <(python3 predutils.py -g $filein)
#gappos=${array[0]}
#gapsize=${array[1]}

# use ungapped model for now
gappos=0
gapsize=0

python olskmer.py $filein $output -k $kmer -d $chunk -g $gapsize -p $gappos
