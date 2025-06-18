import json
from typing import List, Dict
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import timeit
from .tools import get_company_info
from transformers.utils import get_json_schema
from .tools import get_current_temperature, get_current_wind_speed, multiply, current_time
from amanda_ia.aia import AIAService
import logging
from aia_utils.logs_cfg import config_logger
config_logger()
logger = logging.getLogger(__name__)
import os
from unittest.mock import patch

##### Para borrar modelos ~/.cache/huggingface/hub/

model_id = "devanshamin/Qwen2-1.5B-Instruct-Function-Calling-v1"
#model_id = "Qwen/Qwen2-0.5B-Instruct"
#model_id = "gpt2"
model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float32, device_map="auto")
tokenizer = AutoTokenizer.from_pretrained(model_id)

# Asegúrate de que el modelo tiene un token de relleno adecuado
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

def inference(prompt: str) -> str:
  model_inputs = tokenizer([prompt], return_tensors="pt").to('cpu')
  generated_ids = model.generate(model_inputs.input_ids, attention_mask=model_inputs.attention_mask, max_new_tokens=512)
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
    response = response.replace("```json\n", "").replace("```", "")
    print("The difference of time is :", 
              timeit.default_timer() - start)
    return response

## Excelente y muy bueno a futuro ocupar #####
#poetry run pytest tests/test_functions.py::test_functions4 -s
def test_functions4():
    input_text = "enciende la bomba de agua en el invernadero por favor"
    input_text = "puedes encender la bomba de agua del invernadero"
    #input_text = "enciende la luz en el invernadero"
    #input_text = "enciende las luces del invernadero"
    input_text = "apaga las luces del invernadero por favor"
    print("test functions5")

    aiaSvc = AIAService(os.environ['TEST_CLOUDKAFKA_TOPIC_PRODUCER'], os.environ['CLOUDKAFKA_TOPIC_CONSUMER'], "version")
    aiaExecutorSchema = get_json_schema(aiaSvc.execute)
    print(aiaExecutorSchema)
    tools = [aiaExecutorSchema]
    response = execute_function(input_text, tools)
    jsonData = json.loads(response)
    logger.info(input_text)
    logger.debug(jsonData)
    
    # Mock para send_mqtt_message
    with patch.object(aiaSvc, 'send_mqtt_message') as mock_mqtt:
        mock_mqtt.return_value = True
        aiaSvc.send_mqtt_message(response)
        mock_mqtt.assert_called_once_with(response)
    
    # Validaciones del response
    assert isinstance(jsonData, dict), "La respuesta debe ser un diccionario"
    assert "name" in jsonData, "La respuesta debe contener name"
    assert "arguments" in jsonData, "La respuesta debe contener arguments"
    
    # Validar que los argumentos son un diccionario válido
    args = jsonData["arguments"]
    assert isinstance(args, dict), "Los argumentos deben ser un diccionario"
    assert "accion" in args, "Los argumentos deben contener accion"
    assert "objeto" in args, "Los argumentos deben contener objeto"
    assert "ubicacion" in args, "Los argumentos deben contener ubicacion"
    
    # Validar que la acción y el objetivo son strings
    assert isinstance(args["accion"], str), "accion debe ser un string"
    assert isinstance(args["objeto"], str), "objeto debe ser un string"
    assert isinstance(args["ubicacion"], str), "ubicacion debe ser un string"
    
    #input_text = "esto es un mensaje de prueba de error"
    #response = execute_function(input_text, tools)
    #print(response)
