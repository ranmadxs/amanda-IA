from amanda_ia import __version__
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import os
import json
from dotenv import load_dotenv
from amanda_ia.aia import AIAService
import pytest
# Load environment variables
load_dotenv()

device = "cuda" if torch.cuda.is_available() else "cpu"

# Test version
def test_version():
    print(__version__)
    assert __version__ == '0.1.0'

# Function to get current weather
def get_current_weather(location, unit='fahrenheit'):
    print("Fetching weather for:", location)
    """Get the current weather in a given location"""
    if 'tokyo' in location.lower():
        return json.dumps({
            'location': 'Tokyo',
            'temperature': '10',
            'unit': 'celsius'
        })
    elif 'san francisco' in location.lower():
        return json.dumps({
            'location': 'San Francisco',
            'temperature': '72',
            'unit': 'fahrenheit'
        })
    elif 'paris' in location.lower():
        return json.dumps({
            'location': 'Paris',
            'temperature': '22',
            'unit': 'celsius'
        })
    else:
        return json.dumps({'location': location, 'temperature': 'unknown'})

# Function to simulate action
def functionIa(msg, action='action'):
    print(f"Executing action {msg} {action}")
    return f"Acabo de ejecutar la acción {action} con el mensaje {msg}"

# Test case for the AI model
#poetry run pytest tests/test_amanda_ia.py::test_ia -s
@pytest.mark.skip(reason="no aplica")
def test_ia():
    print("test_ia")
    # Load the model and tokenizer
    model = AutoModelForCausalLM.from_pretrained(
        "HuggingFaceH4/zephyr-7b-beta",
        torch_dtype="auto",
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained("HuggingFaceH4/zephyr-7b-beta")

    # Define the conversation and function to be used
    prompt = "quiero saber el código 000278k"

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt}
    ]

    messages = [
        {"role": "system", "content": "Si me preguntan por el código 000278k yo respondo LOLAZO XD."},
        {"role": "user", "content": prompt}
    ]
    messages = [{
        'role': 'user',
        'content': "What's the weather like in San Francisco?"
    }]

    functions = [{
        'name': 'get_current_weather',
        'description': 'Get the current weather in a given location',
        'parameters': {
            'type': 'object',
            'properties': {
                'location': {
                    'type': 'string',
                    'description': 'The city and state, e.g. San Francisco, CA',
                },
                'unit': {
                    'type': 'string',
                    'enum': ['celsius', 'fahrenheit']
                },
            },
            'required': ['location'],
        },
    }]

    # Apply chat template
    text = tokenizer.apply_chat_template(
        conversation=messages, 
        tools=functions,
        tokenize=False,
        add_generation_prompt=True
    )
    print("CUDA available:", torch.cuda.is_available())
    print("Tokenized input:", text)

    model_inputs = tokenizer([text], return_tensors="pt").to(device)
    print("Model inputs:", model_inputs)

    # Generate response
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
    
    # Parse the response to execute function
    try:
        function_call = json.loads(response)
        function_name = function_call['name']
        function_args = function_call['arguments']
        
        if function_name == 'get_current_weather':
            result = get_current_weather(**function_args)
            print("Function result:", result)
        else:
            print("No matching function found.")
    except json.JSONDecodeError as e:
        print("Failed to parse function call from response:", str(e))
    except KeyError as e:
        print("Key error in function call:", str(e))

