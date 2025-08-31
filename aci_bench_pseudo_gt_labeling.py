import os
import time
import json
import tempfile
import shutil
from tqdm import tqdm
from pprint import pprint
import asyncio
from openai import OpenAI
from google import genai
from google.genai import types


async def batch_inference(system_prompt: str, user_prompts: list[str], model_provider: str = "google", model_name: str = "gemini-2.5-flash"):
    if any(_ in model_provider.lower().strip() for _ in ["google", "gemini"]):
        client = genai.Client()  # The client gets the API key from the environment variable `GEMINI_API_KEY`.
        requests = [
            {
                'contents': [{
                    'parts': [{
                        'text': prompt
                    }]
                }],
            } for prompt in user_prompts
        ]
        batch_job = client.batches.create(
            model=model_name,
            src=requests,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt
            )
        )
        while True:
            time.sleep(5)
            batch_job_result = client.batches.get(name=batch_job.name)
            if batch_job_result.state.name in ('JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED', 'JOB_STATE_EXPIRED'):
                break
            print("🔥 waiting for batch inference completions (checking every 5s)...")
        
        print("✅ batch inference complete!")
        responses = []
        for idx, response in enumerate(batch_job_result.dest.inlined_responses):
            print(f"\n--- Response {idx+1} ---")
            if response.response:
                text = response.response.text
            else:
                text = "⚠️ ERROR: No Response from Gemini Batch Inference"
            responses.append(text)
            print(text)
        assert len(prompts) == len(responses)
        return responses
    elif "openai" in model_provider.lower().strip():
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        # Step 1: Prepare JSON Lines (.jsonl) content for batch
        records = []
        for idx, prompt in enumerate(user_prompts):
            records.append({
                "custom_id": f"task-{idx}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
            })

        # Step 2: Write JSONL to a temp file and upload
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".jsonl", encoding="utf-8") as tmp:
            for rec in records:
                tmp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            file = client.files.create(file=f, purpose="batch")

        # Step 3: Create batch job
        batch = client.batches.create(
            input_file_id=file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h"
        )

        # Step 4: Poll for completion
        while True:
            status = client.batches.retrieve(batch.id)
            if status.status in ("completed", "failed", "cancelled", "expired"):
                break
            print("Waiting for batch to complete...", flush=True)
            time.sleep(5)

        if status.status != "completed":
            # 디버깅용 로그 찍기
            print(f"[ERROR] Batch failed. Status: {status.status}")
            print(f"[DEBUG] Error details: {status}")
            raise RuntimeError(f"Batch job ended with status={status.status}")

        # Step 5: Retrieve batch results
        output_file_id = status.output_file_id
        file_responses = client.files.content(output_file_id).text

        results_map = {}
        for line in file_responses.strip().split("\n"):
            if not line.strip():
                continue
            obj = json.loads(line)
            custom_id = obj.get("custom_id")
            content = (
                obj.get("response", {})
                .get("body", {})
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            results_map[custom_id] = content

        responses = [results_map.get(f"task-{idx}") for idx in range(len(user_prompts))]

        return responses


async def pseudo_gt_labeling(json_path: str, batch_size: int = 5, model_provider: str = "google", model_name: str = "gemini-2.5-flash",):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # back up original file
    base, ext = os.path.splitext(json_path)
    backup_path = f"{base}_original{ext}"
    shutil.copy2(json_path, backup_path)

    # Collect Source Dialogue & Index for Batch Processing
    dialogues = []
    indices = []
    for idx, item in enumerate(data.get("data")):
        dialogue = item.get("src", "")
        if dialogue.strip():
            dialogues.append(dialogue)
            indices.append(idx)
    assert len(dialogues) == len(indices)

    system_prompt = (
        "You are a physician writing a clinical note based on a dialogue with the patient."
        "Write only the \”SUBJECTIVE\” part and \”ASSESSMENT AND PLAN\” part of note."
        "\”SUBJECTIVE\” part should include the section of [CHIEF COMPLAINT] and [HISTORY OF PRESENT ILLNESS]."
        "\”ASSESSMENT AND PLAN\” part should list each medical problem separately, while explaining medical reasoning, diagnostic and therapeutic plans for each problems. It may also include a short section of follow up instruction when applicable, at the end of the note."
        "Only include information contained in the dialogue.\n"
        "Follow the format as the example below:\n"
        "[\"SUBJECTIVE \nCHIEF COMPLAINT \nAnnual health maintenance examination. \nHISTORY OF PRESENT ILLNESS \nThe patient is a pleasant [age]-year-old male who presents for his annual health maintenance examination. He reports no new complaints today. He denies any recent changes in his hearing. He continues to take niacin for his dyslipidemia, and he has had no problems with hemorrhoids in the last 6 months. He also denies any problems with concha bullosa of the left nostril or septal deviation. \n\"ASSESSMENT AND PLAN: \n1. Possible COPD exacerbation \nAssessment: Increased work of breathing with wheezing on exam, suggesting COPD exacerbation. He does have frequent COPD exacerbation in the past. Differential diagnosis include pneumonia (though no fever or cough), PE (though no risk factors) or simple viral infection. \nPlan: \n- WIll obtain CXR. \n- Will start duoneb therapy and oral prednisone 30mg Qday. \n2. Hypertension \nAssessment: The patient's blood pressure is well controlled. Plan: \n- Continue lisinopril 20mg Qday. \nFollow-up instructions: \n- return to clinic in 1 week, or sooner of failed to response with current treatment.]\n"
    )

    # Batch Processing w/ API Calls
    for start in tqdm(range(0, len(dialogues), batch_size), desc="processing batches..."):
        batch_dialogues = dialogues[start:start+batch_size]
        prompts = []
        for dialogue in batch_dialogues:
            prompt=(
                "Here's the actual dialogue between doctor and the patient:\n"
                f"{dialogue}"
            )
            prompts.append(prompt)

        responses = await batch_inference(
            model_provider=model_provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompts=prompts
        )
        for batch_idx, response in enumerate(responses):
            idx = indices[start+batch_idx]
            data["data"][idx]["tgt"] = response
        
    # Pseudo-GT Labeling 거친 새로운 json 저장 (원본파일명으로)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"✅ {model_name} 기반으로 Pseudo-GT Labeling 완료 : {json_path.split('/')[-1]}")


async def main():
    input_files = [
        "benchmark_output/scenarios/aci_bench/aci_bench_test_1.json",
        "benchmark_output/scenarios/aci_bench/aci_bench_test_2.json",
        "benchmark_output/scenarios/aci_bench/aci_bench_test_3.json"
    ]

    tasks = [
        pseudo_gt_labeling(
            json_path=file,
            batch_size=40,
            model_provider="openai",
            model_name="gpt-5-2025-08-07"
        )
        for file in input_files
    ]

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())


"""
nohup python aci_bench_pseudo_gt_labeling.py > aci_bench_pseudo_gt_labeling.out 2>&1 &
"""