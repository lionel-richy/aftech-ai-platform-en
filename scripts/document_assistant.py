"""
AFTECH document assistant.

This script is a simple example of "RAG" (Retrieval-Augmented Generation):
1) the document passages closest to a question are retrieved (via
   embeddings + cosine similarity);
2) these passages are given to a language model (Qwen3) so it writes an
   answer based ONLY on this content.

The idea: instead of letting the model "make up" an answer, it is forced
to rely on the company's real documents.

NOTE (presentation build): SYSTEM_PROMPT, QUESTIONS and
REPONSE_NON_TROUVEE below are left in French on purpose — they are
functional content sent verbatim to the LLM (or real test inputs run
against the actual indexed documents), sharing the exact same exception
already applied to backend/app/rag_engine.py in this repo. Everything
else (comments, docstrings, CLI/print output) has been translated to English.
"""

import glob
import json
import os
import time

import torch
from sentence_transformers import SentenceTransformer, util
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

DATA_DIR = "data/samples"
RESULTS_PATH = "results/benchmarks/rag_test.json"

# Embedding model: turns a text into a list of numbers (a vector) that
# represents its meaning. Two texts close in meaning will have close vectors.
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

# Generation model: the one that writes the final answer
LLM_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

TOP_K = 3  # number of most relevant passages to retrieve

# Minimum similarity score to accept querying Qwen.
# Below this threshold, the documents are considered to not cover the
# question's topic, so there's no point asking Qwen.
MIN_SCORE = 0.60

# Questions automatically asked at the end of the script.
# The last one deliberately tests a topic absent from the documents, to
# check that the assistant knows how to say "I don't know".
QUESTIONS = [
    "Quelle est la longueur minimale d'un mot de passe ?",
    "Dans combien de temps un incident P1 doit-il être pris en charge ?",
    "Combien de jours avant le départ faut-il demander un congé ?",
    "Quel est le chiffre d'affaires annuel d'AFTECH ?",
]

# Reinforced system message: Qwen is explicitly forbidden from
# supplementing with its own general knowledge, to avoid "making things up".
SYSTEM_PROMPT = (
    "Tu es un assistant documentaire. Tu réponds toujours en français, de façon "
    "simple et claire. Tu dois répondre UNIQUEMENT à partir du contexte fourni "
    "dans le message de l'utilisateur. Ne complète jamais avec tes connaissances "
    "générales, même si tu penses connaître la réponse. Si le contexte ne "
    "contient pas clairement la réponse, réponds exactement : "
    '"Information non trouvée dans les documents".'
)

REPONSE_NON_TROUVEE = "Information non trouvée dans les documents."


def charger_paragraphes():
    """Reads every .txt file in data/samples and splits it into paragraphs.

    Splitting by paragraph (rather than whole document) lets similarity
    search retrieve precise passages, not whole texts that are too long.
    """
    paragraphes = []  # the text of each paragraph
    sources = []  # the file name each paragraph comes from (same index)

    for chemin in sorted(glob.glob(os.path.join(DATA_DIR, "*.txt"))):
        with open(chemin, encoding="utf-8") as fichier:
            contenu = fichier.read()

        # A paragraph = a block of text separated by a blank line
        blocs = [bloc.strip() for bloc in contenu.split("\n\n") if bloc.strip()]

        for bloc in blocs:
            paragraphes.append(bloc)
            sources.append(os.path.basename(chemin))

    return paragraphes, sources


def recuperer_passages(question, embedder, embeddings_paragraphes, paragraphes, sources):
    """Finds the TOP_K paragraphs closest to the question.

    The question's vector is compared to each paragraph's with cosine
    similarity: the closer the score is to 1, the more the two texts are
    about the same thing.
    """
    embedding_question = embedder.encode(question, convert_to_tensor=True)
    scores = util.cos_sim(embedding_question, embeddings_paragraphes)[0]

    nb_resultats = min(TOP_K, len(paragraphes))
    meilleurs_indices = torch.topk(scores, k=nb_resultats).indices.tolist()

    resultats = []
    for indice in meilleurs_indices:
        resultats.append(
            {
                "texte": paragraphes[indice],
                "source": sources[indice],
                "score": float(scores[indice]),
            }
        )
    return resultats


