#!/bin/bash
#SBATCH -J WJK-MedHELM
#SBATCH --output=./logs/%x_%A_%a.out
#SBATCH --error=./logs/%x_%A_%a.err
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-gpu=4
#SBATCH --mem-per-gpu=24G
#SBATCH -p batch_grad
#SBATCH -t 1-0
#SBATCH --array=1-18

# conda activate 환경
# source ~/.bashrc
# conda activate HELM

# Pick any suite name of your choice
export SUITE_NAME=my-medhelm-suite

# Get these from the list below
export SCHEMA_PATH=schema_medhelm.yaml

# -------------------
# MedHELM 결과 요약
# -------------------
helm-summarize --schema $SCHEMA_PATH --suite $SUITE_NAME

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