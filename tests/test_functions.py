import json
from typing import List, Dict
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import timeit
from .tools import get_company_info
from transformers.utils import get_json_schema
from .tools import get_current_temperature, get_current_wind_speed, multiply, current_time
from amanda_ia.aia import AIAService

##### Para borrar modelos ~/.cache/huggingface/hub/
##### Mañana hacer pruebas en español con las funciones!

model_id = "devanshamin/Qwen2-1.5B-Instruct-Function-Calling-v1"
#model_id = "Qwen/Qwen2-0.5B-Instruct"
model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float32, device_map="auto")
tokenizer = AutoTokenizer.from_pretrained(model_id)

def inference(prompt: str) -> str:
  model_inputs = tokenizer([prompt], return_tensors="pt").to('cpu')
  generated_ids = model.generate(model_inputs.input_ids, max_new_tokens=512)
  generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)]
  response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
  return response

#messages = [{"role": "user", "content": "What is the speed of light?"}]
#prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
#response = inference(prompt)
#print(response)



def get_prompt(user_input: str, tools: List[Dict] | None = None):
  #prompt = 'Extract the information from the following - \n{}'.format(user_input)
  prompt = 'Extraer la información de lo siguiente - \n{}'.format(user_input)
  messages = [
            {"role": "user", "content": prompt}
        ]
  prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    tools=tools
  )
  return prompt

def execute_function(input_text: str, tools: List[Dict] | None = None) -> str:
    start = timeit.default_timer()
    print("The start time is :", start)
    prompt = get_prompt(input_text, tools=tools)
    response = inference(prompt)
    print("The difference of time is :", 
              timeit.default_timer() - start)
    return response


#poetry run pytest tests/test_functions.py::test_functions -s
def test_functions():
    input_text = "Founded in 2021, Pluto raised $4 million across multiple seed funding rounds, valuing the company at $12 million (pre-money), according to PitchBook. The startup was backed by investors including Switch Ventures, Caffeinated Capital and Maxime Seguineau."
    input_text = "Fundada en 2021, Pluto recaudó $4 millones en múltiples rondas de financiación inicial, valorando la empresa en $12 millones (pre-money), según PitchBook. La startup fue respaldada por inversores como Switch Ventures, Caffeinated Capital y Maxime Seguineau."
    response = execute_function(input_text, [get_company_info])
    print(response)

#poetry run pytest tests/test_functions.py::test_functions2 -s
def test_functions2():
    input_text = "Multiplica los números 3 y 5"
    print("test functions")
    schemaMul = get_json_schema(multiply)
    print(schemaMul)
    schemaCur = get_json_schema(current_time)
    print(schemaCur)
    tools = [schemaCur, schemaMul]
    response = execute_function(input_text, tools)
    print(response)

#poetry run pytest tests/test_functions.py::test_functions3 -s
def test_functions3():
    input_text = "Me puedes dar la hora local?"
    print("test functions")
    schemaMul = get_json_schema(multiply)
    print(schemaMul)
    #schemaCur = get_json_schema(current_time)
    schemaCur = {
        "type": "function", 
        "function": {
            "name": "current_time",
            "description": "Get the current local time as a string."
        }
    }    
    print(schemaCur)
    tools = [schemaCur, schemaMul]
    response = execute_function(input_text, tools)
    print(response)


#poetry run pytest tests/test_functions.py::test_functions4 -s
def test_functions4():
    input_text = "enciende la bomba de agua en el invernadero por favor"
    print("test functions4")

    aiaSvc = AIAService("topic_producer", "topic_consumer", "version")
    aiaExecutorSchema = get_json_schema(aiaSvc.execute)
    print(aiaExecutorSchema)
    tools = [aiaExecutorSchema]
    response = execute_function(input_text, tools)
    print(response)
    aiaSvc.send_mqtt_message(response)