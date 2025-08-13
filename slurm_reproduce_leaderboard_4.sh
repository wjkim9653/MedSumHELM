#!/bin/bash
#SBATCH --nodelist=moana-y4  # 노드 특정 요청
#SBATCH -J WJK-MedHELM        # 작업 이름
#SBATCH --output=./logs/%x_%j.out             # 표준 출력 로그 (%x=job name, %j=job id)
#SBATCH --error=./logs/%x_%j.err              # 표준 에러 로그
#SBATCH --gres=gpu:1                           # GPU 1개 요청 (필요 없으면 주석 처리)
#SBATCH --cpus-per-gpu=8
#SBATCH --mem-per-gpu=24G
#SBATCH -p batch_ce_ugrad
#SBATCH -t 1-0

# Conda 환경 활성화
# source ~/.bashrc
# conda activate HELM

# 작업 디렉토리 이동
# cd /data/wjkim9653/repos/MedSumHELM

# Pick any suite name of your choice
export SUITE_NAME=my-medhelm-suite

# Replace this with your model or models
# export MODELS_TO_RUN=meta/llama-3.2-1b-instruct
# export MODELS_TO_RUN=openai/gpt-4.1-nano-2025-04-14
MODELS_TO_RUN="meta/llama-3.1-8b-instruct" # meta/llama-3.2-3b-instruct meta/llama-3.1-8b-instruct meta/llama-3.3-70b-instruct-turbo"

# Get these from the list below
export RUN_ENTRIES_CONF_PATH=run_entries_medhelm_public.conf
export SCHEMA_PATH=schema_medhelm.yaml
export NUM_TRAIN_TRIALS=1
export MAX_EVAL_INSTANCES=10
export PRIORITY=2

# -------------------
# MedHELM 평가 수행
# -------------------
helm-run --conf-paths $RUN_ENTRIES_CONF_PATH --num-train-trials $NUM_TRAIN_TRIALS --max-eval-instances $MAX_EVAL_INSTANCES --priority $PRIORITY --suite $SUITE_NAME --models-to-run $MODELS_TO_RUN --disable-cache

# -------------------
# MedHELM 결과 요약
# -------------------
helm-summarize --schema $SCHEMA_PATH --suite $SUITE_NAME

# -------------------
# 웹으로 리더보드 시각화
# -------------------
# helm-server --suite $SUITE_NAME  # 프런트엔드 코드에 문제 있어 보임...

# -------------------
# 결과 테이블 출력
# -------------------
TEX_FILE="./benchmark_output/runs/${SUITE_NAME}/groups/latex/aci_bench_aci_bench_.tex"

if [[ -f "$TEX_FILE" ]]; then
    echo "===== Benchmark Results ====="
    # 헤더 추출
    header=$(grep '&' "$TEX_FILE" | head -n 1 | sed 's/\\\\//g' | sed 's/^[ \t]*//;s/[ \t]*$//')

    # 데이터 추출, 정렬 (Jury Score = 2번째 필드)
    grep '&' "$TEX_FILE" \
        | tail -n +2 \
        | sed 's/\\\\//g' \
        | sed 's/^[ \t]*//;s/[ \t]*$//' \
        | awk -F'&' '{print $0}' \
        | sort -t'&' -k2,2nr \
        | { echo "$header"; cat; } \
        | column -t -s '&'
else
    echo "결과 파일이 없습니다: $TEX_FILE"
fi