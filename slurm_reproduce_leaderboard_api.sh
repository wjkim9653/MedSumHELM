#!/bin/bash
#SBATCH -J WJK-MedHELM        # 작업 이름
#SBATCH --output=./logs/%x_%j.out             # 표준 출력 로그 (%x=job name, %j=job id)
#SBATCH --error=./logs/%x_%j.err              # 표준 에러 로그
#SBATCH --gres=gpu:1                           # GPU 1개 요청 (필요 없으면 주석 처리)
#SBATCH --cpus-per-gpu=4
#SBATCH --mem-per-gpu=24G
#SBATCH -p batch_grad
#SBATCH -t 1-0

# Conda 환경 활성화
# source ~/.bashrc
# conda activate HELM

# 작업 디렉토리 이동
# cd /data/wjkim9653/repos/MedSumHELM

# Pick any suite name of your choice
export SUITE_NAME=my-medhelm-suite

# Replace this with your model or models
MODELS_TO_RUN="anthropic/claude-3-7-sonnet-20250219 openai/gpt-4.1-2025-04-14 openai/gpt-4.1-mini-2025-04-14 openai/gpt-4.1-nano-2025-04-14 meta/llama-3.3-70b-instruct-turbo"  # deepseek-ai/deepseek-r1-0528

# Get these from the list below
export RUN_ENTRIES_CONF_PATH=run_entries_medhelm_public.conf
export SCHEMA_PATH=schema_medhelm.yaml
export NUM_TRAIN_TRIALS=1
export MAX_EVAL_INSTANCES=20
export PRIORITY=2

# -------------------
# MedHELM 평가 수행
# -------------------
helm-run --conf-paths $RUN_ENTRIES_CONF_PATH --num-train-trials $NUM_TRAIN_TRIALS --max-eval-instances $MAX_EVAL_INSTANCES --priority $PRIORITY --suite $SUITE_NAME --models-to-run $MODELS_TO_RUN --disable-cache

# 결과 요약은 모든 모델 실행 후 한 번만 수행하도록 별도 스크립트에서 진행