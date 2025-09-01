#!/bin/bash
#SBATCH -J WJK-MedHELM
#SBATCH --output=./logs/%x_%A_%a.out
#SBATCH --error=./logs/%x_%A_%a.err
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-gpu=4
#SBATCH --mem-per-gpu=24G
#SBATCH -p batch_grad
#SBATCH -t 1-0
#SBATCH --array=1-3  # 모델 수에 맞게 범위 잡아주기

# conda activate 환경
# source ~/.bashrc
# conda activate HELM

export SUITE_NAME=my-medhelm-suite
export RUN_ENTRIES_CONF_PATH=run_entries_medhelm_public.conf
export SCHEMA_PATH=schema_medhelm.yaml
export NUM_TRAIN_TRIALS=1
export MAX_EVAL_INSTANCES=20
export PRIORITY=2

# 모델 선택
MODEL_LIST_FILE="/data/wjkim9653/projects/MedSumHELM/open_models_to_run.txt"
MODEL=$(sed -n "${SLURM_ARRAY_TASK_ID}p" $MODEL_LIST_FILE)

echo "===== Running model: $MODEL ====="
helm-run --conf-paths $RUN_ENTRIES_CONF_PATH \
         --num-train-trials $NUM_TRAIN_TRIALS \
         --max-eval-instances $MAX_EVAL_INSTANCES \
         --priority $PRIORITY \
         --suite $SUITE_NAME \
         --models-to-run $MODEL \
         --disable-cache

# 결과 요약은 모든 모델 실행 후 한 번만 수행하도록 별도 스크립트에서 진행