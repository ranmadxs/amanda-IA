from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import json
from transformers.utils import get_json_schema
from .tools import get_current_temperature, get_current_wind_speed, multiply, current_time
import pytest

# poetry run pytest tests/test_tool.py::test_functions -s
@pytest.mark.skip(reason="lento para offline")
def test_functions():
    device = "cpu"
    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.bfloat16, device_map="auto")
    print("test functions")
    schemaMul = get_json_schema(multiply)
    print(schemaMul)
    schemaCur = get_json_schema(current_time)
    print(schemaCur)
    messages = [
        {"role": "system", "content": "Tu eres un bot que ejecuta funciones en tools."},
        {"role": "user", "content": "puedes dar la hora local?"}
    ]
    inputs = tokenizer.apply_chat_template(
        conversation=messages, 
        chat_template="tool_use",
        tools = [schemaCur, schemaMul],
        tokenize=True,
        add_generation_prompt=True,return_dict=True, return_tensors="pt"
    )
    print("================= Inputs ===================")
    print(tokenizer.chat_template)
    #inputs = tokenizer([text], return_tensors="pt", truncation=True, padding=True,).to(device)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    out = model.generate(**inputs, max_new_tokens=128)
    print(tokenizer.decode(out[0][len(inputs["input_ids"][0]):]))