def construire_prompt(question, passages):
    """Builds the text sent to Qwen (the context; the strict instructions
    are already set further up in SYSTEM_PROMPT)."""
    contexte = "\n\n".join(f"[{p['source']}] {p['texte']}" for p in passages)
    return f"Contexte :\n{contexte}\n\nQuestion : {question}"


def main():
    # --- Step 1: prepare the documents (the "Retrieval" part of RAG) ---
    print("Reading and splitting the documents...")
    paragraphes, sources = charger_paragraphes()
    print(f"{len(paragraphes)} paragraphs found in {len(set(sources))} file(s).\n")

    # bge-m3 runs very well on CPU: no need for the GPU at this step,
    # we keep the GPU free for the generation model (Qwen)
    print(f"Loading embedding model {EMBEDDING_MODEL_NAME} on CPU...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")

    print("Computing embeddings for all paragraphs...\n")
    embeddings_paragraphes = embedder.encode(paragraphes, convert_to_tensor=True)

    # --- Step 2: prepare the generation model (the "Generation" part of RAG) ---
    if not torch.cuda.is_available():
        raise RuntimeError("No GPU detected. This script must run on a Colab session with a GPU.")

    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU detected: {gpu_name}")

    # The Tesla T4 doesn't handle bfloat16 correctly: force float16 in this specific case
    if "T4" in gpu_name:
        compute_dtype = torch.float16
    elif torch.cuda.is_bf16_supported():
        compute_dtype = torch.bfloat16
    else:
        compute_dtype = torch.float16
    print(f"Compute dtype used: {compute_dtype}")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading model {LLM_MODEL_NAME} in 4-bit...\n")
    tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        LLM_MODEL_NAME,
        quantization_config=quant_config,
        device_map="auto",
    )

    # --- Step 3: answer each question ---
    resultats_tests = []  # accumulates a summary of each test, for the final JSON

    for question in QUESTIONS:
        print("=" * 70)
        print(f"Question: {question}\n")

        passages = recuperer_passages(question, embedder, embeddings_paragraphes, paragraphes, sources)
        meilleur_score = passages[0]["score"] if passages else 0.0

        print("Passages found (source file + similarity score):")
        for p in passages:
            apercu = p["texte"][:80].replace("\n", " ")
            print(f"  - [{p['source']}] score={p['score']:.3f}: {apercu}...")
        print(f"Best score: {meilleur_score:.3f}")

        # If even the best passage is too weakly relevant, there's no
        # point querying Qwen: the documents probably don't cover this topic.
        if meilleur_score < MIN_SCORE:
            reponse = REPONSE_NON_TROUVEE
            sources_utilisees = []
            temps_reponse = 0.0
            print(f"\nScore below threshold ({MIN_SCORE}), Qwen is not queried.")
        else:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": construire_prompt(question, passages)},
            ]

            # return_dict=True: get both input_ids AND attention_mask, which generate() expects
            inputs = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            ).to(model.device)

            debut = time.perf_counter()
            output_ids = model.generate(
                **inputs,
                max_new_tokens=250,
                do_sample=False,
            )
            temps_reponse = time.perf_counter() - debut

            # Keep only the generated tokens, not the question echoed back in the output
            generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
            reponse = tokenizer.decode(generated_ids, skip_special_tokens=True)

            # Sources actually used = those of the passages sent to Qwen
            sources_utilisees = [p["source"] for p in passages]

        print(f"\nAnswer: {reponse}")
        print(f"Sources used: {sources_utilisees}")
        print(f"Response time: {temps_reponse:.2f} s\n")

        resultats_tests.append(
            {
                "question": question,
                "reponse": reponse,
                "sources": sources_utilisees,
                "scores": [p["score"] for p in passages],
                "temps_reponse_secondes": temps_reponse,
            }
        )

    # --- Step 4: save the results so the tests can be compared to each other ---
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(resultats_tests, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
