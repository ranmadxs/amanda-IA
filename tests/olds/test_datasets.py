from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
import pytest
#OK
# poetry run pytest tests/test_datasets.py::test_dataset -s
@pytest.mark.skip(reason="no aplica")
def test_dataset():
    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    chat1 = [
        {"role": "user", "content": "PepitoLolazo es más grande que PepitoSolito?"},
        {"role": "assistant", "content": "PepitoLolazo es más grande que PepitoSolito."}
    ]
    chat2 = [
    {"role": "user", "content": "¿Qué es más grande un virus o una bacteria?"},
        {"role": "assistant", "content": "Una bacteria."}
    ]

    dataset = Dataset.from_dict({"chat": [chat1, chat2]})
    dataset = dataset.map(lambda x: {"formatted_chat": tokenizer.apply_chat_template(x["chat"], tokenize=False, add_generation_prompt=True)})
    print(dataset['formatted_chat'])
    formatted_chats = dataset['formatted_chat']
    formatted_chats_as_strings = [str(chat) for chat in formatted_chats]

    return formatted_chats_as_strings


# poetry run pytest tests/test_datasets.py::test_exe -s
@pytest.mark.skip(reason="no aplica")
def test_exe():
    print("test_exe")
    device = "cpu"
    dataset = test_dataset()
    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint)
    messages = [{"role": "user", "content": "¿cuál es más grande PepitoLolazo o PepitoSolito?. Dame la respuesta por favor "}]
    
    text = tokenizer.apply_chat_template(
        conversation=messages, 
        tokenize=False,
        add_generation_prompt=True
    )
    
    print(text)
    array_txt = dataset[0]
    print(array_txt)
    model_inputs = tokenizer([dataset[0], text], return_tensors="pt", truncation=True, padding=True,).to(device)
    print("Model inputs:", model_inputs)
    generated_ids = model.generate(
        model_inputs.input_ids,
        max_new_tokens=512
    )
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    print("================= Response ===================")
    print(response)