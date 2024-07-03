from amanda_ia import __version__
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"

#poetry run pytest tests/test_amanda_ia.py::test_version -s
def test_version():
    print(__version__)
    assert __version__ == '0.1.0'

#poetry run pytest tests/test_amanda_ia.py::test_ia -s
def test_ia():
    print("test_ia")
    # load the model and tokenizer
    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen2-0.5B-Instruct",
        torch_dtype="auto",
        device_map="auto"
    )

    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2-0.5B-Instruct")

    prompt = "¿Puedes hablar en español?."
    messages = [
        {"role": "system", "content": "Eres un asistente que habla español."},
        {"role": "user", "content": prompt},
         {"role": "user", "content": "¿puedes enviar mensajes a una cola kafka?"}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    print (torch.cuda.is_available())
    print (text)

    model_inputs = tokenizer([text], return_tensors="pt").to(device)
    print (model_inputs)
    # Directly use generate() and tokenizer.decode() to get the output.
    # Use `max_new_tokens` to control the maximum output length.
    generated_ids = model.generate(
        model_inputs.input_ids,
        max_new_tokens=512
    )
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    print("================= response ===================")
    print(response)