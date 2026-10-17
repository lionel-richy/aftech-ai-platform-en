import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# Model name on Hugging Face
MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# Test question (no real data, just a fixed example)
QUESTION = "Explique simplement le rôle d'un assistant documentaire dans une entreprise."

MAX_NEW_TOKENS = 250


def main():
    # Check that a GPU is available, otherwise this script has no point
    if not torch.cuda.is_available():
        raise RuntimeError("No GPU detected. This script must run on a Colab session with a GPU.")

    # GPU name (e.g. "Tesla T4")
    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU detected: {gpu_name}")

    # Total GPU memory, converted to GB for readability
    total_memory_go = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"Total GPU memory: {total_memory_go:.2f} GB")

    # bfloat16 is more stable but not supported on every GPU (e.g. T4 doesn't support it)
    # Fall back to float16 if bfloat16 isn't available
    if torch.cuda.is_bf16_supported():
        compute_dtype = torch.bfloat16
        print("Compute dtype used: bfloat16")
    else:
        compute_dtype = torch.float16
        print("Compute dtype used: float16 (bfloat16 not supported on this GPU)")

    # 4-bit quantization config (drastically reduces memory usage)
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading model {MODEL_NAME} in 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=quant_config,
        device_map="auto",
    )

    # Reset the memory counter so we only measure inference
    torch.cuda.reset_peak_memory_stats()

    # Qwen3 is a chat model: use the conversation format, and explicitly ask
    # for a response in French (kept in French on purpose — this prompt is
    # sent as-is to the LLM and this script specifically demonstrates the
    # model's French output; translating the instruction itself would change
    # what the script demonstrates, not just its wording).
    messages = [
        {"role": "system", "content": "Tu réponds toujours en français, de façon simple et claire."},
        {"role": "user", "content": QUESTION},
    ]
    # return_dict=True: get a dict (input_ids + attention_mask) rather than a
    # plain tensor, so generate() also receives the attention_mask
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)

    print("Generating the response...")
    start_time = time.perf_counter()
    output_ids = model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,
    )
    elapsed_seconds = time.perf_counter() - start_time

    # Keep only the generated tokens (not the question echoed back in the output)
    generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # GPU memory used during generation (peak reached)
    peak_memory_go = torch.cuda.max_memory_allocated() / (1024**3)

    print("\n--- Question ---")
    print(QUESTION)
    print("\n--- Response ---")
    print(response)
    print("\n--- Measurements ---")
    print(f"Response time: {elapsed_seconds:.2f} seconds")
    print(f"GPU memory used (peak): {peak_memory_go:.2f} GB")


if __name__ == "__main__":
    main()
