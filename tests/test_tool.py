from transformers import load_tool
from .tools import HFModelDownloadsTool, get_current_temperature, get_current_wind_speed, multiply, current_time
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.utils import get_json_schema
import torch

#https://www.sbert.net/docs/quickstart.html#sentence-transformer    -----> otreo transformer
#hay    que revisar todos los tipos de pipelines. en especial token-classification ---> arma el arbol semántico. 
# la cumbnia maxima para NLP y cambiar toda la logica en el cortez nlu zero-shot-classification
# poetry run pytest tests/test_tool.py::test_tool -s
def test_tool():
    document_qa = load_tool("document-question-answering")
    print(f"- {document_qa.name}: {document_qa.description}")
    print("XDDDDDDDDDDDDDDDDDDDDDD")
    controlnet_transformer = load_tool("diffusers/controlnet-canny-tool")
    print(f"- {controlnet_transformer.name}: {controlnet_transformer.description}")
    print("XXDXXXXXXX")


# poetry run pytest tests/test_tool.py::test_tool2 -s
def test_tool2():
    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint)
    tools = [get_current_temperature, get_current_wind_speed]
    messages = [
        {"role": "system", "content": "You are a bot that responds to weather queries. You should reply with the unit used in the queried location."},
        {"role": "user", "content": "Hey, what's the temperature in Paris right now?"}
    ]
    inputs = tokenizer.apply_chat_template(messages, chat_template="tool_use", tools=tools, add_generation_prompt=True, return_dict=True, return_tensors="pt")
    print(inputs)
    print("XXXXXXXXXXXXXXXXXXXXXXXXXº1")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    print(inputs)
    print("XXXXXXXXXXXXXXXXXXXXXXXXXº2")
    out = model.generate(**inputs, max_new_tokens=128)
    print(tokenizer.decode(out[0][len(inputs["input_ids"][0]):]))

# poetry run pytest tests/test_tool.py::test_functions -s
def test_functions():
    device = "cpu"
    checkpoint = "Qwen/Qwen2-0.5B-Instruct"
    checkpoint = "devanshamin/Qwen2-1.5B-Instruct-Function-Calling-v1"
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
    '''
    print(tokenizer.chat_template)
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
    '''